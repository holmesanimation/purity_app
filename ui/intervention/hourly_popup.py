from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit
from PySide6.QtCore import Qt
from ui.intervention.base_popup import BasePopup
from ui.widgets.mood_picker import MoodPicker
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, FONT_FAMILY, FONT_SIZE_NORMAL, FONT_SIZE_SMALL,
)


class HourlyPopup(BasePopup):
    DEFAULT_WIDTH  = 400
    DEFAULT_HEIGHT = 340

    def __init__(self, parent=None):
        super().__init__("⏰ Quick Check-In", parent)
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._build()

    def _build(self):
        mood_lbl = QLabel("How are you feeling right now?")
        mood_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mood_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self.body_layout.addWidget(mood_lbl)
        self.body_layout.addWidget(MoodPicker())

        work_input = QTextEdit()
        work_input.setPlaceholderText("What are you working on?")
        work_input.setFixedHeight(60)
        self.body_layout.addWidget(work_input)

        submit_btn = QPushButton("Submit")
        submit_btn.clicked.connect(self.accept)
        self.button_row.addWidget(submit_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setStyleSheet(
            f"background-color: transparent; color: {COLOR_TEXT_MUTED};"
            f"border: 1px solid #DDD8CF; border-radius: 6px; padding: 6px 12px;"
        )
        dismiss_btn.clicked.connect(self.reject)
        self.button_row.addWidget(dismiss_btn)
