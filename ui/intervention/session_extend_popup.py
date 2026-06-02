"""Session-extend popup.

Shown when the web-session timer expires.  Asks the user whether they are
still using the web for their original stated reason.

  - "Yes"  → caller restarts the timer
  - "No"   → caller kills the browser
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from ui.intervention.base_popup import BasePopup
from styles.theme import (
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_SURFACE_2, COLOR_BORDER,
    FONT_FAMILY, FONT_SIZE_NORMAL, FONT_SIZE_SMALL,
)


class SessionExtendPopup(BasePopup):
    DEFAULT_WIDTH = 420
    DEFAULT_HEIGHT = 240

    def __init__(self, choice: str = "", reason: str = "", parent=None) -> None:
        super().__init__("Are you still using the web for...", parent)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._build_ui(choice.strip(), reason.strip())

    def _build_ui(self, choice: str, reason: str) -> None:
        # Choice badge — styled like a button but disabled
        if choice:
            choice_lbl = QLabel(choice)
            choice_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            choice_lbl.setStyleSheet(
                f"color: #2D2926;"
                f"background-color: {COLOR_SURFACE_2};"
                f"border: 1px solid {COLOR_BORDER};"
                f"border-radius: 6px;"
                f"padding: 5px 14px;"
                f"font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_NORMAL}pt;"
                f"font-weight: 600;"
            )
            self.body_layout.addWidget(choice_lbl)

        # Reason text
        if reason:
            reason_lbl = QLabel(reason)
            reason_lbl.setWordWrap(True)
            reason_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            reason_lbl.setStyleSheet(
                f"color: {COLOR_TEXT_MUTED};"
                f"background: transparent;"
                f"font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_SMALL}pt;"
            )
            self.body_layout.addWidget(reason_lbl)

        yes_btn = QPushButton("Yes")
        yes_btn.setDefault(True)
        yes_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_SURFACE_2};"
            f"  color: #2D2926;"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 7px 24px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"}}"
            f"QPushButton:hover {{ background-color: #E8E2D8; }}"
        )
        yes_btn.clicked.connect(self.accept)
        self.button_row.addWidget(yes_btn)

        no_btn = QPushButton("No")
        no_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_SURFACE_2};"
            f"  color: #C47C2B;"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 7px 24px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"}}"
            f"QPushButton:hover {{ background-color: #E8E2D8; }}"
        )
        no_btn.clicked.connect(self.reject)
        self.button_row.addWidget(no_btn)
        self.button_row.addStretch()
