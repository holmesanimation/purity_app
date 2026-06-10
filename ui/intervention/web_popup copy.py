from __future__ import annotations

import random
import re
import difflib
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QEvent, QTimer, QPropertyAnimation
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui.intervention.base_popup import BasePopup
from styles.theme import (
    COLOR_ACCENT, COLOR_ACCENT_DARK,
    COLOR_BORDER, COLOR_SURFACE, COLOR_SURFACE_2, COLOR_SURFACE_3,
    COLOR_TEXT, COLOR_TEXT_MUTED,
    FONT_FAMILY, FONT_SIZE_SMALL, FONT_SIZE_NORMAL, FONT_SIZE_MEDIUM, FONT_SIZE_LARGE,
)

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

_DEFAULT_VERSE_KEY = "internet_default"


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


# ---------------------------------------------------------------------------
# Session duration choices
# ---------------------------------------------------------------------------

_TIME_OPTIONS = [
    ("5m",  5 * 60),
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
    ("determined",  "Determined"),
    ("energized",   "Energized"),
    ("hopeful",     "Hopeful"),
    ("loved",       "Loved"),
    ("encouraged",  "Encouraged"),
    ("rested",      "Rested"),
]

# ---------------------------------------------------------------------------
# Feeling button styles
# ---------------------------------------------------------------------------

_FS_FEELING_BTN = FONT_SIZE_SMALL

_BTN_FEELING_IDLE = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 6px;"
    f"  color: {COLOR_TEXT};"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {_FS_FEELING_BTN}pt;"
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
    f"  font-size: {_FS_FEELING_BTN}pt;"
    f"  font-weight: 700;"
    f"  padding: 6px 8px;"
    f"  text-align: left;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_ACCENT_DARK};"
    f"}}"
)

# ---------------------------------------------------------------------------
# NL helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Return lowercase alphabetic-plus-apostrophe tokens from *text*."""
    return re.findall(r"[a-zA-Z']+", text.lower())


def _evaluate_verse(typed: str, original: str) -> tuple[int, int, int, list[int]]:
    """Compare *typed* against *original* at word level.

    Returns ``(accuracy_pct, n_missing, n_misspelled, bad_original_indices)``
    where ``bad_original_indices`` is the list of token positions in *original*
    that were absent or misspelled in *typed*.
    """
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
            # words present in original but absent in typed
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
        # "delete" = extra typed words, not penalised

    accuracy = round(correct / len(orig_words) * 100)
    return accuracy, n_missing, n_misspelled, bad_indices


def _is_proper_sentence(text: str) -> bool:
    """Return True if *text* contains at least 4 words."""
    return len(text.strip().split()) >= 4


# ---------------------------------------------------------------------------
# WebPopup
# ---------------------------------------------------------------------------

class WebPopup(BasePopup):
    DEFAULT_WIDTH          = 960
    DEFAULT_HEIGHT         = 700
    DEFAULT_HEIGHT_BLOCKED = 200

    def __init__(
        self,
        *,
        permitted: bool = True,
        reason_id: str | None = None,
        parent=None,
        data_root: Path | None = None,  # retained for caller compatibility
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

        # -- verse lookup — prefer user-created encouragements ----------------
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
            if reason_id in _WEB_VERSES:
                key = reason_id
            else:
                key = random.choice(list(_WEB_VERSES.keys()))
            self._verse_title, self._verse_ref, self._verse_text = _WEB_VERSES[key]
            self._verse_note = ""

        self._verse_words = _tokenize(self._verse_text)

        # -- internal state -----------------------------------------------
        self._verse_accuracy: int = 0
        self._hint_offset: int = 0
        self._selected_feelings: set[str] = set()
        self._bad_indices: list[int] = []
        self._feeling_btns: dict[str, QPushButton] = {}
        self._hint_anim: Optional[QPropertyAnimation] = None

        height = self.DEFAULT_HEIGHT if permitted else self.DEFAULT_HEIGHT_BLOCKED
        self.setFixedSize(self.DEFAULT_WIDTH, height)

        if permitted:
            self._build_permitted()
        else:
            self._build_blocked()

    # ------------------------------------------------------------------
    # Permitted layout
    # ------------------------------------------------------------------

    def _build_permitted(self) -> None:
        h_split = QHBoxLayout()
        h_split.setContentsMargins(0, 0, 0, 0)
        h_split.setSpacing(18)
        self.body_layout.addLayout(h_split)

        self._build_left_column(h_split)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        h_split.addWidget(sep)

        self._build_right_column(h_split)

    # ------------------------------------------------------------------
    # Left column — verse exercise + internet purpose
    # ------------------------------------------------------------------

    def _build_left_column(self, parent: QHBoxLayout) -> None:
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(10)
        parent.addLayout(left, stretch=3)

        # ── Encouragement + verse frame ──────────────────────────────
        verse_frame = QFrame()
        verse_frame.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {COLOR_SURFACE_3};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 8px;"
            f"}}"
        )
        vf_layout = QVBoxLayout(verse_frame)
        vf_layout.setContentsMargins(14, 12, 14, 12)
        vf_layout.setSpacing(6)

        title_lbl = QLabel(self._verse_title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_LARGE}pt; font-weight: 700; background: transparent;"
        )
        vf_layout.addWidget(title_lbl)

        if self._verse_note:
            note_lbl = QLabel(self._verse_note)
            note_lbl.setWordWrap(True)
            note_lbl.setStyleSheet(
                f"color: {COLOR_ACCENT}; font-family: '{FONT_FAMILY}';"
                f"font-size: {FONT_SIZE_NORMAL}pt; font-style: italic; background: transparent;"
            )
            vf_layout.addWidget(note_lbl)

        ref_lbl = QLabel(self._verse_ref)
        ref_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-style: italic; background: transparent;"
        )
        vf_layout.addWidget(ref_lbl)

        self._verse_edit = QTextEdit()
        self._verse_edit.setPlaceholderText("Type the verse from memory\u2026")
        self._verse_edit.setMinimumHeight(90)
        self._verse_edit.setMaximumHeight(110)
        self._verse_edit.setStyleSheet(
            f"QTextEdit {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 4px;"
            f"  color: {COLOR_TEXT};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  padding: 4px;"
            f"}}"
        )
        self._verse_edit.installEventFilter(self)
        vf_layout.addWidget(self._verse_edit)

        # Eval row
        eval_row = QHBoxLayout()
        eval_row.setSpacing(8)

        self._eval_label = QLabel("")
        self._eval_label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self._eval_label.hide()
        eval_row.addWidget(self._eval_label, stretch=1)

        self._hint_btn = QPushButton("Hint")
        self._hint_btn.setStyleSheet(self._secondary_btn_style())
        self._hint_btn.clicked.connect(self._on_hint)
        eval_row.addWidget(self._hint_btn)

        self._compare_btn = QPushButton("Compare")
        self._compare_btn.setStyleSheet(self._secondary_btn_style())
        self._compare_btn.clicked.connect(self._on_compare)
        eval_row.addWidget(self._compare_btn)

        vf_layout.addLayout(eval_row)

        # Hint words label (shown briefly, then fades)
        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet(
            f"color: {COLOR_ACCENT_DARK}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-style: italic; background: transparent;"
        )
        self._hint_label.hide()
        vf_layout.addWidget(self._hint_label)

        # Verse display — hidden until Compare pressed
        self._verse_display = QLabel("")
        self._verse_display.setWordWrap(True)
        self._verse_display.setTextFormat(Qt.TextFormat.RichText)
        self._verse_display.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
        )
        self._verse_display.hide()
        vf_layout.addWidget(self._verse_display)

        left.addWidget(verse_frame)

        # ── Internet purpose section ─────────────────────────────────
        purpose_title = QLabel("Why are you on the internet?")
        purpose_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700; background: transparent;"
        )
        left.addWidget(purpose_title)

        self._reason_edit = QTextEdit()
        self._reason_edit.setPlaceholderText(
            "Write a sentence explaining why you are going on the internet\u2026"
        )
        self._reason_edit.setMinimumHeight(60)
        self._reason_edit.setMaximumHeight(80)
        self._reason_edit.setStyleSheet(
            f"QTextEdit {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 4px;"
            f"  color: {COLOR_TEXT};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  padding: 4px;"
            f"}}"
        )
        self._reason_edit.textChanged.connect(self._sync_commit_enabled)
        left.addWidget(self._reason_edit)

        # Commit row
        commit_row = QHBoxLayout()
        commit_row.setSpacing(8)

        time_lbl = QLabel("Time")
        time_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        commit_row.addWidget(time_lbl)

        self._time_combo = QComboBox()
        for label, seconds in _TIME_OPTIONS:
            self._time_combo.addItem(label, seconds)
        commit_row.addWidget(self._time_combo)

        commit_row.addStretch()

        self._commit_btn = QPushButton("I will honor Jesus on the internet")
        self._commit_btn.setEnabled(False)
        self._commit_btn.setStyleSheet(self._commit_btn_style(enabled=False))
        self._commit_btn.clicked.connect(self._on_commit)
        commit_row.addWidget(self._commit_btn)

        left.addLayout(commit_row)
        left.addStretch()

    # ------------------------------------------------------------------
    # Right column — feelings + journal
    # ------------------------------------------------------------------

    def _build_right_column(self, parent: QHBoxLayout) -> None:
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        parent.addLayout(right, stretch=2)

        # ── Feelings section ─────────────────────────────────────────
        feelings_title = QLabel("How are you feeling?")
        feelings_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700; background: transparent;"
        )
        right.addWidget(feelings_title)

        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        for row_idx, (left_entry, right_entry) in enumerate(
            zip(_FEELINGS_LEFT, _FEELINGS_RIGHT)
        ):
            for col_idx, (fid, flabel) in enumerate([left_entry, right_entry]):
                btn = QPushButton(flabel)
                btn.setMinimumHeight(32)
                btn.setStyleSheet(_BTN_FEELING_IDLE)
                btn.clicked.connect(
                    lambda _checked, fid=fid, btn=btn: self._toggle_feeling(fid, btn)
                )
                grid.addWidget(btn, row_idx, col_idx)
                self._feeling_btns[fid] = btn

        right.addWidget(grid_widget)

        # ── Journal section ──────────────────────────────────────────
        journal_sep = QFrame()
        journal_sep.setFrameShape(QFrame.Shape.HLine)
        journal_sep.setStyleSheet(f"color: {COLOR_BORDER};")
        right.addWidget(journal_sep)

        journal_title = QLabel("What are you thinking about?")
        journal_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700; background: transparent;"
        )
        right.addWidget(journal_title)

        self._journal_edit = QTextEdit()
        self._journal_edit.setMinimumHeight(100)
        self._journal_edit.setStyleSheet(
            f"QTextEdit {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 4px;"
            f"  color: {COLOR_TEXT};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  padding: 4px;"
            f"}}"
        )
        self._journal_edit.textChanged.connect(self._sync_record_enabled)
        right.addWidget(self._journal_edit)

        self._journal_status = QLabel("")
        self._journal_status.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        self._journal_status.hide()
        right.addWidget(self._journal_status)

        self._record_btn = QPushButton("Record Journal")
        self._record_btn.setEnabled(False)
        self._record_btn.setStyleSheet(self._secondary_btn_style())
        self._record_btn.clicked.connect(self._on_record_journal)
        right.addWidget(self._record_btn)

        right.addStretch()

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
    def _secondary_btn_style() -> str:
        return (
            f"QPushButton {{"
            f"  background-color: {COLOR_ACCENT};"
            f"  color: #ffffff;"
            f"  border: none;"
            f"  border-radius: 6px;"
            f"  padding: 5px 12px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_SMALL}pt;"
            f"  font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background-color: {COLOR_ACCENT_DARK}; }}"
        )

    @staticmethod
    def _commit_btn_style(*, enabled: bool) -> str:
        if enabled:
            return (
                f"QPushButton {{"
                f"  background-color: {COLOR_ACCENT};"
                f"  color: #ffffff;"
                f"  border: none;"
                f"  border-radius: 6px;"
                f"  padding: 8px 16px;"
                f"  font-family: '{FONT_FAMILY}';"
                f"  font-size: {FONT_SIZE_NORMAL}pt;"
                f"  font-weight: 700;"
                f"}}"
                f"QPushButton:hover {{ background-color: {COLOR_ACCENT_DARK}; }}"
            )
        return (
            f"QPushButton {{"
            f"  background-color: {COLOR_BORDER};"
            f"  color: {COLOR_TEXT_MUTED};"
            f"  border: none;"
            f"  border-radius: 6px;"
            f"  padding: 8px 16px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  font-weight: 600;"
            f"}}"
        )

    # ------------------------------------------------------------------
    # Event filter — verse edit focus-out + Return key
    # ------------------------------------------------------------------

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        verse_edit = getattr(self, "_verse_edit", None)
        if verse_edit is not None and obj is verse_edit:
            if event.type() == QEvent.Type.FocusOut:
                self._on_verse_evaluate()
            elif event.type() == QEvent.Type.KeyPress:
                if (
                    event.key() == Qt.Key.Key_Return
                    and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                ):
                    self._on_verse_evaluate()
                    return True  # consume — don't insert newline
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Verse evaluation
    # ------------------------------------------------------------------

    def _on_verse_evaluate(self) -> None:
        typed = self._verse_edit.toPlainText().strip()
        if not typed:
            return
        accuracy, n_missing, n_misspelled, bad_indices = _evaluate_verse(
            typed, self._verse_text
        )
        self._verse_accuracy = accuracy
        self._bad_indices = bad_indices

        parts: list[str] = [f"{accuracy}% accurate"]
        if n_missing:
            parts.append(f"{n_missing} word{'s' if n_missing != 1 else ''} missing")
        if n_misspelled:
            parts.append(f"{n_misspelled} word{'s' if n_misspelled != 1 else ''} misspelled")
        self._eval_label.setText(" \u2013 ".join(parts))
        self._eval_label.show()
        self._sync_commit_enabled()

    # ------------------------------------------------------------------
    # Hint
    # ------------------------------------------------------------------

    def _on_hint(self) -> None:
        if not self._verse_words:
            return
        if self._hint_anim is not None:
            self._hint_anim.stop()

        start = self._hint_offset % len(self._verse_words)
        snippet = self._verse_words[start : start + 2]
        self._hint_offset += 2

        self._hint_label.setText(" ".join(snippet))

        effect = self._hint_label.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self._hint_label)
            self._hint_label.setGraphicsEffect(effect)
        effect.setOpacity(1.0)
        self._hint_label.show()

        def _start_fade() -> None:
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(500)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.finished.connect(self._hint_label.hide)
            self._hint_anim = anim
            anim.start()

        QTimer.singleShot(3000, _start_fade)

    # ------------------------------------------------------------------
    # Compare
    # ------------------------------------------------------------------

    def _on_compare(self) -> None:
        if not self._eval_label.isVisible():
            self._on_verse_evaluate()

        bad_set = set(self._bad_indices)
        word_pattern = re.compile(r"[a-zA-Z']+")
        matches = list(word_pattern.finditer(self._verse_text))

        result: list[str] = []
        last_end = 0
        for i, m in enumerate(matches):
            result.append(self._verse_text[last_end : m.start()])
            word = m.group()
            result.append(f"<u>{word}</u>" if i in bad_set else word)
            last_end = m.end()
        result.append(self._verse_text[last_end:])

        html = (
            f"<p style=\"font-family:'{FONT_FAMILY}'; font-size:{FONT_SIZE_NORMAL}pt;"
            f" font-style:italic; color:{COLOR_TEXT_MUTED};\">"
            + "".join(result)
            + "</p>"
        )
        self._verse_display.setText(html)
        self._verse_display.show()

    # ------------------------------------------------------------------
    # Commit-button gating
    # ------------------------------------------------------------------

    def _sync_commit_enabled(self) -> None:
        enabled = (
            self._verse_accuracy >= 80
            and _is_proper_sentence(self._reason_edit.toPlainText())
        )
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
        self.selected_feelings = list(self._selected_feelings)
        self.accept()

    # ------------------------------------------------------------------
    # Feeling buttons
    # ------------------------------------------------------------------

    def _toggle_feeling(self, fid: str, btn: QPushButton) -> None:
        if fid in self._selected_feelings:
            self._selected_feelings.discard(fid)
            btn.setStyleSheet(_BTN_FEELING_IDLE)
        else:
            self._selected_feelings.add(fid)
            btn.setStyleSheet(_BTN_FEELING_SELECTED)

    # ------------------------------------------------------------------
    # Journal
    # ------------------------------------------------------------------

    def _sync_record_enabled(self) -> None:
        self._record_btn.setEnabled(
            bool(self._journal_edit.toPlainText().strip())
        )

    def _on_record_journal(self) -> None:
        text = self._journal_edit.toPlainText().strip()
        if not text:
            return

        try:
            from services.notes_setup import notes_writer
            from shane_common.notes.notes_writer import NoteType
            note = notes_writer.build_note(
                note_type=NoteType.GENERAL,
                text=text,
                context={
                    "feelings": sorted(self._selected_feelings),
                    "source": "web_popup",
                },
            )
            notes_writer.commit(note)
        except Exception:
            pass  # non-critical — don't block the UI

        try:
            ts_str = datetime.now().strftime("%Y-%m-%d %#I:%M %p")
        except ValueError:
            ts_str = datetime.now().strftime("%Y-%m-%d %I:%M %p")

        self._journal_status.setText(f"Entry recorded \u2013 {ts_str}")
        self._journal_status.show()
        QTimer.singleShot(5000, self._journal_status.hide)

        # Reset journal UI
        self._journal_edit.clear()
        self._record_btn.setEnabled(False)
        for btn in self._feeling_btns.values():
            btn.setStyleSheet(_BTN_FEELING_IDLE)
        self._selected_feelings.clear()
