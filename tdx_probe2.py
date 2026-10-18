# -*- coding:: utf-8 -*-
"""TDX 深度探针2：raise_exception=True，多服务器验证 quotes/kline/list 三个核心接口。"""
import io
import sys
import time
import traceback

LOG = []


def log(msg):
    s = str(msg)
    LOG.append(s)
    print(s, flush=True)


CANDIDATES = [
    ("115.238.90.165", 7709),
    ("119.147.171.206", 7709),
    ("114.80.80.222", 7711),
    ("221.194.181.176", 7709),
    ("106.120.74.86", 7711),
    ("218.108.50.178", 7709),
    ("119.29.51.30", 7709),
    ("113.105.73.88", 7709),
    ("180.153.18.170", 7709),
    ("117.184.140.156", 7709),
    ("101.227.73.20", 7709),
    ("115.238.56.198", 7709),
]


def probe_one(ip, port):
    from pytdx.hq import TdxHq_API
    api = TdxHq_API(raise_exception=True, heartbeat=False)
    line = [f"### {ip}:{port}"]
    try:
        api.connect(ip, port, time_out=2)
    except Exception as e:
        line.append(f"  connect FAIL: {type(e).__name__}: {e}")
        return None, "\n".join(line)

    # quotes
    t0 = time.time()
    try:
        q = api.get_security_quotes([(1, "600519")])
        if q:
            line.append(f"  quotes OK ({(time.time()-t0)*1000:.0f}ms): "
                        f"price={q[0]['price']} last_close={q[0]['last_close']} "
                        f"open={q[0]['open']} vol={q[0]['vol']} amount={q[0]['amount']:.0f} "
                        f"bid1={q[0]['bid1']} ask1={q[0]['ask1']}")
        else:
            line.append("  quotes OK but EMPTY list")
    except Exception as e:
        orig = getattr(e, "original_exception", None)
        line.append(f"  quotes FAIL: {type(e).__name__}: {e} | "
                    f"orig={type(orig).__name__ if orig else None}: {orig}")
        traceback.print_exc()

    # kline daily
    t0 = time.time()
    try:
        bars = api.get_security_bars(9, 1, "600519", 0, 5)
        if bars:
            line.append(f"  kline OK ({(time.time()-t0)*1000:.0f}ms): {len(bars)} bars, "
                        f"last={bars[-1]['datetime']} close={bars[-1]['close']}")
        else:
            line.append("  kline OK but EMPTY list")
    except Exception as e:
        orig = getattr(e, "original_exception", None)
        line.append(f"  kline FAIL: {type(e).__name__}: {e} | "
                    f"orig={type(orig).__name__ if orig else None}: {orig}")

    # SH list page0
    try:
        lst = api.get_security_list(1, 0)
        line.append(f"  SH list page0: {len(lst) if lst else 0} entries")
        if lst:
            hit = [x for x in lst if x["code"] == "600519"]
            line.append(f"    600519 in page0: {hit}")
    except Exception as e:
        line.append(f"  SH list FAIL: {type(e).__name__}: {e}")

    try:
        api.disconnect()
    except Exception:
        pass
    return api, "\n".join(line)


def main():
    working = None
    for ip, port in CANDIDATES:
        _, text = probe_one(ip, port)
        log(text)
        if "quotes OK (" in text and "kline OK (" in text:
            working = (ip, port)
            log(f">>> FULLY WORKING: {ip}:{port}")
            break
        time.sleep(0.3)

    if working:
        log("\n== 在可用服务器上做进阶验证 ==")
        from pytdx.hq import TdxHq_API
        api = TdxHq_API(raise_exception=True, heartbeat=True)
        api.connect(working[0], working[1], time_out=2)
        # 连续快照测试（模拟3秒轮询）
        for i in range(3):
            t0 = time.time()
            q = api.get_security_quotes([(1, "600519"), (0, "000001"), (0, "300750")])
            ms = (time.time() - t0) * 1000
            prices = [(x["code"], x["price"], x["last_close"]) for x in (q or [])]
            log(f"  poll#{i+1} {ms:.0f}ms {prices}")
            time.sleep(2)
        # 沪深列表分页
        for m in (0, 1):
            total = 0
            start = 0
            while True:
                lst = api.get_security_list(m, start)
                n = len(lst) if lst else 0
                total += n
                if n == 0:
                    break
                start += n
                if start > 40000:
                    break
            log(f"  market={m} 列表总数={total}")
        # K线分页拉日K 500根
        all_bars = []
        start = 0
        while len(all_bars) < 500:
            bars = api.get_security_bars(9, 1, "600519", start, 800)
            if not bars:
                break
            all_bars = bars + all_bars
            start += len(bars)
            if len(bars) < 800:
                break
        log(f"  日K累计={len(all_bars)}根, 最早={all_bars[0]['datetime'] if all_bars else None}, "
            f"最新={all_bars[-1]['datetime'] if all_bars else None}")
        # 1分钟K
        m1 = api.get_security_bars(8, 1, "600519", 0, 300)
        log(f"  1分钟K={len(m1) if m1 else 0}根, 最新={m1[-1]['datetime'] if m1 else None}")
        # 分时
        t = api.get_minute_time_data(1, "600519")
        log(f"  分时={len(t) if t else 0}条, 首={t[0] if t else None}, 尾={t[-1] if t else None}")
        api.disconnect()

    log("\nDEEP PROBE DONE")
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
    with open(r"d:\code\TradeSight\tdx_probe2_out.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + f"\nEXIT={code}\n")
    sys.exit(code)
