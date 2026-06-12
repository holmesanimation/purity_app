"""Commitment question dialog — shown before the internet session opens.

Displays the ``question`` field from a saved encouragement and asks the user
to affirm it with Yes (green) or decline with No (red).  The caller should
check ``dlg.exec() == QDialog.DialogCode.Accepted`` to decide whether to
proceed with opening the internet.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
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
    FONT_FAMILY,
    FONT_SIZE_NORMAL,
)


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


class EncouragementQuestionDialog(QDialog):
    """Yes / No commitment dialog driven by a question string.

    Parameters
    ----------
    question:
        The question text to display (from the encouragement's ``question`` field).
    parent:
        Optional Qt parent widget.
    """

    def __init__(
        self,
        *,
        question: str,
        parent: Optional[QWidget] = None,
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

        self._overlay: Optional[_ScreenDimOverlay] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(20)

        # ── Question label ────────────────────────────────────────────
        question_lbl = QLabel(question)
        question_lbl.setWordWrap(True)
        question_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        question_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: 17pt; font-weight: 700; background: transparent;"
        )
        root.addWidget(question_lbl)

        # ── Yes / No buttons ─────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(16)

        yes_btn = QPushButton("Yes")
        yes_btn.setMinimumHeight(48)
        yes_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: #2e7d32;"
            f"  color: #ffffff;"
            f"  border: none; border-radius: 8px;"
            f"  font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt; font-weight: 700;"
            f"  padding: 10px 32px;"
            f"}}"
            f"QPushButton:hover {{ background-color: #388e3c; }}"
        )
        yes_btn.clicked.connect(self.accept)

        no_btn = QPushButton("No")
        no_btn.setMinimumHeight(48)
        no_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: #c62828;"
            f"  color: #ffffff;"
            f"  border: none; border-radius: 8px;"
            f"  font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt; font-weight: 700;"
            f"  padding: 10px 32px;"
            f"}}"
            f"QPushButton:hover {{ background-color: #d32f2f; }}"
        )
        no_btn.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(yes_btn)
        btn_row.addWidget(no_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self.setFixedWidth(480)
        self.adjustSize()
        self._center_on_screen()

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------

    def _center_on_screen(self) -> None:
        from PySide6.QtGui import QScreen
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
