"""Left-edge sliding dashboard overlay.

A frameless, always-on-top panel that docks to the left side of the primary
monitor.  It animates between:

  • Collapsed — a 2 px accent-coloured strip, plus a 20 px wide semicircular
    tab button centred vertically on the right edge.
  • Expanded  — a 1 000 px wide panel (content area to be added later), with
    the same tab button now at the right edge of the full panel.

Clicking the tab toggles between the two states.
"""

from __future__ import annotations

import math

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
    Property,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget

from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_DARK,
    COLOR_ACCENT_LIGHT,
    COLOR_BORDER,
    COLOR_SURFACE,
)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

_EXPANDED_CONTENT_W: int = 1000   # px — width of the content area when open
_COLLAPSED_CONTENT_W: int = 2     # px — width of the visible strip when closed

_TAB_W: int = 20                  # px — width of the semicircle tab
_TAB_H: int = 60                  # px — total height of the tab (elliptic D shape)

_ANIM_MS: int = 300               # animation duration in milliseconds

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

_C_PANEL = QColor(COLOR_SURFACE)
_C_STRIP = QColor(COLOR_ACCENT)
_C_TAB = QColor(COLOR_ACCENT)
_C_TAB_HOVER = QColor(COLOR_ACCENT_DARK)
_C_ARROW = QColor("#ffffff")


# ---------------------------------------------------------------------------
# Semicircle tab button
# ---------------------------------------------------------------------------

class _TabButton(QWidget):
    """Custom-painted semicircle handle on the right edge of the dashboard."""

    def __init__(self, on_click, parent: QWidget) -> None:
        super().__init__(parent)
        self._on_click = on_click
        self._hovered = False
        self._expanded = False
        self.setFixedSize(_TAB_W, _TAB_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # -- public API --------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.update()

    # -- paint -------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # D-shape: flat left edge, elliptic right bulge.
        # The bounding ellipse spans [-_TAB_W, 0, _TAB_W*2, _TAB_H].
        # arcTo with startAngle=90, spanAngle=-180 sweeps clockwise from the
        # top-centre (0, 0) through the rightmost point to the bottom-centre
        # (0, _TAB_H); closeSubpath draws the flat left edge.
        path = QPainterPath()
        path.moveTo(0, 0)
        path.arcTo(QRectF(-_TAB_W, 0, _TAB_W * 2, _TAB_H), 90.0, -180.0)
        path.closeSubpath()

        color = _C_TAB_HOVER if self._hovered else _C_TAB
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        # Chevron arrow — right-pointing when collapsed, left-pointing when
        # expanded — drawn in the right half of the tab.
        self._draw_chevron(painter)

        painter.end()

    def _draw_chevron(self, painter: QPainter) -> None:
        """Paint a small arrow in the centre of the visible bulge area."""
        cx = _TAB_W * 0.60          # horizontal centre of the bulge region
        cy = _TAB_H / 2.0
        arm = 6.0                    # half-height of chevron arms
        tip = 5.0                    # horizontal depth of the point

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_C_ARROW)

        arrow = QPainterPath()
        if not self._expanded:
            # Right-pointing >
            arrow.moveTo(cx - tip / 2, cy - arm)
            arrow.lineTo(cx + tip / 2, cy)
            arrow.lineTo(cx - tip / 2, cy + arm)
            arrow.closeSubpath()
        else:
            # Left-pointing <
            arrow.moveTo(cx + tip / 2, cy - arm)
            arrow.lineTo(cx - tip / 2, cy)
            arrow.lineTo(cx + tip / 2, cy + arm)
            arrow.closeSubpath()

        painter.drawPath(arrow)

    # -- events ------------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()


# ---------------------------------------------------------------------------
# Dashboard window
# ---------------------------------------------------------------------------

class LeftDockDashboard(QWidget):
    """Sliding dashboard docked to the left edge of the primary monitor.

    Instantiate and keep a strong reference; the widget manages its own
    geometry based on the primary screen.  No Qt parent is required — the
    caller typically stores it as ``self._left_dock``.
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )

        self._expanded: bool = False
        self._content_w: int = _COLLAPSED_CONTENT_W

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._tab = _TabButton(on_click=self._toggle, parent=self)

        # Content panel — sits within the _content_w area, holds dashboard widgets.
        self._content_panel = QWidget(self)
        self._content_panel.setObjectName("dashboardContent")

        self._scroll = QScrollArea(self._content_panel)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)

        from ui.verse_memory_widget import VerseMemoryWidget
        self._verse_widget = VerseMemoryWidget(parent=inner)
        inner_layout.addWidget(self._verse_widget)
        inner_layout.addStretch()

        self._scroll.setWidget(inner)

        panel_layout = QVBoxLayout(self._content_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        panel_layout.addWidget(self._scroll)

        self._anim = QPropertyAnimation(self, b"content_width", self)

        # Periodically re-assert topmost status — Windows can silently demote
        # a WindowStaysOnTopHint window when other apps steal focus.
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(1_000)

        self._sync_geometry()

    # -- animated property -------------------------------------------------

    def _get_content_width(self) -> int:
        return self._content_w

    def _set_content_width(self, value: int) -> None:
        self._content_w = value
        self._sync_geometry()
        self.update()

    content_width = Property(int, _get_content_width, _set_content_width)

    # -- geometry ----------------------------------------------------------

    def _sync_geometry(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        total_w = self._content_w + _TAB_W
        self.setGeometry(screen.left(), screen.top(), total_w, screen.height())
        tab_y = (screen.height() - _TAB_H) // 2
        self._tab.move(self._content_w, tab_y)
        # Keep content panel sized to the content area (never overlaps the tab).
        if hasattr(self, "_content_panel"):
            self._content_panel.setGeometry(0, 0, self._content_w, screen.height())
            self._content_panel.setVisible(self._content_w > _COLLAPSED_CONTENT_W)

    # -- topmost enforcement -----------------------------------------------

    def _reassert_topmost(self) -> None:
        """Re-raise the window so it stays above all non-topmost windows."""
        self.raise_()

    # -- toggle ------------------------------------------------------------

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._tab.set_expanded(self._expanded)
        self._anim.stop()
        self._anim.setStartValue(self._content_w)
        if self._expanded:
            # Snap open immediately, then ease gently into the final position.
            self._anim.setDuration(620)
            self._anim.setEasingCurve(QEasingCurve.Type.OutExpo)
            self._anim.setEndValue(_EXPANDED_CONTENT_W)
        else:
            # Ease out slowly at first, then close with a gentle snap.
            self._anim.setDuration(300)
            self._anim.setEasingCurve(QEasingCurve.Type.InQuart)
            self._anim.setEndValue(_COLLAPSED_CONTENT_W)
        self._anim.start()

    # -- paint -------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self._content_w
        h = self.height()

        if w <= _COLLAPSED_CONTENT_W:
            # Collapsed: just the accent strip.
            painter.fillRect(0, 0, w, h, _C_STRIP)
        else:
            # Expanded: full panel background with a right border line.
            painter.fillRect(0, 0, w, h, _C_PANEL)
            painter.fillRect(w - 1, 0, 1, h, QColor(COLOR_BORDER))

        painter.end()
