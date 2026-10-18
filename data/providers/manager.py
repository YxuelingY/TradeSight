# -*- coding: utf-8 -*-
"""QuoteManager：多源调度 + 熔断 + 快照缓存（feature.md §4.3/§7.5）。"""
from __future__ import annotations
import logging, time
import pandas as pd
from data.providers.base import BaseProvider, QuoteSnapshot, normalize_symbol, is_valid_tick
log = logging.getLogger("tradesight.manager")
_SNAP: dict = {}
_TTL = 3.0
_FAIL: dict = {}
_BAN_UNTIL: dict = {}
_BAN_AFTER = 3
_BAN_SECS = 300
class QuoteManager:
    _inst = None
    def __init__(self):
        self.providers: dict[str, BaseProvider] = {}
        try:
            from data.providers.tencent_provider import TencentProvider
            self.providers["tencent"] = TencentProvider()
        except Exception as e:
            log.warning("tencent init fail: %s", e)
        try:
            from data.providers.eastmoney_provider import EastmoneyProvider
            self.providers["eastmoney"] = EastmoneyProvider()
        except Exception as e:
            log.warning("eastmoney init fail: %s", e)
    @classmethod
    def instance(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst
    def _avail(self, name: str) -> bool:
        if name not in self.providers:
            return False
        if time.time() < _BAN_UNTIL.get(name, 0):
            return False
        return True
    def _ok(self, name: str):
        _FAIL[name] = 0
    def _fail(self, name: str, e: Exception):
        n = _FAIL.get(name, 0) + 1
        _FAIL[name] = n
        log.warning("provider %s fail x%d: %s: %s", name, n, type(e).__name__, e)
        if n >= _BAN_AFTER:
            _BAN_UNTIL[name] = time.time() + _BAN_SECS
            log.warning("provider %s banned %ss", name, _BAN_SECS)
    def get_quotes(self, codes: list[str]) -> tuple[list[QuoteSnapshot], str]:
        """返回 (快照列表, 实际数据源名)。无效tick被过滤，调用方用DB兜底。"""
        codes = [normalize_symbol(c) for c in codes if normalize_symbol(c)]
        if not codes:
            return [], "none"
        now = time.time()
        fresh = [c for c in codes if not (c in _SNAP and now - _SNAP[c][0] < _TTL)]
        for name in ("tencent", "eastmoney"):
            if not self._avail(name) or not fresh:
                continue
            try:
                rows = self.providers[name].get_quotes(fresh) or []
                valid = [r for r in rows if is_valid_tick(r.get("current", 0), r.get("volume", 0), r.get("pre_close", 0))]
                for r in valid:
                    _SNAP[r["symbol"]] = (now, r)
                fresh = [c for c in fresh if c not in {r["symbol"] for r in valid}]
                self._ok(name)
                if not fresh:
                    break
            except Exception as e:
                self._fail(name, e)
        out = [ _SNAP[c][1] for c in codes if c in _SNAP and now - _SNAP[c][0] < 60 ]
        src = "tencent" if out and out[0].get("provider") == "tencent" else "mixed"
        return out, src
    def get_kline(self, code: str, klt: str, beg: str, end: str) -> pd.DataFrame | None:
        code = normalize_symbol(code)
        order = ("tencent", "eastmoney") if klt in ("1", "5", "15", "30", "60") else ("eastmoney", "tencent")
        for name in order:
            if not self._avail(name):
                continue
            try:
                df = self.providers[name].get_kline(code, klt, beg, end)
                self._ok(name)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                self._fail(name, e)
        return None
    def get_minute(self, code: str) -> pd.DataFrame | None:
        for name in ("tencent", "eastmoney"):
            if not self._avail(name):
                continue
            try:
                df = self.providers[name].get_minute(normalize_symbol(code))
                self._ok(name)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                self._fail(name, e)
        return None
