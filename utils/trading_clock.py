# -*- coding: utf-8 -*-
"""交易时钟：盘中高频 / 盘后低频 / 闭市暂停（feature.md §4.3.5）。

时段 09:15-11:30 / 13:00-15:00（含集合竞价），均为北京时间。
"""
from __future__ import annotations

from datetime import datetime, time as dtime

try:
    from zoneinfo import ZoneInfo
    _BJ = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    _BJ = None

_MORNING = (dtime(9, 15), dtime(11, 30))
_AFTERNOON = (dtime(13, 0), dtime(15, 0))


def now_bj() -> datetime:
    now = datetime.now(_BJ) if _BJ else datetime.now()
    return now.replace(tzinfo=None)


def is_trading_now(now: datetime | None = None) -> bool:
    if now is None:
        now = now_bj()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (_MORNING[0] <= t <= _MORNING[1]) or (_AFTERNOON[0] <= t <= _AFTERNOON[1])


def next_interval_ms(now: datetime | None = None, in_ms: int = 3000,
                     off_ms: int = 60000) -> int | None:
    """盘中返回 in_ms；盘后（交易日非交易时段）返回 off_ms；周末返回 None（暂停）。"""
    if now is None:
        now = now_bj()
    if now.weekday() >= 5:
        return None
    return in_ms if is_trading_now(now) else off_ms
