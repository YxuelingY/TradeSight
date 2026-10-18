# -*- coding: utf-8 -*-
"""TDX 扩大探测：QUANTAXIS 全服务器列表，真实取数验活（quotes+bars 非空才算活）。"""
import io
import sys
import time
import traceback

LOG = []


def log(msg):
    s = str(msg)
    LOG.append(s)
    print(s, flush=True)


SERVERS = [
    ("119.147.212.81", 7709), ("112.74.214.43", 7727), ("221.231.141.60", 7709),
    ("101.227.73.20", 7709), ("101.227.77.254", 7709), ("14.215.128.18", 7709),
    ("59.173.18.140", 7709), ("60.28.23.80", 7709), ("119.97.185.59", 7709),
    ("180.153.18.170", 7709), ("218.6.170.47", 7709), ("123.125.108.14", 7709),
    ("180.153.18.172", 80), ("60.191.117.167", 7709), ("115.238.56.198", 7709),
    ("202.108.253.139", 80), ("115.238.90.165", 7709), ("60.12.136.250", 7709),
    ("218.75.126.9", 7709), ("121.36.225.169", 7709), ("123.60.70.228", 7709),
    ("124.70.133.119", 7709), ("119.147.164.60", 7709), ("119.147.171.206", 7709),
    ("119.29.51.30", 7709), ("121.14.104.70", 7709), ("121.14.110.194", 7709),
    ("180.153.39.51", 7709), ("218.108.47.69", 7709), ("218.9.148.108", 7709),
    ("221.194.181.176", 7709), ("61.135.142.73", 7709), ("61.152.249.56", 7709),
]


def main():
    from pytdx.hq import TdxHq_API

    alive = []
    for ip, port in SERVERS:
        api = TdxHq_API(raise_exception=True, heartbeat=False)
        try:
            api.connect(ip, port, time_out=1.5)
        except Exception:
            continue
        # 真实验活：quotes 和 bars 都要非空
        q_ok = b_ok = False
        q_price = None
        b_last = None
        try:
            q = api.get_security_quotes([(1, "600519")])
            if q:
                q_ok = True
                q_price = q[0].get("price")
        except Exception:
            pass
        try:
            bars = api.get_security_bars(9, 1, "600519", 0, 2)
            if bars:
                b_ok = True
                b_last = bars[-1].get("datetime")
        except Exception:
            pass
        try:
            api.disconnect()
        except Exception:
            pass
        status = "ALIVE" if (q_ok and b_ok) else "dead"
        log(f"  {ip}:{port} quotes={'OK:'+str(q_price) if q_ok else 'X'} "
            f"bars={'OK:'+str(b_last) if b_ok else 'X'} => {status}")
        if q_ok and b_ok:
            alive.append((ip, port))
        time.sleep(0.2)

    log(f"\n合计测试 {len(SERVERS)} 台, 全接口可用 {len(alive)} 台: {alive}")
    log("TDX SWEEP DONE")
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
    with open(r"d:\code\TradeSight\tdx_probe_sweep_out.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + f"\nEXIT={code}\n")
    sys.exit(code)
