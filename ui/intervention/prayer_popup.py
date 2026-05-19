from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit
from PySide6.QtCore import Qt
from ui.intervention.base_popup import BasePopup
from ui.widgets.mood_picker import MoodPicker
from services.fake_prayer import FakePrayerService
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, FONT_FAMILY, FONT_SIZE_NORMAL, FONT_SIZE_SMALL,
)


class PrayerPopup(BasePopup):
    DEFAULT_WIDTH  = 400
    DEFAULT_HEIGHT = 360

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._svc = FakePrayerService()
        self._build()

    def _build(self):
        person = self._svc.current()

        heading = QLabel(f"🙏 Pray for: {person.name}")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL + 1}pt;"
            f"font-weight: 700; color: {COLOR_TEXT}; background: transparent;"
        )
        self.body_layout.addWidget(heading)

        if person.notes:
            notes_lbl = QLabel(person.notes)
            notes_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            notes_lbl.setStyleSheet(
                f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
            )
            notes_lbl.setWordWrap(True)
            self.body_layout.addWidget(notes_lbl)

        thought_input = QTextEdit()
        thought_input.setPlaceholderText("What's on your mind?")
        thought_input.setFixedHeight(60)
        self.body_layout.addWidget(thought_input)

        mood_lbl = QLabel("How are you feeling?")
        mood_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self.body_layout.addWidget(mood_lbl)
        self.body_layout.addWidget(MoodPicker())

        prayed_btn = QPushButton("I Prayed ✓")
        prayed_btn.clicked.connect(self.accept)
        self.button_row.addWidget(prayed_btn)

        later_btn = QPushButton("Remind me later")
        later_btn.setStyleSheet(
            f"background-color: transparent; color: {COLOR_TEXT_MUTED};"
            f"border: 1px solid #DDD8CF; border-radius: 6px; padding: 6px 12px;"
        )
        later_btn.clicked.connect(self.reject)
        self.button_row.addWidget(later_btn)
