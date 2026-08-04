"""Internet Settings dialog — manage the permanent URL blacklist.

Opened from Tools → Internet Settings in the main window.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.internet_settings import InternetSettingsService
from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_DARK,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_2,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
    FONT_SIZE_MEDIUM,
)


class InternetSettingsDialog(QDialog):
    """Dialog that lets the user edit the permanent URL blacklist."""

    def __init__(
        self,
        internet_settings_service: InternetSettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = internet_settings_service
        self.setWindowTitle("Internet Settings")
        self.setMinimumWidth(480)
        self.setMinimumHeight(400)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self._build_ui()
        self._load()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Blacklisted URLs")
        title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700;"
        )
        layout.addWidget(title)

        description = QLabel(
            "Enter one domain or URL per line. The Chrome extension will block "
            "all navigation to these domains."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt;"
        )
        layout.addWidget(description)

        self._edit = QTextEdit()
        self._edit.setPlaceholderText(
            "example.com\n"
            "bad-site.net\n"
            "# Lines starting with # are ignored"
        )
        self._edit.setStyleSheet(
            f"QTextEdit {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 4px;"
            f"  color: {COLOR_TEXT};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  padding: 6px;"
            f"}}"
        )
        layout.addWidget(self._edit, stretch=1)

        hint = QLabel(
            "Plain hostnames (example.com) and full URLs are both accepted."
        )
        hint.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; font-style: italic;"
        )
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_SURFACE_2};"
            f"  color: {COLOR_TEXT};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 7px 16px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"}}"
            f"QPushButton:hover {{ background-color: {COLOR_SURFACE}; }}"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_ACCENT};"
            f"  color: #ffffff;"
            f"  border: none;"
            f"  border-radius: 6px;"
            f"  padding: 7px 20px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  font-weight: 700;"
            f"}}"
            f"QPushButton:hover {{ background-color: {COLOR_ACCENT_DARK}; }}"
        )
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        domains = self._service.load_user_domains()
        self._edit.setPlainText("\n".join(domains))

    def _on_save(self) -> None:
        raw = self._edit.toPlainText()
        domains = self._service.parse_raw_input(raw)
        self._service.save_blacklisted_domains(domains)
        self.accept()
