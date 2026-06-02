"""Persistent always-on-top panic button.

A small frameless, semi-transparent floating button anchored at the
bottom-right of the primary screen.  Clicking it emits ``panic_requested``.
``set_elevated(True)`` switches to a danger-accent style when a browser
override has been detected.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

_COLOR_NORMAL_BG   = "rgba(180, 20, 20, 1.0)"
_COLOR_NORMAL_BORDER = "#ef4444"
_COLOR_ELEVATED_BG  = "rgba(220, 10, 10, 1.0)"
_COLOR_ELEVATED_BORDER = "#ff6666"
_COLOR_TEXT        = "#f8fafc"

_STYLE_NORMAL = (
    f"QPushButton {{"
    f"  background-color: {_COLOR_NORMAL_BG};"
    f"  border: 2px solid {_COLOR_NORMAL_BORDER};"
    f"  border-radius: 88px;"
    f"  color: {_COLOR_TEXT};"
    f"  font-size: 26px;"
    f"  font-weight: 700;"
    f"  padding: 0px;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: rgba(210, 30, 30, 1.0);"
    f"  border: 2px solid #ff8888;"
    f"}}"
)

_STYLE_ELEVATED = (
    f"QPushButton {{"
    f"  background-color: {_COLOR_ELEVATED_BG};"
    f"  border: 3px solid {_COLOR_ELEVATED_BORDER};"
    f"  border-radius: 88px;"
    f"  color: {_COLOR_TEXT};"
    f"  font-size: 26px;"
    f"  font-weight: 700;"
    f"  padding: 0px;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: rgba(240, 20, 20, 1.0);"
    f"  border: 3px solid #ffaaaa;"
    f"}}"
)

_OPACITY_DEFAULT = 0.45
_OPACITY_HOVER   = 1.0

_WIDTH  = 176
_HEIGHT = 176
_MARGIN = 20  # px from screen edge


class PanicButton(QWidget):
    """Small frameless floating button.  Emits ``panic_requested`` on click."""

    panic_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_WIDTH, _HEIGHT)

        self._btn = QPushButton("NO", self)
        self._btn.setFixedSize(_WIDTH, _HEIGHT)
        self._btn.setStyleSheet(_STYLE_NORMAL)
        self._btn.clicked.connect(self.panic_requested)

        self.setWindowOpacity(_OPACITY_DEFAULT)

        self._position_bottom_right()
        self.show()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_elevated(self, elevated: bool) -> None:
        """Switch between normal and danger-accent styling."""
        self._btn.setStyleSheet(_STYLE_ELEVATED if elevated else _STYLE_NORMAL)

    # ------------------------------------------------------------------
    # Hover — opacity toggle
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        self.setWindowOpacity(_OPACITY_HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setWindowOpacity(_OPACITY_DEFAULT)
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _position_bottom_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.right() - _WIDTH  - _MARGIN
        y = geo.bottom() - _HEIGHT - _MARGIN
        self.move(x, y)
