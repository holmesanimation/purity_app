"""Panic reason selection dialog — redesigned.

Layout (top to bottom):
  1. Reminder banner  — bold title, regular note, bold verse_ref, italic verse
  2. "How are you feeling?" section header
  3. Reason buttons (2-column grid) — pressing toggles selection and
     spawns / dismisses a floating RecoveryNoteCard beside the dialog
  4. "Help Me" button — enabled when ≥ 1 reason is selected

Usage::

    reminder = panic_reminders.get_random()   # may be None
    dialog = PanicReasonDialog(stats=panic_stats, reminder=reminder, parent=None)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        selected = dialog.selected_reason_ids
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
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
)
from ui.intervention.base_popup import BasePopup

# ---------------------------------------------------------------------------
# Dialog-local font sizes — tweak here without affecting the rest of the app
# ---------------------------------------------------------------------------
_FS_REMINDER_TITLE  = 24   # bold identity headline
_FS_REMINDER_NOTE   = 16   # supporting affirmation
_FS_REMINDER_VERSE  = 16   # scripture reference + quote
_FS_SECTION_HEADER  = 13   # "How are you feeling?" label
_FS_REASON_BTN      = 11   # reason grid buttons
_FS_AWARENESS       = 10   # subtle recurrence copy
_FS_HELP_BTN        = 11   # Help Me button
from ui.intervention.recovery_note_card import CARD_WIDTH, CARD_HEIGHT, RecoveryNoteCard

# ---------------------------------------------------------------------------
# Reason definitions  (stable ID → display label)
# ---------------------------------------------------------------------------

REASON_LABELS: list[tuple[str, str]] = [
    ("home_alone",          "Home Alone"),
    ("triggering_content",  "Triggering Content"),
    ("tired",               "Tired"),
    ("hungry",              "Hungry"),
    ("biological_urge",     "Biological Urge"),
    ("aimless",             "Aimless"),
    ("lonely",              "Lonely"),
    ("discouraged",         "Discouraged"),
    ("anxious",             "Anxious"),
    ("angry",               "Angry"),
    ("avoiding_something",  "Avoiding Something"),
    ("drained",             "Drained"),
]

_REASON_ID_TO_LABEL: dict[str, str] = dict(REASON_LABELS)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_BTN_IDLE = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 8px;"
    f"  color: {COLOR_TEXT};"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {_FS_REASON_BTN}pt;"
    f"  padding: 8px 10px;"
    f"  text-align: left;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_SURFACE};"
    f"  border: 1px solid {COLOR_ACCENT};"
    f"}}"
)

_BTN_SELECTED = (
    f"QPushButton {{"
    f"  background-color: {COLOR_ACCENT};"
    f"  border: 1px solid {COLOR_ACCENT_DARK};"
    f"  border-radius: 8px;"
    f"  color: #ffffff;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {_FS_REASON_BTN}pt;"
    f"  font-weight: 700;"
    f"  padding: 8px 10px;"
    f"  text-align: left;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_ACCENT_DARK};"
    f"}}"
)

_BTN_HELP_ENABLED = (
    f"QPushButton {{"
    f"  background-color: {COLOR_ACCENT};"
    f"  color: #ffffff;"
    f"  border: none;"
    f"  border-radius: 8px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {_FS_HELP_BTN}pt;"
    f"  font-weight: 700;"
    f"  padding: 9px 24px;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_ACCENT_DARK};"
    f"}}"
)

_BTN_HELP_DISABLED = (
    f"QPushButton {{"
    f"  background-color: {COLOR_BORDER};"
    f"  color: {COLOR_TEXT_MUTED};"
    f"  border: none;"
    f"  border-radius: 8px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {_FS_HELP_BTN}pt;"
    f"  font-weight: 600;"
    f"  padding: 9px 24px;"
    f"}}"
)

_REMINDER_FRAME_STYLE = (
    f"QFrame {{"
    f"  background-color: {COLOR_SURFACE_3};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 8px;"
    f"}}"
)

# ---------------------------------------------------------------------------
# Card orbit slots (10 positions around the dialog, filled in order)
# ---------------------------------------------------------------------------
# 3 right → 2 bottom → 3 left → 2 top.

_SLOT_COUNT = 10
_CARD_GAP   = 18   # px gap between card edge and dialog edge


def _compute_slots(dialog_geo: QRect) -> list[QPoint]:
    """Return 10 absolute screen positions for note cards around *dialog_geo*."""
    x, y = dialog_geo.left(), dialog_geo.top()
    w, h = dialog_geo.width(), dialog_geo.height()
    cw, ch = CARD_WIDTH, CARD_HEIGHT
    g = _CARD_GAP
    mid_y = y + (h - ch) // 2

    return [
        # Right (top / mid / bottom)
        QPoint(x + w + g,   y),
        QPoint(x + w + g,   mid_y),
        QPoint(x + w + g,   y + h - ch),
        # Bottom (left-aligned / right-aligned)
        QPoint(x,           y + h + g),
        QPoint(x + w - cw,  y + h + g),
        # Left (top / mid / bottom)
        QPoint(x - cw - g,  y),
        QPoint(x - cw - g,  mid_y),
        QPoint(x - cw - g,  y + h - ch),
        # Top (left-aligned / right-aligned)
        QPoint(x,           y - ch - g),
        QPoint(x + w - cw,  y - ch - g),
    ]


# ---------------------------------------------------------------------------
# Full-screen dim overlay
# ---------------------------------------------------------------------------

class _ScreenDimOverlay(QWidget):
    """Frameless full-screen semi-transparent overlay shown behind the dialog."""

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


class PanicReasonDialog(BasePopup):
    """Redesigned reason selection dialog with reminder banner and note cards.

    Attributes:
        selected_reason_ids: List of selected reason IDs after ``accept()``.
    """

    DEFAULT_WIDTH  = 1000
    DEFAULT_HEIGHT = 800

    def __init__(
        self,
        *,
        stats: Optional[object] = None,     # PanicStats | None
        reminder: Optional[dict] = None,    # Reminder | None
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("", parent)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        # Fix width only; let height shrink/grow with visible content.
        self.setFixedWidth(self.DEFAULT_WIDTH)
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)  # release the fixed-height constraint

        # BasePopup adds a QSpacerItem (addStretch) between body_layout and
        # button_row.  That spacer makes adjustSize() think more space is needed.
        # Remove it so the window height truly tracks visible content.
        root_layout = self.layout()
        for i in range(root_layout.count() - 1, -1, -1):
            item = root_layout.itemAt(i)
            if item is not None and item.spacerItem() is not None:
                root_layout.takeAt(i)
                break

        self.selected_reason_ids: list[str] = []

        self._stats    = stats
        self._reminder = reminder

        # reason_id → {btn, slot, card}
        self._active: dict[str, dict] = {}
        self._selected_ids: set[str] = set()
        self._overlay: Optional[_ScreenDimOverlay] = None

        self._build_ui()
        self.adjustSize()  # fit height to initial visible content

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
        self._close_all_cards()
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        super().done(result)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── 1. Reminder banner ────────────────────────────────────────
        if self._reminder:
            self._add_reminder_banner(self._reminder)

        # ── 2. Awareness copy (subtle, shown only when stats warrant it)
        self._awareness_label = QLabel("")
        self._awareness_label.setWordWrap(True)
        self._awareness_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._awareness_label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-family: '{FONT_FAMILY}';"
            f"font-size: {_FS_AWARENESS}pt; font-style: italic;"
            f"background: transparent; padding: 2px 0 0 0;"
        )
        self._awareness_label.hide()
        self.body_layout.addWidget(self._awareness_label)
        self._populate_awareness_copy()

        # ── 3. "How are you feeling?" expand button (full width) ─────
        self._feeling_btn = QPushButton("How are you feeling?")
        self._feeling_btn.setMinimumHeight(46)
        self._feeling_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_SURFACE_2};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 8px;"
            f"  color: {COLOR_TEXT};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {_FS_SECTION_HEADER}pt;"
            f"  font-weight: 700;"
            f"  padding: 10px;"
            f"  text-align: center;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_ACCENT};"
            f"}}"
        )
        self._feeling_btn.clicked.connect(self._reveal_feelings)
        self.body_layout.addWidget(self._feeling_btn)

        # ── 4. 2-column grid of reason buttons (hidden until revealed) ─
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        grid = QGridLayout(self._grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        for idx, (reason_id, label) in enumerate(REASON_LABELS):
            row, col = divmod(idx, 2)
            btn = QPushButton(label)
            btn.setMinimumHeight(38)
            btn.setStyleSheet(_BTN_IDLE)
            btn.clicked.connect(
                lambda _checked, rid=reason_id, lbl=label, b=btn:
                    self._toggle_reason(rid, lbl, b)
            )
            grid.addWidget(btn, row, col)
            self._active[reason_id] = {"btn": btn, "slot": None, "card": None}

        self._grid_widget.hide()
        self.body_layout.addWidget(self._grid_widget)

        # ── 5. Help Me button (hidden until feelings revealed) ────────
        self._help_btn = QPushButton("Help Me")
        self._help_btn.setMinimumHeight(42)
        self._help_btn.clicked.connect(self._on_accept)
        self._help_btn.hide()
        self.button_row.addWidget(self._help_btn)
        self._sync_help_button()

    def _add_reminder_banner(self, reminder: dict) -> None:
        """Insert the identity reminder block above the reasons grid."""
        frame = QFrame()
        frame.setStyleSheet(_REMINDER_FRAME_STYLE)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(14, 12, 14, 12)
        frame_layout.setSpacing(4)

        # Bold black title
        lbl_title = QLabel(reminder.get("title", ""))
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {_FS_REMINDER_TITLE}pt;"
            f"font-weight: 700; color: #1a1a1a; background: transparent; border: none;"
        )
        frame_layout.addWidget(lbl_title)

        # Regular-weight note
        lbl_note = QLabel(reminder.get("note", ""))
        lbl_note.setWordWrap(True)
        lbl_note.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {_FS_REMINDER_NOTE}pt;"
            f"color: {COLOR_TEXT}; background: transparent; border: none;"
        )
        frame_layout.addWidget(lbl_note)

        # Bold verse reference + italic verse text (rich text label)
        verse_ref  = reminder.get("verse_ref",  "")
        verse_text = reminder.get("verse_text", "")
        if verse_ref or verse_text:
            lbl_verse = QLabel(
                f'<b>{verse_ref}</b><br>'
                f'<i>&#8220;{verse_text}&#8221;</i>'
            )
            lbl_verse.setTextFormat(Qt.TextFormat.RichText)
            lbl_verse.setWordWrap(True)
            lbl_verse.setStyleSheet(
                f"font-family: '{FONT_FAMILY}'; font-size: {_FS_REMINDER_VERSE}pt;"
                f"color: {COLOR_TEXT_MUTED}; background: transparent; border: none;"
                f"padding-top: 4px;"
            )
            frame_layout.addWidget(lbl_verse)

        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body_layout.addWidget(frame)

    def _populate_awareness_copy(self) -> None:
        """Show gentle pastoral awareness copy when recurring reasons exist."""
        if self._stats is None:
            return
        try:
            top = self._stats.get_top_reasons(3)
        except Exception:
            return
        displayed_ids = {rid for rid, _ in REASON_LABELS}
        recurring = [rid for rid in top if rid in displayed_ids]
        if len(recurring) < 2:
            return
        labels = [_REASON_ID_TO_LABEL.get(r, r) for r in recurring[:2]]
        self._awareness_label.setText(
            f"Recent recurring struggle: {' + '.join(labels)}"
        )
        self._awareness_label.show()

    # ------------------------------------------------------------------
    # Reason toggle + card management
    # ------------------------------------------------------------------

    def _toggle_reason(self, reason_id: str, label: str, btn: QPushButton) -> None:
        if reason_id in self._selected_ids:
            self._deselect(reason_id, btn)
        else:
            self._select(reason_id, label, btn)
        self._sync_help_button()

    def _select(self, reason_id: str, label: str, btn: QPushButton) -> None:
        self._selected_ids.add(reason_id)
        btn.setStyleSheet(_BTN_SELECTED)
        slot = self._next_free_slot()
        card = RecoveryNoteCard(reason_id, label)
        card.dismissed.connect(
            lambda rid, b=btn: self._on_card_dismissed(rid, b)
        )
        pos = self._slot_position(slot)
        card.move(pos)
        card.show()
        self._active[reason_id]["slot"] = slot
        self._active[reason_id]["card"] = card

    def _deselect(self, reason_id: str, btn: QPushButton) -> None:
        self._selected_ids.discard(reason_id)
        btn.setStyleSheet(_BTN_IDLE)
        card: Optional[RecoveryNoteCard] = self._active[reason_id].get("card")
        if card is not None:
            try:
                card.dismissed.disconnect()
            except RuntimeError:
                pass
            card.close()
            self._active[reason_id]["card"] = None
            self._active[reason_id]["slot"] = None

    def _on_card_dismissed(self, reason_id: str, btn: QPushButton) -> None:
        """Called when the user clicks × on a card (card closes itself)."""
        self._selected_ids.discard(reason_id)
        btn.setStyleSheet(_BTN_IDLE)
        self._active[reason_id]["card"] = None
        self._active[reason_id]["slot"] = None
        self._sync_help_button()

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
    # Card slot positioning
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
        return len(used) % _SLOT_COUNT  # all slots taken; wrap

    def _slot_position(self, slot: int) -> QPoint:
        slots = _compute_slots(self.geometry())
        return slots[slot % len(slots)]

    # ------------------------------------------------------------------
    # Reveal feelings panel
    # ------------------------------------------------------------------

    def _reveal_feelings(self) -> None:
        """Show the reason grid and Help Me button; hide the expand button."""
        self._feeling_btn.hide()
        self._grid_widget.show()
        self._help_btn.show()
        self._sync_help_button()
        self.adjustSize()  # expand height to fit the newly visible grid

    # ------------------------------------------------------------------
    # Help Me button
    # ------------------------------------------------------------------

    def _sync_help_button(self) -> None:
        has_selection = bool(self._selected_ids)
        self._help_btn.setEnabled(has_selection)
        self._help_btn.setStyleSheet(
            _BTN_HELP_ENABLED if has_selection else _BTN_HELP_DISABLED
        )

    def _on_accept(self) -> None:
        self.selected_reason_ids = list(self._selected_ids)
        self.accept()
