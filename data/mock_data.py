# -*- coding: utf-8 -*-
"""离线模拟数据，用于无网络或 akshare 不可用时的兜底方案"""

import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# 预设股票池（代码, 名称, 基础价格）—— 常见A股，用于离线演示
MOCK_STOCKS = [
    ("000001", "平安银行", 12.50),
    ("000002", "万科A", 7.80),
    ("000063", "中兴通讯", 24.50),
    ("000333", "美的集团", 58.00),
    ("000651", "格力电器", 45.00),
    ("000858", "五粮液", 158.00),
    ("002415", "海康威视", 32.00),
    ("002594", "比亚迪", 220.00),
    ("002714", "牧原股份", 28.00),
    ("300015", "爱尔眼科", 18.50),
    ("300059", "东方财富", 15.20),
    ("300750", "宁德时代", 215.00),
    ("300760", "迈瑞医疗", 280.00),
    ("600000", "浦发银行", 6.90),
    ("600009", "上海医药", 22.00),
    ("600036", "招商银行", 38.50),
    ("600048", "保利发展", 8.50),
    ("600276", "恒瑞医药", 42.00),
    ("600309", "万华化学", 75.00),
    ("600519", "贵州茅台", 1650.00),
    ("600887", "伊利股份", 42.00),
    ("600900", "长江电力", 18.00),
    ("601012", "隆基股份", 35.00),
    ("601318", "中国平安", 42.50),
    ("601398", "工商银行", 4.80),
    ("601668", "中国建筑", 5.80),
    ("601888", "中国中旅", 8.20),
    ("603288", "海天味业", 85.00),
]

# 价值投资指标模板（PE, PB, ROE, 股息率, 总市值亿元）
MOCK_METRICS = {
    "000001": {"pe": 6.5, "pb": 0.8, "roe": 12.5, "dividend_yield": 3.2, "total_market_cap": 2800, "circ_market_cap": 2500},
    "000002": {"pe": 28.0, "pb": 1.2, "roe": 4.5, "dividend_yield": 2.1, "total_market_cap": 1500, "circ_market_cap": 1400},
    "000063": {"pe": 25.0, "pb": 2.5, "roe": 10.0, "dividend_yield": 1.5, "total_market_cap": 2200, "circ_market_cap": 2100},
    "000333": {"pe": 16.0, "pb": 3.2, "roe": 20.0, "dividend_yield": 1.8, "total_market_cap": 3600, "circ_market_cap": 3400},
    "000651": {"pe": 14.0, "pb": 2.0, "roe": 15.0, "dividend_yield": 2.0, "total_market_cap": 1300, "circ_market_cap": 1200},
    "000858": {"pe": 20.0, "pb": 5.0, "roe": 25.0, "dividend_yield": 1.0, "total_market_cap": 98000, "circ_market_cap": 95000},
    "002415": {"pe": 35.0, "pb": 5.0, "roe": 18.0, "dividend_yield": 0.5, "total_market_cap": 4000, "circ_market_cap": 3800},
    "002594": {"pe": 45.0, "pb": 8.0, "roe": 18.0, "dividend_yield": 0.5, "total_market_cap": 89000, "circ_market_cap": 88000},
    "002714": {"pe": 18.0, "pb": 3.0, "roe": 16.0, "dividend_yield": 1.0, "total_market_cap": 2000, "circ_market_cap": 1900},
    "300015": {"pe": 50.0, "pb": 6.0, "roe": 20.0, "dividend_yield": 0.5, "total_market_cap": 2800, "circ_market_cap": 2700},
    "300059": {"pe": 40.0, "pb": 5.0, "roe": 12.0, "dividend_yield": 0.2, "total_market_cap": 3500, "circ_market_cap": 3400},
    "300750": {"pe": 45.0, "pb": 8.0, "roe": 18.0, "dividend_yield": 0.5, "total_market_cap": 89000, "circ_market_cap": 88000},
    "300760": {"pe": 55.0, "pb": 10.0, "roe": 25.0, "dividend_yield": 0.3, "total_market_cap": 4500, "circ_market_cap": 4400},
    "600000": {"pe": 5.2, "pb": 0.6, "roe": 9.8, "dividend_yield": 4.5, "total_market_cap": 2200, "circ_market_cap": 2100},
    "600009": {"pe": 15.0, "pb": 1.5, "roe": 8.0, "dividend_yield": 2.0, "total_market_cap": 1800, "circ_market_cap": 1700},
    "600036": {"pe": 7.0, "pb": 0.9, "roe": 14.0, "dividend_yield": 3.5, "total_market_cap": 15000, "circ_market_cap": 14800},
    "600048": {"pe": 6.0, "pb": 0.8, "roe": 12.0, "dividend_yield": 2.5, "total_market_cap": 900, "circ_market_cap": 850},
    "600276": {"pe": 28.0, "pb": 5.5, "roe": 22.0, "dividend_yield": 0.8, "total_market_cap": 4500, "circ_market_cap": 4300},
    "600309": {"pe": 20.0, "pb": 3.0, "roe": 15.0, "dividend_yield": 1.5, "total_market_cap": 2000, "circ_market_cap": 1900},
    "600519": {"pe": 22.0, "pb": 10.5, "roe": 31.0, "dividend_yield": 1.2, "total_market_cap": 208000, "circ_market_cap": 205000},
    "600887": {"pe": 22.0, "pb": 4.0, "roe": 18.0, "dividend_yield": 1.5, "total_market_cap": 4000, "circ_market_cap": 3900},
    "600900": {"pe": 10.0, "pb": 1.2, "roe": 10.0, "dividend_yield": 2.5, "total_market_cap": 3000, "circ_market_cap": 2900},
    "601012": {"pe": 25.0, "pb": 2.0, "roe": 12.0, "dividend_yield": 1.0, "total_market_cap": 1800, "circ_market_cap": 1700},
    "601318": {"pe": 6.5, "pb": 1.2, "roe": 14.0, "dividend_yield": 3.0, "total_market_cap": 15000, "circ_market_cap": 14800},
    "601398": {"pe": 4.5, "pb": 0.5, "roe": 12.0, "dividend_yield": 5.0, "total_market_cap": 180000, "circ_market_cap": 178000},
    "601668": {"pe": 6.0, "pb": 0.6, "roe": 10.0, "dividend_yield": 4.0, "total_market_cap": 22000, "circ_market_cap": 21800},
    "601888": {"pe": 18.0, "pb": 2.0, "roe": 12.0, "dividend_yield": 1.5, "total_market_cap": 1200, "circ_market_cap": 1100},
    "603288": {"pe": 35.0, "pb": 8.0, "roe": 25.0, "dividend_yield": 0.8, "total_market_cap": 6000, "circ_market_cap": 5800},
}


def _get_base_price(symbol: str) -> float:
    """获取股票基础价格"""
    for code, _, p in MOCK_STOCKS:
        if code == symbol:
            return p
    return 10.0


def _resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """将日线数据重采样为周/月/年线"""
    if df.empty:
        return df
    ohlc = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    resampled = df.resample(rule).agg(ohlc).dropna()
    return resampled
def get_mock_quote(symbol: str) -> dict:
    """返回单只股票的模拟实时行情"""
    code, name, base = next(((c, n, p) for c, n, p in MOCK_STOCKS if c == symbol),
                            (symbol, symbol, 10.0))
    change_pct = random.uniform(-5, 5)
    change = base * change_pct / 100
    current = round(base + change, 2)
    volume = random.randint(1000, 50000) * 100
    amount = round(volume * current / 1e8, 2)
    return {
        "symbol": code,
        "name": name,
        "current": current,
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "volume": volume,
        "amount": amount,
        "open": round(base * random.uniform(0.98, 1.02), 2),
        "high": round(current * random.uniform(1.0, 1.05), 2),
        "low": round(current * random.uniform(0.95, 1.0), 2),
        "pre_close": base,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_mock_quotes(symbols: list) -> list:
    """返回多只股票模拟行情"""
    return [get_mock_quote(s) for s in symbols]


def get_mock_kline(symbol: str, period: str = "daily", days: int = 100) -> pd.DataFrame:
    """生成模拟K线数据，支持 daily, 5d, weekly, monthly, yearly"""
    base_price = _get_base_price(symbol)
    end_date = datetime.now()

    # 根据周期确定回溯天数
    if period == "daily":
        start_date = end_date - timedelta(days=days * 2)
        dates = pd.bdate_range(start=start_date, end=end_date)
        rule = None
    elif period == "5d":
        start_date = end_date - timedelta(days=days * 10)
        dates = pd.bdate_range(start=start_date, end=end_date)
        rule = "5D"
    elif period == "weekly":
        start_date = end_date - timedelta(days=days * 14)
        dates = pd.bdate_range(start=start_date, end=end_date)
        rule = "W-FRI"
    elif period == "monthly":
        start_date = end_date - timedelta(days=days * 45)
        dates = pd.bdate_range(start=start_date, end=end_date)
        rule = "ME"
    elif period == "yearly":
        start_date = end_date - timedelta(days=days * 365)
        dates = pd.bdate_range(start=start_date, end=end_date)
        rule = "YE-DEC"
    else:
        start_date = end_date - timedelta(days=days * 2)
        dates = pd.bdate_range(start=start_date, end=end_date)
        rule = None

    # 用随机游走模拟价格
    np.random.seed(hash(symbol) % (2 ** 32))
    returns = np.random.normal(0, 0.02, size=len(dates))
    prices = base_price * np.exp(np.cumsum(returns))

    data = []
    for i, date in enumerate(dates):
        close = prices[i]
        open_price = prices[i - 1] if i > 0 else close
        high = max(open_price, close) * (1 + abs(np.random.normal(0, 0.01)))
        low = min(open_price, close) * (1 - abs(np.random.normal(0, 0.01)))
        vol = random.randint(1000, 100000) * 100
        data.append([date, round(open_price, 2), round(high, 2), round(low, 2),
                     round(close, 2), vol])

    df = pd.DataFrame(data, columns=["date", "open", "high", "low", "close", "volume"])
    df.set_index("date", inplace=True)

    # 重采样为更长周期
    if rule is not None:
        df = _resample_ohlc(df, rule)

    return df.tail(days)


def get_mock_minute(symbol: str, date_str: str) -> pd.DataFrame:
    """生成模拟分时数据（9:30-11:30, 13:00-15:00）"""
    base_price = _get_base_price(symbol)
    times = []

    # 上午时段
    for h, m in [(9, 30), (9, 31), (9, 32), (9, 33), (9, 34), (9, 35),
                 (9, 36), (9, 37), (9, 38), (9, 39), (9, 40), (9, 41),
                 (9, 42), (9, 43), (9, 44), (9, 45), (9, 46), (9, 47),
                 (9, 48), (9, 49), (9, 50), (9, 51), (9, 52), (9, 53),
                 (9, 54), (9, 55), (9, 56), (9, 57), (9, 58), (9, 59),
                 (10, 0), (10, 1), (10, 2), (10, 3), (10, 4), (10, 5),
                 (10, 6), (10, 7), (10, 8), (10, 9), (10, 10), (10, 11),
                 (10, 12), (10, 13), (10, 14), (10, 15), (10, 16), (10, 17),
                 (10, 18), (10, 19), (10, 20), (10, 21), (10, 22), (10, 23),
                 (10, 24), (10, 25), (10, 26), (10, 27), (10, 28), (10, 29),
                 (11, 0), (11, 1), (11, 2), (11, 3), (11, 30)]:
        times.append(f"{h:02d}:{m:02d}")

    # 下午时段
    for h, m in [(13, 0), (13, 1), (13, 2), (13, 3), (13, 4), (13, 5),
                 (13, 6), (13, 7), (13, 8), (13, 9), (13, 10), (13, 11),
                 (13, 12), (13, 13), (13, 14), (13, 15), (13, 16), (13, 17),
                 (13, 18), (13, 19), (13, 20), (13, 21), (13, 22), (13, 23),
                 (13, 24), (13, 25), (13, 26), (13, 27), (13, 28), (13, 29),
                 (13, 30), (13, 31), (13, 32), (13, 33), (13, 34), (13, 35),
                 (13, 36), (13, 37), (13, 38), (13, 39), (13, 40), (13, 41),
                 (13, 42), (13, 43), (13, 44), (13, 45), (13, 46), (13, 47),
                 (13, 48), (13, 49), (13, 50), (13, 51), (13, 52), (13, 53),
                 (13, 54), (13, 55), (13, 56), (13, 57), (13, 58), (13, 59),
                 (14, 0), (14, 1), (14, 2), (14, 3), (14, 4), (14, 5),
                 (14, 6), (14, 7), (14, 8), (14, 9), (14, 10), (14, 11),
                 (14, 12), (14, 13), (14, 14), (14, 15), (14, 16), (14, 17),
                 (14, 58), (14, 59), (15, 0)]:
        times.append(f"{h:02d}:{m:02d}")

    np.random.seed(hash(symbol + date_str) % (2 ** 32))
    price = base_price
    prices = []
    volumes = []
    amounts = []
    for t in times:
        change_pct = np.random.normal(0, 0.003)
        price = round(price * (1 + change_pct), 2)
        vol = random.randint(100, 5000) * 100
        amt = round(vol * price / 1e8, 4)
        prices.append(price)
        volumes.append(vol)
        amounts.append(amt)

    df = pd.DataFrame({
        "time": times,
        "price": prices,
        "volume": volumes,
        "amount": amounts,
    })
    return df


def get_mock_metrics(symbol: str) -> dict:
    """返回模拟价值投资指标（含当前价格）"""
    base = _get_base_price(symbol)
    m = MOCK_METRICS.get(symbol, {
        "pe": random.uniform(10, 30),
        "pb": random.uniform(1, 5),
        "roe": random.uniform(5, 25),
        "dividend_yield": random.uniform(0, 5),
        "total_market_cap": random.randint(100, 5000),
        "circ_market_cap": random.randint(100, 5000),
    })
    return {
        "current": round(base * random.uniform(0.98, 1.02), 2),
        "pe": m.get("pe", 0),
        "pb": m.get("pb", 0),
        "roe": m.get("roe", 0),
        "dividend_yield": m.get("dividend_yield", 0),
        "total_market_cap": m.get("total_market_cap", 0),
        "circ_market_cap": m.get("circ_market_cap", 0),
    }


def get_mock_search(keyword: str) -> list:
    """模拟搜索：按代码或名称模糊匹配"""
    kw = keyword.lower()
    results = []
    for code, name, _ in MOCK_STOCKS:
        if kw in code.lower() or kw in name.lower():
            results.append({"symbol": code, "name": name})
    return results


def get_mock_all_stocks() -> list:
    """返回所有模拟股票列表（离线演示用）"""
    return [{"symbol": code, "name": name} for code, name, _ in MOCK_STOCKS]