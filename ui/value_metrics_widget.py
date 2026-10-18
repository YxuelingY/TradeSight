# -*- coding: utf-8 -*-
"""价值投资指标组件"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from utils.helpers import fmt_price, fmt_market_cap


class ValueMetricsWidget(QWidget):
    """展示PE、PB、ROE、股息率、市值等价值投资指标"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        group = QGroupBox("价值投资指标")
        group.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        grid = QGridLayout(group)

        self.labels = {}
        metrics = [
            ("price", "当前价格", "-"),
            ("pe", "市盈率 (PE)", "-"),
            ("pb", "市净率 (PB)", "-"),
            ("roe", "净资产收益率 (ROE)", "-"),
            ("dividend_yield", "股息率", "-"),
            ("total_market_cap", "总市值", "-"),
            ("circ_market_cap", "流通市值", "-"),
        ]

        for i, (key, label_text, default) in enumerate(metrics):
            r, c = divmod(i, 3)
            name_lbl = QLabel(label_text)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val_lbl = QLabel(default)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            val_lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            grid.addWidget(name_lbl, r, c * 2)
            grid.addWidget(val_lbl, r, c * 2 + 1)
            self.labels[key] = val_lbl

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(4, 1)
        grid.setColumnStretch(5, 1)

        layout.addWidget(group)
        layout.addStretch()

    def set_metrics(self, metrics: dict, symbol: str = ""):
        """更新指标显示"""
        mapping = {
            "price": metrics.get("current", 0),
            "pe": metrics.get("pe", 0),
            "pb": metrics.get("pb", 0),
            "roe": metrics.get("roe", 0),
            "dividend_yield": metrics.get("dividend_yield", 0),
            "total_market_cap": metrics.get("total_market_cap", 0),
            "circ_market_cap": metrics.get("circ_market_cap", 0),
        }
        for key, val in mapping.items():
            lbl = self.labels.get(key)
            if lbl is None:
                continue
            if key in ("total_market_cap", "circ_market_cap"):
                lbl.setText(fmt_market_cap(val))
            elif key == "price":
                lbl.setText(fmt_price(val))
            elif key == "roe":
                lbl.setText(f"{val:.2f}%" if val else "-")
            elif key == "dividend_yield":
                lbl.setText(f"{val:.2f}%" if val else "-")
            else:
                lbl.setText(f"{val:.2f}" if val else "-")