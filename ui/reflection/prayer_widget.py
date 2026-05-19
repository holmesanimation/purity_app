from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from ui.widgets.card import CardWidget
from services.fake_prayer import FakePrayerService
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ACCENT,
    FONT_FAMILY, FONT_SIZE_LARGE, FONT_SIZE_SMALL, FONT_SIZE_NORMAL,
)


class PrayerWidget(CardWidget):
    def __init__(self, prayer_service: FakePrayerService, parent=None):
        super().__init__("🙏 Prayer Queue", parent)
        self._svc = prayer_service
        self._build()

    def _build(self):
        # Name
        self._name_lbl = QLabel()
        self._name_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_LARGE}pt;"
            f"font-weight: 700; color: {COLOR_TEXT}; background: transparent;"
        )
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self._name_lbl)

        # Notes
        self._notes_lbl = QLabel()
        self._notes_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"color: {COLOR_TEXT_MUTED}; background: transparent;"
        )
        self._notes_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notes_lbl.setWordWrap(True)
        self.body_layout.addWidget(self._notes_lbl)

        # Progress
        self._progress_lbl = QLabel()
        self._progress_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"color: {COLOR_ACCENT}; font-weight: 600; background: transparent;"
        )
        self._progress_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self._progress_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._prayed_btn = QPushButton("I Prayed ✓")
        self._prayed_btn.clicked.connect(self._on_prayed)
        btn_row.addWidget(self._prayed_btn)

        self._skip_btn = QPushButton("Skip for now")
        self._skip_btn.setProperty("flat", "true")
        self._skip_btn.setStyleSheet(
            f"background-color: transparent; color: {COLOR_TEXT_MUTED};"
            f"border: 1px solid #DDD8CF; border-radius: 6px; padding: 6px 12px;"
        )
        self._skip_btn.clicked.connect(self._on_skip)
        btn_row.addWidget(self._skip_btn)

        self.body_layout.addLayout(btn_row)
        self._refresh()

    def _refresh(self):
        person = self._svc.current()
        self._name_lbl.setText(person.name)
        self._notes_lbl.setText(person.notes or "")
        prayed, total = self._svc.progress()
        self._progress_lbl.setText(f"{prayed} of {total} prayed today")

    def _on_prayed(self):
        self._svc.mark_prayed()
        self._refresh()

    def _on_skip(self):
        self._svc.skip()
        self._refresh()
