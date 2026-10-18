# -*- coding: utf-8 -*-
"""K线图表组件（同花顺风格：蜡烛图 + 成交量 + MA线，支持中文显示）"""

import io
import pandas as pd
import matplotlib
matplotlib.use("Qt5Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from PyQt6.QtWidgets import QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout, QPushButton, QButtonGroup
from PyQt6.QtCore import Qt, pyqtSignal

from config import COLOR_UP, COLOR_DOWN

# ---------------------------------------------------------------------------
# matplotlib 中文字体配置（解决中文显示方块问题）
# ---------------------------------------------------------------------------
import matplotlib.font_manager as fm

_CHINESE_FONTS = [
    "Microsoft YaHei",
    "SimHei",
    "WenQuanYi Micro Hei",
    "Arial Unicode MS",
]

_loaded = False
for _f in _CHINESE_FONTS:
    try:
        fm.fontManager.addfont(fm.findfont(_f))
    except Exception:
        pass
    if _f in [f.name for f in fm.fontManager.ttflist]:
        matplotlib.rcParams["font.family"] = _f
        _loaded = True
        break

if not _loaded:
    matplotlib.rcParams["font.family"] = "sans-serif"

matplotlib.rcParams["axes.unicode_minus"] = False


class ChartWidget(QWidget):
    """K线图表控件，内置周期切换按钮"""

    period_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._symbol = ""
        self._period = "daily"
        self._init_ui()

    def _init_ui(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.fig = Figure(figsize=(10, 6), dpi=100, tight_layout=True)
        self.canvas = FigureCanvas(self.fig)

        # 周期切换工具条
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(4, 2, 4, 2)
        btn_layout.setSpacing(4)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        periods = [
            ("日线", "daily"),
            ("五日线", "5d"),
            ("周线", "weekly"),
            ("月线", "monthly"),
            ("年线", "yearly"),
            ("分时", "minute"),
        ]
        self._buttons = {}
        for label, value in periods:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedSize(56, 24)
            btn.setProperty("period", value)
            btn.clicked.connect(self._on_period_clicked)
            self._btn_group.addButton(btn)
            self._buttons[value] = btn
            btn_layout.addWidget(btn)

        self._buttons["daily"].setChecked(True)
        self._buttons["daily"].setStyleSheet(
            "QPushButton:checked { background: #e22a34; color: white; font-weight: bold; }"
        )

        btn_layout.addStretch()

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addLayout(btn_layout)
        self._layout.addWidget(self.canvas)

        self._show_empty()

    def _show_empty(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.text(0.5, 0.5, "暂无K线数据\n请选择一只股票",
                ha="center", va="center", fontsize=14, color="#999999")
        ax.set_xticks([])
        ax.set_yticks([])
        self.canvas.draw()

    def _on_period_clicked(self):
        btn = self.sender()
        if btn is None:
            return
        period = btn.property("period")
        if period:
            self._period = period
            for val, b in self._buttons.items():
                if val == period:
                    b.setChecked(True)
                    b.setStyleSheet(
                        "QPushButton:checked { background: #e22a34; color: white; font-weight: bold; }"
                    )
                else:
                    b.setChecked(False)
                    b.setStyleSheet("")
            self.period_changed.emit(period)
            if self._symbol:
                self.plot_kline(self._symbol, self._last_df, period=period)

    def plot_kline(self, symbol: str, df: pd.DataFrame, period: str = None):
        self._symbol = symbol
        if period is not None:
            self._period = period

        self.fig.clear()

        if df is None or df.empty:
            self._show_empty()
            return

        self._last_df = df

        if self._period == "minute":
            self._plot_minute(df)
        else:
            self._plot_candle(df)

        self.canvas.draw()

    # ------------------------------------------------------------------
    # 蜡烛K线主图（同花顺风格：K线 + 成交量 + MA）
    # ------------------------------------------------------------------
    def _plot_candle(self, df: pd.DataFrame):
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            self._show_empty()
            return

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        df = df.sort_index()

        close = df["close"]
        ma5 = close.rolling(window=5, min_periods=1).mean()
        ma10 = close.rolling(window=10, min_periods=1).mean()
        ma20 = close.rolling(window=20, min_periods=1).mean()

        gs = self.fig.add_gridspec(4, 1, hspace=0.05, height_ratios=[3, 1, 0.05, 0.05])
        ax_price = self.fig.add_subplot(gs[0, 0])
        ax_vol = self.fig.add_subplot(gs[1, 0], sharex=ax_price)

        dates = df.index
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        vols = df["volume"].values

        width = 0.6
        for i, date in enumerate(dates):
            color = COLOR_UP if closes[i] >= opens[i] else COLOR_DOWN
            ax_price.plot([date, date], [lows[i], highs[i]], color=color, linewidth=0.8, zorder=1)
            bottom = min(opens[i], closes[i])
            height = abs(closes[i] - opens[i])
            if height == 0:
                height = bottom * 0.001
            rect = __import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
                (mdates.date2num(date) - width / 2, bottom),
                width, height,
                facecolor=color,
                edgecolor=color,
                zorder=2,
            )
            ax_price.add_patch(rect)

        ax_price.plot(dates, ma5.values, color="#4285f4", linewidth=1.2, label="MA5", zorder=3)
        ax_price.plot(dates, ma10.values, color="#fbbc05", linewidth=1.2, label="MA10", zorder=3)
        ax_price.plot(dates, ma20.values, color="#ea4335", linewidth=1.2, label="MA20", zorder=3)

        ax_price.set_title(f"{self._symbol}  {self._period_name()}", fontsize=12, fontweight="bold", loc="left")
        ax_price.grid(True, alpha=0.3)
        ax_price.legend(loc="upper left", fontsize=8, framealpha=0.9)
        ax_price.set_ylabel("价格")
        ax_price.yaxis.tick_right()
        ax_price.yaxis.set_label_position("right")

        vol_colors = [COLOR_UP if closes[i] >= opens[i] else COLOR_DOWN for i in range(len(closes))]
        ax_vol.bar(dates, vols, width=0.6, color=vol_colors, alpha=0.7, zorder=2)
        ax_vol.set_ylabel("成交量")
        ax_vol.grid(True, alpha=0.3)
        ax_vol.yaxis.tick_right()
        ax_vol.yaxis.set_label_position("right")

        ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        self.fig.autofmt_xdate()
        plt.setp(ax_price.get_xticklabels(), visible=False)

    def _period_name(self) -> str:
        return {
            "daily": "日线",
            "5d": "五日线",
            "weekly": "周线",
            "monthly": "月线",
            "yearly": "年线",
        }.get(self._period, "K线")

    # ------------------------------------------------------------------
    # 分时图
    # ------------------------------------------------------------------
    def _plot_minute(self, df: pd.DataFrame):
        """绘制分时图（价格折线）"""
        required = {"time", "price"}
        if not required.issubset(set(df.columns)):
            self._show_empty()
            return

        ax = self.fig.add_subplot(111)

        times = df["time"].tolist()
        prices = df["price"].astype(float).values

        x = range(len(times))
        ax.plot(x, prices, color=COLOR_UP, linewidth=1.5)

        # 只显示部分刻度标签，避免拥挤
        step = max(1, len(times) // 8)
        ax.set_xticks(list(x)[::step])
        ax.set_xticklabels([times[i] for i in range(0, len(times), step)], rotation=45, ha="right")

        ax.set_title(f"{self._symbol} 分时", fontsize=12, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.set_ylabel("价格")