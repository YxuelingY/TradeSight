# -*- coding: utf-8 -*-
"""主窗口：行情列表 + 搜索 + K线图表（多周期） + 价值投资指标（同花顺风格）"""

import sys

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QFrame, QMessageBox, QPushButton, QLineEdit, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from config import (
    APP_NAME, APP_VERSION, DEFAULT_WATCHLIST, PRICE_REFRESH_INTERVAL,
    PRICE_REFRESH_INTERVAL_OFFHOUR,
    KLINE_PERIODS, DEFAULT_KLINE_PERIOD,
    COLOR_UP, COLOR_DOWN,
)
from data.fetcher import (
    get_quote, get_quotes, get_kline, get_value_metrics, search_stocks,
    get_quote_from_db, get_klines_from_db, get_minute,
    get_all_stock_list, last_source,
)
from utils.trading_clock import next_interval_ms
from ui.stock_list_widget import StockListWidget
from ui.chart_widget import ChartWidget
from ui.value_metrics_widget import ValueMetricsWidget
from ui.search_widget import SearchWidget
from utils.helpers import fmt_price, fmt_pct, fmt_market_cap


class QuoteFetchThread(QThread):
    """后台线程：批量获取行情，避免阻塞GUI"""
    finished = pyqtSignal(list)

    def __init__(self, symbols):
        super().__init__()
        self.symbols = symbols

    def run(self):
        quotes = get_quotes(self.symbols)
        self.finished.emit(quotes)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1400, 900)

        self._current_symbol = ""
        self._current_name = ""
        self._watchlist = [item["code"] for item in DEFAULT_WATCHLIST]
        self._quotes_cache = {}
        self._current_period = DEFAULT_KLINE_PERIOD

        self._init_ui()
        # 不在构造函数中同步加载行情（在线模式下获取全市场行情较慢，会阻塞GUI）
        # 使用 QTimer 延迟加载，保证窗口先显示出来
        QTimer.singleShot(100, self._load_watchlist)
        self._start_price_timer()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ---------- 左侧面板：搜索 + 股票列表 ----------
        left_panel = QFrame()
        left_panel.setFrameShape(QFrame.Shape.StyledPanel)
        left_panel.setStyleSheet("QFrame { background: #fafafa; border: 1px solid #ddd; }")
        left_panel.setFixedWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        self.search_widget = SearchWidget()
        self.search_widget.set_search_function(search_stocks)
        self.search_widget.stock_selected.connect(self._on_symbol_selected)
        left_layout.addWidget(self.search_widget)

        # 加载全市场股票按钮
        self.btn_load_all = QPushButton("加载全市场股票（前200只）")
        self.btn_load_all.setFixedHeight(28)
        self.btn_load_all.clicked.connect(self._load_all_stocks)
        left_layout.addWidget(self.btn_load_all)

        # 历史查询输入框
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("输入代码查询历史（如 600519）")
        self.query_edit.returnPressed.connect(self._on_query_pressed)
        left_layout.addWidget(self.query_edit)

        self.stock_list = StockListWidget()
        self.stock_list.stock_selected.connect(self._on_symbol_selected)
        left_layout.addWidget(self.stock_list, stretch=1)

        root.addWidget(left_panel)

        # ---------- 右侧：股票信息 + K线图表 + 价值指标 ----------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # 股票信息头部（同花顺风格：大字显示名称、价格、涨跌幅）
        self.info_panel = QFrame()
        self.info_panel.setFixedHeight(60)
        self.info_panel.setStyleSheet("QFrame { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; }")
        info_layout = QHBoxLayout(self.info_panel)
        info_layout.setContentsMargins(12, 6, 12, 6)
        info_layout.setSpacing(20)

        self.lbl_name = QLabel("未选择股票")
        self.lbl_name.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #333;")

        self.lbl_price = QLabel("-")
        self.lbl_price.setFont(QFont("Microsoft YaHei", 22, QFont.Weight.Bold))
        self.lbl_price.setStyleSheet(f"color: {COLOR_UP};")

        self.lbl_change = QLabel("-")
        self.lbl_change.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.lbl_change.setStyleSheet(f"color: {COLOR_UP};")

        self.lbl_market_cap = QLabel("总市值: -")
        self.lbl_market_cap.setFont(QFont("Microsoft YaHei", 12))
        self.lbl_market_cap.setStyleSheet("color: #666;")

        info_layout.addWidget(self.lbl_name)
        info_layout.addWidget(self.lbl_price)
        info_layout.addWidget(self.lbl_change)
        info_layout.addWidget(self.lbl_market_cap)
        info_layout.addStretch()

        right_layout.addWidget(self.info_panel)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.chart_widget = ChartWidget()
        self.chart_widget.period_changed.connect(self._on_period_changed)
        splitter.addWidget(self.chart_widget)

        self.metrics_widget = ValueMetricsWidget()
        self.metrics_widget.setFixedHeight(200)
        splitter.addWidget(self.metrics_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 0)

        right_layout.addWidget(splitter)
        root.addWidget(right_panel, stretch=1)

        # 状态栏
        self.statusBar().showMessage("就绪")

    def _load_watchlist(self):
        """加载默认自选股行情（后台线程，不阻塞GUI）"""
        self.statusBar().showMessage("正在加载自选股行情...")
        self._quote_thread = QuoteFetchThread(self._watchlist)
        self._quote_thread.finished.connect(self._on_quotes_loaded)
        self._quote_thread.start()

    def _on_quotes_loaded(self, quotes: list):
        """行情加载完成回调"""
        self._quotes_cache = {q["symbol"]: q for q in quotes}
        self.stock_list.set_data(quotes)
        src = last_source()
        marks = sum(1 for q in quotes if q.get("mocked")) + sum(1 for q in quotes if q.get("stale"))
        tag = f" [{src}]" if src else ""
        if marks:
            tag += f" ({marks}条缓存/模拟)"
        self.statusBar().showMessage(f"已加载 {len(quotes)} 支股票行情{tag}")

    def _start_price_timer(self):
        """定时刷新行情：交易时钟决定节拍（盘中3s/盘后60s/周末暂停）"""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_prices)
        self._schedule_next_tick(initial=True)

    def _schedule_next_tick(self, initial: bool = False):
        ms = next_interval_ms(in_ms=PRICE_REFRESH_INTERVAL,
                              off_ms=PRICE_REFRESH_INTERVAL_OFFHOUR)
        if ms is None:
            self.statusBar().showMessage("周末休市，暂停刷新")
            return
        if initial or not self._timer.isActive():
            self._timer.start(ms)
        else:
            self._timer.setInterval(ms)

    def _refresh_prices(self):
        """刷新所有行情（后台线程）"""
        if hasattr(self, "_quote_thread") and self._quote_thread.isRunning():
            return  # 上次获取尚未完成，跳过
        self._quote_thread = QuoteFetchThread(self._watchlist)
        self._quote_thread.finished.connect(self._on_quotes_refreshed)
        self._quote_thread.start()

    def _on_quotes_refreshed(self, quotes: list):
        """行情刷新完成回调"""
        self._quotes_cache = {q["symbol"]: q for q in quotes}
        for q in quotes:
            self.stock_list.update_row(q["symbol"], q)
        # 若当前有选中股票，也更新其详情
        if self._current_symbol and self._current_symbol in self._quotes_cache:
            self._update_detail(self._current_symbol)
        self._schedule_next_tick()
        src = last_source()
        marks = sum(1 for q in quotes if q.get("mocked")) + sum(1 for q in quotes if q.get("stale"))
        tag = f" [{src}]" if src else ""
        if marks:
            tag += f" ({marks}条缓存/模拟)"
        self.statusBar().showMessage(f"已刷新 {len(quotes)} 支{tag}")

    def _on_symbol_selected(self, symbol: str):
        """用户选择某只股票：更新图表与指标"""
        self._current_symbol = symbol
        # 查找名称
        name = symbol
        for row in range(self.stock_list.table.rowCount()):
            item = self.stock_list.table.item(row, 1)
            if item and self.stock_list.table.item(row, 0).text() == symbol:
                name = item.text()
                break
        self._current_name = name
        self.query_edit.setText(symbol)
        self.statusBar().showMessage(f"已选择：{symbol} {name}")
        self._update_detail(symbol)

    def _on_query_pressed(self):
        """回车查询指定股票"""
        symbol = self.query_edit.text().strip()
        if not symbol:
            return
        self._current_symbol = symbol
        self._current_name = symbol
        self.statusBar().showMessage(f"查询：{symbol}")
        self._update_detail(symbol)

    def _load_all_stocks(self):
        """加载全市场股票列表（前200只）到行情列表"""
        self.statusBar().showMessage("正在加载全市场股票列表...")
        stocks = get_all_stock_list(limit=200)
        if not stocks:
            self.statusBar().showMessage("未能获取股票列表")
            return

        # 批量获取行情（最多200只，可能较慢，先显示列表，行情逐个获取）
        symbols = [s["symbol"] for s in stocks]
        quotes = get_quotes(symbols)
        self._quotes_cache = {q["symbol"]: q for q in quotes}
        self.stock_list.set_data(quotes)
        self.statusBar().showMessage(f"已加载 {len(quotes)} 支股票行情")

    def _on_period_changed(self, period: str):
        """K线周期切换"""
        self._current_period = period
        if self._current_symbol:
            self._update_detail(self._current_symbol)

    def _update_detail(self, symbol: str):
        """加载K线与价值投资指标，并更新股票信息头部"""
        try:
            # 优先实时获取行情，保证头部显示最新价格
            quote = get_quote(symbol)
            if quote:
                name = quote.get("name") or symbol
                current = float(quote.get("current") or 0)
                change_pct = float(quote.get("change_pct") or 0)
                change = float(quote.get("change") or 0)
                self._current_name = name
                self.lbl_name.setText(f"{symbol}  {name}")
                self.lbl_price.setText(fmt_price(current))
                self.lbl_change.setText(f"{fmt_pct(change_pct)}  ({fmt_price(change)})")
                if change >= 0:
                    self.lbl_price.setStyleSheet(f"color: {COLOR_UP};")
                    self.lbl_change.setStyleSheet(f"color: {COLOR_UP};")
                else:
                    self.lbl_price.setStyleSheet(f"color: {COLOR_DOWN};")
                    self.lbl_change.setStyleSheet(f"color: {COLOR_DOWN};")
                # 显示总市值
                market_cap = quote.get("market_cap", 0)
                if not market_cap or market_cap == 0:
                    market_cap = 0
                self.lbl_market_cap.setText(f"总市值: {fmt_market_cap(market_cap)}")

            # K线（按当前周期）
            if self._current_period == "minute":
                df = get_minute(symbol)
                self.chart_widget.plot_kline(symbol, df, period="minute")
            else:
                df = get_kline(symbol, period=self._current_period, days=120)
                self.chart_widget.plot_kline(symbol, df, period=self._current_period)

            # 价值指标（优先实时获取，含市值）
            metrics = get_value_metrics(symbol)
            # 确保指标面板也显示当前价格
            if "current" not in metrics or not metrics.get("current"):
                metrics["current"] = current if quote else 0
            self.metrics_widget.set_metrics(metrics, symbol)
        except Exception as e:
            self.statusBar().showMessage(f"加载股票 {symbol} 数据失败：{str(e)}")
            import traceback
            traceback.print_exc()


def main():
    app = QApplication(sys.argv)
    # 设置默认字体，避免中文乱码
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()