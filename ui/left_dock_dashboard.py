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

import uuid
from datetime import datetime
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
    Property,
)
from PySide6.QtGui import QAction, QColor, QPainter, QPainterPath, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenuBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.fake_journal import FakeJournalService
from services.fake_prayer import FakePrayerService
from services.mock_state import MockAppState
from services.notes_setup import journal_notes_writer
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

_PRAYER_DAILY_TARGET = 5


class _DashboardPrayerCard(QFrame):
    """Prayer Queue card for the dashboard sidebar.

    Shows the current prayer person, an 'X of 5' counter in the header,
    an 'I Prayed' button, and an 'Add Note' button that fires the Prayer popup.
    Background is a radial gradient: #ffa400 at centre, #ffc55e at edges.
    """

    def __init__(self, prayer_service: FakePrayerService, fire_prayer_callback=None, parent=None) -> None:
        super().__init__(parent)
        self._svc = prayer_service
        self._fire_prayer = fire_prayer_callback
        # Transparent base so paintEvent controls the background fully.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setStyleSheet(
            "QFrame { border: none; border-radius: 8px; background: transparent; }"
        )
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(6)

        # Title row: logo left, "X of 5" right
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

        self._progress_lbl = QLabel()
        self._progress_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"font-weight: 600; color: #5a3000; background: transparent;"
        )
        title_row.addWidget(self._progress_lbl)
        outer.addLayout(title_row)

        # Person name
        self._name_lbl = QLabel()
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_LARGE}pt;"
            f"font-weight: 700; color: #3a2000; background: transparent; border: none;"
        )
        outer.addWidget(self._name_lbl)

        # Prayer list (single-line, no border)
        self._prayer_list = QLabel()
        self._prayer_list.setText('My Family')
        self._prayer_list.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prayer_list.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"color: #6b3a00; background: transparent; border: none;"
        )
        outer.addWidget(self._prayer_list)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._prayed_btn = QPushButton("I Prayed ✓")
        self._prayed_btn.setStyleSheet(
            "QPushButton { background-color: #000000; color: #ffffff;"
            " border: none; border-radius: 6px; padding: 6px 12px; }"
            "QPushButton:hover { background-color: #222222; }"
        )
        self._prayed_btn.clicked.connect(self._on_prayed)
        btn_row.addWidget(self._prayed_btn)

        self._add_note_btn = QPushButton("Add Note")
        self._add_note_btn.setStyleSheet(
            f"background-color: rgba(255,255,255,80); color: #5a3000;"
            f"border: 1px solid rgba(90,48,0,120); border-radius: 6px; padding: 6px 12px;"
        )
        self._add_note_btn.clicked.connect(self._on_add_note)
        btn_row.addWidget(self._add_note_btn)

        outer.addLayout(btn_row)
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

    def _refresh(self) -> None:
        person = self._svc.current()
        self._name_lbl.setText(person.name)
        self._prayer_list.setText(person.notes or "")
        prayed, _ = self._svc.progress()
        self._progress_lbl.setText(f"{prayed} of {_PRAYER_DAILY_TARGET}")

    def _on_prayed(self) -> None:
        self._svc.mark_prayed()
        self._refresh()

    def _on_add_note(self) -> None:
        if self._fire_prayer is not None:
            self._fire_prayer()


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


class _DashboardJournalPanel(QWidget):
    """Tab widget mirroring JournalPanel with an enhanced Free Journal tab.

    The Free Journal tab adds:
    - 'Tag Verses' button that opens BibleBrowserDialog in select_mode
    - A tagged-verses row showing selected references with commas and tooltips
    """

    def __init__(self, journal_service: FakeJournalService, bible_library=None, parent=None) -> None:
        super().__init__(parent)
        self._svc = journal_service
        self._bible_library = bible_library
        self._tagged_refs: list[dict] = []  # [{"key": ..., "display": ...}]
        self._tag_library = TagLibrary()
        self._selected_tags: list[str] = []
        self._tag_popup: Optional[QWidget] = None
        self._hovering_verse: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_guided_tab(), "Guided Check-In")
        self._tabs.addTab(self._build_free_tab(), "Free Journal")
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

        # Tags display row
        tags_row = QWidget()
        tags_row.setStyleSheet("background: transparent;")
        tags_hbox = QHBoxLayout(tags_row)
        tags_hbox.setContentsMargins(0, 0, 0, 0)
        tags_hbox.setSpacing(6)

        tags_title = QLabel("Tags:")
        tags_title.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt;"
            f"font-weight: 600; background: transparent;"
        )
        tags_title.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        tags_hbox.addWidget(tags_title)

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

    # -- Tagged verse display ----------------------------------------------

    def _rebuild_tagged_display(self) -> None:
        """Clear and repopulate the tagged-verses horizontal scroll area."""
        # Remove all widgets from layout except the trailing stretch
        while self._tagged_inner_layout.count() > 1:
            item = self._tagged_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, ref in enumerate(self._tagged_refs):
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
            if i < len(self._tagged_refs) - 1:
                sep = QLabel(", ")
                sep.setStyleSheet(
                    f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt;"
                    f"background: transparent;"
                )
                self._tagged_inner_layout.insertWidget(i * 2 + 1, sep)

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
        self._tabs.setCurrentIndex(2)

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
        ctx: dict = {}
        if self._selected_tags:
            ctx["tags"] = list(self._selected_tags)
        if self._tagged_refs:
            ctx["tagged_verses"] = list(self._tagged_refs)
        note = journal_notes_writer.build_note(
            note_type=NoteType.GENERAL,
            text=text,
            context=ctx,
        )
        journal_notes_writer.commit(note)
        self._free_input.clear()
        self._free_timestamp_lbl.setText(self._now_str())
        self._tagged_refs = []
        self._rebuild_tagged_display()
        self._selected_tags = []
        self._rebuild_tags_display()
        self._populate_history()
        self._tabs.setCurrentIndex(2)

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

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%A, %B %d  %H:%M")


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

        from ui.verse_memory_widget import VerseMemoryWidget
        self._verse_widget = VerseMemoryWidget(bible_library=bible_library, parent=inner)
        inner_layout.addWidget(self._verse_widget)

        prayer_svc = FakePrayerService()
        self._prayer_card = _DashboardPrayerCard(
            prayer_service=prayer_svc,
            fire_prayer_callback=self._fire_prayer_popup,
        )
        inner_layout.addWidget(self._prayer_card)

        journal_svc = FakeJournalService()
        self._journal_panel = _DashboardJournalPanel(
            journal_service=journal_svc,
            bible_library=bible_library,
        )
        inner_layout.addWidget(self._journal_panel, stretch=1)

        self._scroll.setWidget(inner)
        panel_layout.addWidget(self._scroll, stretch=1)

        self._anim = QPropertyAnimation(self, b"content_width", self)

        # Periodically re-assert topmost status — Windows can silently demote
        # a WindowStaysOnTopHint window when other apps steal focus.
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(1_000)

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

        title_lbl = QLabel("Shane's Dashboard")
        title_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_LARGE}pt;"
            f"font-weight: 800; color: {COLOR_ACCENT}; background: transparent;"
        )
        row.addWidget(title_lbl)

        row.addStretch()

        streak_badge = QLabel(f"🔥 Day {state.purity_streak_days}")
        streak_badge.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"font-weight: 700; color: {COLOR_TEXT};"
            f"background-color: {COLOR_SURFACE_2}; border-radius: 10px;"
            f"padding: 3px 10px;"
        )
        row.addWidget(streak_badge)

        return header

    # -- Prayer popup ------------------------------------------------------

    def _fire_prayer_popup(self) -> None:
        if self._main_window is not None:
            self._main_window._popup_mgr.trigger("prayer")

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
        if not self._journal_panel._hovering_verse:
            self.raise_()
        popup = self._journal_panel._tag_popup
        if popup is not None and popup.isVisible():
            popup.raise_()

    # -- toggle ------------------------------------------------------------

    def _toggle(self) -> None:
        self._expanded = not self._expanded
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
