# -*- coding: utf-8 -*-
"""通用工具函数"""

from typing import Optional


def fmt_price(value: Optional[float]) -> str:
    """格式化价格"""
    if value is None:
        return "-"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "-"


def fmt_pct(value: Optional[float]) -> str:
    """格式化百分比"""
    if value is None:
        return "-"
    try:
        v = float(value)
        return f"{v:+.2f}%"
    except (TypeError, ValueError):
        return "-"


def fmt_volume(value: Optional[float]) -> str:
    """格式化成交量/成交额为 万/亿"""
    if value is None:
        return "-"
    try:
        v = float(value)
        if abs(v) >= 1e8:
            return f"{v / 1e8:.2f}亿"
        if abs(v) >= 1e4:
            return f"{v / 1e4:.2f}万"
        return f"{v:,.0f}"
    except (TypeError, ValueError):
        return "-"


def fmt_market_cap(value: Optional[float]) -> str:
    """格式化总市值（亿元）"""
    if value is None:
        return "-"
    try:
        v = float(value)
        if v >= 1e4:
            return f"{v / 1e4:.2f}万亿"
        return f"{v:,.2f}亿元"
    except (TypeError, ValueError):
        return "-"