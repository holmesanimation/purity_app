from __future__ import annotations

import difflib
import random
import re
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from ui.intervention.base_popup import BasePopup
from ui.intervention.recovery_note_card import RecoveryNoteCard, CARD_WIDTH, CARD_HEIGHT
from styles.theme import (
    COLOR_ACCENT, COLOR_ACCENT_DARK,
    COLOR_BORDER, COLOR_SURFACE, COLOR_SURFACE_2, COLOR_SURFACE_3,
    COLOR_TEXT, COLOR_TEXT_MUTED,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM, FONT_SIZE_LARGE,
)

# ---------------------------------------------------------------------------
# Banner font sizes  (matching PanicReasonDialog)
# ---------------------------------------------------------------------------

_FS_REMINDER_TITLE = 24
_FS_REMINDER_NOTE  = 16
_FS_REMINDER_VERSE = 16
_FS_SECTION_HEADER = 13
_FS_FEELING_BTN    = 11

# ---------------------------------------------------------------------------
# Card orbit slots  (identical logic to PanicReasonDialog)
# ---------------------------------------------------------------------------

_SLOT_COUNT = 10
_CARD_GAP   = 18


def _compute_slots(dialog_geo: QRect) -> list[QPoint]:
    x, y = dialog_geo.left(), dialog_geo.top()
    w, h = dialog_geo.width(), dialog_geo.height()
    cw, ch = CARD_WIDTH, CARD_HEIGHT
    g = _CARD_GAP
    mid_y = y + (h - ch) // 2
    return [
        QPoint(x + w + g,   y),
        QPoint(x + w + g,   mid_y),
        QPoint(x + w + g,   y + h - ch),
        QPoint(x,           y + h + g),
        QPoint(x + w - cw,  y + h + g),
        QPoint(x - cw - g,  y),
        QPoint(x - cw - g,  mid_y),
        QPoint(x - cw - g,  y + h - ch),
        QPoint(x,           y - ch - g),
        QPoint(x + w - cw,  y - ch - g),
    ]


# ---------------------------------------------------------------------------
# Verse data  (title, reference, bare verse text)
# ---------------------------------------------------------------------------

_WEB_VERSES: dict[str, tuple[str, str, str]] = {
    "internet_default": (
        "You are the salt of the earth",
        "2 Timothy 2:21",
        "If anyone cleanses himself from what is dishonorable, he will be a vessel for honorable use, "
        "set apart as holy, useful to the master of the house, ready for every good work.",
    ),
    "home_alone": (
        "You are never truly alone",
        "Deuteronomy 31:6",
        "The Lord your God goes with you; He will never leave you nor forsake you.",
    ),
    "triggering_content": (
        "You can turn away — that choice is strength",
        "2 Timothy 2:22",
        "Flee from youthful passions and pursue righteousness, faith, love, and peace.",
    ),
    "tired": (
        "Rest is a gift, not a weakness",
        "Matthew 11:28",
        "Come to me, all who labor and are heavy laden, and I will give you rest.",
    ),
    "biological_urge": (
        "The urge is not a command. You have more power than it",
        "1 Corinthians 10:13",
        "God is faithful; He will not let you be tempted beyond what you can bear.",
    ),
    "lonely": (
        "Loneliness is real — and God sees it",
        "Psalm 34:18",
        "The Lord is near to the brokenhearted and saves the crushed in spirit.",
    ),
    "discouraged": (
        "Discouragement is not the final word",
        "Philippians 4:6",
        "Do not be anxious about anything, but in every situation, by prayer, present your requests to God.",
    ),
    "anxious": (
        "Peace is available to you right now",
        "John 14:27",
        "Peace I leave with you; my peace I give you. Do not let your hearts be troubled.",
    ),
    "angry": (
        "Anger is worth listening to — but not obeying right now",
        "Ephesians 4:26",
        "In your anger do not sin. Do not let the sun go down while you are still angry.",
    ),
    "avoiding_something": (
        "Avoidance keeps the weight on. One small step forward is enough",
        "Proverbs 3:5",
        "Trust in the Lord with all your heart and lean not on your own understanding.",
    ),
}

# ---------------------------------------------------------------------------
# Session duration choices
# ---------------------------------------------------------------------------

_TIME_OPTIONS = [
    ("5m",   5 * 60),
    ("10m", 10 * 60),
    ("15m", 15 * 60),
    ("30m", 30 * 60),
    ("1h",  60 * 60),
]

# ---------------------------------------------------------------------------
# Feeling buttons  (left column, right column — 6 rows each)
# ---------------------------------------------------------------------------

_FEELINGS_LEFT = [
    ("tempted",     "Tempted"),
    ("tired",       "Tired"),
    ("anxious",     "Anxious"),
    ("lonely",      "Lonely"),
    ("discouraged", "Discouraged"),
    ("drained",     "Drained"),
]

_FEELINGS_RIGHT = [
    ("determined", "Determined"),
    ("energized",  "Energized"),
    ("hopeful",    "Hopeful"),
    ("loved",      "Loved"),
    ("encouraged", "Encouraged"),
    ("rested",     "Rested"),
]

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

_BTN_FEELING_IDLE = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 6px;"
    f"  color: {COLOR_TEXT};"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_SMALL}pt;"
    f"  padding: 6px 8px;"
    f"  text-align: left;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_SURFACE};"
    f"  border: 1px solid {COLOR_ACCENT};"
    f"}}"
)

_BTN_FEELING_SELECTED = (
    f"QPushButton {{"
    f"  background-color: {COLOR_ACCENT};"
    f"  border: 1px solid {COLOR_ACCENT_DARK};"
    f"  border-radius: 6px;"
    f"  color: #ffffff;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_SMALL}pt;"
    f"  font-weight: 700;"
    f"  padding: 6px 8px;"
    f"  text-align: left;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_ACCENT_DARK};"
    f"}}"
)

_BTN_SECTION = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 8px;"
    f"  color: {COLOR_TEXT};"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_MEDIUM}pt;"
    f"  font-weight: 700;"
    f"  padding: 10px;"
    f"  text-align: center;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_SURFACE};"
    f"  border: 1px solid {COLOR_ACCENT};"
    f"}}"
)

_REMINDER_FRAME_STYLE = (
    f"QFrame {{"
    f"  background-color: {COLOR_SURFACE_3};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 8px;"
    f"}}"
)

_TEXT_EDIT_STYLE = (
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

# ---------------------------------------------------------------------------
# NL helpers (kept as module-level exports; tested independently)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _evaluate_verse(typed: str, original: str) -> tuple[int, int, int, list[int]]:
    typed_words = _tokenize(typed)
    orig_words = _tokenize(original)
    if not orig_words:
        return 100, 0, 0, []

    matcher = difflib.SequenceMatcher(None, typed_words, orig_words, autojunk=False)
    correct = 0
    n_missing = 0
    n_misspelled = 0
    bad_indices: list[int] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            correct += j2 - j1
        elif tag == "insert":
            n_missing += j2 - j1
            bad_indices.extend(range(j1, j2))
        elif tag == "replace":
            typed_len = i2 - i1
            orig_len = j2 - j1
            for k in range(orig_len):
                oi = j1 + k
                bad_indices.append(oi)
                if k < typed_len:
                    ti = i1 + k
                    ratio = difflib.SequenceMatcher(
                        None, typed_words[ti], orig_words[oi]
                    ).ratio()
                    if ratio > 0.6:
                        n_misspelled += 1
                    else:
                        n_missing += 1
                else:
                    n_missing += 1

    accuracy = round(correct / len(orig_words) * 100)
    return accuracy, n_missing, n_misspelled, bad_indices


def _is_proper_sentence(text: str) -> bool:
    return len(text.strip().split()) >= 4


def _ordered_feelings(feelings: Iterable[str]) -> list[str]:
    return sorted(feelings)


# ---------------------------------------------------------------------------
# Full-screen dim overlay  (same as PanicReasonDialog)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# WebPopup
# ---------------------------------------------------------------------------

class WebPopup(BasePopup):
    DEFAULT_WIDTH          = 1000
    DEFAULT_HEIGHT_BLOCKED = 200

    def __init__(
        self,
        *,
        permitted: bool = True,
        reason_id: str | None = None,
        parent=None,
        data_root: Path | None = None,
    ) -> None:
        title = "" if permitted else "Browser Blocked"
        super().__init__(title, parent)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )

        # -- public result attrs ------------------------------------------
        self.selected_choice: str = ""
        self.reason_text: str = ""
        self.allowed_urls: list[str] = []
        self.duration_seconds: int = _TIME_OPTIONS[0][1]
        self.selected_feelings: list[str] = []

        # -- verse lookup: prefer user-created encouragements -------------
        reminder = None
        if data_root is not None:
            try:
                from services.panic_reminders import PanicReminders
                pr = PanicReminders(data_root)
                all_reminders = pr.get_all()
                if all_reminders:
                    reminder = random.choice(all_reminders)
            except Exception:
                pass

        if reminder is not None:
            self._verse_title = reminder.get("title", "")
            self._verse_note  = reminder.get("note", "")
            self._verse_ref   = reminder.get("verse_ref", "")
            self._verse_text  = reminder.get("verse_text", "")
        else:
            key = reason_id if reason_id in _WEB_VERSES else random.choice(list(_WEB_VERSES.keys()))
            self._verse_title, self._verse_ref, self._verse_text = _WEB_VERSES[key]
            self._verse_note = ""

        # public so callers (e.g. MainWindow) can read it after accept()
        self.verse_title: str = self._verse_title

        # -- internal state -----------------------------------------------
        self._selected_feelings: set[str] = set()
        self._feeling_btns: dict[str, QPushButton] = {}
        # reason_id → {btn, slot, card}  (populated in _add_feelings_section)
        self._active: dict[str, dict] = {}
        self._overlay: Optional[_ScreenDimOverlay] = None

        if permitted:
            self.setFixedWidth(self.DEFAULT_WIDTH)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16_777_215)
            root_layout = self.layout()
            for i in range(root_layout.count() - 1, -1, -1):
                item = root_layout.itemAt(i)
                if item is not None and item.spacerItem() is not None:
                    root_layout.takeAt(i)
                    break
            self._build_permitted()
            self.adjustSize()
        else:
            self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT_BLOCKED)
            self._build_blocked()

    # ------------------------------------------------------------------
    # Permitted layout  (top-to-bottom vertical)
    # ------------------------------------------------------------------

    def _build_permitted(self) -> None:
        self._add_reminder_banner()
        self._add_feelings_section()

    def _add_reminder_banner(self) -> None:
        frame = QFrame()
        frame.setStyleSheet(_REMINDER_FRAME_STYLE)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(14, 12, 14, 12)
        frame_layout.setSpacing(4)

        title_lbl = QLabel(self._verse_title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {_FS_REMINDER_TITLE}pt;"
            f"font-weight: 700; color: {COLOR_TEXT}; background: transparent; border: none;"
        )
        frame_layout.addWidget(title_lbl)

        if self._verse_note:
            note_lbl = QLabel(self._verse_note)
            note_lbl.setWordWrap(True)
            note_lbl.setStyleSheet(
                f"font-family: '{FONT_FAMILY}'; font-size: {_FS_REMINDER_NOTE}pt;"
                f"color: {COLOR_TEXT}; background: transparent; border: none;"
            )
            frame_layout.addWidget(note_lbl)

        verse_lbl = QLabel(
            f"<b>{self._verse_ref}</b><br><i>&#8220;{self._verse_text}&#8221;</i>"
        )
        verse_lbl.setTextFormat(Qt.TextFormat.RichText)
        verse_lbl.setWordWrap(True)
        verse_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {_FS_REMINDER_VERSE}pt;"
            f"color: {COLOR_TEXT_MUTED}; background: transparent; border: none; padding-top: 4px;"
        )
        frame_layout.addWidget(verse_lbl)

        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body_layout.addWidget(frame)

    def _add_feelings_section(self) -> None:
        self._feeling_btn = QPushButton("How are you feeling?")
        self._feeling_btn.setMinimumHeight(46)
        self._feeling_btn.setStyleSheet(_BTN_SECTION)
        self._feeling_btn.clicked.connect(self._reveal_feelings)
        self.body_layout.addWidget(self._feeling_btn)

        # Container revealed when the button is clicked
        self._feelings_widget = QWidget()
        self._feelings_widget.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(self._feelings_widget)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)

        # ── 2-column feelings grid ────────────────────────────────────
        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        for row_idx, (left_entry, right_entry) in enumerate(
            zip(_FEELINGS_LEFT, _FEELINGS_RIGHT)
        ):
            for col_idx, (feeling_id, feeling_label) in enumerate((left_entry, right_entry)):
                btn = QPushButton(feeling_label)
                btn.setMinimumHeight(38)
                btn.setStyleSheet(_BTN_FEELING_IDLE)
                btn.clicked.connect(
                    lambda _checked, fid=feeling_id, lbl=feeling_label, b=btn:
                        self._toggle_feeling(fid, lbl, b)
                )
                grid.addWidget(btn, row_idx, col_idx)
                self._feeling_btns[feeling_id] = btn
                self._active[feeling_id] = {"btn": btn, "slot": None, "card": None}

        vbox.addWidget(grid_widget)

        # ── Why are you on the internet? ──────────────────────────────
        purpose_title = QLabel("Why are you on the internet?")
        purpose_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700; background: transparent;"
        )
        vbox.addWidget(purpose_title)

        self._reason_edit = QTextEdit()
        self._reason_edit.setPlaceholderText(
            "Write a sentence explaining why you are going on the internet\u2026"
        )
        self._reason_edit.setFixedHeight(52)
        self._reason_edit.setStyleSheet(_TEXT_EDIT_STYLE)
        self._reason_edit.textChanged.connect(self._sync_commit_enabled)
        vbox.addWidget(self._reason_edit)

        # ── Session length ────────────────────────────────────────────
        time_title = QLabel("How long is this internet session?")
        time_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700; background: transparent;"
        )
        vbox.addWidget(time_title)

        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(8)
        self._time_combo = QComboBox()
        for label, seconds in _TIME_OPTIONS:
            self._time_combo.addItem(label, seconds)
        time_row.addWidget(self._time_combo)
        time_row.addStretch()
        vbox.addLayout(time_row)

        # ── Commit button ─────────────────────────────────────────────
        self._commit_btn = QPushButton("I will honor Jesus online")
        self._commit_btn.setMinimumHeight(42)
        self._commit_btn.setEnabled(False)
        self._commit_btn.setStyleSheet(self._commit_btn_style(enabled=False))
        self._commit_btn.clicked.connect(self._on_commit)
        vbox.addWidget(self._commit_btn)

        self._feelings_widget.hide()
        self.body_layout.addWidget(self._feelings_widget)

    # ------------------------------------------------------------------
    # Blocked layout
    # ------------------------------------------------------------------

    def _build_blocked(self) -> None:
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
            f"  color: {COLOR_TEXT};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 7px 12px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"}}"
            f"QPushButton:hover {{ background-color: {COLOR_SURFACE}; }}"
        )
        btn.clicked.connect(self.reject)
        self.body_layout.addWidget(btn)

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _commit_btn_style(*, enabled: bool) -> str:
        if enabled:
            return (
                f"QPushButton {{"
                f"  background-color: {COLOR_ACCENT};"
                f"  color: #ffffff;"
                f"  border: none;"
                f"  border-radius: 8px;"
                f"  font-family: '{FONT_FAMILY}';"
                f"  font-size: {FONT_SIZE_NORMAL}pt;"
                f"  font-weight: 700;"
                f"  padding: 10px 20px;"
                f"}}"
                f"QPushButton:hover {{ background-color: {COLOR_ACCENT_DARK}; }}"
            )
        return (
            f"QPushButton {{"
            f"  background-color: {COLOR_BORDER};"
            f"  color: {COLOR_TEXT_MUTED};"
            f"  border: none;"
            f"  border-radius: 8px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  font-weight: 600;"
            f"  padding: 10px 20px;"
            f"}}"
        )

    # ------------------------------------------------------------------
    # Dialog lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        if self._overlay is None:
            self._overlay = _ScreenDimOverlay()
            self._overlay.show()
        self.raise_()
        super().showEvent(event)

    def done(self, result: int) -> None:
        self._close_all_cards()
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        super().done(result)

    # ------------------------------------------------------------------
    # Feelings panel reveal
    # ------------------------------------------------------------------

    def _reveal_feelings(self) -> None:
        self._feeling_btn.hide()
        self._feelings_widget.show()
        self.adjustSize()

    # ------------------------------------------------------------------
    # Feeling toggle + card management  (mirrors PanicReasonDialog)
    # ------------------------------------------------------------------

    def _toggle_feeling(self, fid: str, label: str, btn: QPushButton) -> None:
        if fid in self._selected_feelings:
            self._deselect_feeling(fid, btn)
        else:
            self._select_feeling(fid, label, btn)

    def _select_feeling(self, fid: str, label: str, btn: QPushButton) -> None:
        self._selected_feelings.add(fid)
        btn.setStyleSheet(_BTN_FEELING_SELECTED)
        slot = self._next_free_slot()
        card = RecoveryNoteCard(fid, label)
        card.dismissed.connect(
            lambda rid, b=btn: self._on_card_dismissed(rid, b)
        )
        card.move(self._slot_position(slot))
        card.show()
        self._active[fid]["slot"] = slot
        self._active[fid]["card"] = card

    def _deselect_feeling(self, fid: str, btn: QPushButton) -> None:
        self._selected_feelings.discard(fid)
        btn.setStyleSheet(_BTN_FEELING_IDLE)
        card: Optional[RecoveryNoteCard] = self._active[fid].get("card")
        if card is not None:
            try:
                card.dismissed.disconnect()
            except RuntimeError:
                pass
            card.close()
            self._active[fid]["card"] = None
            self._active[fid]["slot"] = None

    def _on_card_dismissed(self, fid: str, btn: QPushButton) -> None:
        self._selected_feelings.discard(fid)
        btn.setStyleSheet(_BTN_FEELING_IDLE)
        self._active[fid]["card"] = None
        self._active[fid]["slot"] = None

    def _close_all_cards(self) -> None:
        for data in self._active.values():
            card: Optional[RecoveryNoteCard] = data.get("card")
            if card is not None:
                try:
                    card.dismissed.disconnect()
                except RuntimeError:
                    pass
                card.close()
                data["card"] = None
                data["slot"] = None

    # ------------------------------------------------------------------
    # Slot positioning
    # ------------------------------------------------------------------

    def _used_slots(self) -> set[int]:
        return {
            data["slot"]
            for data in self._active.values()
            if data.get("slot") is not None
        }

    def _next_free_slot(self) -> int:
        used = self._used_slots()
        for i in range(_SLOT_COUNT):
            if i not in used:
                return i
        return len(used) % _SLOT_COUNT

    def _slot_position(self, slot: int) -> QPoint:
        return _compute_slots(self.geometry())[slot % _SLOT_COUNT]

    def _sync_commit_enabled(self) -> None:
        enabled = _is_proper_sentence(self._reason_edit.toPlainText())
        self._commit_btn.setEnabled(enabled)
        self._commit_btn.setStyleSheet(self._commit_btn_style(enabled=enabled))

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------

    def _on_commit(self) -> None:
        self.duration_seconds = int(self._time_combo.currentData())
        self.allowed_urls = []
        self.reason_text = self._reason_edit.toPlainText().strip()
        self.selected_choice = "internet_session"
        self.selected_feelings = _ordered_feelings(self._selected_feelings)
        self.accept()

