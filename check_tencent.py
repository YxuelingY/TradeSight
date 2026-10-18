# -*- coding: utf-8 -*-
"""腾讯 provider 单步诊断。"""
import traceback
from data.providers.tencent_provider import TencentProvider

p = TencentProvider()
try:
    qs = p.get_quotes(["600519", "000001", "300750"])
    print("QUOTES", type(qs), None if qs is None else len(qs))
    if qs:
        for q in qs:
            print(" ", q.get("symbol"), q.get("name"), q.get("current"), q.get("provider"))
except Exception:
    traceback.print_exc()
try:
    m = p.get_minute("600519")
    print("MINUTE", None if m is None else len(m))
    if m is not None:
        print(m.head(2).to_string())
        print(m.tail(1).to_string())
except Exception:
    traceback.print_exc()
