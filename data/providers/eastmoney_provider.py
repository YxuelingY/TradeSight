# -*- coding: utf-8 -*-
"""东财补充源：K 线/全市场/市值（feature.md §3.3）。

从旧 data/fetcher.py 搬运直连实现，保持 headers/ut/retry 语义。
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from data.providers.base import (
    BaseProvider, QuoteSnapshot, normalize_symbol, to_secid,
)

log = logging.getLogger("tradesight.eastmoney")

try:
    import requests
    _HAS_REQUESTS = True
except Exception:  # pragma: no cover
    _HAS_REQUESTS = False

_UT_KLINE = "7eea3edcaed734bea9cbfc24409ed989"
_UT_QUOTE = "bd1d9ddb04089700cf9c27f6f7426281"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://quote.eastmoney.com/",
}
_TIMEOUT = 8.0
_RETRY = 3
_QUOTE_FIELDS = ("f12,f13,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f15,f16,"
                 "f17,f18,f20,f21,f23,f24,f25,f26,f22")


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class EastmoneyProvider(BaseProvider):
    name = "eastmoney"

    def __init__(self, timeout: float = _TIMEOUT):
        self.timeout = timeout
        self._session = None
        if _HAS_REQUESTS:
            s = requests.Session()
            s.trust_env = False
            s.headers.update(_HEADERS)
            self._session = s

    def _get_json(self, url: str, params: dict | None = None) -> dict | None:
        if self._session is None:
            return None
        last = None
        for i in range(_RETRY):
            try:
                r = self._session.get(url, params=params, timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last = e
                time.sleep(0.5 * (i + 1))
        log.warning("eastmoney req fail: %s: %s", type(last).__name__, last)
        return None

    def _snapshot(self, code: str) -> QuoteSnapshot | None:
        code = normalize_symbol(code)
        data = self._get_json(
            "https://push2.eastmoney.com/api/qt/stock/get",
            {"invt": "2", "fltt": "2", "fields": _QUOTE_FIELDS,
             "secid": to_secid(code), "ut": _UT_QUOTE})
        if not data or not data.get("data"):
            return None
        d = data["data"]
        pre = _num(d.get("f18"))
        cur = _num(d.get("f2"))
        if pre != 0:
            chg, pct = cur - pre, (cur - pre) / pre * 100
        else:
            chg, pct = _num(d.get("f3")), _num(d.get("f4"))
        return QuoteSnapshot(symbol=code, name=d.get("f14") or code, current=cur,
                             change=chg, change_pct=pct,
                             volume=_num(d.get("f5")), amount=_num(d.get("f6")),
                             open=_num(d.get("f17")), high=_num(d.get("f15")),
                             low=_num(d.get("f16")), pre_close=pre,
                             market_cap=_num(d.get("f20")) + _num(d.get("f21")),
                             timestamp="", stale=False, mocked=False,
                             provider="eastmoney")

    def get_quotes(self, codes: list[str]) -> list[QuoteSnapshot]:
        out = []
        for c in codes:
            try:
                s = self._snapshot(c)
            except Exception as e:
                log.warning("eastmoney quote fail %s: %s", c, e)
                continue
            if s is not None:
                out.append(s)
        return out

    def get_kline(self, code: str, klt: str, beg: str, end: str) -> pd.DataFrame | None:
        code = normalize_symbol(code)
        data = self._get_json(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            {"fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
             "ut": _UT_KLINE, "klt": klt, "fqt": "0",
             "secid": to_secid(code), "beg": beg, "end": end, "_": str(int(time.time() * 1000))})
        try:
            klines = (data or {}).get("data", {}).get("klines") or []
        except AttributeError:
            return None
        if not klines:
            return None
        recs = []
        for item in klines:
            try:
                p = item.split(",")
                recs.append({"date": pd.Timestamp(p[0]), "open": float(p[1]),
                             "close": float(p[2]), "high": float(p[3]),
                             "low": float(p[4]), "volume": float(p[5]),
                             "amount": float(p[6]) if len(p) > 6 else 0.0})
            except (IndexError, ValueError):
                continue
        df = pd.DataFrame(recs)
        if df.empty:
            return None
        df.set_index("date", inplace=True)
        return df.sort_index()[["open", "high", "low", "close", "volume"]].astype(float)

    def get_minute(self, code: str) -> pd.DataFrame | None:
        return None  # 分时走腾讯

    def get_market_page(self, page: int = 1, page_size: int = 100) -> list[dict]:
        """全市场分页（东财 clist）：返回 [{symbol,name}]，失败返回 []。

        fs=m:0+m:1 覆盖沪深A股；fields=f12(代码),f14(名称)。
        """
        data = self._get_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            {"pn": str(page), "pz": str(page_size), "po": "1", "np": "1",
             "ut": _UT_QUOTE, "fltt": "2", "invt": "2",
             "fid": "f3", "fs": "m:0+m:1",
             "fields": "f12,f14"})
        try:
            diff = (data or {}).get("data", {}).get("diff") or []
        except AttributeError:
            return []
        out = []
        for d in diff:
            code, name = d.get("f12"), d.get("f14")
            if code and name:
                out.append({"symbol": normalize_symbol(code), "name": name})
        return out

    def get_all_codes(self, page_size: int = 100, max_pages: int = 60) -> list[dict]:
        """全A代码表（约5000只，~50页）。单页失败即停，避免半截表。"""
        all_rows: list[dict] = []
        for p in range(1, max_pages + 1):
            rows = self.get_market_page(p, page_size)
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < page_size:
                break
        return all_rows

    def health(self) -> bool:
        try:
            return bool(self._snapshot("600519"))
        except Exception:
            return False
