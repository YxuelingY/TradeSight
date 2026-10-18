# -*- coding: utf-8 -*-
"""清理 trade_sight.db 中的模拟/陈旧缓存数据，强制应用下次加载时抓取真实数据。

保留 stock_info（真实股票名称），清空行情/K线/分时/指标缓存表。
"""
import io, sys, sqlite3, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

DB = os.path.join(r"d:\code\TradeSight", "trade_sight.db")
print(f"DB = {DB}  exists={os.path.exists(DB)}", flush=True)

conn = sqlite3.connect(DB)
cur = conn.cursor()

tables = ["stock_quote", "stock_kline", "stock_minute", "stock_metrics"]
print("--- 清理前行数 ---", flush=True)
for t in tables:
    try:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n}", flush=True)
    except Exception as e:
        print(f"  {t}: (表不存在) {e}", flush=True)

# 抽样：600519 现有 K线价格区间（确认是模拟数据 base±5%）
try:
    row = cur.execute("SELECT MIN(close), MAX(close), COUNT(*) FROM stock_kline WHERE code='600519' AND period='daily'").fetchone()
    print(f"  [sample] 600519 daily close min/max/count = {row}", flush=True)
except Exception:
    pass

print("--- 执行清理 ---", flush=True)
for t in tables:
    try:
        cur.execute(f"DELETE FROM {t}")
        print(f"  DELETE {t}: {cur.rowcount} rows", flush=True)
    except Exception as e:
        print(f"  DELETE {t} 失败: {e}", flush=True)
conn.commit()

print("--- 清理后行数 ---", flush=True)
for t in tables:
    n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n}", flush=True)

# stock_info 保留（真实名称）
n_info = cur.execute("SELECT COUNT(*) FROM stock_info").fetchone()[0]
print(f"  stock_info(保留): {n_info}", flush=True)

conn.close()
print("\nCLEANUP DONE", flush=True)
