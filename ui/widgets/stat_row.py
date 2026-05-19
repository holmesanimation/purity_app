from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER,
    FONT_FAMILY, FONT_SIZE_NORMAL,
)


class StatRow(QWidget):
    """Horizontal row: label + value + optional status indicator."""

    def __init__(self, label: str, value: str, status: str = "normal", parent=None):
        """
        status: "normal" | "good" | "warning" | "danger"
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
        )
        layout.addWidget(self._label)
        layout.addStretch()

        self._value_label = QLabel(value)
        self._set_value_style(status)
        layout.addWidget(self._value_label)

    def _set_value_style(self, status: str):
        color_map = {
            "good":    COLOR_SUCCESS,
            "warning": COLOR_WARNING,
            "danger":  COLOR_DANGER,
            "normal":  COLOR_TEXT,
        }
        color = color_map.get(status, COLOR_TEXT)
        self._value_label.setStyleSheet(
            f"color: {color}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-weight: 600; background: transparent;"
        )

    def set_value(self, value: str, status: str = "normal"):
        self._value_label.setText(value)
        self._set_value_style(status)
