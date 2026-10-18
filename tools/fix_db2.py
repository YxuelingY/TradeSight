# -*- coding: utf-8 -*-
"""patch upsert_klines + touch + fetch helper, tolerant to CRLF."""
import pathlib, re
p = pathlib.Path(__file__).resolve().parents[1] / "data" / "database.py"
t = p.read_text(encoding="utf-8")
orig = t
# 1. upsert values add updated_at (only if not already)
if "close, volume, updated_at" not in t:
    t = t.replace("close, volume)\n                VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  "close, volume, updated_at)\n                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
    t = t.replace('float(row.get("volume", 0)),\n                ),',
                  'float(row.get("volume", 0)),\n                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),\n                ),')
# 2. after commit+close add touch (only once)
if "touch_kline_sync(code, period)" not in t:
    t = t.replace("        conn.commit()\n    finally:\n        conn.close()\n\n\ndef get_klines_from_db",
                  "        conn.commit()\n    finally:\n        conn.close()\n    try:\n        touch_kline_sync(code, period)\n    except Exception:\n        pass\n\n\ndef get_klines_from_db")
if t != orig:
    p.write_text(t, encoding="utf-8")
    print("patched database.py")
else:
    print("no change needed")
