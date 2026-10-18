# -*- coding: utf-8 -*-
"""全市场日线本地化增量同步（data/database.py 的配套逻辑）。

策略（用户要求）：
1. 本地存 A 股所有股票的单日价格（stock_kline, period='daily'）。
2. 每次只远程获取最近一天的价格（beg=本地最新日期, end=今天）。
3. 每行都存 updated_at 时间；kline_sync 表记每只的水位 last_date。
4. 当发现数据库数据有时差（last_date < 最新交易日）则更新数据库。

用法：
    from data import kline_sync
    kline_sync.sync_one("600519")          # 单只增量同步
    kline_sync.sync_all_stocks(limit=...)   # 全市场批量同步（断点续传）
    kline_sync.get_sync_status()            # 同步进度总览
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd

from data.providers.base import normalize_symbol
from data.database import (
    get_conn,
    get_all_stock_info,
    upsert_klines,
    get_klines_from_db,
    get_kline_last_date,
    get_kline_sync,
    touch_kline_sync,
    get_stale_kline_codes,
)

log = logging.getLogger("tradesight.kline_sync")


def latest_trading_day(today: datetime | None = None) -> str:
    """最新交易日（YYYY-MM-DD）：周末回退到周五，不含节假日（节假日靠远端空返回兜底）。"""
    d = today or datetime.now()
    while d.weekday() >= 5:  # 周六/周日回退
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _next_day(date_str: str) -> str:
    d = datetime.strptime(date_str[:10], "%Y-%m-%d") + timedelta(days=1)
    return d.strftime("%Y%m%d")


def _today_compact() -> str:
    return datetime.now().strftime("%Y%m%d")


def sync_one(code: str, period: str = "daily") -> dict:
    """单只增量同步：只拉本地缺口（last_date+1 -> 今天），返回同步结果摘要。

    返回 {"code","ok","last_date","new_rows","skipped"}。
    """
    from data.providers.manager import QuoteManager as _QM

    code = normalize_symbol(code)
    last = get_kline_last_date(code, period)
    today = latest_trading_day()

    # 无时差：本地已是最新，直接读库返回
    if last and last >= today:
        df = get_klines_from_db(code, period, limit=500)
        return {"code": code, "ok": True, "last_date": last,
                "new_rows": 0, "skipped": True,
                "rows": 0 if df is None else len(df)}

    beg = _next_day(last) if last else "20150101"
    mgr = _QM.instance()
    try:
        df = mgr.get_kline(code, "101" if period == "daily" else period,
                           beg, _today_compact())
    except Exception as e:  # noqa: BLE001
        log.warning("sync_one %s fail: %s", code, e)
        return {"code": code, "ok": False, "error": str(e),
                "last_date": last, "new_rows": 0, "skipped": False}
    if df is None or df.empty:
        # 远端无新数据（如节假日）：仍刷新水位时间，避免反复拉取
        try:
            touch_kline_sync(code, period, last)
        except Exception:
            pass
        return {"code": code, "ok": True, "last_date": last,
                "new_rows": 0, "skipped": True}
    upsert_klines(code, period, df)
    new_last = get_kline_last_date(code, period)
    return {"code": code, "ok": True, "last_date": new_last,
            "new_rows": len(df), "skipped": False}


def sync_batch(codes: list[str], period: str = "daily",
               pause: float = 0.15) -> dict:
    """批量增量同步（只补有时差的），返回 {ok, fail, skipped, details}。"""
    ok = fail = skipped = 0
    details = []
    for c in codes:
        r = sync_one(c, period)
        details.append(r)
        if not r.get("ok"):
            fail += 1
        elif r.get("skipped"):
            skipped += 1
        else:
            ok += 1
        if pause:
            time.sleep(pause)
    return {"ok": ok, "fail": fail, "skipped": skipped, "details": details}


def sync_all_stocks(period: str = "daily", batch: int = 200,
                    pause: float = 0.15, limit: int | None = None) -> dict:
    """全市场同步：查 stock_info 全量代码，只对 last_date < 最新交易日的拉取。

    断点续传：每批提交一次水位，中断后重跑自动跳过已同步的。
    limit 供调试（只同步前 N 只）。
    """
    infos = get_all_stock_info()
    if limit:
        infos = infos[:limit]
    today = latest_trading_day()
    stale = get_stale_kline_codes(period, today, limit=len(infos))
    stale_set = {r["code"] for r in stale}
    # 保持 stock_info 顺序，stale 优先在前
    ordered = [r["code"] for r in stale] + \
        [i["code"] for i in infos if i["code"] not in stale_set]
    if limit:
        ordered = ordered[:limit]
    log.info("sync_all: total=%d stale=%d today=%s", len(ordered), len(stale), today)
    total = {"ok": 0, "fail": 0, "skipped": 0}
    for i in range(0, len(ordered), batch):
        chunk = ordered[i:i + batch]
        r = sync_batch(chunk, period, pause=pause)
        total["ok"] += r["ok"]
        total["fail"] += r["fail"]
        total["skipped"] += r["skipped"]
        log.info("sync_all progress %d/%d ok=%d fail=%d skip=%d",
                 min(i + batch, len(ordered)), len(ordered),
                 total["ok"], total["fail"], total["skipped"])
    total["total"] = len(ordered)
    total["today"] = today
    return total


def get_sync_status(period: str = "daily") -> dict:
    """同步进度总览：总数/已同步到最新/有时差/从未同步。"""
    today = latest_trading_day()
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM stock_info").fetchone()["c"]
        fresh = conn.execute(
            "SELECT COUNT(*) AS c FROM kline_sync WHERE period = ? AND last_date >= ?",
            (period, today)).fetchone()["c"]
        stale = conn.execute(
            "SELECT COUNT(*) AS c FROM kline_sync WHERE period = ? AND last_date < ?",
            (period, today)).fetchone()["c"]
    finally:
        conn.close()
    never = max(0, (total or 0) - (fresh or 0) - (stale or 0))
    return {"period": period, "today": today, "total": total or 0,
            "fresh": fresh or 0, "stale": stale or 0, "never": never}
