# -*- coding: utf-8 -*-
"""验证：本地日线时间戳 + 增量同步（只远程拉缺口）。
用法：python tools/verify_kline_sync.py [CODE]"""
import sys
sys.path.insert(0, ".")
from data import kline_sync
from data.database import get_conn, get_klines_from_db

code = sys.argv[1] if len(sys.argv) > 1 else "600519"
print("status-before:", kline_sync.get_sync_status())
res = kline_sync.sync_one(code)
print("sync_one:", res)
df = get_klines_from_db(code, "daily", limit=5)
print(df.tail(3) if df is not None else "EMPTY")
conn = get_conn()
try:
    rows = conn.execute("SELECT date, close, updated_at FROM stock_kline WHERE code=? AND period='daily' ORDER BY date DESC LIMIT 3", (code,)).fetchall()
    for r in rows:
        print("row:", dict(r))
    sync = conn.execute("SELECT * FROM kline_sync WHERE code=? AND period='daily'", (code,)).fetchone()
    print("sync:", dict(sync) if sync else None)
finally:
    conn.close()
print("status-after:", kline_sync.get_sync_status())
