# -*- coding: utf-8 -*-
"""SQLite 持久化层，用于本地缓存股票数据，便于后期离线查询"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trade_sight.db")


def get_conn() -> sqlite3.Connection:
    """获取数据库连接，若表不存在则自动创建"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # 股票基本信息
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_info (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            market TEXT DEFAULT 'A',
            updated_at TEXT
        )
    """)

    # 实时行情快照（最新一条）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_quote (
            code TEXT PRIMARY KEY,
            name TEXT,
            current REAL,
            change REAL,
            change_pct REAL,
            volume REAL,
            amount REAL,
            open REAL,
            high REAL,
            low REAL,
            pre_close REAL,
            timestamp TEXT,
            updated_at TEXT
        )
    """)

    # K线数据（支持日/周/月/年/五日线；updated_at=本地写入时间，用于时差对账）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_kline (
            code TEXT,
            period TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            updated_at TEXT,
            PRIMARY KEY (code, period, date)
        )
    """)

    # 分时数据（仅存最近交易日）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_minute (
            code TEXT,
            time TEXT,
            price REAL,
            volume REAL,
            amount REAL,
            date TEXT,
            PRIMARY KEY (code, date, time)
        )
    """)

    # 价值投资指标
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_metrics (
            code TEXT PRIMARY KEY,
            pe REAL,
            pb REAL,
            roe REAL,
            dividend_yield REAL,
            total_market_cap REAL,
            circ_market_cap REAL,
            updated_at TEXT
        )
    """)

    # K线同步水位：每只每周期一条，记本地最新日期 + 对账时间，用于增量更新判定
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kline_sync (
            code TEXT,
            period TEXT,
            last_date TEXT,
            row_count INTEGER DEFAULT 0,
            updated_at TEXT,
            PRIMARY KEY (code, period)
        )
    """)
    # 存量库兼容：老 stock_kline 无 updated_at 列则补上（存上时间）
    try:
        _cols = [r[1] for r in cur.execute("PRAGMA table_info(stock_kline)").fetchall()]
        if "updated_at" not in _cols:
            cur.execute("ALTER TABLE stock_kline ADD COLUMN updated_at TEXT")
    except Exception:
        pass

    conn.commit()


# ---------------------------------------------------------------------------
# 股票基本信息
# ---------------------------------------------------------------------------
def upsert_stock_info(code: str, name: str, market: str = "A") -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO stock_info (code, name, market, updated_at) VALUES (?, ?, ?, ?)",
            (code, name, market, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()


def get_stock_name(code: str) -> Optional[str]:
    """从数据库查询股票名称，若不存在返回 None"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT name FROM stock_info WHERE code = ?", (code,)).fetchone()
        return row["name"] if row else None
    finally:
        conn.close()


def get_all_stock_info() -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT code, name, market FROM stock_info").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 行情快照
# ---------------------------------------------------------------------------
def upsert_quote(quote: Dict[str, Any]) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO stock_quote
            (code, name, current, change, change_pct, volume, amount, open, high, low, pre_close, timestamp, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quote.get("symbol"),
                quote.get("name"),
                quote.get("current"),
                quote.get("change"),
                quote.get("change_pct"),
                quote.get("volume"),
                quote.get("amount"),
                quote.get("open"),
                quote.get("high"),
                quote.get("low"),
                quote.get("pre_close"),
                quote.get("timestamp"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
        if quote.get("symbol") and quote.get("name"):
            upsert_stock_info(quote["symbol"], quote["name"])
    finally:
        conn.close()


def get_quote_from_db(code: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM stock_quote WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# K线数据
# ---------------------------------------------------------------------------
def upsert_klines(code: str, period: str, df: pd.DataFrame) -> None:
    """将 DataFrame 写入 stock_kline 表（代码, 周期, 日期为主键）"""
    if df is None or df.empty:
        return
    conn = get_conn()
    try:
        cur = conn.cursor()
        for date, row in df.iterrows():
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
            cur.execute(
                """
                INSERT OR REPLACE INTO stock_kline
                (code, period, date, open, high, low, close, volume, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    period,
                    date_str,
                    float(row.get("open", 0)),
                    float(row.get("high", 0)),
                    float(row.get("low", 0)),
                    float(row.get("close", 0)),
                    float(row.get("volume", 0)),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    try:
        touch_kline_sync(code, period)
    except Exception:
        pass


def get_klines_from_db(code: str, period: str, limit: int = 500) -> Optional[pd.DataFrame]:
    """从数据库读取K线，返回带日期索引的DataFrame"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT date, open, high, low, close, volume
            FROM stock_kline
            WHERE code = ? AND period = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (code, period, limit),
        ).fetchall()
        if not rows:
            return None
        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df = df.sort_index()
        return df[["open", "high", "low", "close", "volume"]].astype(float)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 分时数据
# ---------------------------------------------------------------------------
def upsert_minute(code: str, date_str: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    conn = get_conn()
    try:
        cur = conn.cursor()
        for _, row in df.iterrows():
            cur.execute(
                """
                INSERT OR REPLACE INTO stock_minute
                (code, date, time, price, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    date_str,
                    str(row.get("time", "")),
                    float(row.get("price", 0)),
                    float(row.get("volume", 0)),
                    float(row.get("amount", 0)),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_minute_from_db(code: str, date_str: str) -> Optional[pd.DataFrame]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT time, price, volume, amount
            FROM stock_minute
            WHERE code = ? AND date = ?
            ORDER BY time ASC
            """,
            (code, date_str),
        ).fetchall()
        if not rows:
            return None
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 价值投资指标
# ---------------------------------------------------------------------------
def upsert_metrics(code: str, metrics: Dict[str, Any]) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO stock_metrics
            (code, pe, pb, roe, dividend_yield, total_market_cap, circ_market_cap, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                metrics.get("pe"),
                metrics.get("pb"),
                metrics.get("roe"),
                metrics.get("dividend_yield"),
                metrics.get("total_market_cap"),
                metrics.get("circ_market_cap"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_metrics_from_db(code: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM stock_metrics WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# K线同步元数据（增量对账：本地只记“最新日期+对账时间”，远程只拉最近一天）
# ---------------------------------------------------------------------------
def get_kline_sync(code: str, period: str) -> Optional[Dict[str, Any]]:
    """返回 {last_date, row_count, updated_at}，无记录则 None。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT code, period, last_date, row_count, updated_at"
            " FROM kline_sync WHERE code = ? AND period = ?",
            (code, period),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_kline_last_date(code: str, period: str) -> Optional[str]:
    """本地该周期最新交易日（YYYY-MM-DD），优先读 kline_sync，无则回查 stock_kline。"""
    sync = get_kline_sync(code, period)
    if sync and sync.get("last_date"):
        return sync["last_date"]
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT MAX(date) AS m FROM stock_kline WHERE code = ? AND period = ?",
            (code, period),
        ).fetchone()
        if row and row["m"]:
            return str(row["m"])[:10]
        return None
    finally:
        conn.close()


def touch_kline_sync(code: str, period: str, last_date: str | None = None) -> None:
    """刷新同步水位：last_date 为空则用库内 MAX(date)。row_count 同步更新。"""
    conn = get_conn()
    try:
        if not last_date:
            row = conn.execute(
                "SELECT MAX(date) AS m, COUNT(*) AS c FROM stock_kline"
                " WHERE code = ? AND period = ?",
                (code, period),
            ).fetchone()
            last_date = str(row["m"])[:10] if row and row["m"] else None
            count = int(row["c"] or 0) if row else 0
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM stock_kline WHERE code = ? AND period = ?",
                (code, period),
            ).fetchone()
            count = int(row["c"] or 0) if row else 0
        conn.execute(
            "INSERT OR REPLACE INTO kline_sync (code, period, last_date, row_count, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (code, period, last_date,
             count, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()


def get_stale_kline_codes(period: str, before_date: str, limit: int = 500) -> List[Dict[str, Any]]:
    """查出 last_date 早于 before_date（有时差）或从未同步过的代码，用于批量补齐。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT si.code AS code, si.name AS name, ks.last_date AS last_date
            FROM stock_info si LEFT JOIN kline_sync ks
              ON ks.code = si.code AND ks.period = ?
            WHERE ks.last_date IS NULL OR ks.last_date < ?
            ORDER BY si.code ASC
            LIMIT ?
            """,
            (period, before_date, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()