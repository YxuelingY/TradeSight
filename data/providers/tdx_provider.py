# -*- coding: utf-8 -*-
"""TDX 插槽（默认禁用，feature.md §3.1）。

pytdx 1.72 协议已失效，仅保留 get_security_list 能力 + GBK 截断容错，
quotes/kline 主动 NotSupported，避免静默空数据污染上层。
"""
from __future__ import annotations

import logging

import pandas as pd

from data.providers.base import BaseProvider, QuoteSnapshot

log = logging.getLogger("tradesight.tdx")


class TdxProvider(BaseProvider):
    name = "tdx"
    enabled = False

    def __init__(self, servers=None):
        self.servers = servers or []
        self._api = None
        try:
            from pytdx.hq import TdxHq_API  # type: ignore
            self._api_cls = TdxHq_API
        except Exception as e:
            self._api_cls = None
            log.warning("pytdx unavailable, tdx disabled: %s", e)

    def health(self) -> bool:
        return False

    def get_quotes(self, codes: list[str]) -> list[QuoteSnapshot]:
        raise NotImplementedError("TDX quotes deprecated (2026-07 protocol change)")

    def get_kline(self, code: str, klt: str, beg: str, end: str) -> pd.DataFrame | None:
        raise NotImplementedError("TDX kline deprecated")

    def get_minute(self, code: str) -> pd.DataFrame | None:
        raise NotImplementedError("TDX minute deprecated")

    def get_security_list(self, market: int = 0, page: int = 0):
        """仅调试用：SZ list 可用，SH 需 GBK 截断容错。"""
        if self._api_cls is None or not self.servers:
            return []
        api = self._api_cls()
        for host, port in self.servers:
            try:
                if not api.connect(host, port):
                    continue
                rows = api.get_security_list(market, page)
                api.disconnect()
                return rows or []
            except UnicodeDecodeError:
                try:
                    api.disconnect()
                except Exception:
                    pass
                continue
            except Exception as e:
                log.warning("tdx list fail %s:%s %s", host, port, e)
                try:
                    api.disconnect()
                except Exception:
                    pass
                continue
        return []
