# -*- coding: utf-8 -*-
"""离线验证 fetcher：导入、代理补丁、代码映射、周期映射、mock 模式跑通（不联网）。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.path.insert(0, r"d:\code\TradeSight")

import requests
print("[1] import data.fetcher ...", flush=True)
from data import fetcher
print("  import OK", flush=True)

# 代理补丁是否生效
s = requests.Session()
print(f"[2] proxy bypass: Session.trust_env={s.trust_env} (期望 False)", flush=True)

# 代码映射
cases = [("600519", "1.600519"), ("000001", "0.000001"), ("300750", "0.300750"),
         ("sh600519", "1.600519"), ("600519.SH", "1.600519"), ("000858", "0.000858")]
print("[3] _to_secid / _normalize_symbol:", flush=True)
for raw, expect in cases:
    got = fetcher._to_secid(raw)
    mark = "OK" if got == expect else "FAIL"
    print(f"  {mark} _to_secid({raw!r})={got} (期望 {expect}); normalize={fetcher._normalize_symbol(raw)!r}", flush=True)

# 周期映射
print(f"[4] _EM_KLT={fetcher._EM_KLT}", flush=True)
for p in ("daily", "weekly", "monthly", "5d", "yearly", "minute"):
    print(f"  {p} -> {fetcher._EM_KLT.get(p)}", flush=True)

# _num
print(f"[5] _num: _num('1329')={fetcher._num('1329')} _num(None)={fetcher._num(None)} _num('x')={fetcher._num('x')}", flush=True)

# 强制 mock 模式跑通公共函数（确认非联网路径不崩）
print("[6] mock 模式跑通公共函数:", flush=True)
fetcher.DATA_SOURCE = "mock"
q = fetcher.get_quote("600519")
print(f"  get_quote -> name={q.get('name')} current={q.get('current')} keys={sorted(q.keys())}", flush=True)
qs = fetcher.get_quotes(["600519", "000001"])
print(f"  get_quotes -> {len(qs)} 条", flush=True)
kl = fetcher.get_kline("600519", period="daily", days=30)
print(f"  get_kline -> shape={kl.shape} cols={list(kl.columns)}", flush=True)
mt = fetcher.get_minute("600519")
print(f"  get_minute -> shape={mt.shape} cols={list(mt.columns)} head_time={mt['time'].iloc[0] if len(mt) else None}", flush=True)
mg = fetcher.get_value_metrics("600519")
print(f"  get_value_metrics -> {mg}", flush=True)

print("\nOFFLINE VALIDATION DONE", flush=True)
