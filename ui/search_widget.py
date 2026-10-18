# -*- coding: utf-8 -*-
"""股票搜索组件"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal


class SearchWidget(QWidget):
    """搜索框 + 结果列表，选中后发出 stock_selected 信号"""

    stock_selected = pyqtSignal(str)  # 发送选中的股票代码

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        tip = QLabel("搜索股票（代码/名称）")
        tip.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(tip)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("例如：600519 或 茅台")
        self.edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.edit)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(200)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        self._results = []

    def _on_text_changed(self, text: str):
        text = text.strip()
        self.list_widget.clear()
        if not text:
            self._results = []
            return

        # 调用外部搜索（由 MainWindow 注入回调）
        search_fn = getattr(self, "_search_fn", None)
        if not search_fn:
            return

        try:
            results = search_fn(text)
        except Exception:
            results = []

        self._results = results
        for item in results:
            display = f"{item.get('symbol', '')}  {item.get('name', '')}"
            q_item = QListWidgetItem(display)
            q_item.setData(Qt.ItemDataRole.UserRole, item.get("symbol", ""))
            self.list_widget.addItem(q_item)

    def set_search_function(self, fn):
        """注入搜索回调函数"""
        self._search_fn = fn

    def _on_item_clicked(self, item: QListWidgetItem):
        symbol = item.data(Qt.ItemDataRole.UserRole)
        if symbol:
            self.stock_selected.emit(symbol)
            self.edit.clear()
            self.list_widget.clear()