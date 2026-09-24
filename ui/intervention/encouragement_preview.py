"""Shared helper to show a single encouragement as a blocking banner dialog.

Mirrors the "Preview Encouragement" button in the encouragement editor, so
the same visual presentation can be reused from other flows (e.g. the
web-launch flow in ``ui/main_window.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

_BACKGROUNDS_DIR = Path("G:/PURITY_APP/images/backgrounds")


class _BackgroundOverlay(QWidget):
    """Full-screen dim + optional background-image overlay."""

    def __init__(self, image_path: Optional[Path]) -> None:
        super().__init__(
            None,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._pixmap = QPixmap(str(image_path)) if image_path is not None else QPixmap()
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 190))
        if not self._pixmap.isNull():
            pw, ph = self._pixmap.width(), self._pixmap.height()
            if pw > self.width() or ph > self.height():
                pix = self._pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            else:
                pix = self._pixmap
            x = (self.width() - pix.width()) // 2
            y = (self.height() - pix.height()) // 2
            painter.drawPixmap(x, y, pix)


def show_encouragement_preview(
    reminder: dict,
    bible_library: object,
    parent: Optional[QWidget] = None,
) -> None:
    """Show *reminder* as a single-button banner dialog; blocks until dismissed."""
    from ui.intervention.panic_reason_dialog import PanicReasonDialog

    data = dict(reminder)
    data["note"] = ""

    bg_overlay: Optional[_BackgroundOverlay] = None
    bg_name = data.get("background")
    if bg_name:
        image_path = _BACKGROUNDS_DIR / bg_name
        if image_path.exists():
            bg_overlay = _BackgroundOverlay(image_path)
            bg_overlay.show()

    dlg = PanicReasonDialog(stats=None, reminder=data, bible_library=bible_library, parent=parent)

    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.FramelessWindowHint)
    if bg_overlay is not None:
        dlg._overlay = bg_overlay
    dlg._grid_widget.hide()
    dlg._help_btn.hide()
    dlg._feeling_btn.clicked.disconnect(dlg._reveal_feelings)
    dlg._feeling_btn.setText(data.get("question") or "(No question set)")
    dlg._feeling_btn.clicked.connect(dlg.accept)

    try:
        dlg.exec()
    finally:
        if bg_overlay is not None:
            bg_overlay.hide()
            bg_overlay.deleteLater()
