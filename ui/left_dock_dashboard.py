"""Left-edge sliding dashboard overlay.

A frameless, always-on-top panel that docks to the left side of the primary
monitor.  It animates between:

  • Collapsed — a 2 px accent-coloured strip, plus a 20 px wide semicircular
    tab button centred vertically on the right edge.
  • Expanded  — a 700 px wide panel (content area to be added later), with
    the same tab button now at the right edge of the full panel.

Clicking the tab toggles between the two states.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    QTimer,
    Qt,
    Property,
)
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenuBar,
    QPushButton,
    QToolButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.bible_canon import BOOK_KEYS, CANON, display_ref, normalize_ref
from services.diet_state import DietState, calories_today_from_notes
from services.fake_journal import FakeJournalService
from services.mock_state import MockAppState
from services.notes_setup import bible_notes_writer, journal_notes_writer, notes_repo, prayer_notes_writer as _default_prayer_notes_writer
from services.tag_library import TagLibrary
from shane_common.notes.notes_writer import NoteType
from models.journal import JournalEntry
from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_DARK,
    COLOR_ACCENT_LIGHT,
    COLOR_BACKGROUND,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_2,
    COLOR_SURFACE_3,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

_EXPANDED_CONTENT_W: int = 700   # px — width of the content area when open
_COLLAPSED_CONTENT_W: int = 2     # px — width of the visible strip when closed

_TAB_W: int = 20                  # px — width of the semicircle tab
_TAB_H: int = 60                  # px — total height of the tab (elliptic D shape)

_ANIM_MS: int = 300               # animation duration in milliseconds

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

_C_PANEL = QColor(COLOR_SURFACE)
_C_STRIP = QColor(COLOR_ACCENT)
_C_TAB = QColor(COLOR_ACCENT)
_C_TAB_HOVER = QColor(COLOR_ACCENT_DARK)
_C_ARROW = QColor("#ffffff")


# ---------------------------------------------------------------------------
# Semicircle tab button
# ---------------------------------------------------------------------------

class _TabButton(QWidget):
    """Custom-painted semicircle handle on the right edge of the dashboard."""

    def __init__(self, on_click, parent: QWidget) -> None:
        super().__init__(parent)
        self._on_click = on_click
        self._hovered = False
        self._expanded = False
        self.setFixedSize(_TAB_W, _TAB_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # -- public API --------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.update()

    # -- paint -------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # D-shape: flat left edge, elliptic right bulge.
        # The bounding ellipse spans [-_TAB_W, 0, _TAB_W*2, _TAB_H].
        # arcTo with startAngle=90, spanAngle=-180 sweeps clockwise from the
        # top-centre (0, 0) through the rightmost point to the bottom-centre
        # (0, _TAB_H); closeSubpath draws the flat left edge.
        path = QPainterPath()
        path.moveTo(0, 0)
        path.arcTo(QRectF(-_TAB_W, 0, _TAB_W * 2, _TAB_H), 90.0, -180.0)
        path.closeSubpath()

        color = _C_TAB_HOVER if self._hovered else _C_TAB
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        # Chevron arrow — right-pointing when collapsed, left-pointing when
        # expanded — drawn in the right half of the tab.
        self._draw_chevron(painter)

        painter.end()

    def _draw_chevron(self, painter: QPainter) -> None:
        """Paint a small arrow in the centre of the visible bulge area."""
        cx = _TAB_W * 0.60          # horizontal centre of the bulge region
        cy = _TAB_H / 2.0
        arm = 6.0                    # half-height of chevron arms
        tip = 5.0                    # horizontal depth of the point

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_C_ARROW)

        arrow = QPainterPath()
        if not self._expanded:
            # Right-pointing >
            arrow.moveTo(cx - tip / 2, cy - arm)
            arrow.lineTo(cx + tip / 2, cy)
            arrow.lineTo(cx - tip / 2, cy + arm)
            arrow.closeSubpath()
        else:
            # Left-pointing <
            arrow.moveTo(cx + tip / 2, cy - arm)
            arrow.lineTo(cx - tip / 2, cy)
            arrow.lineTo(cx + tip / 2, cy + arm)
            arrow.closeSubpath()

        painter.drawPath(arrow)

    # -- events ------------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()


# ---------------------------------------------------------------------------
# Prayer card widget
# ---------------------------------------------------------------------------

_ARROW_BTN_W = 10  # px — arrow buttons must be no wider than this

_ARROW_BTN_STYLE = (
    "QPushButton { background: transparent; border: none; color: #5a3000;"
    " font-size: 14px; font-weight: 800; padding: 0px; }"
    "QPushButton:hover { background-color: rgba(255,255,255,120) }"
    "QPushButton:disabled { color: rgba(90,48,0,80); }"
)

_VERSE_BTN_STYLE = (
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

_VERSE_NAV_BTN_STYLE = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  color: {COLOR_TEXT};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 6px;"
    f"  font-size: 16px;"
    f"  font-weight: 800;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {COLOR_SURFACE};"
    f"  color: {COLOR_TEXT};"
    f"  border: 1px solid {COLOR_ACCENT};"
    f"}}"
)


class _DashboardPrayerCard(QFrame):
    """Prayer session card for the dashboard sidebar.

    Sources its recipients from a session list (set via ``start_session``,
    normally called when a Pulse fires), not a fixed daily queue.  Left/right
    arrow buttons cycle through the session; 'I Prayed' marks the currently
    viewed recipient as prayed for; 'Add Note' commits a single note tagged
    with the recipient's name via the Prayer-owner notes writer.
    Background is a radial gradient: #ffa400 at centre, #ffc55e at edges.
    """

    def __init__(self, prayer_notes_writer=_default_prayer_notes_writer, new_session_callback=None, open_recipients_callback=None, prayed_callback=None, parent=None) -> None:
        super().__init__(parent)
        self._notes_writer = prayer_notes_writer
        self._new_session_callback = new_session_callback
        self._open_recipients_callback = open_recipients_callback
        self._prayed_callback = prayed_callback
        self._session_names: list[str] = []
        self._prayed_flags: list[bool] = []
        self._current_index: int = 0
        # Transparent base so paintEvent controls the background fully.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setStyleSheet(
            "QFrame { border: none; border-radius: 8px; background: transparent; }"
        )
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(4)

        self._prev_btn = QPushButton("⮜")
        self._prev_btn.setIconSize(QSize(10, 16))
        self._prev_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._prev_btn.setFixedWidth(_ARROW_BTN_W)
        self._prev_btn.setStyleSheet(_ARROW_BTN_STYLE)
        self._prev_btn.clicked.connect(self._on_prev)
        outer.addWidget(self._prev_btn)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        # Title row: logo left, "X of Y" right
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)

        logo_lbl = QLabel()
        logo_lbl.setStyleSheet("background: transparent; border: none;")
        _logo_path = r"G:\PURITY_APP\images\prayermate_logo.png"
        _pixmap = QPixmap(_logo_path)
        if not _pixmap.isNull():
            _pixmap = _pixmap.scaledToWidth(140, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(_pixmap)
        else:
            logo_lbl.setText("Prayer")
            logo_lbl.setStyleSheet(
                f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_MEDIUM}pt;"
                f"font-weight: 700; color: {COLOR_TEXT}; background: transparent;"
            )
        title_row.addWidget(logo_lbl)
        title_row.addStretch()

        self.recipients_btn = QToolButton()
        self.recipients_btn.setText("Recipients")
        self.recipients_btn.setStyleSheet(
            "QToolButton { background-color: rgba(255,255,255,80); color: #5a3000;"
            " border: 1px solid rgba(90,48,0,120); border-radius: 6px}"
            "QToolButton:hover { background-color: rgba(255,255,255,120); }"
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"font-weight: 600; color: #5a3000; background: transparent;"
        )
        title_row.addWidget(self.recipients_btn)
        self.recipients_btn.clicked.connect(self._on_recipients_clicked)

        self._progress_lbl = QLabel()
        self._progress_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"font-weight: 600; color: #5a3000; background: transparent;"
        )
        title_row.addWidget(self._progress_lbl)
        vbox.addLayout(title_row)

        # Person name
        self._name_lbl = QLabel()
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_LARGE}pt;"
            f"font-weight: 700; color: #3a2000; background: transparent; border: none;"
        )
        vbox.addWidget(self._name_lbl)

        self._last_note_lbl = QLabel()
        self._last_note_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._last_note_lbl.setWordWrap(True)
        self._last_note_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"color: #5a3000; background: transparent; border: none;"
        )
        self._last_note_lbl.setVisible(False)
        vbox.addWidget(self._last_note_lbl)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._prayed_btn = QPushButton("I Prayed ✓")
        self._prayed_btn.setCheckable(True)
        self._prayed_btn.setStyleSheet(
            "QPushButton { background-color: rgba(255,255,255,80); color: #5a3000;"
            " border: 1px solid rgba(90,48,0,120); border-radius: 6px; padding: 6px 12px; }"
            "QPushButton:hover { background-color: rgba(255,255,255,120); }"
            "QPushButton:checked { background-color: #000000; color: #ffffff; border: none; }"
            "QPushButton:checked:hover { background-color: #222222; }"
        )
        self._prayed_btn.toggled.connect(self._on_prayed_toggled)
        btn_row.addWidget(self._prayed_btn)

        self._add_note_btn = QPushButton("Add Note")
        self._add_note_btn.setStyleSheet(
            "QPushButton { background-color: rgba(255,255,255,80); color: #5a3000;"
            " border: 1px solid rgba(90,48,0,120); border-radius: 6px; padding: 6px 12px; }"
            "QPushButton:hover { background-color: rgba(255,255,255,120); }"
        )
        self._add_note_btn.clicked.connect(self._on_add_note)
        btn_row.addWidget(self._add_note_btn)

        vbox.addLayout(btn_row)

        self._new_session_btn = QPushButton("New Session")
        self._new_session_btn.setStyleSheet(
            "QPushButton { background-color: rgba(255,255,255,60); color: #5a3000;"
            " border: 1px solid rgba(90,48,0,90); border-radius: 6px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: rgba(255,255,255,120); }"
        )
        self._new_session_btn.clicked.connect(self._on_new_session)
        vbox.addWidget(self._new_session_btn)

        outer.addWidget(content, stretch=1)

        self._next_btn = QPushButton("⮞")
        self._next_btn.setIconSize(QSize(10, 16))
        self._next_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._next_btn.setFixedWidth(_ARROW_BTN_W)
        self._next_btn.setStyleSheet(_ARROW_BTN_STYLE)
        self._next_btn.clicked.connect(self._on_next)
        outer.addWidget(self._next_btn)

        self._refresh()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect()
        cx = r.width() / 2.0
        cy = r.height() / 2.0
        radius = max(cx, cy)

        grad = QRadialGradient(cx, cy, radius)
        grad.setColorAt(0.0, QColor("#ffa400"))
        grad.setColorAt(1.0, QColor("#ffc55e"))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(r, 8, 8)
        painter.end()

    # -- session management -------------------------------------------------

    def start_session(self, names: list[str]) -> None:
        """Begin a new prayer session — called each time a Pulse fires."""
        self._session_names = list(names)
        self._prayed_flags = [False] * len(self._session_names)
        self._current_index = 0
        self._refresh()

    def _current_name(self) -> str | None:
        if not self._session_names:
            return None
        return self._session_names[self._current_index]

    def _on_prev(self) -> None:
        if len(self._session_names) < 2:
            return
        self._current_index = (self._current_index - 1) % len(self._session_names)
        self._refresh()

    def _on_next(self) -> None:
        if len(self._session_names) < 2:
            return
        self._current_index = (self._current_index + 1) % len(self._session_names)
        self._refresh()

    def _refresh(self) -> None:
        total = len(self._session_names)
        name = self._current_name()

        if name is None:
            self._name_lbl.setText("No active prayer session")
            self._progress_lbl.setText("")
            self._prayed_btn.blockSignals(True)
            self._prayed_btn.setChecked(False)
            self._prayed_btn.blockSignals(False)
            return

        prayed = self._prayed_flags[self._current_index]
        self._name_lbl.setText(name)
        self._progress_lbl.setText(f"{self._current_index + 1} of {total}")
        self._prayed_btn.blockSignals(True)
        self._prayed_btn.setChecked(prayed)
        self._prayed_btn.blockSignals(False)
        self._refresh_last_note_label(name)

    def _rows_for_recipient(self, name: str) -> list:
        return [
            row
            for row in notes_repo.rows_for_owner("Prayer")
            if name in (row.context.get("tags") or [])
        ]

    def _refresh_last_note_label(self, name: str) -> None:
        rows = self._rows_for_recipient(name)
        if not rows:
            self._last_note_lbl.setVisible(False)
            return
        latest = max(rows, key=lambda r: r.ts or 0)
        preview = (latest.text or "")[:80]
        self._last_note_lbl.setText(f"Last note: {preview}")
        self._last_note_lbl.setVisible(True)

    def _on_recipients_clicked(self) -> None:
        if self._open_recipients_callback is not None:
            self._open_recipients_callback()
            
    def _on_prayed_toggled(self, checked: bool) -> None:
        if not self._session_names:
            return
        self._prayed_flags[self._current_index] = checked
        if checked and self._prayed_callback is not None:
            name = self._current_name()
            if name is not None:
                self._prayed_callback(name)

    def _on_add_note(self) -> None:
        name = self._current_name()
        if name is None:
            return
        from ui.notes.note_dialog import NoteDialog

        NoteDialog(
            writer=self._notes_writer,
            owner="Prayer",
            context={"tags": [name]},
            show_type_selector=False,
            history_rows=self._rows_for_recipient(name),
            parent=self.window(),
        ).exec()
        self._refresh_last_note_label(name)

    def _on_new_session(self) -> None:
        if self._new_session_callback is not None:
            self._new_session_callback()


# ---------------------------------------------------------------------------
# Tag picker popup
# ---------------------------------------------------------------------------

class _TagPickerPopup(QWidget):
    """Frameless popup for selecting tags from the tag library.

    Shown below the Tags button.  Auto-dismisses when the user clicks outside
    (Qt.WindowType.Popup semantics).  Every toggle and new-tag addition fires
    *on_changed* immediately so the parent stays in sync.
    """

    def __init__(
        self,
        library: TagLibrary,
        selected: list[str],
        on_changed,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self._library = library
        self._selected = list(selected)
        self._on_changed = on_changed

        self.setFixedWidth(220)
        self.setStyleSheet(
            f"QWidget {{ background-color: {COLOR_SURFACE}; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("New tag\u2026")
        self._edit.setStyleSheet(
            f"QLineEdit {{ background-color: {COLOR_SURFACE_2}; color: {COLOR_TEXT};"
            f" border: 1px solid {COLOR_BORDER}; border-radius: 4px;"
            f" font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f" padding: 4px; }}"
        )
        self._edit.returnPressed.connect(self._add_new_tag)
        outer.addWidget(self._edit)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        outer.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setFixedHeight(180)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._tag_container = QWidget()
        self._tag_container.setStyleSheet("background: transparent;")
        self._tag_vbox = QVBoxLayout(self._tag_container)
        self._tag_vbox.setContentsMargins(0, 0, 0, 0)
        self._tag_vbox.setSpacing(1)
        scroll.setWidget(self._tag_container)
        outer.addWidget(scroll)

        self._rebuild_checkboxes()

    def _rebuild_checkboxes(self) -> None:
        while self._tag_vbox.count():
            item = self._tag_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for tag in self._library.load():
            cb = QCheckBox(tag)
            cb.setStyleSheet(
                f"QCheckBox {{ color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
                f" font-size: {FONT_SIZE_SMALL}pt; background: transparent; padding: 3px 4px; }}"
                f"QCheckBox::indicator {{ border: 1px solid {COLOR_BORDER};"
                f" width: 13px; height: 13px; }}"
                f"QCheckBox::indicator:checked {{ background-color: {COLOR_ACCENT};"
                f" border: 1px solid {COLOR_ACCENT}; }}"
            )
            cb.setChecked(tag in self._selected)
            cb.toggled.connect(lambda checked, t=tag: self._toggle(t, checked))
            self._tag_vbox.addWidget(cb)
        self._tag_vbox.addStretch()

    def _toggle(self, tag: str, checked: bool) -> None:
        if checked and tag not in self._selected:
            self._selected.append(tag)
        elif not checked and tag in self._selected:
            self._selected.remove(tag)
        self._on_changed(list(self._selected))

    def _add_new_tag(self) -> None:
        tag = self._edit.text().strip().lower()
        if not tag:
            return
        self._library.add(tag)
        if tag not in self._selected:
            self._selected.append(tag)
        self._edit.clear()
        self._on_changed(list(self._selected))
        self._rebuild_checkboxes()


# ---------------------------------------------------------------------------
# Hover-tracking label (pauses dashboard topmost-raise during tooltip display)
# ---------------------------------------------------------------------------

class _HoverLabel(QLabel):
    """QLabel that fires ``on_enter`` / ``on_leave`` callbacks on mouse hover."""

    def __init__(self, text: str, on_enter, on_leave, parent=None) -> None:
        super().__init__(text, parent)
        self._on_enter = on_enter
        self._on_leave = on_leave

    def enterEvent(self, event) -> None:  # noqa: N802
        self._on_enter()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._on_leave()
        super().leaveEvent(event)


# ---------------------------------------------------------------------------
# Dashboard journal panel (tab widget with tagged verses)
# ---------------------------------------------------------------------------

_GUIDED_QUESTIONS = [
    "How are you feeling right now?",
    "Was there a moment of struggle or temptation today?",
    "What good thing did you do for your soul today?",
]


# ---------------------------------------------------------------------------
# Free-form journal widget (verse tagging + note commit)
# ---------------------------------------------------------------------------

class _FreeJournalWidget(QWidget):
    """Free-text journal entry: tagged verses, tags, and a commit button.

    ``auto_tagged_ref`` (set via :meth:`set_auto_tagged_ref`) is always saved
    with the entry in addition to whatever is picked via "Tag Verses".
    """

    def __init__(
        self,
        journal_service: FakeJournalService,
        bible_library=None,
        notes_writer=journal_notes_writer,
        prayer_recipient_name: str | None = None,
        prayer_notes_writer=None,
        auto_tagged_ref: Optional[dict] = None,
        on_saved=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._svc = journal_service
        self._bible_library = bible_library
        self._notes_writer = notes_writer
        self._prayer_recipient_name = prayer_recipient_name
        self._prayer_notes_writer = prayer_notes_writer
        self._on_saved = on_saved
        self._auto_tagged_ref: Optional[dict] = auto_tagged_ref
        self._tagged_refs: list[dict] = []  # additional [{"key": ..., "display": ...}]
        self._tag_library = TagLibrary()
        self._selected_tags: list[str] = []
        self._tag_popup: Optional[QWidget] = None
        self._hovering_verse: bool = False
        self._tag_prayer_btn: Optional[QPushButton] = None

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(8)

        self._free_timestamp_lbl = QLabel(self._now_str())
        self._free_timestamp_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        vbox.addWidget(self._free_timestamp_lbl)

        self._free_input = QTextEdit()
        self._free_input.setPlaceholderText("Write freely…")
        vbox.addWidget(self._free_input, stretch=1)

        # Tagged verses row
        tagged_row = QWidget()
        tagged_row.setStyleSheet("background: transparent;")
        tagged_hbox = QHBoxLayout(tagged_row)
        tagged_hbox.setContentsMargins(0, 0, 0, 0)
        tagged_hbox.setSpacing(6)

        tagged_title = QLabel("Tagged Verses:")
        tagged_title.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt;"
            f"font-weight: 600; background: transparent;"
        )
        tagged_title.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        tagged_hbox.addWidget(tagged_title)

        self._tagged_scroll = QScrollArea()
        self._tagged_scroll.setFixedHeight(28)
        self._tagged_scroll.setWidgetResizable(True)
        self._tagged_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._tagged_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tagged_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tagged_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self._tagged_inner = QWidget()
        self._tagged_inner.setStyleSheet("background: transparent;")
        self._tagged_inner_layout = QHBoxLayout(self._tagged_inner)
        self._tagged_inner_layout.setContentsMargins(0, 0, 0, 0)
        self._tagged_inner_layout.setSpacing(0)
        self._tagged_inner_layout.addStretch()
        self._tagged_scroll.setWidget(self._tagged_inner)
        tagged_hbox.addWidget(self._tagged_scroll, stretch=1)

        vbox.addWidget(tagged_row)

        self._view_notes_btn = QPushButton("View 0 Notes")
        self._view_notes_btn.setFixedWidth(140)
        self._view_notes_btn.clicked.connect(self._on_view_notes)
        vbox.addWidget(self._view_notes_btn)

        # Tags display row
        tags_row = QWidget()
        tags_row.setStyleSheet("background: transparent;")
        tags_hbox = QHBoxLayout(tags_row)
        tags_hbox.setContentsMargins(0, 0, 0, 0)
        tags_hbox.setSpacing(6)

        # tags_title = QLabel("Tags:")
        # tags_title.setStyleSheet(
        #     f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt;"
        #     f"font-weight: 600; background: transparent;"
        # )
        # tags_title.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # tags_hbox.addWidget(tags_title)

        self._tags_scroll = QScrollArea()
        self._tags_scroll.setFixedHeight(28)
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._tags_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tags_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self._tags_inner = QWidget()
        self._tags_inner.setStyleSheet("background: transparent;")
        self._tags_inner_layout = QHBoxLayout(self._tags_inner)
        self._tags_inner_layout.setContentsMargins(0, 0, 0, 0)
        self._tags_inner_layout.setSpacing(0)
        self._tags_inner_layout.addStretch()
        self._tags_scroll.setWidget(self._tags_inner)
        tags_hbox.addWidget(self._tags_scroll, stretch=1)
        vbox.addWidget(tags_row)

        # Button row: Tag Verses | Tags | spacer | Save Journal Entry
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)

        tag_btn = QPushButton("Tag Verses")
        tag_btn.setFixedWidth(100)
        tag_btn.clicked.connect(self._open_bible_browser)
        btn_row.addWidget(tag_btn)

        if self._prayer_recipient_name is not None:
            self._tag_prayer_btn = QPushButton("Tag Prayer Recipient")
            self._tag_prayer_btn.setCheckable(True)
            self._tag_prayer_btn.setFixedWidth(180)
            self._tag_prayer_btn.setStyleSheet(
                f"QPushButton {{ background-color: {COLOR_SURFACE_2}; color: {COLOR_TEXT}; }}"
                f"QPushButton:checked {{ background-color: {COLOR_ACCENT}; color: white;"
                f" border: 2px solid {COLOR_ACCENT_DARK}; font-weight: 700; }}"
            )
            btn_row.addWidget(self._tag_prayer_btn)

        self._tags_picker_btn = QPushButton("Tags")
        self._tags_picker_btn.setFixedWidth(60)
        self._tags_picker_btn.clicked.connect(self._open_tag_picker)
        btn_row.addWidget(self._tags_picker_btn)

        btn_row.addStretch()

        save_btn = QPushButton("Save Journal Entry")
        save_btn.setFixedWidth(180)
        save_btn.clicked.connect(self._save_free)
        btn_row.addWidget(save_btn)

        vbox.addLayout(btn_row)

        self._rebuild_tagged_display()

    # -- public API ----------------------------------------------------

    def set_auto_tagged_ref(self, ref: Optional[dict]) -> None:
        """Set the verse that is always tagged on save, regardless of picks."""
        self._auto_tagged_ref = ref
        self._rebuild_tagged_display()

    # -- Tagged verse display ----------------------------------------------

    def _display_refs(self) -> list[dict]:
        """Auto-tagged ref (if any) followed by additionally tagged refs, deduped."""
        refs: list[dict] = []
        seen: set[str] = set()
        if self._auto_tagged_ref is not None:
            refs.append(self._auto_tagged_ref)
            seen.add(self._auto_tagged_ref["key"])
        for ref in self._tagged_refs:
            if ref["key"] not in seen:
                refs.append(ref)
                seen.add(ref["key"])
        return refs

    def _rebuild_tagged_display(self) -> None:
        """Clear and repopulate the tagged-verses horizontal scroll area."""
        # Remove all widgets from layout except the trailing stretch
        while self._tagged_inner_layout.count() > 1:
            item = self._tagged_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        refs = self._display_refs()
        for i, ref in enumerate(refs):
            display = ref.get("display", ref.get("key", ""))
            key = ref.get("key", "")

            # Build tooltip text from bible_library if available
            tooltip_text = display
            if self._bible_library is not None:
                version = self._bible_library.get_latest_version(key)
                if version:
                    tooltip_text = f"{display}: {version['text']}"

            lbl = _HoverLabel(
                display,
                on_enter=self._on_verse_hover_enter,
                on_leave=self._on_verse_hover_leave,
            )
            lbl.setToolTip(tooltip_text)
            lbl.setStyleSheet(
                f"color: {COLOR_ACCENT}; font-size: {FONT_SIZE_SMALL}pt;"
                f"background: transparent;"
            )
            self._tagged_inner_layout.insertWidget(i * 2, lbl)

            # Add comma separator (not after the last item)
            if i < len(refs) - 1:
                sep = QLabel(", ")
                sep.setStyleSheet(
                    f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt;"
                    f"background: transparent;"
                )
                self._tagged_inner_layout.insertWidget(i * 2 + 1, sep)

        self._update_view_notes_button()

    def _rows_for_tagged_notes(self) -> list:
        """Return previously committed notes (this widget's owner) tagged with any displayed verse."""
        keys = {ref["key"] for ref in self._display_refs()}
        if not keys:
            return []
        owner = self._notes_writer._owner
        return [
            row
            for row in notes_repo.rows_for_owner(owner)
            if any(tagged.get("key") in keys for tagged in (row.context.get("tagged_verses") or []))
        ]

    def _update_view_notes_button(self) -> None:
        count = len(self._rows_for_tagged_notes())
        self._view_notes_btn.setText(f"View {count} Notes")

    def _on_view_notes(self) -> None:
        from ui.notes.note_dialog import NoteDialog

        ctx: dict = {}
        combined_refs = self._display_refs()
        if combined_refs:
            ctx["tagged_verses"] = combined_refs
        if self._selected_tags or combined_refs:
            ctx["tags"] = list(self._selected_tags) + [
                ref["display"] for ref in combined_refs if ref.get("display")
            ]
        NoteDialog(
            writer=self._notes_writer,
            owner=self._notes_writer._owner,
            context=ctx,
            show_type_selector=False,
            history_rows=self._rows_for_tagged_notes(),
            parent=self.window(),
        ).exec()
        self._update_view_notes_button()

    def _rebuild_tags_display(self) -> None:
        """Clear and repopulate the tags horizontal scroll area."""
        while self._tags_inner_layout.count() > 1:
            item = self._tags_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, tag in enumerate(self._selected_tags):
            lbl = QLabel(f"#{tag}")
            lbl.setStyleSheet(
                f"color: {COLOR_ACCENT}; font-size: {FONT_SIZE_SMALL}pt;"
                f"background: transparent;"
            )
            self._tags_inner_layout.insertWidget(i * 2, lbl)
            if i < len(self._selected_tags) - 1:
                sep = QLabel(", ")
                sep.setStyleSheet(
                    f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt;"
                    f"background: transparent;"
                )
                self._tags_inner_layout.insertWidget(i * 2 + 1, sep)

    def _on_verse_hover_enter(self) -> None:
        self._hovering_verse = True

    def _on_verse_hover_leave(self) -> None:
        self._hovering_verse = False

    # -- Bible browser -----------------------------------------------------

    def _open_bible_browser(self) -> None:
        if self._bible_library is None:
            return
        from ui.tools.bible_browser_dialog import BibleBrowserDialog
        dlg = BibleBrowserDialog(
            bible_library=self._bible_library,
            selected_refs=list(self._tagged_refs),
            select_mode=True,
            parent=None,
        )
        if dlg.exec():
            self._tagged_refs = dlg.get_selected_refs()
            self._rebuild_tagged_display()

    def _open_tag_picker(self) -> None:
        self._tag_popup = _TagPickerPopup(
            library=self._tag_library,
            selected=list(self._selected_tags),
            on_changed=self._on_tags_changed,
        )
        self._tag_popup.adjustSize()
        pos = self._tags_picker_btn.mapToGlobal(
            self._tags_picker_btn.rect().topLeft()
        )
        self._tag_popup.move(pos.x(), pos.y() - self._tag_popup.height())
        self._tag_popup.show()
        self._tag_popup.raise_()

    def _on_tags_changed(self, tags: list[str]) -> None:
        self._selected_tags = tags
        self._rebuild_tags_display()

    # -- Save ----------------------------------------------------------

    def _save_free(self) -> None:
        text = self._free_input.toPlainText().strip()
        if not text:
            return
        entry = JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            entry_type="free_journal",
            free_text=text,
            tags=list(self._selected_tags),
        )
        self._svc.append(entry)
        tag_prayer = self._tag_prayer_btn is not None and self._tag_prayer_btn.isChecked()
        writer = self._prayer_notes_writer if tag_prayer else self._notes_writer
        ctx: dict = {}
        tags = list(self._selected_tags)
        if tag_prayer and self._prayer_recipient_name is not None:
            tags.append(self._prayer_recipient_name)
        combined_refs = self._display_refs()
        if combined_refs:
            ctx["tagged_verses"] = combined_refs
            tags.extend(ref["display"] for ref in combined_refs if ref.get("display"))
        if tags:
            ctx["tags"] = tags
        note = writer.build_note(
            note_type=NoteType.GENERAL,
            text=text,
            context=ctx,
        )
        writer.commit(note)
        if self._tag_prayer_btn is not None:
            self._tag_prayer_btn.setChecked(False)
        self._free_input.clear()
        self._free_timestamp_lbl.setText(self._now_str())
        self._tagged_refs = []
        self._rebuild_tagged_display()
        self._selected_tags = []
        self._rebuild_tags_display()
        if self._on_saved is not None:
            self._on_saved()

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%A, %B %d  %H:%M")


class _DashboardJournalPanel(QWidget):
    """Tab widget mirroring JournalPanel with an enhanced Free Journal tab.

    The Free Journal tab adds:
    - 'Tag Verses' button that opens BibleBrowserDialog in select_mode
    - A tagged-verses row showing selected references with commas and tooltips
    """

    def __init__(
        self,
        journal_service: FakeJournalService,
        bible_library=None,
        parent=None,
        notes_writer=journal_notes_writer,
        prayer_recipient_name: str | None = None,
        prayer_notes_writer=None,
        leading_tabs: list[tuple[str, QWidget]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = journal_service
        self._prayer_recipient_name = prayer_recipient_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        layout.addWidget(self._tabs)

        self._free_journal = _FreeJournalWidget(
            journal_service=journal_service,
            bible_library=bible_library,
            notes_writer=notes_writer,
            prayer_recipient_name=prayer_recipient_name,
            prayer_notes_writer=prayer_notes_writer,
            on_saved=self._on_journal_saved,
        )

        # Offset applied to tab indices below when leading tabs are prepended.
        self._tab_offset = len(leading_tabs) if leading_tabs else 0
        for title, widget in leading_tabs or []:
            self._tabs.addTab(widget, title)

        self._tabs.addTab(self._build_guided_tab(), "Guided Check-In")
        self._tabs.addTab(self._free_journal, "Free Journal")
        self._tabs.addTab(self._build_history_tab(), "History")

    # -- Tab builders ------------------------------------------------------

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

    def _build_history_tab(self) -> QWidget:
        from PySide6.QtWidgets import QListWidget
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(4)

        self._history_list = QListWidget()
        self._history_list.setSpacing(2)
        vbox.addWidget(self._history_list)

        self._populate_history()
        return w

    # -- Actions -----------------------------------------------------------

    def _save_guided(self) -> None:
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
        self._tabs.setCurrentIndex(self._tab_offset + 2)

    def _populate_history(self) -> None:
        self._history_list.clear()
        from PySide6.QtWidgets import QListWidgetItem
        for entry in self._svc.get_all():
            ts = entry.timestamp.strftime("%b %d %H:%M")
            if entry.entry_type == "free_journal":
                preview = (entry.free_text or "")[:60]
                text = f"[{ts}] {preview}"
            else:
                text = f"[{ts}] Guided Check-In"
            self._history_list.addItem(QListWidgetItem(text))

    def _on_journal_saved(self) -> None:
        self._populate_history()
        self._tabs.setCurrentIndex(self._tab_offset + 2)

    # -- compatibility shims (external callers/tests reach into these) -----

    @property
    def _prayer_notes_writer(self):
        return self._free_journal._prayer_notes_writer

    @property
    def _free_input(self):
        return self._free_journal._free_input

    @property
    def _tag_prayer_btn(self):
        return self._free_journal._tag_prayer_btn

    @property
    def _hovering_verse(self):
        return self._free_journal._hovering_verse

    @property
    def _tag_popup(self):
        return self._free_journal._tag_popup

    def _save_free(self) -> None:
        self._free_journal._save_free()


# ---------------------------------------------------------------------------
# Read-mode verse widget (Read tab)
# ---------------------------------------------------------------------------

class _VerseWidget(QWidget):
    """Verse reading panel: verse text, a reflection prompt, and a journal.

    Whichever verse is displayed is always tagged on the embedded journal
    entry; "Tag Verses" only adds further verses to that entry.
    """

    def __init__(
        self,
        bible_library=None,
        journal_service: Optional[FakeJournalService] = None,
        notes_writer=bible_notes_writer,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._bible_library = bible_library
        self._verse_key: Optional[str] = None
        self._verse_ref: str = ""
        self._verse_text: str = ""

        self._build_ui(journal_service or FakeJournalService(), notes_writer)
        self.load_random_verse()

    # -- public API ----------------------------------------------------

    def load_random_verse(self) -> None:
        if not self._bible_library:
            self._ref_lbl.setText("No Bible library available.")
            return
        keys = self._bible_library.get_all_verse_keys()
        if not keys:
            self._verse_key = None
            self._ref_lbl.setText("No verses saved yet.")
            self._verse_display.setText("")
            return
        self.load_verse(random.choice(keys))

    def load_verse(self, key: str) -> None:
        if not self._bible_library:
            return
        entry = self._bible_library.get_verse(key)
        if not entry:
            return
        latest = self._bible_library.get_latest_version(key)
        self._verse_key = key
        self._verse_ref = entry.get("display", key)
        self._verse_text = latest["text"] if latest else ""
        self._ref_lbl.setText(self._verse_ref)
        self._verse_display.setText(self._verse_text)
        self._journal.set_auto_tagged_ref({"key": key, "display": self._verse_ref})

    def step_verse(self, delta: int) -> None:
        """Move to the adjacent verse in canonical order, rolling over book/canon bounds."""
        if not self._verse_key:
            self.load_random_verse()
            return
        parts = self._verse_key.rsplit("_", 2)
        if len(parts) != 3 or parts[0] not in BOOK_KEYS:
            return
        book_key, chapter, verse = parts[0], int(parts[1]), int(parts[2])
        book_idx = BOOK_KEYS.index(book_key)
        verse += delta
        verse_counts = CANON[book_key]
        if verse < 1:
            chapter -= 1
            if chapter < 1:
                book_idx = (book_idx - 1) % len(BOOK_KEYS)
                book_key = BOOK_KEYS[book_idx]
                verse_counts = CANON[book_key]
                chapter = len(verse_counts)
            verse = verse_counts[chapter - 1]
        elif verse > verse_counts[chapter - 1]:
            chapter += 1
            if chapter > len(verse_counts):
                book_idx = (book_idx + 1) % len(BOOK_KEYS)
                book_key = BOOK_KEYS[book_idx]
                verse_counts = CANON[book_key]
                chapter = 1
            verse = 1
        key = normalize_ref(book_key, chapter, verse)
        display = display_ref(book_key, chapter, verse)
        latest = self._bible_library.get_latest_version(key) if self._bible_library else None
        self._verse_key = key
        self._verse_ref = display
        self._verse_text = latest["text"] if latest else ""
        self._ref_lbl.setText(display)
        self._verse_display.setText(self._verse_text or "(No text saved for this verse.)")
        self._journal.set_auto_tagged_ref({"key": key, "display": display})

    def is_hovering_verse(self) -> bool:
        return self._journal._hovering_verse

    def tag_popup(self):
        return self._journal._tag_popup

    # -- build UI --------------------------------------------------------

    def _build_ui(self, journal_service: FakeJournalService, notes_writer) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

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
        vf.setSpacing(8)

        self._ref_lbl = QLabel()
        self._ref_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ref_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}';"
            f"font-size: {FONT_SIZE_NORMAL}pt; font-weight: 700; background: transparent;"
        )
        vf.addWidget(self._ref_lbl)

        self._verse_display = QLabel("")
        self._verse_display.setWordWrap(True)
        self._verse_display.setStyleSheet(
            f"font-family: 'Georgia'; font-size: {FONT_SIZE_LARGE}pt;"
            f" font-style: italic; color: {COLOR_TEXT_MUTED}; background: transparent;"
        )
        vf.addWidget(self._verse_display)

        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self._prev_btn.setIconSize(QSize(16, 16))
        self._prev_btn.setFixedWidth(_ARROW_BTN_W)
        self._prev_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._prev_btn.setStyleSheet(_VERSE_NAV_BTN_STYLE)
        self._prev_btn.clicked.connect(lambda: self.step_verse(-1))

        self._next_btn = QPushButton()
        self._next_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self._next_btn.setIconSize(QSize(16, 16))
        self._next_btn.setFixedWidth(_ARROW_BTN_W)
        self._next_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._next_btn.setStyleSheet(_VERSE_NAV_BTN_STYLE)
        self._next_btn.clicked.connect(lambda: self.step_verse(1))

        verse_row = QHBoxLayout()
        verse_row.setContentsMargins(0, 0, 0, 0)
        verse_row.setSpacing(6)
        verse_row.addWidget(self._prev_btn)
        verse_row.addWidget(verse_frame, stretch=1)
        verse_row.addWidget(self._next_btn)
        outer.addLayout(verse_row)

        self._question_lbl = QLabel(
            "What is God saying to you through this verse, and how will you respond?"
        )
        self._question_lbl.setWordWrap(True)
        self._question_lbl.setStyleSheet(
            f"font-weight: 600; color: {COLOR_TEXT_MUTED};"
            f"font-size: {FONT_SIZE_SMALL}pt; background: transparent;"
        )
        outer.addWidget(self._question_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        new_verse_btn = QPushButton("New Verse")
        new_verse_btn.setStyleSheet(_VERSE_BTN_STYLE)
        new_verse_btn.clicked.connect(self.load_random_verse)
        btn_row.addWidget(new_verse_btn)

        browse_btn = QPushButton("Browse Verses")
        browse_btn.setStyleSheet(_VERSE_BTN_STYLE)
        browse_btn.clicked.connect(self._on_browse)
        btn_row.addWidget(browse_btn)

        btn_row.addStretch()
        outer.addLayout(btn_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        outer.addWidget(sep)

        self._journal = _FreeJournalWidget(
            journal_service=journal_service,
            bible_library=self._bible_library,
            notes_writer=notes_writer,
        )
        outer.addWidget(self._journal, stretch=1)

    def _on_browse(self) -> None:
        if not self._bible_library:
            return
        from ui.tools.bible_browser_dialog import BibleBrowserDialog
        dlg = BibleBrowserDialog(
            bible_library=self._bible_library,
            select_mode=True,
            parent=self.window(),
        )
        if dlg.exec():
            refs = dlg.get_selected_refs()
            if refs:
                self.load_verse(refs[0]["key"])


# ---------------------------------------------------------------------------
# Diet / Health section
# ---------------------------------------------------------------------------

_WATER_COUNT = 8
_DIET_ICON_DIR = Path(__file__).parent / "icons" / "diet"

_C_WATER_CHECKED = QColor("#2f80ed")
_C_VITAMIN_CHECKED = QColor("#f2994a")
_C_ICON_UNCHECKED = QColor("#ffffff")


def _painted_icon(kind: str, checked: bool) -> QIcon:
    """Fallback icon (bottle/capsule shape) used when no PNG asset is supplied."""
    pixmap = QPixmap(28, 28)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = (_C_WATER_CHECKED if kind == "water" else _C_VITAMIN_CHECKED) if checked else _C_ICON_UNCHECKED
    painter.setBrush(color)
    painter.setPen(QColor(COLOR_BORDER))
    if kind == "water":
        painter.drawRoundedRect(QRectF(8, 2, 12, 24), 3, 3)
    else:
        painter.drawRoundedRect(QRectF(4, 9, 20, 10), 5, 5)
    painter.end()
    return QIcon(pixmap)


def _load_diet_icon(kind: str, checked: bool) -> QIcon:
    name = f"{kind}_{'checked' if checked else 'unchecked'}.png"
    path = _DIET_ICON_DIR / name
    if path.exists():
        return QIcon(str(path))
    return _painted_icon(kind, checked)


class _DietHealthSection(QWidget):
    """Health row: water/vitamin toggles, and a calorie budget tracker.

    ``diet_state`` persists water/vitamin data per calendar day; today's
    calories are derived from Diet notes via ``notes_repo``.
    """

    def __init__(
        self,
        diet_state: DietState,
        notes_repo,
        daily_calorie_budget: int = 2000,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._diet_state = diet_state
        self._notes_repo = notes_repo
        self._daily_calorie_budget = daily_calorie_budget
        self._water_btns: list[QPushButton] = []
        self._vitamin_btn: Optional[QPushButton] = None

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        title = QLabel("Health")
        title.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_MEDIUM}pt;"
            f"font-weight: 700; color: {COLOR_TEXT}; background: transparent;"
        )
        vbox.addWidget(title)

        icons_row = QHBoxLayout()
        icons_row.setSpacing(4)
        for i in range(_WATER_COUNT):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(32, 32)
            btn.setFlat(True)
            btn.toggled.connect(lambda checked, idx=i: self._on_water_toggled(idx, checked))
            icons_row.addWidget(btn)
            self._water_btns.append(btn)

        vitamin_btn = QPushButton()
        vitamin_btn.setCheckable(True)
        vitamin_btn.setFixedSize(32, 32)
        vitamin_btn.setFlat(True)
        vitamin_btn.toggled.connect(self._on_vitamin_toggled)
        icons_row.addWidget(vitamin_btn)
        self._vitamin_btn = vitamin_btn

        icons_row.addStretch()
        vbox.addLayout(icons_row)

        calorie_row = QHBoxLayout()
        calorie_row.setSpacing(8)
        self._calories_btn = QPushButton("Calories Dialog")
        self._calories_btn.clicked.connect(self._on_open_calories_dialog)
        calorie_row.addWidget(self._calories_btn)

        self._calories_lbl = QLabel()
        self._calories_lbl.setStyleSheet(
            f"color: {COLOR_TEXT}; font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"background: transparent;"
        )
        calorie_row.addWidget(self._calories_lbl)

        self._calories_warning_lbl = QLabel("\u26A0")
        self._calories_warning_lbl.setToolTip("Exceeds your daily calorie budget.")
        self._calories_warning_lbl.setStyleSheet("color: #eb5757; font-size: 14pt; background: transparent;")
        self._calories_warning_lbl.setVisible(False)
        calorie_row.addWidget(self._calories_warning_lbl)

        calorie_row.addStretch()
        vbox.addLayout(calorie_row)

        self.refresh()

    # -- toggles -------------------------------------------------------

    def _on_water_toggled(self, index: int, checked: bool) -> None:
        self._water_btns[index].setIcon(_load_diet_icon("water", checked))
        count = sum(1 for btn in self._water_btns if btn.isChecked())
        self._diet_state.set_water_count(count)

    def _on_vitamin_toggled(self, checked: bool) -> None:
        if self._vitamin_btn is not None:
            self._vitamin_btn.setIcon(_load_diet_icon("vitamin", checked))
        self._diet_state.set_vitamins_taken(checked)

    # -- calories dialog -------------------------------------------------

    def _on_open_calories_dialog(self) -> None:
        from ui.notes.calories_dialog import CaloriesDialog

        CaloriesDialog(
            on_result_changed=self.refresh,
            parent=self.window(),
        ).exec()

    # -- refresh -----------------------------------------------------------

    def set_daily_calorie_budget(self, budget: int) -> None:
        self._daily_calorie_budget = budget
        self.refresh()

    def refresh(self) -> None:
        day = self._diet_state.get_today()
        water_count = int(day.get("water_count", 0))
        for i, btn in enumerate(self._water_btns):
            checked = i < water_count
            btn.blockSignals(True)
            btn.setChecked(checked)
            btn.blockSignals(False)
            btn.setIcon(_load_diet_icon("water", checked))

        vitamins_taken = bool(day.get("vitamins_taken", False))
        if self._vitamin_btn is not None:
            self._vitamin_btn.blockSignals(True)
            self._vitamin_btn.setChecked(vitamins_taken)
            self._vitamin_btn.blockSignals(False)
            self._vitamin_btn.setIcon(_load_diet_icon("vitamin", vitamins_taken))

        total = int(calories_today_from_notes(self._notes_repo))
        self._calories_lbl.setText(f"{total} of {self._daily_calorie_budget} calories")
        self._calories_warning_lbl.setVisible(total > self._daily_calorie_budget)


# ---------------------------------------------------------------------------
# Dashboard window
# ---------------------------------------------------------------------------

class LeftDockDashboard(QWidget):
    """Sliding dashboard docked to the left edge of the primary monitor.

    Instantiate and keep a strong reference; the widget manages its own
    geometry based on the primary screen.  No Qt parent is required — the
    caller typically stores it as ``self._left_dock``.
    """

    def __init__(self, bible_library=None, main_window=None) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )

        self._bible_library = bible_library
        self._main_window = main_window
        self._expanded: bool = False
        self._content_w: int = _COLLAPSED_CONTENT_W
        self._streak_badge_lbl: Optional[QLabel] = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._tab = _TabButton(on_click=self._toggle, parent=self)

        # Content panel — sits within the _content_w area, holds dashboard widgets.
        self._content_panel = QWidget(self)
        self._content_panel.setObjectName("dashboardContent")

        panel_layout = QVBoxLayout(self._content_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Menu bar
        panel_layout.addWidget(self._build_menu_bar())

        # Dashboard header
        panel_layout.addWidget(self._build_dashboard_header())

        # Scrollable content area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(12)

        self._prayer_card = _DashboardPrayerCard(
            new_session_callback=self._request_new_prayer_session,
            open_recipients_callback=self._request_open_prayer_tool,
            prayed_callback=self._request_mark_prayed,
        )
        inner_layout.addWidget(self._prayer_card)

        journal_svc = FakeJournalService()

        from ui.verse_memory_widget import VerseMemoryWidget

        self._read_widget = _VerseWidget(bible_library=bible_library, journal_service=journal_svc)
        self._memorize_widget = VerseMemoryWidget(bible_library=bible_library)

        self._journal_panel = _DashboardJournalPanel(
            journal_service=journal_svc,
            bible_library=bible_library,
            leading_tabs=[("Read", self._read_widget), ("Memorize", self._memorize_widget)],
        )
        inner_layout.addWidget(self._journal_panel, stretch=1)

        diet_state = self._main_window._get_diet_state() if self._main_window is not None else DietState(Path.home() / ".purity")
        daily_budget = self._main_window._get_daily_calorie_budget() if self._main_window is not None else 2000
        self._diet_section = _DietHealthSection(diet_state=diet_state, notes_repo=notes_repo, daily_calorie_budget=daily_budget)
        inner_layout.addWidget(self._diet_section)

        self._scroll.setWidget(inner)
        panel_layout.addWidget(self._scroll, stretch=1)

        self._anim = QPropertyAnimation(self, b"content_width", self)

        # Periodically re-assert topmost status — Windows can silently demote
        # a WindowStaysOnTopHint window when other apps steal focus.
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(1_000)

        if not self._prayer_card._session_names:
            # Call main_window's session-name builder but apply directly to self,
            # since main_window._left_dock isn't assigned until this __init__ returns.
            if self._main_window is not None:
                self.start_prayer_session(self._main_window._build_prayer_session_names())

        self._sync_geometry()

    # -- Menu bar ----------------------------------------------------------

    def _build_menu_bar(self) -> QMenuBar:
        menu_bar = QMenuBar()
        menu_bar.setStyleSheet(
            f"QMenuBar {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border-bottom: 1px solid {COLOR_BORDER};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_SMALL}pt;"
            f"  color: {COLOR_TEXT};"
            f"}}"
            f"QMenuBar::item:selected {{ background-color: {COLOR_ACCENT_LIGHT}; }}"
            f"QMenu {{"
            f"  background-color: {COLOR_SURFACE};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_SMALL}pt;"
            f"  color: {COLOR_TEXT};"
            f"}}"
            f"QMenu::item:selected {{ background-color: {COLOR_ACCENT_LIGHT}; }}"
        )

        file_menu = menu_bar.addMenu("File")
        prefs_action = QAction("Preferences", menu_bar)
        prefs_action.triggered.connect(self._action_open_preferences)
        prefs_action.setEnabled(self._main_window is not None)
        file_menu.addAction(prefs_action)

        tools_menu = menu_bar.addMenu("Tools")

        view_journals_action = QAction("View Journals", menu_bar)
        view_journals_action.triggered.connect(self._action_open_log_viewer)
        tools_menu.addAction(view_journals_action)

        edit_encouragements_action = QAction("Edit Encouragements", menu_bar)
        edit_encouragements_action.triggered.connect(self._action_edit_encouragements)
        edit_encouragements_action.setEnabled(self._main_window is not None)
        tools_menu.addAction(edit_encouragements_action)

        bible_browser_action = QAction("Bible Browser", menu_bar)
        bible_browser_action.triggered.connect(self._action_open_bible_browser)
        bible_browser_action.setEnabled(self._main_window is not None)
        tools_menu.addAction(bible_browser_action)

        launch_pulse_action = QAction("Launch Pulse", menu_bar)
        launch_pulse_action.triggered.connect(self._action_launch_pulse)
        tools_menu.addAction(launch_pulse_action)

        debug_menu = menu_bar.addMenu("Debug")

        expire_web_action = QAction("Expire Web Session", menu_bar)
        expire_web_action.triggered.connect(self._action_expire_web_session)
        debug_menu.addAction(expire_web_action)

        honor_dialog_action = QAction("Test Honor Dialog", menu_bar)
        honor_dialog_action.triggered.connect(self._action_test_honor_dialog)
        debug_menu.addAction(honor_dialog_action)

        open_logs_folder_action = QAction("Open Logs Folder", menu_bar)
        open_logs_folder_action.triggered.connect(self._action_open_logs_folder)
        open_logs_folder_action.setEnabled(self._main_window is not None)
        debug_menu.addAction(open_logs_folder_action)

        return menu_bar

    # -- Menu action forwarders --------------------------------------------

    def _action_open_preferences(self) -> None:
        if self._main_window is not None:
            self._main_window._open_preferences()

    def _action_open_log_viewer(self) -> None:
        if self._main_window is not None:
            self._main_window._open_log_viewer()

    def _action_edit_encouragements(self) -> None:
        if self._main_window is not None:
            self._main_window._open_encouragement_editor()

    def _action_open_bible_browser(self) -> None:
        if self._main_window is not None:
            self._main_window._open_bible_browser()

    def _action_launch_pulse(self) -> None:
        if self._main_window is not None:
            self._main_window._launch_manual_pulse()

    def _action_expire_web_session(self) -> None:
        if self._main_window is not None:
            self._main_window._debug_expire_web_session()

    def _action_test_honor_dialog(self) -> None:
        if self._main_window is not None:
            self._main_window._debug_web_session_honor_dialog()

    def _action_open_logs_folder(self) -> None:
        if self._main_window is not None:
            self._main_window._open_logs_folder()

    # -- Dashboard header --------------------------------------------------

    def _build_dashboard_header(self) -> QWidget:
        state = MockAppState()
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"background-color: {COLOR_SURFACE};"
            f"border-bottom: 1px solid {COLOR_BORDER};"
        )
        row = QHBoxLayout(header)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(16)

        icon_lbl = QLabel()
        icon_pixmap = QPixmap(str(Path(__file__).parent / "icons" / "icon_32x32.png"))
        if not icon_pixmap.isNull():
            icon_lbl.setPixmap(icon_pixmap)
        icon_lbl.setStyleSheet("background: transparent;")
        row.addWidget(icon_lbl)

        title_lbl = QLabel("Shane's Dashboard")
        title_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_LARGE}pt;"
            f"font-weight: 800; color: {COLOR_ACCENT}; background: transparent;"
        )
        row.addWidget(title_lbl)

        row.addStretch()

        streak_badge = QLabel(self._streak_badge_text())
        streak_badge.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"font-weight: 700; color: {COLOR_TEXT};"
            f"background-color: {COLOR_SURFACE_2}; border-radius: 10px;"
            f"padding: 3px 10px;"
        )
        row.addWidget(streak_badge)
        self._streak_badge_lbl = streak_badge

        return header

    def _streak_badge_text(self) -> str:
        if self._main_window is not None:
            days = self._main_window._get_streak_days()
        else:
            days = MockAppState().purity_streak_days
        return f"\U0001f525 Day {days}"

    def refresh_streak_badge(self) -> None:
        if self._streak_badge_lbl is not None:
            self._streak_badge_lbl.setText(self._streak_badge_text())

    # -- Prayer session ------------------------------------------------------

    def start_prayer_session(self, names: list[str]) -> None:
        """Reset the prayer card with a new session's recipient names."""
        self._prayer_card.start_session(names)

    def _request_new_prayer_session(self) -> None:
        if self._main_window is not None:
            self._main_window._start_new_prayer_session()

    def _request_open_prayer_tool(self) -> None:
        if self._main_window is not None:
            self._main_window._open_prayer_tool()

    def _request_mark_prayed(self, name: str) -> None:
        if self._main_window is not None:
            self._main_window._mark_prayer_recipient_prayed(name)

    # -- animated property -------------------------------------------------

    def _get_content_width(self) -> int:
        return self._content_w

    def _set_content_width(self, value: int) -> None:
        self._content_w = value
        self._sync_geometry()
        self.update()

    content_width = Property(int, _get_content_width, _set_content_width)

    # -- geometry ----------------------------------------------------------

    def _sync_geometry(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        total_w = self._content_w + _TAB_W
        self.setGeometry(screen.left(), screen.top(), total_w, screen.height())
        tab_y = (screen.height() - _TAB_H) // 2
        self._tab.move(self._content_w, tab_y)
        # Keep content panel sized to the content area (never overlaps the tab).
        if hasattr(self, "_content_panel"):
            self._content_panel.setGeometry(0, 0, self._content_w, screen.height())
            self._content_panel.setVisible(self._content_w > _COLLAPSED_CONTENT_W)

    # -- topmost enforcement -----------------------------------------------

    def _reassert_topmost(self) -> None:
        """Re-raise the window so it stays above all non-topmost windows."""
        if QApplication.activePopupWidget() is not None:
            return
        if not self._journal_panel._hovering_verse and not self._read_widget.is_hovering_verse():
            self.raise_()
        popup = self._journal_panel._tag_popup
        if popup is not None and popup.isVisible():
            popup.raise_()
        read_popup = self._read_widget.tag_popup()
        if read_popup is not None and read_popup.isVisible():
            read_popup.raise_()

    # -- toggle ------------------------------------------------------------

    def _toggle(self) -> None:
        self._set_expanded(not self._expanded)

    def expand(self) -> None:
        """Expand the dashboard if collapsed; no-op if already expanded."""
        self._set_expanded(True)

    def _set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._tab.set_expanded(self._expanded)
        self._anim.stop()
        self._anim.setStartValue(self._content_w)
        if self._expanded:
            # Snap open immediately, then ease gently into the final position.
            self._anim.setDuration(620)
            self._anim.setEasingCurve(QEasingCurve.Type.OutExpo)
            self._anim.setEndValue(_EXPANDED_CONTENT_W)
        else:
            # Ease out slowly at first, then close with a gentle snap.
            self._anim.setDuration(300)
            self._anim.setEasingCurve(QEasingCurve.Type.InQuart)
            self._anim.setEndValue(_COLLAPSED_CONTENT_W)
        self._anim.start()

    # -- paint -------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self._content_w
        h = self.height()

        if w <= _COLLAPSED_CONTENT_W:
            # Collapsed: just the accent strip.
            painter.fillRect(0, 0, w, h, _C_STRIP)
        else:
            # Expanded: full panel background with a right border line.
            painter.fillRect(0, 0, w, h, _C_PANEL)
            painter.fillRect(w - 1, 0, 1, h, QColor(COLOR_BORDER))

        painter.end()
