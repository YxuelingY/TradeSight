# TradeSight 实时行情重构需求设计（feature.md）

> 面向其他 Agent：按本文实现“通达信协议风格”的实时行情重构。
> 现状结论先行：**不要做纯 TDX 重构**——探针已证明 pytdx 1.72 + 公网 TDX 服务器链路已不可用。
> 本方案采用 **TDX 协议抽象 + 多源灾备**：对外暴露 TDX 风格接口，底层主用腾讯/东财 HTTP，预留 TDX 二进制通道插槽。

---
## 1. 背景与目标

### 1.1 用户原始诉求
- “为什么同花顺可以实时更新股票数据，我这里不行？”
- “按照通达信的协议重新改吧，改之前先输出需求设计 feature.md”。

### 1.2 本文档目标
- 解释现状为什么不行、同花顺/通达信为什么行；
- 给出可落地的重构需求 + 架构 + 接口契约 + 任务拆分；
- 任何 Agent 只读本文 + `data/fetcher.py` + `data/database.py` + `ui/main_window.py` 即可开工，无需再读探针脚本。

---
## 2. 现状诊断（TradeSight 当前实现）

### 2.1 现有数据链（`data/fetcher.py` 实测）
```
UI(QTimer 60s / QThread QuoteFetchThread)
 -> fetcher.get_quotes(symbols, chunk=30)
 -> 东财 push 单票接口 (push2.eastmoney.com, ut=bd1d9ddb…, timeout 8s, retry 3, trust_env=False 直连绕过代理)
 -> akshare 仅用于 search (stock_info_a_code_name)
 -> SQLite 缓存 (stock_quote / stock_kline / stock_minute / stock_metrics)
 -> 失败回退 mock_data
```

### 2.2 现有缺陷（为什么“不行”）
1. **单点脆弱**：只依赖东财 push + 单一 ut token。东财对密集请求会 `RemoteDisconnected`，批量 200 只即被限流/复位。
2. **批量模型错误**：`get_quotes` 是“30 只一组串行单票循环”，200 只约 7+ 次串行 RTT，UI 显示“加载慢/不实时”。
3. **刷新节拍错误**：`config.PRICE_REFRESH_INTERVAL = 60000`（1 分钟），且无交易时段判断。盘中 1 分钟轮询观感即“不实时”。
4. **休市零值污染**：东财返回 `f43/f44 = 0`（休市无成交），需固化“休市不覆写 DB”规则。
5. **K 线/分时/估值耦合**：`get_value_metrics` 与 `get_quote` 共享 3s 快照缓存，但全走单票快照；K 线 `beg=20150101` 全量拉取后 `tail(days)`，无增量更新。
6. **线程模型脆弱**：`QuoteFetchThread` 一次性 `finished.emit`，无心跳、无重连、无超时熔断；失败静默回退 mock，用户无法区分真假数据。

### 2.3 为什么同花顺/通达信“行”
| 维度 | 同花顺/通达信 | TradeSight 现状 |
|---|---|---|
| 接入 | 自建行情网关 + 交易所直连/券商托管席位，多地域容灾 | 公网 HTTP 抓包接口（东财 push），单 token |
| 协议 | 私有二进制（TDX: TCP 7709，长连接，会话 hello + 心跳 + 分页取数 + 板块/除权本地库） | 无状态 HTTPS JSON 轮询 |
| 推送 | 服务端有变化即推（盘中约 3s 级 tick 聚合推送） | 客户端 60s 主动拉 |
| 批量 | 一包 80-100 只 quotes，服务端分页 + 增量 | 30 只串行单票 GET |
| 灾备 | 主/备站自动切换 + 本地缓存 + 盘后补 K | 单站失败即 mock |
| 时间 | 交易时段高频，非交易时段降频/停轮询 | 全天 60s 一刀切 |

一句话：**人家是“长连接二进制推送 + 多活网关”，我们是“单站 HTTP 轮询”，协议代差决定了实时性上限。**

---
## 3. 探针结论（决定架构的关键证据，无需复跑）

探针脚本：`tdx_probe*.py` + `tdx_probe_tencent.py` + `tdx_probe_sweep.py`（输出 `tdx_*_out.txt`）。

### 3.1 TDX（pytdx 1.72，PyPI 2021 后停更）——已判死刑
- 可达站仅 3 台，其余超时/拒绝。
- `get_security_list(SZ, p0)` 正常 1000 条 → 链路是通的。
- `get_security_quotes` 全空、`get_security_bars` 报残包/2 字节 stub，三站一致 → 服务端 2026-07-17 协议升级后旧命令被废弃，客户端修不回来（社区 mootdx/tdxpy issue 同证，均停更）。
- 附带 bug：SH p0 `UnicodeDecodeError: b'ChatGPT\xb8'`——“ChatGPT 概念”GBK 名被 8 字节截断，pytdx 解析器未做容错。
- **结论：不得以纯 TDX 作为唯一实时源。TDX 只保留适配器插槽。**

### 3.2 腾讯（`qt.gtimg.cn` / `ifzq.gtimg.cn`）——定为主实时源
- `qt.gtimg.cn?q=sh600519,sz000001,…` 一次 6 只 **238ms / 3103B / 88 字段**，含 name/price/pre/open/vol/amount/change/pct，连续批量无 429 → 可做 80-100 只/包批量轮询。
- 分时 `trends` OK：267 条/日，首 0930 末 1530，字段 time/price/volume/amount。
- 分钟 K 返回结构为 `{"qt":{…}, "m1":[…]}`，list 解析（非 dict）。
- **结论：实时 quotes + 分时走腾讯。**

### 3.3 东财（现有）——定为 K 线/市值补充源
- K 线 `push2his.eastmoney.com/api/qt/stock/kline/get?klt=101/102/103/1/5/…&fqt=0` 稳定。
- 批量行情 `clist/get?fs=m:0+m:1…` 可做全市场兜底，但分页慢（约 5000 只 60s），仅作灾备/补全。

---
## 4. 总体方案：TDX 风格抽象 + 双 HTTP 主备

### 4.1 设计口号
> “像 TDX 一样思考，用 HTTP 落地”：上层只认 TDX 语义（批量 quotes、分页 K、server pool、心跳重连），底层用腾讯/东财实现，未来真 TDX 复活即插即用。

### 4.2 架构
```
UI (main_window / stock_list_widget / chart_widget)
  TradingClock: 盘中 3s / 盘后 60s / 休市暂停
  QuoteWorker(QThread) --signal--> set_data/update_row
        | 仅调 Facade
data/fetcher.py (Facade, 保持现有函数签名兼容)
  get_quote / get_quotes / get_kline / get_minute /
  get_value_metrics / search_stocks / get_all_stock_list
        | 委托
data/providers/manager.py (QuoteManager 单例)
  ServerPool(健康分 + 熔断) + Fallback链
  Fallback: Tencent -> Eastmoney -> SQLite -> Mock
  TDXAdapter: 预留，默认 disable
       |           |              |
TencentProvider EastmoneyProvider TdxProvider(stub)
qt.gtimg.cn    push2(.his)      pytdx(可选依赖)
```

### 4.3 关键策略
1. Provider 接口统一（见 5.2），新增源只需实现 4 方法 + 注册，不改 UI。
2. 批量优先：quotes 一律批量（腾讯 80/包串行 2-3 包；东财 clist 分页仅灾备），禁止单票循环作为主路径。
3. 休市不污染：current==0 且 volume==0 且 pre_close==0 视为无效 tick：不写 DB、不覆写 UI 快照，返回 DB 缓存并标记 stale=true、mocked=false。
4. DB 为真源兜底：网络全失败返回 DB 最新 + stale=true；DB 也无才 mock + mocked=true，UI 状态栏必须明示“离线/缓存/模拟”。
5. 交易时钟：新建 utils/trading_clock.py 判断 09:15-11:30 / 13:00-15:00：盘中 3000ms，盘后 60000ms，闭市暂停轮询只读 DB。
6. 熔断与重连：ServerPool 记录每站连续失败数 >=3 熔断 5 分钟；单请求 timeout 盘中 5s / 盘后 8s，retry 2 次退避 0.5s/1s。
7. 增量 K 线：DB 存最新 date，下次 beg=last_date 只拉增量后 upsert 合并；分时当日全量覆写。
8. 线程安全：所有网络 I/O 在 QThread 内，Facade 返回纯 dict/DataFrame，UI 只做渲染。

---
## 5. 接口契约（其他 Agent 必须遵守）

### 5.1 Facade（data/fetcher.py 对外签名不变）
- get_quote(symbol) -> dict
- get_quotes(symbols) -> list[dict]
- get_kline(symbol, period="daily", days=120) -> DataFrame（index=date, cols=[open,high,low,close,volume]）
- get_minute(symbol, date_str=None) -> DataFrame（cols=[time,price,volume,amount]）
- get_value_metrics(symbol) -> dict（pe,pb,roe,dividend_yield,total_market_cap,circ_market_cap）
- search_stocks(keyword) -> list[dict]
- get_all_stock_list(limit=200) -> list[dict]（symbol,code,name,market）
- quote dict 统一字段：symbol,name,current,change,change_pct,volume,amount,open,high,low,pre_close,market_cap,stale,mocked,timestamp

### 5.2 Provider 基类（新建 data/providers/base.py）
- QuoteSnapshot(TypedDict)：同上 quote 字段。
- BaseProvider(ABC)：name；get_quotes(codes)；get_kline(code,klt,beg,end)；get_minute(code)；health()。
- 工具函数：normalize_symbol（去 SH/SZ/BJ 前缀与 .SH/.SZ 后缀，得纯 6 位）；to_secid（6 开头->1.xxx 否则 0.xxx）；to_tencent_sym（6/9/11 开头->sh 否则 sz，指数直通）；is_valid_tick（休市判定）。

### 5.3 代码与周期映射
- daily->101, weekly->102, monthly->103, 1m/5m/15m/30m/60m->1/5/15/30/60, minute->1, 5d->101(tail 5), yearly->103。

### 5.4 腾讯字段（qt.gtimg.cn，0 基，单票 88 字段）
- [1]=名称 [2]=代码 [3]=现价 [4]=昨收 [5]=今开 [6]=成交量(手) [30]=时间；change=现价-昨收。
- 分时 trends：data.{sym}.trends=[[HH:MM,price,vol,amt],…]，vol 为手，需 *100 对齐东财（股）。

### 5.5 DB 约束（复用 data/database.py，不改表结构）
- upsert_quote 仅当 tick 有效才写；get_quote_from_db 兜底必须带 stale=True。
- K 线 upsert_klines(code,period,df) 主键 (code,period,date)；分钟 upsert_minute(code,date,df) 主键 (code,date,time)。

---
## 6. 非功能需求
- 盘中 8 只自选轮询 P95 < 800ms，200 只列表 < 3s。
- 公网失败 1s 内降级到 DB 缓存，UI 不卡死（网络永不跑 UI 线程）。
- trust_env=False 直连（绕过系统代理）+ 显式 timeout，禁止无超时请求。
- 日志：每次源切换/熔断 warning 一次，含 provider/耗时/错误类，不刷屏。
- 依赖：pytdx>=1.72 为可选（import 失败即 disable）；主力仅 requests+pandas。

---
## 7. 任务拆分（按序认领，星号可并行）
1. [并行] 新建 data/providers/base.py：BaseProvider + QuoteSnapshot + normalize/secid/tencent 前缀 + is_valid_tick。
2. [并行] 新建 data/providers/tencent_provider.py：qt.gtimg.cn 批量 quotes（80/包）+ ifzq trends 分时 + health；list 解析；vol 手转股。
3. [并行] 新建 data/providers/eastmoney_provider.py：从现 fetcher.py 搬运 _em_snapshot/_em_quotes/_em_kline（含 headers/ut/retry）。
4. 新建 data/providers/tdx_provider.py：pytdx 懒导入，get_security_list 可用 + GBK 截断补丁（decode errors=ignore），quotes/kline 默认 NotSupported 且 health=False。
5. 新建 data/providers/manager.py：QuoteManager 单例 + ServerPool 熔断 + Fallback 链 + 3s 快照缓存 + 增量 K 线 beg=last_date。
6. 重构 data/fetcher.py 为 Facade：保留 5.1 签名，内部全委托 manager；DATA_SOURCE 改为 PROVIDER_ORDER=["tencent","eastmoney","db","mock"]（兼容旧值）。
7. [并行] 新建 utils/trading_clock.py：is_trading_now()/next_interval_ms()（盘中 3000 / 盘后 60000 / 闭市 None）；main_window 改为动态 interval，状态栏显示数据源+stale/mock。
8. config.py：PRICE_REFRESH_INTERVAL=3000，新增 OFFHOUR=60000、QUOTE_BATCH_SIZE=80、PROVIDER_ORDER、TDX_ENABLED=False、TDX_SERVERS（3 台可达）。
9. 验证：盘中/盘后各跑 get_quotes(['600519','000001']) + main.py 看 3s 跳动；休市用例断言 DB 不被零值覆写。

---
## 8. 验收标准
- 自选 8 只盘中 3s 自动刷新，无全量闪烁（update_row 而非 set_data）。
- 断网 → 状态栏“离线缓存”，价格不变且不归零；恢复 5s 内切回腾讯。
- 腾讯 429/超时 → 自动切东财，日志仅一条 warn。
- K 线日/周/月/分钟均有真实（非 mock）数据，增量第二次加载 < 500ms。
- 无 pytdx 环境启动正常；requirements 不强制 pytdx。

---
## 9. 风险与取舍
- 腾讯字段无官方文档，依赖抓包位序 → 字段解析全包 try/except，单字段失败不丢整包。
- 东财 ut token 会过期 → 全包 403/空即熔断切源，token 集中放 eastmoney_provider.py 顶部便于一处更新。
- 真 TDX 复活成本高（需逆向新 hello/加密）→ 本期只做插槽，不投入逆向。


---

## 10. 长连接方案论证（本节只补文档，不改代码）

### 10.1 结论先行

1. **“UI 层长连接”可以做，且推荐做**：把现在的 `QTimer + QuoteFetchThread（每次拉全量、finished 一次性返回）`
   演进为 `QuoteHub（后台常驻线程/服务）+ 订阅推送（signal/slot）`，UI 只收 diff（`update_row`），不主动轮询。
   这不依赖上游是否支持推送，本期即可做，收益是 UI 不闪烁、不阻塞、断线可感知。
2. **“上游长连接直连交易所”不要做**：散户没有交易所直连资格；同花顺/通达信的长连接背后是
   自建行情网关 + 托管席位 + 付费专线 + 私有二进制协议，TradeSight 用公网免费 HTTP 源复刻不了，
   投入产出比极低。
3. **“上游 HTTP 改推送”做不了**：腾讯 `qt.gtimg.cn` / 东财 `push2` 免费接口只暴露了无状态 HTTP 轮询，
   没有公开的 WS/SSE 订阅语义；`requests.Session（trust_env=False）` 的 Keep-Alive 只是 TCP 复用，
   不是服务端推送。强行“长连接化”仍是轮询套壳，还多一层重连/粘包复杂度。

### 10.2 HTTP 轮询 vs 长连接的本质区别

| 维度 | 现状 HTTP 轮询（已落地） | 真长连接（同花顺/TDX 风格） |
|---|---|---|
| 连接模型 | 每次（或每批）新建请求→响应→断开（Keep-Alive 只是复用 TCP，应用层仍一问一答） | 一条 TCP/WS 常驻，握手一次，之后双向帧 |
| 数据方向 | 客户端拉（Poll）：没变化也问一次 | 服务端推（Push）：有变化才下发 diff + 心跳 |
| 实时性下限 | 受轮询间隔限制（盘中 3s），两次之间变化不可见 | 受服务端聚合窗口限制（约 tick 级，盘中 1~3s 聚合推） |
| 头部开销 | 每次带 HTTP 头 + TLS 握手（复用后减轻），200 只分包即 3~7 次 RTT | 握手一次，后续只有二进制帧头（几字节）+ 心跳 |
| 服务端压力 | 空轮询多，易触发 429/`RemoteDisconnected`（东财已实测复位） | 订阅制：只收自己订阅的代码 diff，空闲只有心跳 |
| 断线感知 | 靠“下次轮询超时”才知道断了（最慢延迟一个周期） | 心跳超时秒级感知 + 自动重连 + 续传 seq |
| 批量语义 | 一包 80 只 GET，URL 长度/字段数受限 | 一包 80~100 只二进制，分页 + 增量 seq，本地按 code 合并 |
| 防火墙/代理 | 443 出向一般放行，`trust_env=False` 直连即可 | 7709 等私有端口常被封，WS 也要处理代理透传 |
| 复杂度 | 低：timeout + retry + 熔断即可 | 高：hello/鉴权/心跳/重连/粘包/分包/断点续传/本地库对账 |
| 数据源要求 | 公网免费 JSON 即可 | 需要网关 SL A：主备站、token/会话、协议版本跟随（TDX 2026-07 已证明跟随成本） |

一句话：**Keep-Alive 省的是“握手”，推送省的是“空问”；前者我们已经有（Session 复用），后者免费上游不给。**

### 10.3 为什么同花顺能推、我们只能拉

```
同花顺/通达信：
  交易所 -> 券商托管/网关（付费专线） -> 自建行情集群（多活） -> TCP/私有二进制长连接 -> 客户端
  特点：订阅制 + 会话 hello + 心跳 + 服务端聚合 3s 推 + 本地除权/板块库 + 主备切换

TradeSight（现状）：
  腾讯/东财公网 HTTP -> requests 轮询（盘中3s/盘后60s） -> Manager 熔断 -> SQLite -> UI
  特点：无状态、无订阅、无推送、无会话；“实时”是高频轮询模拟出来的
```

差距不在客户端写法，在**网关和线路**：人家为推送付了专线 + 服务器 + 协议维护费；
我们用免费抓包接口，只能做“像推送一样勤快的拉”。

### 10.4 如果硬要做长连接，三条路的取舍

- **路线 A（推荐，纯本地改造，不碰上游）：本地 QuoteHub 推送**
  后台常驻 `QuoteHub(QThread)` 内做 3s 轮询 + diff（只 emit 变化的 symbol），UI 侧从
  `QTimer 拉` 改为 `signal 收`。对外仍是 HTTP，但 UI 体感 = 推送（不闪烁、秒级断线提示、
  周末自动停）。成本 1~2 天，无外部依赖，与现有 Manager/Facade 完全兼容。
- **路线 B（不推荐，伪长连接）：HTTP 套 WS/SSE 壳**
  本地起 WS 网关，网关内仍轮询腾讯/东财，再转推给 UI。多了网关运维和重连逻辑，
  实时性仍被上游 3s 轮询卡住，收益≈0，只增加故障点。
- **路线 C（暂缓，真上游推送）：TDX 复活 / 券商 API / 付费行情**
  需逆向新 hello/加密（TDX 2026-07 已断）、或接券商 QMT/Level2、或买付费 WS 行情。
  成本按周计，且有合规/稳定性风险。触发条件：TDX 社区出现可用新协议实现，或决定付费。

### 10.5 给其他 Agent 的决策

- 本期不动上游，保持 `Tencent -> Eastmoney -> DB -> Mock` HTTP 链（§4/§7 已落地验证：
  茅台 1329、平安 11.5、批量 3 只 tencent、分时 146 行）。
- 要优化“实时感”，只做路线 A（本地推送化），不要碰路线 B/C。
- 路线 A 的接口约束（预留，不实现）：`QuoteHub.subscribe(codes)` / `unsubscribe(codes)` /
  `quotes_changed(list[QuoteSnapshot])` / `connection_state(src, stale_n, mocked_n)`，
  复用现有 `QuoteSnapshot` 字段与 `last_source()` 语义；心跳 = 交易时钟节拍，断线 = 熔断计数。
- 验收仍按 §8：3s 跳动无闪烁、断网显“离线缓存”不归零、429 一条 warn 即切换。

