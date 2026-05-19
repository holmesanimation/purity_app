from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from styles.theme import (
    COLOR_SURFACE, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED,
    FONT_FAMILY, FONT_SIZE_MEDIUM,
)


class CardWidget(QFrame):
    """Styled surface card with optional title and a body layout for child widgets."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.setStyleSheet(
            f"QFrame[class='card'] {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 8px;"
            f"}}"
        )
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(6)

        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet(
                f"font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_MEDIUM}pt;"
                f"font-weight: 700;"
                f"color: {COLOR_TEXT};"
                f"background: transparent;"
                f"padding-bottom: 2px;"
            )
            title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            outer.addWidget(title_label)

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        outer.addLayout(self.body_layout)
