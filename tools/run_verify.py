# -*- coding: utf-8 -*-
"""verify runner that writes result to file (terminal output capture broken)."""
import sys, traceback
sys.path.insert(0, ".")
out = []
try:
    from data import kline_sync
    from data.database import get_conn, get_klines_from_db
    code = "600519"
    out.append("status-before: %s" % (kline_sync.get_sync_status(),))
    res = kline_sync.sync_one(code)
    out.append("sync_one: %s" % (res,))
    df = get_klines_from_db(code, "daily", limit=5)
    out.append("df_tail: %s" % (df.tail(3).to_dict() if df is not None else "EMPTY",))
    conn = get_conn()
    try:
        rows = conn.execute("SELECT date, close, updated_at FROM stock_kline WHERE code=? AND period='daily' ORDER BY date DESC LIMIT 3", (code,)).fetchall()
        for r in rows:
            out.append("row: %s" % (dict(r),))
        sync = conn.execute("SELECT * FROM kline_sync WHERE code=? AND period='daily'", (code,)).fetchone()
        out.append("sync: %s" % (dict(sync) if sync else None,))
    finally:
        conn.close()
    out.append("status-after: %s" % (kline_sync.get_sync_status(),))
except Exception:
    out.append(traceback.format_exc())
open("tools/verify_out.txt", "w", encoding="utf-8").write("\n".join(out))
print("wrote tools/verify_out.txt")
