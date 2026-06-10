from __future__ import annotations

import random
from typing import Callable, Optional

_GOD_ADJECTIVES = [
    "Great", "Beautiful", "Kind", "Gracious", "Thoughtful", "Wise", "Pure", "Loving"
]

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QScreen
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from styles.theme import (
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
)

_FS_REASON_TITLE = 11
_FS_REASON_TEXT = 13
_FS_QUESTION = 16
_FS_GOD_IS_GREAT = 38
_FS_REACH_OUT = 14


class _ScreenDimOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 190))


class WebSessionHonorDialog(QDialog):
    """Post-session accountability check: did you honour Jesus online?

    Usage::

        dlg = WebSessionHonorDialog(
            reason="I was looking up Bible verses",
            reach_out_callback=some_callable,
        )
        dlg.exec()
    """

    def __init__(
        self,
        *,
        reason: str,
        reach_out_callback: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(
            f"QDialog {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 2px solid {COLOR_BORDER};"
            f"  border-radius: 14px;"
            f"}}"
        )

        self._reach_out_callback = reach_out_callback
        self._fade_anim: Optional[QPropertyAnimation] = None
        self._overlay: Optional[_ScreenDimOverlay] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(14)

        # ── Reason label ──────────────────────────────────────────────
        self._reason_title_lbl = QLabel("Your reason for going online:")
        self._reason_title_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {_FS_REASON_TITLE}pt; background: transparent;"
        )
        root.addWidget(self._reason_title_lbl)

        self._reason_lbl = QLabel(reason or "(no reason recorded)")
        self._reason_lbl.setWordWrap(True)
        self._reason_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {_FS_REASON_TEXT}pt; font-style: italic; background: transparent;"
        )
        root.addWidget(self._reason_lbl)

        root.addSpacing(6)

        # ── Question ─────────────────────────────────────────────────
        self._question_lbl = QLabel("Did you honor Jesus online?")
        self._question_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._question_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {_FS_QUESTION}pt; font-weight: 700; background: transparent;"
        )
        root.addWidget(self._question_lbl)

        root.addSpacing(4)

        # ── Yes / No buttons ─────────────────────────────────────────
        self._btn_row_widget = QWidget()
        self._btn_row_widget.setStyleSheet("background: transparent;")
        btn_row = QHBoxLayout(self._btn_row_widget)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(16)

        self._yes_btn = QPushButton("Yes")
        self._yes_btn.setMinimumHeight(44)
        self._yes_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: #2e7d32;"
            f"  color: #ffffff;"
            f"  border: none; border-radius: 8px;"
            f"  font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt; font-weight: 700;"
            f"  padding: 8px 24px;"
            f"}}"
            f"QPushButton:hover {{ background-color: #388e3c; }}"
        )
        self._yes_btn.clicked.connect(self._on_yes)

        self._no_btn = QPushButton("No")
        self._no_btn.setMinimumHeight(44)
        self._no_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: #c62828;"
            f"  color: #ffffff;"
            f"  border: none; border-radius: 8px;"
            f"  font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt; font-weight: 700;"
            f"  padding: 8px 24px;"
            f"}}"
            f"QPushButton:hover {{ background-color: #d32f2f; }}"
        )
        self._no_btn.clicked.connect(self._on_no)

        btn_row.addStretch()
        btn_row.addWidget(self._yes_btn)
        btn_row.addWidget(self._no_btn)
        btn_row.addStretch()
        root.addWidget(self._btn_row_widget)

        # ── "God is …!" label (hidden until Yes) ─────────────────
        self._god_great_lbl = QLabel(f"God is {random.choice(_GOD_ADJECTIVES)}!")
        self._god_great_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._god_great_lbl.setStyleSheet(
            f"color: #2e7d32; font-family: '{FONT_FAMILY}';"
            f"font-size: {_FS_GOD_IS_GREAT}pt; font-weight: 800; background: transparent;"
        )
        self._god_great_lbl.hide()
        root.addWidget(self._god_great_lbl)

        # ── Reach-out section (hidden until No) ──────────────────────
        self._reach_out_widget = QWidget()
        self._reach_out_widget.setStyleSheet("background: transparent;")
        ro_layout = QVBoxLayout(self._reach_out_widget)
        ro_layout.setContentsMargins(0, 0, 0, 0)
        ro_layout.setSpacing(12)

        ro_lbl = QLabel("You should reach out to the group…")
        ro_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ro_lbl.setWordWrap(True)
        ro_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {_FS_REACH_OUT}pt; background: transparent;"
        )
        ro_layout.addWidget(ro_lbl)

        ro_btn_row = QHBoxLayout()
        ro_btn_row.setContentsMargins(0, 0, 0, 0)
        ro_btn_row.setSpacing(10)

        self._reach_out_btn = QPushButton("Reach Out")
        self._reach_out_btn.setMinimumHeight(44)
        self._reach_out_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: #1565c0;"
            f"  color: #ffffff;"
            f"  border: none; border-radius: 8px;"
            f"  font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt; font-weight: 700;"
            f"  padding: 8px 24px;"
            f"}}"
            f"QPushButton:hover {{ background-color: #1976d2; }}"
        )
        self._reach_out_btn.clicked.connect(self._on_reach_out)

        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(44)
        close_btn.setFixedWidth(72)  # ~half the Reach Out button width
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_BORDER};"
            f"  color: {COLOR_TEXT_MUTED};"
            f"  border: none; border-radius: 8px;"
            f"  font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"  padding: 8px 10px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {COLOR_SURFACE}; }}"
        )
        close_btn.clicked.connect(self.reject)

        ro_btn_row.addStretch()
        ro_btn_row.addWidget(self._reach_out_btn)
        ro_btn_row.addWidget(close_btn)
        ro_btn_row.addStretch()
        ro_layout.addLayout(ro_btn_row)

        self._reach_out_widget.hide()
        root.addWidget(self._reach_out_widget)

        self.setFixedWidth(480)
        self.adjustSize()
        self._center_on_screen()

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _center_on_screen(self) -> None:
        screen: Optional[QScreen] = QApplication.primaryScreen()
        if screen is None:
            return
        self.adjustSize()
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    # ------------------------------------------------------------------
    # Overlay lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        if self._overlay is None:
            self._overlay = _ScreenDimOverlay()
            self._overlay.show()
        self.raise_()
        super().showEvent(event)

    def done(self, result: int) -> None:
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        super().done(result)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_yes(self) -> None:
        # Hide everything except the God is … label
        self._reason_title_lbl.hide()
        self._reason_lbl.hide()
        self._question_lbl.hide()
        self._btn_row_widget.hide()
        self._reach_out_widget.hide()

        # Resize to a compact square so the label fills it
        self.setFixedSize(480, 200)
        self._god_great_lbl.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._god_great_lbl.show()
        self._center_on_screen()

        opacity_effect = QGraphicsOpacityEffect(self._god_great_lbl)
        opacity_effect.setOpacity(1.0)
        self._god_great_lbl.setGraphicsEffect(opacity_effect)

        self._fade_anim = QPropertyAnimation(opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(1_000)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_anim.finished.connect(self.accept)
        QTimer.singleShot(2_000, self._fade_anim.start)

    def _on_no(self) -> None:
        self._btn_row_widget.hide()
        self._reach_out_widget.show()
        self.adjustSize()
        self._center_on_screen()

    def _on_reach_out(self) -> None:
        self._reach_out_btn.setEnabled(False)
        self._reach_out_btn.setText("Sent ✓")
        if self._reach_out_callback is not None:
            self._reach_out_callback()
