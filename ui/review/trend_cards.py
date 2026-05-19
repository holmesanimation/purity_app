from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_SUCCESS, COLOR_WARNING, COLOR_SURFACE,
    COLOR_BORDER, COLOR_SURFACE_2,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM,
)

_TREND_DATA = [
    {
        "label":  "Temptation Frequency",
        "value":  "↓ 2 this week",
        "detail": "Down from 5 last week",
        "status": "good",
    },
    {
        "label":  "Avg Sleep",
        "value":  "6.8 hrs",
        "detail": "Target: 7+ hrs",
        "status": "warning",
    },
    {
        "label":  "Mood Trend",
        "value":  "😊 Improving",
        "detail": "3-day upward trend",
        "status": "good",
    },
    {
        "label":  "Journal Streak",
        "value":  "5 days",
        "detail": "Personal best!",
        "status": "good",
    },
]

_STATUS_COLORS = {
    "good":    COLOR_SUCCESS,
    "warning": COLOR_WARNING,
    "normal":  COLOR_TEXT,
}


def _trend_card(data: dict) -> QFrame:
    card = QFrame()
    card.setStyleSheet(
        f"QFrame {{"
        f"  background-color: {COLOR_SURFACE};"
        f"  border: 1px solid {COLOR_BORDER};"
        f"  border-radius: 8px;"
        f"  padding: 2px;"
        f"}}"
    )
    vbox = QVBoxLayout(card)
    vbox.setContentsMargins(12, 10, 12, 10)
    vbox.setSpacing(4)

    label_lbl = QLabel(data["label"])
    label_lbl.setStyleSheet(
        f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
        f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
    )
    vbox.addWidget(label_lbl)

    value_color = _STATUS_COLORS.get(data["status"], COLOR_TEXT)
    value_lbl = QLabel(data["value"])
    value_lbl.setStyleSheet(
        f"color: {value_color}; font-family: '{FONT_FAMILY}';"
        f"font-size: {FONT_SIZE_NORMAL}pt; font-weight: 700; background: transparent;"
    )
    vbox.addWidget(value_lbl)

    detail_lbl = QLabel(data["detail"])
    detail_lbl.setStyleSheet(
        f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
        f"font-size: {FONT_SIZE_SMALL}pt; font-style: italic; background: transparent;"
    )
    vbox.addWidget(detail_lbl)
    return card


class TrendCardsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        for data in _TREND_DATA:
            layout.addWidget(_trend_card(data), stretch=1)
