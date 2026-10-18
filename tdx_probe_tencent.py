# -*- coding: utf-8 -*-
"""腾讯行情接口探针：批量快照 qt.gtimg.cn + 分钟K线 ifzq.gtimg.cn + 分时，本机实测可用性。"""
import io
import json
import re
import sys
import time
import traceback
import urllib.request

LOG = []


def log(msg):
    s = str(msg)
    LOG.append(s)
    print(s, flush=True)


HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://gu.qq.com/",
}


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main():
    log("== [1] qt.gtimg.cn 批量实时行情（一次6只）==")
    t0 = time.time()
    try:
        raw = fetch("http://qt.gtimg.cn/q=sh600519,sz000001,sz300750,sh000001,sz000858,sh601318")
        ms = (time.time() - t0) * 1000
        text = raw.decode("gbk", errors="replace")
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r'v_(\w+)="(.*)"', line)
            if not m:
                continue
            code = m.group(1)
            f = m.group(2).split("~")
            # 字段: 1名称 2代码 3现价 4昨收 5今开 6成交量(手) 37成交额(万) 32涨跌 33涨跌%
            log(f"  {code}: name={f[1]} price={f[3]} pre={f[4]} open={f[5]} "
                f"vol(手)={f[6]} amount(万)={f[37] if len(f)>37 else '?'} "
                f"change={f[31] if len(f)>31 else '?'} pct={f[32] if len(f)>32 else '?'} "
                f"fields={len(f)}")
        log(f"  耗时 {ms:.0f}ms, 原始字节 {len(raw)}")
    except Exception as e:
        log(f"  FAIL {type(e).__name__}: {e}")
        traceback.print_exc()

    log("\n== [2] ifzq.gtimg.cn 分钟K线（日K dq + 5分钟 m5 + 1分钟 m1）==")
    for tag, param in [("日K", "sh600519,,,320"), ("5分钟", "sh600519,m5,,320"),
                       ("1分钟", "sh600519,m1,,320")]:
        t0 = time.time()
        try:
            raw = fetch(f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={param}")
            ms = (time.time() - t0) * 1000
            data = json.loads(raw.decode("utf-8", errors="replace"))
            code = param.split(",")[0]
            node = data.get("data", {}).get(code, {})
            key = [k for k in node.keys() if k.startswith(("qfq", "day", "m"))]
            bars = None
            for k in key:
                if isinstance(node[k], dict) and "data" in node[k]:
                    bars = node[k]["data"]
                    used = k
                    break
            if bars:
                log(f"  {tag} OK ({ms:.0f}ms): key={used} {len(bars)}根")
                log(f"    首根={bars[0]}")
                log(f"    末根={bars[-1]}")
            else:
                log(f"  {tag} FAIL keys={list(node.keys())} raw={raw[:200]}")
        except Exception as e:
            log(f"  {tag} FAIL {type(e).__name__}: {e}")

    log("\n== [3] ifzq 分时（分钟线 m1 语义的当日数据 vs trends）==")
    try:
        # 腾讯分时接口
        raw = fetch("https://ifzq.gtimg.cn/appstock/app/minute/query?code=sh600519")
        data = json.loads(raw.decode("utf-8", errors="replace"))
        node = data.get("data", {}).get("sh600519", {})
        md = node.get("data", {})
        mins = md.get("data", []) if isinstance(md, dict) else []
        log(f"  分时 OK: date={md.get('date') if isinstance(md, dict) else '?'} {len(mins)}条")
        if mins:
            log(f"    首={mins[0]} 末={mins[-1]}")
    except Exception as e:
        log(f"  FAIL {type(e).__name__}: {e}")

    log("\n== [4] 二次批量验证限流（再发2次，间隔1秒）==")
    for i in range(2):
        try:
            t0 = time.time()
            raw = fetch("http://qt.gtimg.cn/q=sh600519,sz000001")
            log(f"  #{i+1} OK {(time.time()-t0)*1000:.0f}ms {len(raw)}字节")
        except Exception as e:
            log(f"  #{i+1} FAIL {type(e).__name__}: {e}")
        time.sleep(1)

    log("\nTENCENT PROBE DONE")
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
    with open(r"d:\code\TradeSight\tdx_probe_tencent_out.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + f"\nEXIT={code}\n")
    sys.exit(code)
