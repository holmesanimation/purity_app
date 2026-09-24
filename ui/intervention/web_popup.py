from __future__ import annotations

import difflib
import random
import re
import traceback
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import Qt, QPoint, QRect, QPropertyAnimation, QEasingCurve, QByteArray, QTimer
from PySide6.QtGui import QColor, QPainter, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
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
    return len(text.strip().split()) > 6


def _ordered_feelings(feelings: Iterable[str]) -> list[str]:
    return sorted(feelings)


# ---------------------------------------------------------------------------
# Full-screen dim overlay  (same as PanicReasonDialog)
# ---------------------------------------------------------------------------

class _KeywordLineEdit(QLineEdit):
    """QLineEdit that consumes Return/Enter so it never activates a focused button."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Emit returnPressed (handled by WebPopup._on_keyword_confirmed)
            # then consume the event so it cannot propagate and click a button.
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


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
                traceback.print_exc()

        if reminder is not None:
            self._verse_title    = reminder.get("title", "")
            self._verse_note     = reminder.get("note", "")
            self._verse_ref      = reminder.get("verse_ref", "")
            self._verse_text     = reminder.get("verse_text", "")
            self._verse_question = reminder.get("question", "")
            self._verse_keyword  = reminder.get("keyword", "")
        else:
            key = reason_id if reason_id in _WEB_VERSES else random.choice(list(_WEB_VERSES.keys()))
            self._verse_title, self._verse_ref, self._verse_text = _WEB_VERSES[key]
            self._verse_note     = ""
            self._verse_question = ""
            self._verse_keyword  = ""

        # public so callers (e.g. MainWindow) can read it after accept()
        self.verse_title: str = self._verse_title

        # -- internal state -----------------------------------------------
        self._selected_feelings: set[str] = set()
        self._feeling_btns: dict[str, QPushButton] = {}
        # reason_id → {btn, slot, card}  (populated in _add_feelings_section)
        self._active: dict[str, dict] = {}
        self._overlay: Optional[_ScreenDimOverlay] = None
        self._commit_delay_elapsed: bool = False

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

        # ── Title (with optional keyword blank) ───────────────────────
        kw = self._verse_keyword
        if kw:
            import re as _re
            parts = _re.split(_re.escape(kw), self._verse_title, maxsplit=1, flags=_re.IGNORECASE)
            title_row = QWidget()
            title_row.setStyleSheet("background: transparent;")
            title_hl = QHBoxLayout(title_row)
            title_hl.setContentsMargins(0, 0, 0, 0)
            title_hl.setSpacing(4)
            _title_style = (
                f"font-family: '{FONT_FAMILY}'; font-size: {_FS_REMINDER_TITLE}pt;"
                f"font-weight: 700; color: {COLOR_TEXT}; background: transparent; border: none;"
            )
            if parts[0]:
                lbl_before = QLabel(parts[0])
                lbl_before.setStyleSheet(_title_style)
                title_hl.addWidget(lbl_before)
            self._keyword_input = _KeywordLineEdit()
            from PySide6.QtGui import QFont, QFontMetrics
            _kw_font = QFont(FONT_FAMILY, _FS_REMINDER_TITLE)
            _kw_font.setWeight(QFont.Weight.Bold)
            _kw_fm = QFontMetrics(_kw_font)
            _kw_text_px = _kw_fm.horizontalAdvance(kw)
            self._keyword_input.setFixedWidth(_kw_text_px + 24)  # 12px padding each side
            self._keyword_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._keyword_input.setStyleSheet(
                f"QLineEdit {{"
                f"  background: transparent;"
                f"  border: none;"
                f"  border-bottom: 2px solid {COLOR_ACCENT};"
                f"  color: {COLOR_ACCENT};"
                f"  font-family: '{FONT_FAMILY}';"
                f"  font-size: {_FS_REMINDER_TITLE}pt;"
                f"  font-weight: 700;"
                f"  padding: 0px 2px;"
                f"}}"
            )
            self._keyword_input.textChanged.connect(self._on_keyword_typed)
            self._keyword_input.returnPressed.connect(self._on_keyword_confirmed)
            title_hl.addWidget(self._keyword_input)
            if len(parts) > 1 and parts[1]:
                lbl_after = QLabel(parts[1])
                lbl_after.setStyleSheet(_title_style)
                title_hl.addWidget(lbl_after)
            title_hl.addStretch()
            frame_layout.addWidget(title_row)
        else:
            self._keyword_input = None
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
        # Wrap all form content so it can be hidden until the keyword is typed.
        self._session_form_widget = QWidget()
        self._session_form_widget.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(self._session_form_widget)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)

        # ── Why are you going on the internet? ────────────────────────
        internet_title = QLabel("Why are you going on the internet?")
        internet_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_MEDIUM}pt; font-weight: 700; background: transparent;"
        )
        vbox.addWidget(internet_title)

        self._selected_internet_reason: str = ""
        self._internet_reason_btns: dict[str, tuple] = {}
        internet_row = QHBoxLayout()
        internet_row.setContentsMargins(0, 0, 0, 0)
        internet_row.setSpacing(8)
        for reason_id, label, base_color, dark_color, faded_color in [
            ("work",          "Work",          "#2d7a4f", "#1e5235", "#c8d9cc"),
            ("entertainment", "Entertainment", "#c06a00", "#7a4300", "#dfd0bc"),
            ("boredom",       "Boredom",       "#c06a00", "#7a4300", "#dfd0bc"),
            ("temptation",    "Temptation",    "#b03020", "#7a1e12", "#ddc8c5"),
        ]:
            btn = QPushButton(label)
            btn.setMinimumHeight(38)
            btn.setStyleSheet(self._internet_reason_btn_style(base_color, dark_color, faded_color, selected=False))
            btn.clicked.connect(
                lambda _checked, rid=reason_id, bc=base_color, dc=dark_color, fc=faded_color, b=btn:
                    self._select_internet_reason(rid, bc, dc, fc, b)
            )
            internet_row.addWidget(btn)
            self._internet_reason_btns[reason_id] = (btn, base_color, dark_color, faded_color)
        internet_row.addStretch()
        vbox.addLayout(internet_row)

        # ── What will you be doing online? ────────────────────────────
        self._reason_edit = QTextEdit()
        self._reason_edit.setPlaceholderText("Describe what you\u2019ll be doing online\u2026 (more than 6 words)")
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
        _combo_popup_style = (
            f"QComboBox {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 6px;"
            f"  color: {COLOR_TEXT};"
            f"  padding: 5px 9px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"}}"
            f"QComboBox::drop-down {{ border: none; width: 20px; }}"
            f"QComboBox QAbstractItemView {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  color: {COLOR_TEXT};"
            f"  selection-background-color: {COLOR_SURFACE_3};"
            f"  selection-color: {COLOR_TEXT};"
            f"  outline: none;"
            f"}}"
        )
        self._time_combo.setStyleSheet(_combo_popup_style)
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

        self.body_layout.addWidget(self._session_form_widget)
        if self._verse_keyword:
            self._session_form_widget.hide()

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
    def _internet_reason_btn_style(base_color: str, dark_color: str, faded_color: str, *, selected: bool) -> str:
        if selected:
            return (
                f"QPushButton {{"
                f"  background-color: {base_color};"
                f"  border: 2px solid #ffffff;"
                f"  border-radius: 8px;"
                f"  color: #ffffff;"
                f"  font-family: '{FONT_FAMILY}';"
                f"  font-size: {FONT_SIZE_NORMAL}pt;"
                f"  font-weight: 700;"
                f"  padding: 8px 20px;"
                f"}}"
                f"QPushButton:hover {{ background-color: {dark_color}; }}"
            )
        return (
            f"QPushButton {{"
            f"  background-color: {faded_color};"
            f"  border: 1px solid {base_color};"
            f"  border-radius: 8px;"
            f"  color: {dark_color};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  font-weight: 600;"
            f"  padding: 8px 20px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {base_color}; color: #ffffff; }}"
        )

    def _select_internet_reason(self, reason_id: str, base_color: str, dark_color: str, faded_color: str, btn: QPushButton) -> None:
        self._selected_internet_reason = reason_id
        for rid, (b, bc, dc, fc) in self._internet_reason_btns.items():
            b.setStyleSheet(self._internet_reason_btn_style(bc, dc, fc, selected=(rid == reason_id)))
        self._sync_commit_enabled()

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
        self.activateWindow()
        if getattr(self, "_keyword_input", None) is not None:
            self._keyword_input.setFocus()
        # Keyword-gated form starts the delay once the commit button is actually visible.
        if getattr(self, "_commit_btn", None) is not None and not self._verse_keyword:
            self._start_commit_delay()
        super().showEvent(event)

    def _start_commit_delay(self) -> None:
        if self._commit_delay_elapsed:
            return
        QTimer.singleShot(5000, self._on_commit_delay_elapsed)

    def _on_commit_delay_elapsed(self) -> None:
        self._commit_delay_elapsed = True
        self._sync_commit_enabled()

    def done(self, result: int) -> None:
        self._close_all_cards()
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        super().done(result)

    # ------------------------------------------------------------------
    # Feelings panel reveal
    # ------------------------------------------------------------------

    def _on_keyword_typed(self, text: str) -> None:
        """Visual feedback only — reveal happens on Enter."""
        pass

    def _on_keyword_confirmed(self) -> None:
        """Called when the user presses Enter in the keyword input."""
        if getattr(self, "_keyword_input", None) is None:
            return
        text = self._keyword_input.text()
        if text.strip().lower() != self._verse_keyword.lower():
            return
        if self._session_form_widget.isVisible():
            return
        self._animate_form_open()
        self._start_commit_delay()

    def _animate_form_open(self) -> None:
        # Show the form unconstrained so the layout can compute its natural size.
        self._session_form_widget.setMaximumHeight(16_777_215)
        self._session_form_widget.show()
        self._session_form_widget.updateGeometry()
        form_target_h = self._session_form_widget.sizeHint().height()

        # Collapse back to zero for the animation start.
        self._session_form_widget.setMaximumHeight(0)
        start_dialog_h = self.height()

        anim = QPropertyAnimation(self._session_form_widget, QByteArray(b"maximumHeight"), self)
        anim.setDuration(400)
        anim.setStartValue(0)
        anim.setEndValue(form_target_h)
        anim.setEasingCurve(QEasingCurve.Type.OutExpo)

        # Drive the dialog height directly — avoids adjustSize() querying the
        # form widget's full sizeHint and jumping to the target height immediately.
        def _on_value(v: int) -> None:
            self.resize(self.width(), start_dialog_h + v)

        anim.valueChanged.connect(_on_value)
        anim.finished.connect(lambda: (
            self._session_form_widget.setMaximumHeight(16_777_215),
            self.adjustSize(),
        ))
        anim.start()
        self._form_open_anim = anim  # keep reference so GC doesn't kill it

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
        enabled = (
            self._commit_delay_elapsed
            and _is_proper_sentence(self._reason_edit.toPlainText())
            and bool(self._selected_internet_reason)
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
        self.selected_feelings = []
        self.accept()

