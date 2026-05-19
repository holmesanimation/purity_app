import uuid
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTextEdit,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QSizePolicy,
)
from PySide6.QtCore import Qt
from services.fake_journal import FakeJournalService
from models.journal import JournalEntry
from styles.theme import (
    COLOR_TEXT_MUTED, COLOR_SURFACE, COLOR_BORDER,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL,
)

_GUIDED_QUESTIONS = [
    "How are you feeling right now?",
    "Was there a moment of struggle or temptation today?",
    "What good thing did you do for your soul today?",
]


class JournalPanel(QWidget):
    def __init__(self, journal_service: FakeJournalService, parent=None):
        super().__init__(parent)
        self._svc = journal_service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_guided_tab(), "Guided Check-In")
        self._tabs.addTab(self._build_free_tab(), "Free Journal")
        self._tabs.addTab(self._build_history_tab(), "History")

    # ── Tab builders ──────────────────────────────────────────────

    def _build_guided_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(8)

        self._guided_inputs: list[QTextEdit] = []
        for q in _GUIDED_QUESTIONS:
            lbl = QLabel(q)
            lbl.setStyleSheet(
                f"font-weight: 600; color: {COLOR_TEXT_MUTED};"
                f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
            )
            lbl.setWordWrap(True)
            vbox.addWidget(lbl)

            ta = QTextEdit()
            ta.setFixedHeight(56)
            ta.setPlaceholderText("Your response…")
            vbox.addWidget(ta)
            self._guided_inputs.append(ta)

        save_btn = QPushButton("Save Check-In")
        save_btn.setFixedWidth(160)
        save_btn.clicked.connect(self._save_guided)
        vbox.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignRight)
        vbox.addStretch()
        return w

    def _build_free_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(8)

        self._free_timestamp_lbl = QLabel(self._now_str())
        self._free_timestamp_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        vbox.addWidget(self._free_timestamp_lbl)

        self._free_input = QTextEdit()
        self._free_input.setPlaceholderText("Write freely…")
        vbox.addWidget(self._free_input)

        save_btn = QPushButton("Save Journal Entry")
        save_btn.setFixedWidth(180)
        save_btn.clicked.connect(self._save_free)
        vbox.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignRight)
        return w

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(4)

        self._history_list = QListWidget()
        self._history_list.setSpacing(2)
        vbox.addWidget(self._history_list)

        self._populate_history()
        return w

    # ── Actions ───────────────────────────────────────────────────

    def _save_guided(self):
        responses = [ta.toPlainText().strip() for ta in self._guided_inputs]
        if not any(responses):
            return
        entry = JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            entry_type="guided_checkin",
            responses=responses,
        )
        self._svc.append(entry)
        for ta in self._guided_inputs:
            ta.clear()
        self._populate_history()
        # Switch to History tab to show the result
        self._tabs.setCurrentIndex(2)

    def _save_free(self):
        text = self._free_input.toPlainText().strip()
        if not text:
            return
        entry = JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            entry_type="free_journal",
            free_text=text,
        )
        self._svc.append(entry)
        self._free_input.clear()
        self._free_timestamp_lbl.setText(self._now_str())
        self._populate_history()
        self._tabs.setCurrentIndex(2)

    def _populate_history(self):
        self._history_list.clear()
        for entry in self._svc.get_all():
            ts = entry.timestamp.strftime("%b %d, %Y  %H:%M")
            if entry.entry_type == "guided_checkin":
                preview = " | ".join(r for r in entry.responses if r)[:80]
                label = f"[Check-In]  {ts}\n{preview}"
            else:
                preview = (entry.free_text or "")[:80]
                label = f"[Journal]  {ts}\n{preview}"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._history_list.addItem(item)

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%B %d, %Y  %H:%M")
