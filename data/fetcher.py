# -*- coding: utf-8 -*-
"""股票数据获取层 Facade（重构后，feature.md §5.1/§7.6）。

对外签名与旧版兼容；内部委托 data.providers.manager.QuoteManager：
Tencent -> Eastmoney -> SQLite(DB) -> Mock。
"""

import time
import logging

import pandas as pd

from config import DATA_SOURCE, DATABASE_PATH
from data.database import (
    upsert_stock_info,
    get_stock_name,
    upsert_quote,
    get_quote_from_db,
    upsert_klines,
    get_klines_from_db,
    upsert_minute,
    get_minute_from_db,
    upsert_metrics,
    get_metrics_from_db,
)
from data.mock_data import (
    get_mock_quote,
    get_mock_quotes,
    get_mock_kline,
    get_mock_metrics,
    get_mock_search,
    get_mock_minute,
    get_mock_all_stocks,
)

try:
    import akshare as ak
    HAS_AKSHARE = True
except Exception:  # pragma: no cover - 允许无 akshare 环境
    HAS_AKSHARE = False

import logging as _logging
log = _logging.getLogger("tradesight.facade")
_LAST_SRC = "db"


def last_source() -> str:
    return _LAST_SRC


def _db_quote_to_ui(cached: dict, symbol: str) -> dict:
    return {
        "symbol": cached.get("code") or symbol,
        "name": cached.get("name") or symbol,
        "current": _num(cached.get("current")),
        "change": _num(cached.get("change")),
        "change_pct": _num(cached.get("change_pct")),
        "volume": _num(cached.get("volume")),
        "amount": _num(cached.get("amount")),
        "open": _num(cached.get("open")),
        "high": _num(cached.get("high")),
        "low": _num(cached.get("low")),
        "pre_close": _num(cached.get("pre_close")),
        "market_cap": 0.0,
        "timestamp": cached.get("timestamp"),
        "stale": True,
        "mocked": False,
        "provider": "db",
    }

try:
    import requests
    _HAS_REQUESTS = True
except Exception:  # pragma: no cover
    _HAS_REQUESTS = False


# ---------------------------------------------------------------------------
# 代理绕过：所有 requests 会话忽略系统代理环境变量，直连东方财富
# ---------------------------------------------------------------------------
if _HAS_REQUESTS:
    _orig_session_init = requests.Session.__init__

    def _session_init_no_proxy(self, *args, **kwargs):
        _orig_session_init(self, *args, **kwargs)
        self.trust_env = False

    try:
        requests.Session.__init__ = _session_init_no_proxy
    except Exception:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# 东财直连接口公共配置
# ---------------------------------------------------------------------------
_EM_UT_KLINE = "7eea3edcaed734bea9cbfc24409ed989"     # K线接口 token
_EM_UT_QUOTE = "bd1d9ddb04089700cf9c27f6f7426281"    # 行情/批量接口 token
_EM_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://quote.eastmoney.com/",
}
_EM_TIMEOUT = 8.0   # 秒，防止 UI 线程长时间挂起
_EM_RETRY = 3

# 周期 -> 东财 klt 参数
_EM_KLT = {
    "daily": "101", "weekly": "102", "monthly": "103",
    "5d": "101", "yearly": "103",          # 5日线复用日线，年线复用月线
    "1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60",
    "minute": "1",
}

# 单票快照短缓存：同一次刷新内 get_quote 与 get_value_metrics 共享，避免重复请求
_SNAPSHOT_CACHE = {}   # code -> (fetch_time, snapshot)
_SNAPSHOT_TTL = 3.0    # 秒


def _normalize_symbol(symbol: str) -> str:
    """统一股票代码格式：去除 sh/sz/bj 前缀与 .SH/.SZ 等后缀，返回纯数字代码"""
    symbol = (symbol or "").strip().upper()
    for prefix in ("SH", "SZ", "BJ", "HK"):
        if symbol.startswith(prefix) and symbol[len(prefix):].isdigit():
            symbol = symbol[len(prefix):]
            break
    for suffix in (".SH", ".SZ", ".BJ", ".HK", ".US", ".SH.XSHG", ".SZ.XSHE"):
        if symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]
    return symbol.strip()


def _to_secid(symbol: str) -> str:
    """纯数字代码 -> 东财 secid。沪市(6开头)市场码=1，其余=0。"""
    code = _normalize_symbol(symbol)
    market = "1" if code.startswith("6") else "0"
    return f"{market}.{code}"


def _num(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _em_get_json(url: str, params: dict) -> dict:
    """带超时与退避重试的东财 GET，返回解析后的 JSON。全部失败则抛出最后一次异常。"""
    last_err = None
    for attempt in range(_EM_RETRY):
        try:
            session = requests.Session()
            resp = session.get(url, params=params, headers=_EM_HEADERS, timeout=_EM_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001 - 需捕获所有网络异常以重试
            last_err = e
            if attempt < _EM_RETRY - 1:
                time.sleep(0.6 * (attempt + 1))
    raise last_err


def _em_snapshot(symbol: str) -> dict:
    """单票实时快照（行情 + 估值），一次请求取回。失败向上抛异常。

    字段(东财 push2/api/qt/stock/get)：
      f43 最新价 f44 最高 f45 最低 f46 今开 f47 成交量 f48 成交额 f60 昨收
      f169 涨跌额 f170 涨跌幅 f57 代码 f58 名称
      f116 总市值 f117 流通市值 f163 市盈率(动) f167 市净率 f173 净资产收益率
    """
    code = _normalize_symbol(symbol)
    params = {
        "fltt": "2", "invt": "2", "secid": _to_secid(code), "ut": _EM_UT_QUOTE,
        "fields": "f43,f44,f45,f46,f47,f48,f60,f169,f170,f57,f58,f116,f117,f163,f167,f173",
    }
    data = _em_get_json("https://push2.eastmoney.com/api/qt/stock/get", params).get("data")
    if not data:
        raise ValueError(f"empty snapshot for {code}")
    return {
        "code": str(data.get("f57", code)),
        "name": data.get("f58") or code,
        "price": _num(data.get("f43")),
        "open": _num(data.get("f46")),
        "high": _num(data.get("f44")),
        "low": _num(data.get("f45")),
        "pre_close": _num(data.get("f60")),
        "change": _num(data.get("f169")),
        "change_pct": _num(data.get("f170")),
        "volume": _num(data.get("f47")),
        "amount": _num(data.get("f48")),
        "total_market_cap": _num(data.get("f116")),
        "circ_market_cap": _num(data.get("f117")),
        "pe": _num(data.get("f163")),
        "pb": _num(data.get("f167")),
        "roe": _num(data.get("f173")),
    }


def _get_snapshot_cached(symbol: str) -> dict:
    """带短 TTL 缓存的单票快照，避免同一次刷新内重复请求"""
    code = _normalize_symbol(symbol)
    now = time.time()
    cached = _SNAPSHOT_CACHE.get(code)
    if cached and (now - cached[0]) < _SNAPSHOT_TTL:
        return cached[1]
    snap = _em_snapshot(code)
    _SNAPSHOT_CACHE[code] = (now, snap)
    return snap


def _em_batch_snapshots(symbols: list) -> dict:
    """批量实时快照，一次请求取回多只股票。返回 {code: snapshot}。失败向上抛异常。

    字段(东财 push2/api/qt/ulist.np/get)：
      f12 代码 f14 名称 f2 最新价 f3 涨跌幅 f4 涨跌额 f5 成交量 f6 成交额
      f15 最高 f16 最低 f17 今开 f18 昨收 f9 市盈率 f20 总市值 f21 流通市值 f23 市净率
    """
    codes = [_normalize_symbol(s) for s in symbols]
    params = {
        "secids": ",".join(_to_secid(c) for c in codes),
        "fields": "f2,f3,f4,f5,f6,f9,f12,f14,f15,f16,f17,f18,f20,f21,f23",
        "fltt": "2", "invt": "2", "ut": _EM_UT_QUOTE,
    }
    data = _em_get_json("https://push2.eastmoney.com/api/qt/ulist.np/get", params).get("data")
    if not data:
        raise ValueError("empty batch snapshot")
    diff = data.get("diff", [])
    if isinstance(diff, dict):
        diff = list(diff.values())

    result = {}
    for row in diff:
        code = str(row.get("f12", ""))
        if not code:
            continue
        result[code] = {
            "code": code,
            "name": row.get("f14") or code,
            "price": _num(row.get("f2")),
            "open": _num(row.get("f17")),
            "high": _num(row.get("f15")),
            "low": _num(row.get("f16")),
            "pre_close": _num(row.get("f18")),
            "change": _num(row.get("f4")),
            "change_pct": _num(row.get("f3")),
            "volume": _num(row.get("f5")),
            "amount": _num(row.get("f6")),
            "total_market_cap": _num(row.get("f20")),
            "circ_market_cap": _num(row.get("f21")),
            "pe": _num(row.get("f9")),
            "pb": _num(row.get("f23")),
        }
    return result


def _em_kline(symbol: str, klt: str, fqt: str = "0",
              beg: str = "19700101", end: str = "20500101") -> pd.DataFrame:
    """K线（日/周/月/分钟通用），返回 DataFrame[open,high,low,close,volume,amount]。

    kline 字段串格式: 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
    """
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
        "ut": _EM_UT_KLINE,
        "klt": klt, "fqt": fqt,
        "secid": _to_secid(symbol),
        "beg": beg, "end": end,
    }
    data = _em_get_json("https://push2his.eastmoney.com/api/qt/stock/kline/get", params).get("data")
    if not (data and data.get("klines")):
        raise ValueError(f"empty klines for {symbol}")

    rows = [item.split(",") for item in data["klines"]]
    df = pd.DataFrame(rows)
    df = df.iloc[:, :11]  # 只取前11列（丢弃 f116 等附加列）
    df.columns = ["date", "open", "close", "high", "low", "volume", "amount",
                  "amp", "pct", "chg", "turn"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume", "amount"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    return df[["open", "high", "low", "close", "volume", "amount"]]


def _is_kline_stale(df: pd.DataFrame, period: str) -> bool:
    """判断缓存 K线是否过期：最新一根K线距今超过阈值则需重新获取。"""
    if df is None or df.empty:
        return True
    last = df.index.max()
    if pd.isna(last):
        return True
    now = pd.Timestamp.now().normalize()
    last_day = pd.Timestamp(last).normalize()
    if period in ("minute", "1m", "5m", "15m", "30m", "60m"):
        return last_day < now  # 分时数据当日有效
    return (now - last_day).days > 5  # 日/周/月：容忍周末与小长假滞后


def _snapshot_to_quote(snap: dict, symbol: str) -> dict:
    """将快照 dict 转为 UI/DB 期望的 quote 结构（含 market_cap 供头部显示）"""
    return {
        "symbol": snap.get("code") or symbol,
        "name": snap.get("name") or symbol,
        "current": snap.get("price", 0.0),
        "change": snap.get("change", 0.0),
        "change_pct": snap.get("change_pct", 0.0),
        "volume": snap.get("volume", 0.0),
        "amount": snap.get("amount", 0.0),
        "open": snap.get("open", 0.0),
        "high": snap.get("high", 0.0),
        "low": snap.get("low", 0.0),
        "pre_close": snap.get("pre_close", 0.0),
        "market_cap": snap.get("total_market_cap", 0.0),
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# 全市场股票列表缓存（避免重复调用 akshare 接口导致搜索缓慢）
_all_stock_cache = None
_all_stock_cache_time = 0


def _get_all_stock_list_cached() -> list:
    """获取全市场股票列表（带缓存，缓存有效期1小时）"""
    global _all_stock_cache, _all_stock_cache_time
    import time
    now = time.time()
    if _all_stock_cache is not None and (now - _all_stock_cache_time) < 3600:
        return _all_stock_cache
    if DATA_SOURCE == "akshare" and HAS_AKSHARE:
        try:
            df = ak.stock_info_a_code_name()
            df["code"] = df["code"].astype(str)
            results = [{"symbol": r["code"], "name": r["name"]} for _, r in df.iterrows()]
            _all_stock_cache = results
            _all_stock_cache_time = now
            for item in results:
                upsert_stock_info(item["symbol"], item["name"])
            return results
        except Exception:
            pass
    return get_mock_all_stocks()


def search_stocks(keyword: str) -> list:
    """按关键词搜索股票，返回 [{symbol, name}, ...]。支持全市场模糊匹配。"""
    keyword = (keyword or "").strip()

    if DATA_SOURCE == "akshare" and HAS_AKSHARE:
        try:
            # 获取全市场股票列表（代码+名称）
            stock_df = ak.stock_info_a_code_name()
            stock_df["code"] = stock_df["code"].astype(str)

            if keyword:
                mask = stock_df["code"].str.contains(keyword, na=False) | \
                       stock_df["name"].str.contains(keyword, na=False)
                res = stock_df.loc[mask, ["code", "name"]].head(50)
            else:
                # 关键词为空时返回前50只（避免一次性加载太多）
                res = stock_df.head(50)

            results = [{"symbol": r["code"], "name": r["name"]} for _, r in res.iterrows()]
            # 批量缓存名称到数据库
            for item in results:
                upsert_stock_info(item["symbol"], item["name"])
            return results
        except Exception:
            pass

    if keyword:
        return get_mock_search(keyword)
    return [{"symbol": s["symbol"], "name": s["name"]} for s in get_mock_all_stocks()[:50]]


def get_all_stock_list(limit: int = 200) -> list:
    """获取全市场股票列表，用于“查询所有上市公司”功能。

    联网模式下返回 akshare 的全市场列表（约4000只）；
    离线模式下返回模拟股票池。
    limit：返回数量上限，避免一次性加载过多。
    """
    if DATA_SOURCE == "akshare" and HAS_AKSHARE:
        try:
            df = ak.stock_info_a_code_name()
            df["code"] = df["code"].astype(str)
            res = df.head(limit)
            results = [{"symbol": r["code"], "name": r["name"]} for _, r in res.iterrows()]
            for item in results:
                upsert_stock_info(item["symbol"], item["name"])
            return results
        except Exception:
            pass

    return [{"symbol": s["symbol"], "name": s["name"]} for s in get_mock_all_stocks()[:limit]]


def get_quote(symbol: str) -> dict:
    """获取单只股票实时行情：Manager(腾讯->东财) -> DB(stale) -> mock(mocked)。"""
    from data.providers.manager import QuoteManager as _QM
    global _LAST_SRC
    symbol = _normalize_symbol(symbol)

    if DATA_SOURCE != "mock":
        try:
            rows, src = _QM.instance().get_quotes([symbol])
            if rows:
                q = dict(rows[0])
                q.setdefault("stale", False)
                q.setdefault("mocked", False)
                upsert_quote(q)
                _LAST_SRC = src
                return q
        except Exception as e:  # noqa: BLE001
            log.warning("get_quote manager fail %s: %s", symbol, e)

        cached = get_quote_from_db(symbol)
        if cached:
            _LAST_SRC = "db"
            return _db_quote_to_ui(cached, symbol)

    quote = get_mock_quote(symbol)
    quote["mocked"] = True
    quote["provider"] = "mock"
    upsert_quote(quote)
    _LAST_SRC = "mock"
    return quote


def get_quotes(symbols: list) -> list:
    """批量获取行情：Manager -> 缺失逐个补 -> mock，保证返回顺序与输入一致。"""
    from data.providers.manager import QuoteManager as _QM
    global _LAST_SRC
    if not symbols:
        return []
    syms = [_normalize_symbol(s) for s in symbols]

    rows: list = []
    if DATA_SOURCE != "mock":
        try:
            rows, src = _QM.instance().get_quotes(syms)
            _LAST_SRC = src
        except Exception as e:  # noqa: BLE001
            log.warning("get_quotes manager fail: %s", e)
            rows = []
        by_sym = {r.get("symbol"): dict(r) for r in rows}
        result = []
        for sym in syms:
            q = by_sym.get(sym)
            if q is None:
                q = get_quote(sym)  # 缺失个股走单票链路（含DB/mock）
            else:
                q.setdefault("stale", False)
                q.setdefault("mocked", False)
                upsert_quote(q)
            result.append(q)
        return result

    _LAST_SRC = "mock"
    return [get_quote(s) for s in syms]


def get_kline(symbol: str, period: str = "daily", days: int = 100) -> pd.DataFrame:
    """获取K线：DB新鲜直返 -> Manager增量(beg=last_date) -> 旧缓存 -> mock。"""
    from data.providers.manager import QuoteManager as _QM
    symbol = _normalize_symbol(symbol)

    df = get_klines_from_db(symbol, period, limit=days)
    if df is not None and len(df) >= max(10, days // 2) and not _is_kline_stale(df, period):
        return df.tail(days)

    if DATA_SOURCE != "mock":
        try:
            klt = _EM_KLT.get(period, "101")
            beg = "20150101"
            if df is not None and not df.empty:
                try:
                    beg = (pd.Timestamp(df.index.max()) + pd.Timedelta(days=1)).strftime("%Y%m%d")
                except Exception:
                    beg = "20150101"
            end = pd.Timestamp.now().strftime("%Y%m%d")
            fresh = _QM.instance().get_kline(symbol, klt, beg, end)
            if fresh is not None and not fresh.empty:
                upsert_klines(symbol, period, fresh)
                merged = get_klines_from_db(symbol, period, limit=days)
                if merged is not None and not merged.empty:
                    return merged.tail(days)
                return fresh.tail(days)
        except Exception as e:  # noqa: BLE001
            log.warning("get_kline manager fail %s: %s", symbol, e)

    if df is not None and not df.empty:
        return df.tail(days)

    df = get_mock_kline(symbol, period=period, days=days)
    upsert_klines(symbol, period, df)
    return df.tail(days)


def get_minute(symbol: str, date_str: str = None) -> pd.DataFrame:
    """获取分时：DB当日直返 -> Manager(腾讯) -> mock。"""
    from data.providers.manager import QuoteManager as _QM
    symbol = _normalize_symbol(symbol)
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    if date_str is None:
        date_str = today

    df = get_minute_from_db(symbol, date_str)
    if df is not None and not df.empty and date_str == today:
        return df

    if DATA_SOURCE != "mock":
        try:
            out = _QM.instance().get_minute(symbol)
            if out is not None and not out.empty:
                upsert_minute(symbol, date_str, out)
                return out
        except Exception as e:  # noqa: BLE001
            log.warning("get_minute manager fail %s: %s", symbol, e)

    df = get_mock_minute(symbol, date_str)
    df["mocked"] = True
    upsert_minute(symbol, date_str, df.drop(columns=["mocked"], errors="ignore"))
    return df


def get_value_metrics(symbol: str) -> dict:
    """获取价值指标：快照(腾讯含市值) -> DB -> mock。"""
    from data.providers.manager import QuoteManager as _QM
    symbol = _normalize_symbol(symbol)

    if DATA_SOURCE != "mock":
        try:
            rows, _ = _QM.instance().get_quotes([symbol])
            if rows:
                snap = rows[0]
                cap = _num(snap.get("market_cap"))
                metrics = {
                    "pe": _num(snap.get("pe")),
                    "pb": 0.0,
                    "total_market_cap": cap / 1e8 if cap else 0.0,
                    "circ_market_cap": cap / 1e8 if cap else 0.0,
                    "roe": 0.0,
                    "dividend_yield": 0.0,
                }
                # 东财补充市值/估值（腾讯快照无市值时）
                if not metrics["total_market_cap"]:
                    try:
                        from data.providers.eastmoney_provider import EastmoneyProvider as _EM
                        es = _EM()._snapshot(symbol)
                        if es:
                            ec = _num(es.get("market_cap"))
                            metrics["total_market_cap"] = ec / 1e8 if ec else 0.0
                            metrics["circ_market_cap"] = metrics["total_market_cap"]
                            metrics["pe"] = metrics["pe"] or _num(es.get("pe"))
                    except Exception:
                        pass
                upsert_metrics(symbol, metrics)
                return metrics
        except Exception as e:  # noqa: BLE001
            log.warning("get_value_metrics manager fail %s: %s", symbol, e)

        cached = get_metrics_from_db(symbol)
        if cached:
            return {
                "pe": _num(cached["pe"]),
                "pb": _num(cached["pb"]),
                "total_market_cap": _num(cached["total_market_cap"]),
                "circ_market_cap": _num(cached["circ_market_cap"]),
                "roe": _num(cached["roe"]),
                "dividend_yield": _num(cached["dividend_yield"]),
            }

    metrics = get_mock_metrics(symbol)
    upsert_metrics(symbol, metrics)
    return metrics