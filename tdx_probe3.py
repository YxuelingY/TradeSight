# -*- coding: utf-8 -*-
"""TDX 探针3：TDX_DEBUG 原始包 + SZ/SH 隔离测试，定位 quotes/kline 失败的真实原因。"""
import io
import os
import sys
import time
import traceback

os.environ["TDX_DEBUG"] = "1"

LOG = []


def log(msg):
    s = str(msg)
    LOG.append(s)
    print(s, flush=True)


def test(api, label, fn):
    try:
        r = fn()
        if isinstance(r, list):
            log(f"  {label}: OK list[{len(r)}]"
                + (f" first={r[0]}" if r else ""))
        else:
            log(f"  {label}: OK {type(r).__name__}={r}")
        return r
    except Exception as e:
        orig = getattr(e, "original_exception", None)
        log(f"  {label}: FAIL {type(e).__name__}: {e} | orig={orig!r}")
        return None


def main():
    from pytdx.hq import TdxHq_API

    for ip, port in [("115.238.90.165", 7709),
                     ("180.153.18.170", 7709),
                     ("shtdx.gtjas.com", 7709),
                     ("jstdx.gtjas.com", 7709)]:
        log(f"\n########## {ip}:{port} ##########")
        api = TdxHq_API(raise_exception=True, heartbeat=False)
        try:
            api.connect(ip, port, time_out=3)
        except Exception as e:
            log(f"  connect FAIL: {e}")
            continue

        log("  --- SZ quotes ---")
        test(api, "SZ quotes 000001+300750",
             lambda: api.get_security_quotes([(0, "000001"), (0, "300750")]))
        log("  --- SH quotes ---")
        test(api, "SH quotes 600519",
             lambda: api.get_security_quotes([(1, "600519")]))
        log("  --- SZ kline cat9 ---")
        test(api, "SZ kline 000001",
             lambda: api.get_security_bars(9, 0, "000001", 0, 5))
        log("  --- SH kline cat9 ---")
        test(api, "SH kline 600519",
             lambda: api.get_security_bars(9, 1, "600519", 0, 5))
        log("  --- SH kline cat4(日) ---")
        test(api, "SH kline cat4 600519",
             lambda: api.get_security_bars(4, 1, "600519", 0, 5))
        log("  --- index kline SH999999 ---")
        test(api, "index kline",
             lambda: api.get_index_bars(9, 1, "999999", 0, 5))
        log("  --- SZ list ---")
        r = test(api, "SZ list p0", lambda: api.get_security_list(0, 0))
        log("  --- SH list ---")
        test(api, "SH list p0", lambda: api.get_security_list(1, 0))
        test(api, "SH list p1000", lambda: api.get_security_list(1, 1000))

        try:
            api.disconnect()
        except Exception:
            pass
        # 只详细调试第一台
        break

    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    code = 0
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 2
    # TDX_DEBUG 走 logging StreamHandler -> stderr，捕获到文件
    with open(r"d:\code\TradeSight\tdx_probe3_out.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + f"\nEXIT={code}\n")
    sys.exit(code)
