# -*- coding: utf-8 -*-
"""股票行情列表组件"""

from PyQt6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from config import COLOR_UP, COLOR_DOWN
from utils.helpers import fmt_price, fmt_pct, fmt_volume


class StockListWidget(QWidget):
    """股票行情列表，点击行发出 stock_selected 信号"""

    stock_selected = pyqtSignal(str)  # 发送股票代码

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "代码", "名称", "最新价", "涨跌额", "涨跌幅", "成交量", "成交额"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._on_double_clicked)

        layout.addWidget(self.table)

    def _on_double_clicked(self, row: int, column: int):
        symbol_item = self.table.item(row, 0)
        if symbol_item:
            self.stock_selected.emit(symbol_item.text())

    def set_data(self, quotes: list):
        """用行情数据填充表格"""
        self.table.setRowCount(len(quotes))
        for row, q in enumerate(quotes):
            self._fill_row(row, q)

    def _fill_row(self, row: int, q: dict):
        items = [
            q.get("symbol", ""),
            q.get("name", ""),
            fmt_price(q.get("current")),
            fmt_price(q.get("change")),
            fmt_pct(q.get("change_pct")),
            fmt_volume(q.get("volume")),
            fmt_volume(q.get("amount")),
        ]
        for col, text in enumerate(items):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            # 涨跌颜色
            if col in (3, 4):
                change = q.get("change", 0) or 0
                if change > 0:
                    item.setForeground(QColor(COLOR_UP))
                elif change < 0:
                    item.setForeground(QColor(COLOR_DOWN))
            self.table.setItem(row, col, item)

    def update_row(self, symbol: str, q: dict):
        """更新指定代码的一行行情"""
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text() == symbol:
                self._fill_row(row, q)
                break