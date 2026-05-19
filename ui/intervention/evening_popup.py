from PySide6.QtWidgets import QLabel, QPushButton, QCheckBox, QVBoxLayout
from PySide6.QtCore import Qt
from ui.intervention.base_popup import BasePopup
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, FONT_FAMILY, FONT_SIZE_NORMAL, FONT_SIZE_SMALL,
)

_SHUTDOWN_STEPS = [
    "Closed all work tabs and browser windows",
    "Reviewed tomorrow's top priorities",
    "Said a short prayer of gratitude",
    "Devices set to Do Not Disturb",
    "Ready to rest — no late-night scrolling",
]


class EveningPopup(BasePopup):
    DEFAULT_WIDTH  = 400
    DEFAULT_HEIGHT = 360

    def __init__(self, parent=None):
        super().__init__("🌙 Night Reset", parent)
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._build()

    def _build(self):
        subtitle = QLabel("Complete your shutdown checklist before closing for the night.")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self.body_layout.addWidget(subtitle)

        for step in _SHUTDOWN_STEPS:
            cb = QCheckBox(step)
            cb.setStyleSheet(
                f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
                f"color: {COLOR_TEXT};"
            )
            self.body_layout.addWidget(cb)

        done_btn = QPushButton("All done ✓")
        done_btn.clicked.connect(self.accept)
        self.button_row.addStretch()
        self.button_row.addWidget(done_btn)
        self.button_row.addStretch()
