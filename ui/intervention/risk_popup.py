from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout
from PySide6.QtCore import Qt
from ui.intervention.base_popup import BasePopup
from services.mock_state import MockAppState
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER,
    COLOR_SURFACE_2,
    FONT_FAMILY, FONT_SIZE_NORMAL, FONT_SIZE_SMALL,
)

_RISK_DATA = {
    "low": {
        "heading": "🟢 Strong State",
        "color": COLOR_SUCCESS,
        "factors": [
            "Good sleep last night",
            "Prayer completed this morning",
            "Low stress level today",
        ],
        "action": "Keep your commitments. You're doing well.",
    },
    "medium": {
        "heading": "⚠️ Elevated Risk",
        "color": COLOR_WARNING,
        "factors": [
            "Fatigue from limited sleep",
            "Higher than normal stress",
            "Skipped morning routine",
        ],
        "action": "Take a 5-minute break. Pray or call a friend.",
    },
    "high": {
        "heading": "🔴 High Risk State",
        "color": COLOR_DANGER,
        "factors": [
            "Poor sleep quality",
            "Elevated stress and isolation",
            "Multiple triggers identified today",
        ],
        "action": "Reach out to your accountability partner now.",
    },
}


class RiskPopup(BasePopup):
    DEFAULT_WIDTH  = 400
    DEFAULT_HEIGHT = 320

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._build()

    def _build(self):
        state = MockAppState()
        data = _RISK_DATA.get(state.risk_level, _RISK_DATA["low"])

        heading = QLabel(data["heading"])
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL + 2}pt;"
            f"font-weight: 700; color: {data['color']}; background: transparent;"
        )
        self.body_layout.addWidget(heading)

        for factor in data["factors"]:
            row = QLabel(f"• {factor}")
            row.setStyleSheet(
                f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
                f"padding-left: 4px;"
            )
            self.body_layout.addWidget(row)

        action_lbl = QLabel(data["action"])
        action_lbl.setWordWrap(True)
        action_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; font-style: italic; background: transparent;"
            f"padding-top: 4px;"
        )
        self.body_layout.addWidget(action_lbl)

        dismiss_btn = QPushButton("I understand")
        dismiss_btn.clicked.connect(self.accept)
        self.button_row.addStretch()
        self.button_row.addWidget(dismiss_btn)
        self.button_row.addStretch()
