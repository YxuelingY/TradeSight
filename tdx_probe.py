# -*- coding: utf-8 -*-
"""TDX 协议联网探针：测服务器可达性、行情字段、K线、分时、股票列表、财务数据。"""
import io
import json
import socket
import sys
import time

socket.setdefaulttimeout(8)

LOG = []


def log(msg):
    s = str(msg)
    LOG.append(s)
    print(s, flush=True)


CANDIDATES = [
    ("119.147.171.206", 7709, "广州行情主站"),
    ("115.238.90.165", 7709, "深圳行情主站"),
    ("180.153.18.170", 7709, "上海行情主站"),
    ("114.80.80.222", 7711, "上海行情主站2"),
    ("221.194.181.176", 7709, "北京行情主站2"),
    ("106.120.74.86", 7711, "北京行情主站1"),
    ("218.108.50.178", 7709, "杭州行情主站"),
    ("119.29.51.30", 7709, "腾讯行情"),
    ("113.105.73.88", 7709, "深圳行情"),
    ("117.184.140.156", 7709, "移动行情"),
]


def try_connect():
    from pytdx.hq import TdxHq_API
    best = None
    for ip, port, name in CANDIDATES:
        api = TdxHq_API()
        t0 = time.time()
        try:
            ok = api.connect(ip, port, time_out=2)
        except Exception as e:
            log(f"  FAIL {name} {ip}:{port} -> {type(e).__name__}: {e}")
            continue
        cost = time.time() - t0
        if not ok:
            log(f"  FAIL {name} {ip}:{port} connect=False ({cost:.2f}s)")
            continue
        try:
            cnt = api.get_security_count(0)
            log(f"  OK   {name} {ip}:{port} ({cost:.2f}s) 深市证券数={cnt}")
            if best is None:
                best = (api, ip, port, name, cost)
            else:
                api.disconnect()
        except Exception as e:
            log(f"  FAIL {name} {ip}:{port} ping -> {type(e).__name__}: {e}")
            try:
                api.disconnect()
            except Exception:
                pass
        if best is not None:
            break
    return best


def main():
    try:
        import pandas as pd  # noqa
    except Exception:
        pass

    log("== [1] 服务器探测 ==")
    found = try_connect()
    if not found:
        log("NO SERVER REACHABLE")
        return 1
    api, ip, port, name, _ = found
    log(f"使用服务器: {name} {ip}:{port}")

    log("\n== [2] 批量行情 get_security_quotes ==")
    try:
        res = api.get_security_quotes([(1, "600519"), (0, "000001"), (0, "300750")])
        for r in res or []:
            log(json.dumps(dict(r), ensure_ascii=False, default=str))
    except Exception as e:
        log(f"FAIL {type(e).__name__}: {e}")

    log("\n== [3] 日K get_security_bars(9) ==")
    try:
        bars = api.get_security_bars(9, 1, "600519", 0, 5)
        for b in bars or []:
            log(json.dumps(dict(b), ensure_ascii=False, default=str))
    except Exception as e:
        log(f"FAIL {type(e).__name__}: {e}")

    log("\n== [4] 1分钟K get_security_bars(8) 最近300根（统计今日根数）==")
    try:
        bars = api.get_security_bars(8, 1, "600519", 0, 300)
        today = time.strftime("%Y-%m-%d")
        n_today = sum(1 for b in bars or [] if str(b["datetime"]).startswith(today))
        log(f"返回 {len(bars or [])} 根, 今日 {n_today} 根, 最新3根:")
        for b in (bars or [])[-3:]:
            log(json.dumps(dict(b), ensure_ascii=False, default=str))
    except Exception as e:
        log(f"FAIL {type(e).__name__}: {e}")

    log("\n== [5] 当日分时 get_minute_time_data ==")
    try:
        t = api.get_minute_time_data(1, "600519")
        log(f"返回 {len(t or [])} 条, 前2条+后2条:")
        for x in (t or [])[:2] + (t or [])[-2:]:
            log(json.dumps(dict(x), ensure_ascii=False, default=str))
    except Exception as e:
        log(f"FAIL {type(e).__name__}: {e}")

    log("\n== [6] 股票列表页 get_security_list（找600519的名称）==")
    try:
        page = api.get_security_list(1, 0)
        hit = [x for x in (page or []) if x["code"] == "600519"]
        log(f"首页 {len(page or [])} 条, 600519 -> {hit}")
        # 深市找 000001
        page2 = api.get_security_list(0, 0)
        hit2 = [x for x in (page2 or []) if x["code"] == "000001"]
        log(f"深市首页 {len(page2 or [])} 条, 000001 -> {hit2}")
    except Exception as e:
        log(f"FAIL {type(e).__name__}: {e}")

    log("\n== [7] 财务 get_finance_info ==")
    try:
        f = api.get_finance_info(1, "600519")
        if f:
            keys = ["code", "zongguben", "liutongguben", "meigujingzichan",
                    "jinglirun", "zhuyingshouru", "jingzichan", "updated_date"]
            log(json.dumps({k: f.get(k) for k in keys}, ensure_ascii=False, default=str))
            price = 1311.0  # 假设最新价，仅演示单位口径
            zgb = f.get("zongguben") or 0
            jl = f.get("jinglirun") or 0
            bps = f.get("meigujingzichan") or 0
            if zgb and jl:
                eps = jl / zgb
                log(f"单位口径推算: 总股本={zgb:.0f}股, EPS={eps:.4f}, "
                    f"PE@1311={price/eps:.2f}, PB@1311={price/bps:.2f}, "
                    f"总市值={price*zgb/1e8:.0f}亿")
    except Exception as e:
        log(f"FAIL {type(e).__name__}: {e}")

    log("\n== [8] 心跳/连拍：连续3次行情请求测限流 ==")
    try:
        for i in range(3):
            t0 = time.time()
            r = api.get_security_quotes([(1, "600519")])
            log(f"  #{i+1} {(time.time()-t0)*1000:.0f}ms price={r[0]['price'] if r else None}")
            time.sleep(1)
    except Exception as e:
        log(f"FAIL {type(e).__name__}: {e}")

    try:
        api.disconnect()
    except Exception:
        pass

    log("\nPROBE DONE")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    code = 0
    try:
        code = main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        code = 2
    with open(r"d:\code\TradeSight\tdx_probe_out.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + f"\nEXIT={code}\n")
    sys.exit(code)
