from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from styles.theme import (
    COLOR_TEXT, COLOR_BORDER, FONT_FAMILY, FONT_SIZE_MEDIUM,
)


class SectionHeader(QLabel):
    """Bold section title label with bottom spacing."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(
            f"QLabel {{"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_MEDIUM}pt;"
            f"  font-weight: 700;"
            f"  color: {COLOR_TEXT};"
            f"  background: transparent;"
            f"  padding-bottom: 4px;"
            f"  border-bottom: 1px solid {COLOR_BORDER};"
            f"  margin-bottom: 4px;"
            f"}}"
        )
