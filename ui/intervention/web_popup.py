from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton
from PySide6.QtCore import Qt
from ui.intervention.base_popup import BasePopup
from styles.theme import (
    COLOR_TEXT_MUTED, COLOR_WARNING, COLOR_SURFACE_2, COLOR_TEXT,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM,
)

_CHOICES = [
    ("Work", True),
    ("Research", True),
    ("Entertainment", False),
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


class WebReasonPopup(BasePopup):
    DEFAULT_WIDTH = 420
    DEFAULT_HEIGHT = 300

    def __init__(self, *, choice_label: str, parent=None):
        super().__init__("Why this is okay right now", parent)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.choice_label = str(choice_label)
        self.reason_text = ""
        self._build_ui()

    def _build_ui(self) -> None:
        choice_lbl = QLabel(f"Choice: {self.choice_label}")
        choice_lbl.setWordWrap(True)
        choice_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self.body_layout.addWidget(choice_lbl)

        reason_lbl = QLabel("Reason:")
        reason_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
        )
        self.body_layout.addWidget(reason_lbl)

        self._reason_edit = QPlainTextEdit()
        self._reason_edit.setPlaceholderText("Write why you are opening the web right now...")
        self._reason_edit.setMinimumHeight(120)
        self._reason_edit.textChanged.connect(self._sync_commit_enabled)
        self.body_layout.addWidget(self._reason_edit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.button_row.addWidget(cancel_btn)

        self._commit_btn = QPushButton("Commit")
        self._commit_btn.setDefault(True)
        self._commit_btn.setEnabled(False)
        self._commit_btn.clicked.connect(self._on_commit)
        self.button_row.addWidget(self._commit_btn)
        self.button_row.addStretch()

    def _sync_commit_enabled(self) -> None:
        self._commit_btn.setEnabled(bool(self._reason_edit.toPlainText().strip()))

    def _on_commit(self) -> None:
        self.reason_text = self._reason_edit.toPlainText().strip()
        if not self.reason_text:
            self._sync_commit_enabled()
            return
        self.accept()


class WebPopup(BasePopup):
    DEFAULT_WIDTH         = 400
    DEFAULT_HEIGHT        = 340
    DEFAULT_HEIGHT_BLOCKED = 200

    def __init__(self, permitted: bool = True, parent=None):
        title = "You opened a web browser. Why?" if permitted else "Browser Blocked"
        super().__init__(title, parent)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.selected_choice = ""
        self.reason_text = ""
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

        reason_popup = WebReasonPopup(choice_label=label, parent=self)
        reason_popup.move(self.pos())
        if reason_popup.exec() == self.DialogCode.Accepted:
            self.reason_text = reason_popup.reason_text
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
