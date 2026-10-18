# -*- coding: utf-8 -*-
"""Provider 基类与通用工具（feature.md §5.2/§5.3）。

所有行情源实现 BaseProvider；Facade 只依赖本模块定义的契约。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict

import pandas as pd


class QuoteSnapshot(TypedDict, total=False):
    symbol: str
    name: str
    current: float
    change: float
    change_pct: float
    volume: float
    amount: float
    open: float
    high: float
    low: float
    pre_close: float
    market_cap: float
    timestamp: str
    stale: bool
    mocked: bool
    provider: str


class KlineRequest(TypedDict, total=False):
    code: str
    klt: str
    beg: str
    end: str


class BaseProvider(ABC):
    """行情源抽象。实现者保证：异常只抛、不吞；空数据返回 [] / None。"""

    name: str = "base"

    @abstractmethod
    def get_quotes(self, codes: list[str]) -> list[QuoteSnapshot]:
        """批量快照，codes 为纯 6 位代码。"""
        raise NotImplementedError

    @abstractmethod
    def get_kline(self, code: str, klt: str, beg: str, end: str) -> pd.DataFrame | None:
        """K 线，返回 index=date cols=[open,high,low,close,volume,amount?] 或 None。"""
        raise NotImplementedError

    @abstractmethod
    def get_minute(self, code: str) -> pd.DataFrame | None:
        """当日分时，cols=[time,price,volume,amount] 或 None。"""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 代码格式工具
# ---------------------------------------------------------------------------

def normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    for prefix in ("SH", "SZ", "BJ", "HK"):
        if s.startswith(prefix) and s[len(prefix):].isdigit():
            s = s[len(prefix):]
            break
    for suffix in (".SH", ".SZ", ".BJ", ".HK", ".SS"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    return s


def to_secid(code: str) -> str:
    code = normalize_symbol(code)
    market = "1" if code[:1] == "6" else "0"
    return f"{market}.{code}"


def to_tencent_sym(code: str) -> str:
    code = normalize_symbol(code)
    # 注意：000001 同时对应 sz000001(平安银行) 与 sh000001(上证指数)；
    # 默认按股票处理 -> sz000001，指数请直接传带前缀的 sh000001（上层保留前缀时）。
    # 这里 normalize 已去前缀，统一按股票映射。
    prefix = "sh" if code[:1] in ("6", "9") or code[:2] == "11" else "sz"
    return prefix + code


def is_valid_tick(current: float, volume: float, pre_close: float) -> bool:
    """休市无效 tick 判定：现价/量/昨收全 0 则无效。"""
    try:
        return not (float(current or 0) == 0 and float(volume or 0) == 0
                    and float(pre_close or 0) == 0)
    except (TypeError, ValueError):
        return False
