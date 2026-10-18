# -*- coding: utf-8 -*-
"""腾讯行情源（主实时源，feature.md 3.2/5.4）。

- 批量快照：http://qt.gtimg.cn/q=sh600519,sz000001...（~ 分隔，GBK）
  [1]=名称 [2]=代码 [3]=现价 [4]=昨收 [5]=今开 [6]=量(手)
  [30]=时间 [31]=涨跌 [32]=涨跌% [37]=额(万)
- 分时：https://ifzq.gtimg.cn/appstock/app/minute/query?code=sh600519
- 分钟K：https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m1,,320
"""
from __future__ import annotations

import json
import logging
import re
import time

import pandas as pd

from data.providers.base import (
    BaseProvider, QuoteSnapshot, normalize_symbol, to_tencent_sym,
)

log = logging.getLogger("tradesight.tencent")

try:
    import requests
    _HAS_REQUESTS = True
except Exception:  # pragma: no cover
    _HAS_REQUESTS = False

_QT_URL = "http://qt.gtimg.cn/q={codes}"
_MINUTE_URL = "https://ifzq.gtimg.cn/appstock/app/minute/query?code={sym}"
_MKLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={sym},{k},{a},{n}"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://gu.qq.com/",
}
_TIMEOUT = 5.0


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_qt_line(sym: str, payload: str) -> QuoteSnapshot | None:
    """解析单行 v_sh600519=...。单字段失败不丢整包。"""
    try:
        f = payload.split("~")
        if len(f) < 33:
            return None
        code = normalize_symbol(f[2] or sym[2:])
        current = _num(f[3]); pre = _num(f[4]); open_ = _num(f[5])
        vol = _num(f[6]) * 100.0
        amount = _num(f[37]) * 1e4 if len(f) > 37 and f[37] else 0.0
        change = _num(f[31]) if len(f) > 31 and f[31] else current - pre
        pct = _num(f[32]) if len(f) > 32 and f[32] else (change / pre * 100 if pre else 0.0)
        ts = f[30] if len(f) > 30 else ""
        return QuoteSnapshot(symbol=code, name=f[1] or code, current=current,
                             change=change, change_pct=pct, volume=vol, amount=amount,
                             open=open_, high=0.0, low=0.0, pre_close=pre,
                             market_cap=0.0, timestamp=ts, stale=False,
                             mocked=False, provider="tencent")
    except Exception:
        return None


class TencentProvider(BaseProvider):
    name = "tencent"

    def __init__(self, timeout: float = _TIMEOUT, batch_size: int = 80):
        self.timeout = timeout
        self.batch_size = batch_size
        self._session = None
        if _HAS_REQUESTS:
            s = requests.Session()
            s.trust_env = False
            s.headers.update(_HEADERS)
            self._session = s

    def _fetch_qt(self, syms: list[str]) -> str:
        url = _QT_URL.format(codes=",".join(syms))
        if self._session is None:
            raise RuntimeError("requests unavailable")
        r = self._session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.content.decode("gbk", errors="replace")

    def get_quotes(self, codes: list[str]) -> list[QuoteSnapshot]:
        out: list[QuoteSnapshot] = []
        syms = [to_tencent_sym(c) for c in codes if normalize_symbol(c)]
        for i in range(0, len(syms), self.batch_size):
            chunk = syms[i:i + self.batch_size]
            try:
                text = self._fetch_qt(chunk)
            except Exception as e:
                log.warning("tencent qt batch fail n=%d: %s: %s", len(chunk),
                            type(e).__name__, e)
                continue
            for m in re.finditer(r'v_(\w+)="([^"]*)"', text):
                snap = _parse_qt_line(m.group(1), m.group(2))
                if snap is not None:
                    out.append(snap)
            time.sleep(0.05)
        return out

    def _fetch_json(self, url: str) -> dict | list | None:
        if self._session is None:
            return None
        try:
            r = self._session.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("tencent json fail: %s: %s", type(e).__name__, e)
            return None

    def get_kline(self, code: str, klt: str, beg: str, end: str) -> pd.DataFrame | None:
        """分钟 K（m1/m5/m15/m30/m60）；日线走东财，此处仅分钟。"""
        m = {"1": "m1", "5": "m5", "15": "m15", "30": "m30", "60": "m60"}.get(klt)
        if m is None:
            return None
        sym = to_tencent_sym(code)
        data = self._fetch_json(_MKLINE_URL.format(sym=sym, k=m, a="", n=320))
        try:
            rows = (data or {}).get("data", {}).get(sym, {}).get(m, [])
        except AttributeError:
            return None
        if not rows:
            return None
        recs = []
        for r in rows:
            try:
                recs.append({"date": pd.Timestamp(r[0]), "open": float(r[1]),
                             "close": float(r[2]), "high": float(r[3]),
                             "low": float(r[4]), "volume": float(r[5]),
                             "amount": float(r[6]) if len(r) > 6 else 0.0})
            except (IndexError, ValueError):
                continue
        if not recs:
            return None
        df = pd.DataFrame(recs)
        cols = ["open", "high", "low", "close", "volume", "amount"]
        try:
            return df.set_index("date").sort_index()[cols]
        except Exception as e:
            log.warning("tencent kline fail %s: %s: %s", code, type(e).__name__, e)
            return None

    def get_minute(self, code: str) -> pd.DataFrame | None:
        sym = to_tencent_sym(code)
        data = self._fetch_json(_MINUTE_URL.format(sym=sym))
        try:
            qd = (data or {}).get("data", {}).get(sym, {}).get("qt", {})
            lines = qd.get(sym, [""])[1:] or []
            pre = float(qd.get(sym, ["0", "0"])[1] or 0)
        except (AttributeError, IndexError, ValueError):
            return None
        if not lines:
            return None
        recs = []
        for ln in lines:
            try:
                t, p, v = ln.split(" ")
                recs.append({"time": t, "price": float(p), "volume": float(v) * 100.0,
                             "amount": float(p) * float(v) * 100.0})
            except ValueError:
                continue
        if not recs:
            return None
        df = pd.DataFrame(recs)
        if pre:
            df.attrs["pre_close"] = pre
        return df[["time", "price", "volume", "amount"]]

    def health(self) -> bool:
        try:
            return bool(self.get_quotes(["600519"]))
        except Exception:
            return False
