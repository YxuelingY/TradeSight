# -*- coding: utf-8 -*-
"""TradeSight 全局配置"""

import os

# 应用基本信息
APP_NAME = "TradeSight"
APP_VERSION = "1.0.0"

# 默认观察列表（可自行扩展）
DEFAULT_WATCHLIST = [
    {"code": "000001", "name": "平安银行", "market": "A"},
    {"code": "000002", "name": "万科A", "market": "A"},
    {"code": "600000", "name": "浦发银行", "market": "A"},
    {"code": "600519", "name": "贵州茅台", "market": "A"},
    {"code": "000333", "name": "美的集团", "market": "A"},
    {"code": "300750", "name": "宁德时代", "market": "A"},
    {"code": "600276", "name": "恒瑞医药", "market": "A"},
    {"code": "000858", "name": "五粮液", "market": "A"},
]

# K线时间周期映射（同花顺风格：日/五日/分时/周/年）
KLINE_PERIODS = {
    "日线": "daily",
    "五日线": "5d",
    "分时": "minute",
    "周线": "weekly",
    "月线": "monthly",
    "年线": "yearly",
}

# 默认K线周期
DEFAULT_KLINE_PERIOD = "daily"

# 数据库文件路径
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "trade_sight.db")

# 界面颜色主题（红涨绿跌，符合中国股市习惯）
COLOR_UP = "#e22a34"      # 涨
COLOR_DOWN = "#0d8c4d"    # 跌
COLOR_TEXT = "#333333"
COLOR_BG = "#ffffff"
COLOR_GRID = "#e5e5e5"

# 更新间隔（毫秒）
PRICE_REFRESH_INTERVAL = 3000  # 盘中 3s（交易时钟动态调整）
PRICE_REFRESH_INTERVAL_OFFHOUR = 60000  # 盘后 60s

# 数据源配置（feature.md §7.6/§7.8）
# PROVIDER_ORDER：按序降级 Tencent -> Eastmoney -> SQLite(DB) -> Mock
PROVIDER_ORDER = ["tencent", "eastmoney", "db", "mock"]
QUOTE_BATCH_SIZE = 80
TDX_ENABLED = False
TDX_SERVERS: list = []  # 如 [("119.147.212.81", 7709)]，启用时填入可达站

# 数据源配置
# "akshare"：联网模式，可查询全市场所有上市公司（约4000只，需联网，可能较慢）
# "mock"：离线模拟模式，支持预设28只常见股票，适合演示和离线运行（默认）
DATA_SOURCE = "akshare"  # akshare / mock

# 是否默认加载全市场股票列表（联网模式下建议 True，但列表很长会稍慢）
LOAD_ALL_STOCKS_ON_START = False

# 股票市场后缀映射（用于akshare）
MARKET_SUFFIX = {
    "A": "",
    "HK": ".HK",
    "US": "",
}