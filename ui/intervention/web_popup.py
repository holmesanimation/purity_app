from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt
from ui.intervention.base_popup import BasePopup
from services.browser_session import parse_allowed_urls
from styles.theme import (
    COLOR_TEXT_MUTED, COLOR_WARNING, COLOR_SURFACE_2, COLOR_TEXT,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM,
)

_CHOICES = [
    ("Work", True),
    ("Research", True),
    ("Entertainment", True),
    ("Bored", False),
    ("Tempted", False),
    ("I don't know", False),
]

_REDIRECT_MSG = (
    "That's okay. Consider stepping away for 5 minutes,\n"
    "saying a quick prayer, or texting a friend instead."
)


def is_permitted_web_choice(label: str) -> bool:
    for choice_label, is_permitted in _CHOICES:
        if choice_label == label:
            return is_permitted
    return False


_TIME_OPTIONS = [
    ("5m", 5 * 60),
    ("10m", 10 * 60),
    ("15m", 15 * 60),
    ("30m", 30 * 60),
    ("1h", 60 * 60),
]


_PREV_URLS_PANEL_WIDTH = 210


class WebSessionConfigPopup(BasePopup):
    DEFAULT_WIDTH = 680
    DEFAULT_HEIGHT = 380

    def __init__(self, *, choice_label: str, parent=None, data_root: Path | None = None):
        super().__init__("Why this is okay right now", parent)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.choice_label = str(choice_label)
        self.allowed_urls: list[str] = []
        self.duration_seconds = _TIME_OPTIONS[0][1]

        if data_root is not None:
            from services.url_history import UrlHistory
            self._url_history: UrlHistory | None = UrlHistory(data_root)
        else:
            self._url_history = None

        self._build_ui()

    def _build_ui(self) -> None:
        # ── Two-column horizontal split ──────────────────────────────
        h_split = QHBoxLayout()
        h_split.setContentsMargins(0, 0, 0, 0)
        h_split.setSpacing(14)
        self.body_layout.addLayout(h_split)

        # ── Left column ──────────────────────────────────────────────
        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        h_split.addLayout(left_col, stretch=1)

        choice_lbl = QLabel(f"Choice: {self.choice_label}")
        choice_lbl.setWordWrap(True)
        choice_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        left_col.addWidget(choice_lbl)

        urls_lbl = QLabel("URLs")
        urls_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
        )
        left_col.addWidget(urls_lbl)

        self._urls_edit = QPlainTextEdit()
        self._urls_edit.setPlaceholderText("https://example.com\nhttps://docs.python.org/3/")
        self._urls_edit.setMinimumHeight(130)
        self._urls_edit.textChanged.connect(self._sync_commit_enabled)
        left_col.addWidget(self._urls_edit)

        self._validation_lbl = QLabel("")
        self._validation_lbl.setWordWrap(True)
        self._validation_lbl.setStyleSheet(
            f"color: {COLOR_WARNING}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self._validation_lbl.hide()
        left_col.addWidget(self._validation_lbl)

        time_lbl = QLabel("Time")
        time_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
        )
        left_col.addWidget(time_lbl)

        self._time_combo = QComboBox()
        for label, seconds in _TIME_OPTIONS:
            self._time_combo.addItem(label, seconds)
        left_col.addWidget(self._time_combo)

        # ── Right column — Previous URLs ─────────────────────────────
        right_widget = QWidget()
        right_widget.setFixedWidth(_PREV_URLS_PANEL_WIDTH)
        right_col = QVBoxLayout(right_widget)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(6)
        h_split.addWidget(right_widget, stretch=0)

        prev_title = QLabel("Previous URLs")
        prev_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent; font-weight: 600;"
        )
        right_col.addWidget(prev_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 4, 0)
        scroll_layout.setSpacing(4)

        top_urls = self._url_history.get_top_urls(6) if self._url_history is not None else []
        for url in top_urls:
            btn = QPushButton(url)
            btn.setToolTip(url)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {COLOR_SURFACE_2};"
                f"  color: {COLOR_TEXT};"
                f"  border: 1px solid #DDD8CF;"
                f"  border-radius: 4px;"
                f"  padding: 5px 8px;"
                f"  font-family: '{FONT_FAMILY}';"
                f"  font-size: {FONT_SIZE_SMALL}pt;"
                f"  text-align: left;"
                f"}}"
                f"QPushButton:hover {{ background-color: #E8E2D8; }}"
            )
            btn.clicked.connect(lambda checked, u=url: self._add_url_to_edit(u))
            scroll_layout.addWidget(btn)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        right_col.addWidget(scroll)

        # ── Button row ───────────────────────────────────────────────
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.button_row.addWidget(cancel_btn)

        self._ok_btn = QPushButton("Ok")
        self._ok_btn.setDefault(True)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._on_commit)
        self.button_row.addWidget(self._ok_btn)
        self.button_row.addStretch()

    def _add_url_to_edit(self, url: str) -> None:
        """Append *url* to the text edit if it is not already present."""
        current = self._urls_edit.toPlainText()
        existing = {line.strip() for line in current.splitlines() if line.strip()}
        if url in existing:
            return
        if current.strip():
            self._urls_edit.setPlainText(current.rstrip("\n") + "\n" + url)
        else:
            self._urls_edit.setPlainText(url)

    def _sync_commit_enabled(self) -> None:
        has_urls = bool(self._urls_edit.toPlainText().strip())
        self._ok_btn.setEnabled(has_urls)
        if has_urls:
            self._validation_lbl.hide()

    def _on_commit(self) -> None:
        try:
            self.allowed_urls = parse_allowed_urls(self._urls_edit.toPlainText())
        except ValueError as exc:
            self._validation_lbl.setText(str(exc))
            self._validation_lbl.show()
            self.allowed_urls = []
            return
        if not self.allowed_urls:
            self._sync_commit_enabled()
            return
        self.duration_seconds = int(self._time_combo.currentData())
        self.accept()


class WebPopup(BasePopup):
    DEFAULT_WIDTH         = 400
    DEFAULT_HEIGHT        = 340
    DEFAULT_HEIGHT_BLOCKED = 200

    def __init__(self, permitted: bool = True, parent=None, data_root: Path | None = None):
        title = "You opened a web browser. Why?" if permitted else "Browser Blocked"
        super().__init__(title, parent)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.selected_choice = ""
        self.reason_text = ""
        self.allowed_urls: list[str] = []
        self.duration_seconds: int = _TIME_OPTIONS[0][1]
        self._data_root = data_root
        height = self.DEFAULT_HEIGHT if permitted else self.DEFAULT_HEIGHT_BLOCKED
        self.setFixedSize(self.DEFAULT_WIDTH, height)
        if permitted:
            self._build_choices()
        else:
            self._build_blocked()

    # ------------------------------------------------------------------
    # Permitted browser — ask why
    # ------------------------------------------------------------------

    def _build_choices(self):
        self._redirect_lbl = QLabel("")
        self._redirect_lbl.setWordWrap(True)
        self._redirect_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._redirect_lbl.setStyleSheet(
            f"color: {COLOR_WARNING}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self._redirect_lbl.hide()
        self.body_layout.addWidget(self._redirect_lbl)

        for label, is_permitted in _CHOICES:
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {COLOR_SURFACE_2};"
            f"  color: {'#2D2926' if is_permitted else '#C47C2B'};"
                f"  border: 1px solid #DDD8CF;"
                f"  border-radius: 6px;"
                f"  padding: 7px 12px;"
                f"  font-family: '{FONT_FAMILY}';"
                f"  font-size: {FONT_SIZE_NORMAL}pt;"
                f"  text-align: left;"
                f"}}"
                f"QPushButton:hover {{ background-color: #E8E2D8; }}"
            )
            btn.clicked.connect(
                lambda checked, permitted=is_permitted, lbl=label: self._on_choice(permitted, lbl)
            )
            self.body_layout.addWidget(btn)

    def _on_choice(self, is_permitted: bool, label: str):
        self.selected_choice = label
        self.reason_text = ""
        if not is_permitted:
            self._redirect_lbl.setText(_REDIRECT_MSG)
            self._redirect_lbl.show()
            self.reject()
            return

        session_popup = WebSessionConfigPopup(choice_label=label, parent=self, data_root=self._data_root)
        session_popup.move(self.pos())
        if session_popup.exec() == self.DialogCode.Accepted:
            self.allowed_urls = list(session_popup.allowed_urls)
            self.duration_seconds = int(session_popup.duration_seconds)
            self.reason_text = "\n".join(self.allowed_urls)
            self.accept()
            return

        self.reject()

    # ------------------------------------------------------------------
    # Blocked browser — inform and dismiss
    # ------------------------------------------------------------------

    def _build_blocked(self):
        lbl = QLabel("This browser is not permitted.")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; background: transparent;"
        )
        self.body_layout.addWidget(lbl)

        btn = QPushButton("Dismiss")
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_SURFACE_2};"
            f"  color: #2D2926;"
            f"  border: 1px solid #DDD8CF;"
            f"  border-radius: 6px;"
            f"  padding: 7px 12px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"}}"
            f"QPushButton:hover {{ background-color: #E8E2D8; }}"
        )
        btn.clicked.connect(self.reject)
        self.body_layout.addWidget(btn)
