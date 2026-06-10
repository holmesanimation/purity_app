"""Verse memorisation practice widget.

A standalone tool for practising scripture memory.  It is not a gate — the
user can open a new verse any time they like and practice as often as they
want.

Public API
----------
``VerseMemoryWidget(parent=None)``
    Ready to use immediately.  Loads a random verse on construction.

``load_verse(key)``
    Load a specific verse by key from ``_WEB_VERSES``.

``load_random_verse()``
    Pick a random verse and reload the UI.
"""

from __future__ import annotations

import difflib
import random
import re
from typing import Optional

from PySide6.QtCore import QEvent, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_DARK,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_2,
    COLOR_SURFACE_3,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    FONT_SIZE_LARGE,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
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

# ---------------------------------------------------------------------------
# NL helpers  (duplicated here to keep this file self-contained)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _evaluate_verse(typed: str, original: str) -> tuple[int, int, int, list[int]]:
    """Compare *typed* against *original* at word level.

    Returns ``(accuracy_pct, n_missing, n_misspelled, bad_original_indices)``.
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


# ---------------------------------------------------------------------------
# VerseMemoryWidget
# ---------------------------------------------------------------------------

class VerseMemoryWidget(QWidget):
    """Self-contained scripture memorisation practice panel.

    Drop anywhere as a child widget.  No signals to wire up; all state is
    internal.  Call ``load_random_verse()`` programmatically or let the user
    press "New Verse".
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._verse_title: str = ""
        self._verse_ref: str = ""
        self._verse_text: str = ""
        self._verse_words: list[str] = []
        self._verse_accuracy: int = 0
        self._hint_offset: int = 0
        self._bad_indices: list[int] = []
        self._hint_anim: Optional[QPropertyAnimation] = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._build_ui()
        self.load_random_verse()

    # -- public API --------------------------------------------------------

    def load_random_verse(self) -> None:
        key = random.choice(list(_WEB_VERSES.keys()))
        self.load_verse(key)

    def load_verse(self, key: str) -> None:
        title, ref, text = _WEB_VERSES.get(key, _WEB_VERSES["internet_default"])
        self._verse_title = title
        self._verse_ref = ref
        self._verse_text = text
        self._verse_words = _tokenize(text)
        self._verse_accuracy = 0
        self._hint_offset = 0
        self._bad_indices = []
        self._refresh_verse_display()
        self._reset_practice_area()

    # -- build UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # ── Verse header frame ───────────────────────────────────────
        verse_frame = QFrame()
        verse_frame.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {COLOR_SURFACE_3};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 8px;"
            f"}}"
        )
        vf = QVBoxLayout(verse_frame)
        vf.setContentsMargins(14, 12, 14, 12)
        vf.setSpacing(4)

        self._title_lbl = QLabel()
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_LARGE}pt; font-weight: 700; background: transparent;"
        )
        vf.addWidget(self._title_lbl)

        self._ref_lbl = QLabel()
        self._ref_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-style: italic; background: transparent;"
        )
        vf.addWidget(self._ref_lbl)

        outer.addWidget(verse_frame)

        # ── Practice text area ───────────────────────────────────────
        self._verse_edit = QTextEdit()
        self._verse_edit.setPlaceholderText("Type the verse from memory…")
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
        outer.addWidget(self._verse_edit)

        # ── Eval row ─────────────────────────────────────────────────
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

        outer.addLayout(eval_row)

        # ── Hint words label (fades out) ─────────────────────────────
        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet(
            f"color: {COLOR_ACCENT_DARK}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-style: italic; background: transparent;"
        )
        self._hint_label.hide()
        outer.addWidget(self._hint_label)

        # ── Full verse display (shown after Compare) ─────────────────
        self._verse_display = QLabel("")
        self._verse_display.setWordWrap(True)
        self._verse_display.setTextFormat(Qt.TextFormat.RichText)
        self._verse_display.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; background: transparent;"
        )
        self._verse_display.hide()
        outer.addWidget(self._verse_display)

        # ── Divider ──────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        outer.addWidget(sep)

        # ── New Verse button ─────────────────────────────────────────
        new_verse_btn = QPushButton("New Verse")
        new_verse_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_SURFACE_2};"
            f"  color: {COLOR_TEXT};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 6px 14px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_SMALL}pt;"
            f"  font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_ACCENT};"
            f"}}"
        )
        new_verse_btn.clicked.connect(self.load_random_verse)
        outer.addWidget(new_verse_btn)

    # -- helpers -----------------------------------------------------------

    def _refresh_verse_display(self) -> None:
        self._title_lbl.setText(self._verse_title)
        self._ref_lbl.setText(self._verse_ref)

    def _reset_practice_area(self) -> None:
        self._verse_edit.clear()
        self._eval_label.hide()
        self._eval_label.setText("")
        self._hint_label.hide()
        self._hint_label.setText("")
        self._verse_display.hide()
        self._verse_display.setText("")
        if self._hint_anim is not None:
            self._hint_anim.stop()
            self._hint_anim = None

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

    # -- event filter — verse edit -----------------------------------------

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if obj is self._verse_edit:
            if event.type() == QEvent.Type.FocusOut:
                self._on_verse_evaluate()
            elif event.type() == QEvent.Type.KeyPress:
                if (
                    event.key() == Qt.Key.Key_Return
                    and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                ):
                    self._on_verse_evaluate()
                    return True
        return super().eventFilter(obj, event)

    # -- verse evaluation --------------------------------------------------

    def _on_verse_evaluate(self) -> None:
        typed = self._verse_edit.toPlainText().strip()
        if not typed:
            self._eval_label.hide()
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

    # -- hint --------------------------------------------------------------

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

        QTimer.singleShot(3_000, _start_fade)

    # -- compare -----------------------------------------------------------

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
