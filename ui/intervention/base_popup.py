from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication
from styles.theme import (
    COLOR_SURFACE, COLOR_BORDER, COLOR_TEXT,
    FONT_FAMILY, FONT_SIZE_MEDIUM, FONT_SIZE_NORMAL,
)


class BasePopup(QDialog):
    """Base intervention popup: centered, soft-styled, small footprint."""

    DEFAULT_WIDTH  = 400
    DEFAULT_HEIGHT = 300

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowTitleHint
        )
        self.setModal(False)
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setStyleSheet(
            f"QDialog {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 10px;"
            f"}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # Title label (populated by subclasses if needed)
        if title:
            self._title_label = QLabel(title)
            self._title_label.setStyleSheet(
                f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_MEDIUM}pt;"
                f"font-weight: 700; color: {COLOR_TEXT}; background: transparent;"
            )
            self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._title_label.setWordWrap(True)
            root.addWidget(self._title_label)
        else:
            self._title_label = None

        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        root.addLayout(self.body_layout)

        root.addStretch()

        self.button_row = QHBoxLayout()
        self.button_row.setSpacing(8)
        root.addLayout(self.button_row)

    def show_centered(self):
        """Center on the primary screen and show."""
        screen: QScreen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width()  - self.width())  // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
