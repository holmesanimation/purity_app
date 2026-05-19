from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from services.mock_state import MockAppState
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER,
    COLOR_SURFACE_2, COLOR_BORDER,
    FONT_FAMILY, FONT_SIZE_TITLE, FONT_SIZE_NORMAL, FONT_SIZE_SMALL,
)

_RISK_STYLES = {
    "low":    ("🟢 Strong state",    COLOR_SUCCESS),
    "medium": ("⚠️ Elevated risk",  COLOR_WARNING),
    "high":   ("🔴 High risk state", COLOR_DANGER),
}


class StreakWidget(QWidget):
    def __init__(self, state: MockAppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Streak badge
        badge_container = QWidget()
        badge_container.setStyleSheet(
            f"background-color: {COLOR_SURFACE_2}; border-radius: 10px;"
            f"border: 1px solid {COLOR_BORDER};"
        )
        badge_layout = QVBoxLayout(badge_container)
        badge_layout.setContentsMargins(16, 12, 16, 12)
        badge_layout.setSpacing(2)

        streak_num = QLabel(str(self._state.purity_streak_days))
        streak_num.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_TITLE}pt;"
            f"font-weight: 800; color: {COLOR_TEXT}; background: transparent;"
        )
        streak_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_layout.addWidget(streak_num)

        day_lbl = QLabel("Day streak")
        day_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"color: {COLOR_TEXT_MUTED}; background: transparent;"
        )
        day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_layout.addWidget(day_lbl)

        layout.addWidget(badge_container)

        # Focus state label
        label_text, color = _RISK_STYLES.get(
            self._state.risk_level, ("🟢 Strong state", COLOR_SUCCESS)
        )
        state_lbl = QLabel(label_text)
        state_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"font-weight: 600; color: {color}; background: transparent;"
        )
        state_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(state_lbl)
