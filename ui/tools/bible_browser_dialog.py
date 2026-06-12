"""Bible Browser — two-column dialog for navigating the Protestant canon,
entering verse text, and selecting verses for use in encouragements.

Left panel:  QTreeWidget — all 66 books, chapters, and verses pre-populated.
             Grey items have no saved text; normal-colour items do.
             Supports Ctrl+click and Shift+click for multi-select.

Right panel: QStackedWidget with three pages:
             0 — placeholder (nothing or non-verse selected)
             1 — single verse view with saved version cards + add button
             2 — "Multiple Verses Selected" placeholder

Open as a standalone browser::

    dlg = BibleBrowserDialog(bible_library)
    dlg.exec()

Open to select verses (returns selection to caller)::

    dlg = BibleBrowserDialog(bible_library, selected_refs=current_refs, select_mode=True)
    if dlg.exec():
        refs = dlg.get_selected_refs()
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QSize, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyledItemDelegate,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from services.bible_canon import BOOKS, BOOK_DISPLAY, CANON, normalize_ref, display_ref
from services.bible_library import BibleLibrary
from shane_common.ui.spellcheck_highlighter import enable_spellcheck
from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_DARK,
    COLOR_BACKGROUND,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_SURFACE,
    COLOR_SURFACE_2,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
    FONT_SIZE_MEDIUM,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BIBLE_VERSIONS = ["NIV", "ESV", "KJV", "NKJV", "CSB", "NLT", "NASB", "MSG"]

_TREE_ITEM_TYPE_BOOK    = QTreeWidgetItem.ItemType.UserType + 1
_TREE_ITEM_TYPE_CHAPTER = QTreeWidgetItem.ItemType.UserType + 2
_TREE_ITEM_TYPE_VERSE   = QTreeWidgetItem.ItemType.UserType + 3

# Custom data role for chapter/verse circle indicators.
_CIRCLE_ROLE    = Qt.ItemDataRole.UserRole + 10
_CIRCLE_NONE    = 0   # no indicator
_CIRCLE_PARTIAL = 1   # outline only (some verses saved)
_CIRCLE_FULL    = 2   # filled (all verses saved / verse has content)
_MEMORIZE_ROLE  = Qt.ItemDataRole.UserRole + 11  # verse marked for memorization

# ---------------------------------------------------------------------------
# Tree item delegate — draws circle indicators on the right
# ---------------------------------------------------------------------------

class _CircleDelegate(QStyledItemDelegate):
    """Draws a small filled or outline circle on the right side of tree items.

    Circle state is stored in ``_CIRCLE_ROLE`` on each item:
      _CIRCLE_NONE    — no circle drawn
      _CIRCLE_PARTIAL — outline circle (green border, transparent fill)
      _CIRCLE_FULL    — filled circle (solid green)
    """

    _RADIUS = 4    # px
    _MARGIN = 10   # px from right edge of item rect

    def paint(self, painter, option, index) -> None:  # noqa: N802
        super().paint(painter, option, index)
        circle_state  = index.data(_CIRCLE_ROLE)
        is_memorizing = index.data(_MEMORIZE_ROLE)

        r  = self._RADIUS
        cx = float(option.rect.right() - self._MARGIN - r)
        cy = float(option.rect.center().y())

        if circle_state:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(COLOR_ACCENT)
            if circle_state == _CIRCLE_FULL:
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
            else:  # _CIRCLE_PARTIAL
                painter.setBrush(Qt.BrushStyle.NoBrush)
                pen = QPen(color)
                pen.setWidthF(1.5)
                painter.setPen(pen)
            painter.drawEllipse(QPointF(cx, cy), r, r)
            painter.restore()

        if is_memorizing:
            painter.save()
            mem_font = painter.font()
            mem_font.setBold(True)
            mem_font.setPointSize(7)
            painter.setFont(mem_font)
            painter.setPen(QColor("#C0392B"))
            lx = int(cx) - r - 12
            painter.drawText(
                lx, option.rect.top(), 10, option.rect.height(),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter),
                "M",
            )
            painter.restore()


# ---------------------------------------------------------------------------
# Stylesheet helpers
# ---------------------------------------------------------------------------

_FIELD_NORMAL = (
    f"background-color: {COLOR_SURFACE_2};"
    f"color: {COLOR_TEXT};"
    f"border: 1px solid {COLOR_BORDER};"
    f"border-radius: 4px;"
)

_BTN_PRIMARY = (
    f"QPushButton {{"
    f"  background-color: {COLOR_ACCENT};"
    f"  color: #ffffff;"
    f"  border: none;"
    f"  border-radius: 6px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  font-weight: 700;"
    f"  padding: 7px 20px;"
    f"}}"
    f"QPushButton:hover {{ background-color: {COLOR_ACCENT_DARK}; }}"
    f"QPushButton:disabled {{ background-color: {COLOR_BORDER}; color: {COLOR_TEXT_MUTED}; }}"
)

_BTN_SECONDARY = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  color: {COLOR_TEXT};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 6px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  padding: 7px 16px;"
    f"}}"
    f"QPushButton:hover {{ background-color: {COLOR_SURFACE}; border-color: {COLOR_ACCENT}; }}"
)

_BTN_DANGER = (
    f"QPushButton {{"
    f"  background-color: #C0392B;"
    f"  color: #ffffff;"
    f"  border: none;"
    f"  border-radius: 4px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  font-weight: 700;"
    f"  padding: 6px 12px;"
    f"}}"
    f"QPushButton:hover {{ background-color: #96281B; }}"
)

_BTN_ADD = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  color: {COLOR_ACCENT};"
    f"  border: 1px solid {COLOR_ACCENT};"
    f"  border-radius: 4px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  font-weight: 700;"
    f"  padding: 4px 14px;"
    f"}}"
    f"QPushButton:hover {{ background-color: {COLOR_SURFACE}; }}"
)

_COMBO_STYLE = (
    f"QComboBox {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  color: {COLOR_TEXT};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 4px;"
    f"  padding: 4px 8px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"}}"
    f"QComboBox::drop-down {{ border: none; }}"
)

# ---------------------------------------------------------------------------
# VerseVersionCard
# ---------------------------------------------------------------------------

class VerseVersionCard(QFrame):
    """Displays one saved version of a verse; toggles between view and edit modes."""

    def __init__(
        self,
        book_key: str,
        chapter: int,
        verse: int,
        display: str,
        bible_library: BibleLibrary,
        version_data: Optional[dict],   # None = brand-new card (edit mode immediately)
        on_saved: callable,
        on_deleted: callable,
        on_memorize_changed: "callable | None" = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._book_key = book_key
        self._chapter = chapter
        self._verse = verse
        self._display = display
        self._library = bible_library
        self._version_data = version_data  # {"version": ..., "text": ...} or None
        self._on_saved = on_saved
        self._on_deleted = on_deleted
        self._on_memorize_changed = on_memorize_changed
        self._is_new = (version_data is None)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background-color: {COLOR_SURFACE};"
            f" border: 1px solid {COLOR_BORDER};"
            f" border-radius: 6px; padding: 0; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(6)

        if self._is_new:
            self._build_edit_ui()
        else:
            self._build_view_ui()

    # ------------------------------------------------------------------
    # View mode
    # ------------------------------------------------------------------

    def _build_view_ui(self) -> None:
        self._clear_layout()
        version_name = self._version_data["version"] if self._version_data else ""
        verse_text   = self._version_data["text"]    if self._version_data else ""

        version_lbl = QLabel(version_name)
        version_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"font-weight: 700; color: {COLOR_ACCENT}; background: transparent; border: none;"
        )
        self._layout.addWidget(version_lbl)

        text_lbl = QLabel(f'"{verse_text}"')
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_MEDIUM}pt;"
            f"font-style: italic; color: {COLOR_TEXT}; background: transparent; border: none;"
        )
        self._layout.addWidget(text_lbl)

        # Bottom row: hint label + Memorize toggle button
        bottom_row = QHBoxLayout()
        hint_lbl = QLabel("Double-click to edit")
        hint_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_SMALL}pt;"
            f"color: {COLOR_TEXT_MUTED}; background: transparent; border: none;"
        )
        bottom_row.addWidget(hint_lbl)
        bottom_row.addStretch()

        ref_key = normalize_ref(self._book_key, self._chapter, self._verse)
        is_mem = self._library.is_memorizing(ref_key)
        mem_btn = QPushButton("Memorize")
        mem_btn.setCheckable(True)
        mem_btn.setChecked(is_mem)
        mem_btn.setStyleSheet(self._mem_btn_style(is_mem))
        mem_btn.toggled.connect(
            lambda checked, k=ref_key, b=mem_btn: self._on_memorize_toggled(k, checked, b)
        )
        bottom_row.addWidget(mem_btn)
        self._layout.addLayout(bottom_row)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if not self._is_new:
            self._build_edit_ui()
        super().mouseDoubleClickEvent(event)

    @staticmethod
    def _mem_btn_style(checked: bool) -> str:
        if checked:
            return (
                "QPushButton { background-color: #C0392B; color: #ffffff;"
                " border: none; border-radius: 4px; font-size: 9pt;"
                " padding: 2px 8px; font-weight: 700; }"
                "QPushButton:hover { background-color: #96281B; }"
            )
        return (
            "QPushButton { background-color: transparent; color: #667067;"
            " border: 1px solid #C9D2C7; border-radius: 4px; font-size: 9pt; padding: 2px 8px; }"
            "QPushButton:hover { background-color: #E7ECE5; }"
        )

    def _on_memorize_toggled(self, ref_key: str, checked: bool, btn: QPushButton) -> None:
        self._library.set_memorizing(ref_key, checked)
        btn.setStyleSheet(self._mem_btn_style(checked))
        if self._on_memorize_changed:
            self._on_memorize_changed()

    # ------------------------------------------------------------------
    # Edit mode
    # ------------------------------------------------------------------

    def _build_edit_ui(self) -> None:
        self._clear_layout()

        self._version_combo = QComboBox()
        self._version_combo.setStyleSheet(_COMBO_STYLE)
        for v in _BIBLE_VERSIONS:
            self._version_combo.addItem(v)
        if self._version_data:
            idx = _BIBLE_VERSIONS.index(self._version_data["version"]) \
                if self._version_data["version"] in _BIBLE_VERSIONS else 0
            self._version_combo.setCurrentIndex(idx)
        self._layout.addWidget(self._version_combo)

        self._text_edit = QTextEdit()
        self._text_edit.setAcceptRichText(False)
        self._text_edit.setPlaceholderText("Type the verse text here…")
        self._text_edit.setStyleSheet(_FIELD_NORMAL)
        self._text_edit.setMinimumHeight(80)
        self._text_edit.setMaximumHeight(140)
        if self._version_data:
            self._text_edit.setPlainText(self._version_data["text"])
        self._layout.addWidget(self._text_edit)
        enable_spellcheck(self._text_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addStretch()

        if not self._is_new:
            delete_btn = QPushButton("Delete")
            delete_btn.setStyleSheet(_BTN_DANGER)
            delete_btn.clicked.connect(self._on_delete)
            btn_row.addWidget(delete_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(_BTN_PRIMARY)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        self._layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        version_name = self._version_combo.currentText()
        text = self._text_edit.toPlainText().strip()
        if not text:
            return
        key = normalize_ref(self._book_key, self._chapter, self._verse)
        self._library.set_version(key, self._display, version_name, text)
        self._version_data = {"version": version_name, "text": text}
        self._is_new = False
        self._on_saved()

    def _on_delete(self) -> None:
        if not self._version_data:
            return
        key = normalize_ref(self._book_key, self._chapter, self._verse)
        self._library.delete_version(key, self._version_data["version"])
        self._on_deleted()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Clear sub-layout widgets
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()


# ---------------------------------------------------------------------------
# BibleBrowserDialog
# ---------------------------------------------------------------------------

class BibleBrowserDialog(QDialog):
    """Two-column Bible browser: tree on the left, verse content on the right."""

    def __init__(
        self,
        bible_library: BibleLibrary,
        selected_refs: Optional[list[dict]] = None,
        select_mode: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint,
        )
        self.setWindowTitle("Bible Browser")
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)

        self._library = bible_library
        self._select_mode = select_mode
        self._selected_refs_in = selected_refs or []

        # Tracks the currently displayed verse (book_key, chapter, verse)
        self._current_verse: Optional[tuple[str, int, int]] = None
        # The scrollable container inside the single-verse panel
        self._verse_list_widget: Optional[QWidget] = None

        self._build_ui()
        self._populate_tree()
        if self._selected_refs_in:
            self._restore_selection(self._selected_refs_in)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(300)
        left.setStyleSheet(
            f"background-color: {COLOR_SURFACE};"
            f"border-right: 1px solid {COLOR_BORDER};"
        )
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        lv.setSpacing(6)

        search_lbl = QLabel("Bible")
        search_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_MEDIUM}pt;"
            f"font-weight: 700; color: {COLOR_TEXT}; background: transparent;"
        )
        lv.addWidget(search_lbl)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setStyleSheet(
            f"QTreeWidget {{"
            f"  background-color: {COLOR_BACKGROUND};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 4px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  color: {COLOR_TEXT};"
            f"}}"
            f"QTreeWidget::item {{ padding: 3px 6px; }}"
            f"QTreeWidget::item:selected {{"
            f"  background-color: {COLOR_ACCENT};"
            f"  color: #ffffff;"
            f"}}"
        )
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.setItemDelegate(_CircleDelegate(self._tree))
        lv.addWidget(self._tree, stretch=1)

        root.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────
        right_outer = QWidget()
        right_outer.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")
        rv = QVBoxLayout(right_outer)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        # Stacked content area
        self._stack = QStackedWidget()
        rv.addWidget(self._stack, stretch=1)

        # Page 0 — empty placeholder
        page0 = QWidget()
        p0v = QVBoxLayout(page0)
        lbl0 = QLabel("Select a verse to view or enter its contents.")
        lbl0.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl0.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
            f"color: {COLOR_TEXT_MUTED}; background: transparent;"
        )
        p0v.addStretch()
        p0v.addWidget(lbl0)
        p0v.addStretch()
        self._stack.addWidget(page0)

        # Page 1 — single verse content (built dynamically)
        self._page1 = QWidget()
        self._page1.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")
        self._page1_layout = QVBoxLayout(self._page1)
        self._page1_layout.setContentsMargins(18, 14, 18, 10)
        self._page1_layout.setSpacing(8)
        self._stack.addWidget(self._page1)

        # Page 2 — multi-select placeholder
        page2 = QWidget()
        p2v = QVBoxLayout(page2)
        lbl2 = QLabel("Multiple Verses Selected")
        lbl2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl2.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_MEDIUM}pt;"
            f"font-weight: 700; color: {COLOR_TEXT_MUTED}; background: transparent;"
        )
        p2v.addStretch()
        p2v.addWidget(lbl2)
        p2v.addStretch()
        self._stack.addWidget(page2)

        # ── Bottom button bar ─────────────────────────────────────────
        bar = QWidget()
        bar.setStyleSheet(
            f"background-color: {COLOR_SURFACE};"
            f"border-top: 1px solid {COLOR_BORDER};"
        )
        bv = QHBoxLayout(bar)
        bv.setContentsMargins(14, 8, 14, 8)
        bv.setSpacing(8)
        bv.addStretch()

        self._select_btn = QPushButton("Select Passages")
        self._select_btn.setStyleSheet(_BTN_PRIMARY)
        self._select_btn.setVisible(self._select_mode)
        self._select_btn.clicked.connect(self.accept)
        bv.addWidget(self._select_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_BTN_SECONDARY)
        close_btn.clicked.connect(self.reject)
        bv.addWidget(close_btn)

        rv.addWidget(bar)

        root.addWidget(right_outer, stretch=1)

    # ------------------------------------------------------------------
    # Presence map  (single scan of the library dict)
    # ------------------------------------------------------------------

    def _build_presence_map(self) -> dict[str, dict[int, int]]:
        """Scan bible_library once and return saved-verse counts.

        Returns::

            {book_key: {chapter_idx: saved_verse_count, ...}, ...}
        """
        presence: dict[str, dict[int, int]] = {}
        for key in self._library._data:
            parts = key.split("_")
            if len(parts) < 3:
                continue
            try:
                chapter_num = int(parts[-2])
                book_key    = "_".join(parts[:-2])
            except ValueError:
                continue
            presence.setdefault(book_key, {})
            presence[book_key][chapter_num] = presence[book_key].get(chapter_num, 0) + 1
        return presence

    @staticmethod
    def _circle_from_counts(saved: int, total: int) -> int:
        if saved == 0:
            return _CIRCLE_NONE
        return _CIRCLE_FULL if saved >= total else _CIRCLE_PARTIAL

    # ------------------------------------------------------------------
    # Tree population  (lazy — books only at startup)
    # ------------------------------------------------------------------

    # Sentinel userData stored in the dummy placeholder child so we can detect
    # whether a parent node has already been fully populated.
    _PLACEHOLDER = {"type": "placeholder"}

    def _populate_tree(self) -> None:
        """Add one item per book.  Each book gets a dummy child so the
        expand arrow appears; real children are created on first expand."""
        # Single scan of the library to build presence counts.
        presence = self._build_presence_map()

        self._tree.blockSignals(True)
        self._tree.clear()

        for book_key, book_display, verse_counts in BOOKS:
            book_item = QTreeWidgetItem(self._tree, _TREE_ITEM_TYPE_BOOK)
            book_item.setText(0, book_display)
            book_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "book", "key": book_key})
            bold_font = book_item.font(0)
            bold_font.setWeight(QFont.Weight.DemiBold)
            book_item.setFont(0, bold_font)
            # Dummy placeholder so the expand arrow is shown.
            self._add_placeholder(book_item)
            # Book circle: compare total saved across all chapters vs total verses.
            book_presence = presence.get(book_key, {})
            book_saved = sum(book_presence.values())
            book_total = sum(verse_counts)
            book_item.setData(0, _CIRCLE_ROLE,
                              self._circle_from_counts(book_saved, book_total))

        self._tree.blockSignals(False)

    def _add_placeholder(self, parent: QTreeWidgetItem) -> None:
        ph = QTreeWidgetItem(parent)
        ph.setText(0, "")
        ph.setData(0, Qt.ItemDataRole.UserRole, self._PLACEHOLDER)

    def _is_placeholder_populated(self, item: QTreeWidgetItem) -> bool:
        """Return True if *item* has already had its real children created."""
        if item.childCount() == 0:
            return True  # no children expected or already cleaned
        first_data = item.child(0).data(0, Qt.ItemDataRole.UserRole) or {}
        return first_data.get("type") != "placeholder"

    def _expand_book(self, book_item: QTreeWidgetItem) -> None:
        """Populate all chapters (with placeholder children) for a book."""
        if self._is_placeholder_populated(book_item):
            return
        book_key = (book_item.data(0, Qt.ItemDataRole.UserRole) or {}).get("key", "")
        verse_counts = CANON.get(book_key, [])
        # Single scan for this book's chapter presence counts.
        book_presence = self._build_presence_map().get(book_key, {})

        self._tree.blockSignals(True)
        book_item.takeChild(0)
        for ch_idx, verse_count in enumerate(verse_counts, start=1):
            ch_item = QTreeWidgetItem(book_item, _TREE_ITEM_TYPE_CHAPTER)
            ch_item.setText(0, f"Chapter {ch_idx}")
            ch_item.setData(0, Qt.ItemDataRole.UserRole,
                            {"type": "chapter", "key": book_key, "chapter": ch_idx})
            self._add_placeholder(ch_item)
            ch_item.setData(0, _CIRCLE_ROLE,
                            self._circle_from_counts(
                                book_presence.get(ch_idx, 0), verse_count))
        self._tree.blockSignals(False)

    def _expand_chapter(self, ch_item: QTreeWidgetItem) -> None:
        """Populate all verse items for a chapter."""
        if self._is_placeholder_populated(ch_item):
            return
        data = ch_item.data(0, Qt.ItemDataRole.UserRole) or {}
        book_key = data.get("key", "")
        ch_idx = data.get("chapter", 1)
        verse_counts = CANON.get(book_key, [])
        if ch_idx < 1 or ch_idx > len(verse_counts):
            return
        verse_count = verse_counts[ch_idx - 1]

        self._tree.blockSignals(True)
        ch_item.takeChild(0)  # remove placeholder
        for v_idx in range(1, verse_count + 1):
            v_item = QTreeWidgetItem(ch_item, _TREE_ITEM_TYPE_VERSE)
            v_item.setText(0, f"Verse {v_idx}")
            ref_key = normalize_ref(book_key, ch_idx, v_idx)
            ref_display = display_ref(book_key, ch_idx, v_idx)
            has = self._library.has_verse(ref_key)
            v_item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "verse",
                "key": ref_key,
                "display": ref_display,
                "book_key": book_key,
                "chapter": ch_idx,
                "verse": v_idx,
            })
            self._apply_verse_color(v_item, has)
            v_item.setData(0, _CIRCLE_ROLE, _CIRCLE_FULL if has else _CIRCLE_NONE)
            v_item.setData(0, _MEMORIZE_ROLE, self._library.is_memorizing(ref_key))
        # Chapter circle is already set from _expand_book; no rescan needed.
        self._tree.blockSignals(False)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        kind = data.get("type")
        if kind == "book":
            self._expand_book(item)
        elif kind == "chapter":
            self._expand_chapter(item)

    def _apply_verse_color(self, item: QTreeWidgetItem, has_text: bool) -> None:
        color = QColor(COLOR_TEXT) if has_text else QColor(COLOR_TEXT_MUTED)
        item.setForeground(0, color)

    # ------------------------------------------------------------------
    # Selection restoration
    # ------------------------------------------------------------------

    def _restore_selection(self, refs: list[dict]) -> None:
        """Select tree items matching the given verse-ref list.

        Eagerly expands only the specific book→chapter paths needed.
        """
        if not refs:
            return

        # Build lookup: book_key → {chapter → [verse, ...]}
        from collections import defaultdict
        needed: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
        for r in refs:
            key = r.get("key", "")  # e.g. "john_3_16"
            parts = key.split("_")
            if len(parts) >= 3:
                try:
                    verse_num = int(parts[-1])
                    chapter_num = int(parts[-2])
                    book_key = "_".join(parts[:-2])
                    needed[book_key][chapter_num].append(verse_num)
                except ValueError:
                    pass

        selected_keys = {r["key"] for r in refs}

        self._tree.blockSignals(True)
        self._tree.clearSelection()

        root = self._tree.invisibleRootItem()
        for b_idx in range(root.childCount()):
            book_item = root.child(b_idx)
            book_data = book_item.data(0, Qt.ItemDataRole.UserRole) or {}
            book_key = book_data.get("key", "")
            if book_key not in needed:
                continue
            # Expand the book so its chapters exist
            self._expand_book(book_item)
            book_item.setExpanded(True)
            for ch_idx in range(book_item.childCount()):
                ch_item = book_item.child(ch_idx)
                ch_data = ch_item.data(0, Qt.ItemDataRole.UserRole) or {}
                chapter_num = ch_data.get("chapter", -1)
                if chapter_num not in needed[book_key]:
                    continue
                # Expand the chapter so its verses exist
                self._expand_chapter(ch_item)
                ch_item.setExpanded(True)
                for v_idx in range(ch_item.childCount()):
                    v_item = ch_item.child(v_idx)
                    v_data = v_item.data(0, Qt.ItemDataRole.UserRole) or {}
                    if v_data.get("key") in selected_keys:
                        v_item.setSelected(True)

        self._tree.blockSignals(False)

    # ------------------------------------------------------------------
    # Selection slot
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        items = self._tree.selectedItems()

        # Filter to only verse-level items
        verse_items = [
            it for it in items
            if (it.data(0, Qt.ItemDataRole.UserRole) or {}).get("type") == "verse"
        ]

        if not verse_items:
            self._stack.setCurrentIndex(0)
            self._current_verse = None
            return

        if len(verse_items) == 1:
            data = verse_items[0].data(0, Qt.ItemDataRole.UserRole)
            self._load_single_verse(
                data["book_key"], data["chapter"], data["verse"],
                data["display"], data["key"],
            )
        else:
            self._stack.setCurrentIndex(2)
            self._current_verse = None

    # ------------------------------------------------------------------
    # Single-verse panel
    # ------------------------------------------------------------------

    def _load_single_verse(
        self, book_key: str, chapter: int, verse: int, ref_display: str, ref_key: str
    ) -> None:
        self._current_verse = (book_key, chapter, verse)
        self._refresh_page1(book_key, chapter, verse, ref_display, ref_key)
        self._stack.setCurrentIndex(1)

    def _refresh_page1(
        self,
        book_key: str,
        chapter: int,
        verse: int,
        ref_display: str,
        ref_key: str,
    ) -> None:
        # Clear existing page1 contents
        while self._page1_layout.count():
            item = self._page1_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Recursively delete widgets inside sub-layouts (e.g. header_row)
                sub = item.layout()
                while sub.count():
                    sub_item = sub.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()
                sub.deleteLater()
        self._verse_list_widget = None

        # Header row: verse name + "+" button
        header_row = QHBoxLayout()
        header_lbl = QLabel(ref_display)
        header_lbl.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_MEDIUM}pt;"
            f"font-weight: 700; color: {COLOR_TEXT}; background: transparent;"
        )
        header_row.addWidget(header_lbl, stretch=1)

        add_btn = QPushButton("+ Add Version")
        add_btn.setStyleSheet(_BTN_ADD)
        add_btn.clicked.connect(
            lambda: self._on_add_version(book_key, chapter, verse, ref_display, ref_key)
        )
        header_row.addWidget(add_btn)
        self._page1_layout.addLayout(header_row)

        # Scroll area containing version cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")

        container = QWidget()
        container.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 4, 0, 4)
        container_layout.setSpacing(8)
        self._verse_list_widget = container

        entry = self._library.get_verse(ref_key)
        if entry:
            for vd in entry["versions"]:
                card = VerseVersionCard(
                    book_key, chapter, verse, ref_display,
                    self._library, vd,
                    on_saved=lambda bk=book_key, ch=chapter, v=verse, rd=ref_display, rk=ref_key:
                        self._on_version_saved(bk, ch, v, rd, rk),
                    on_deleted=lambda bk=book_key, ch=chapter, v=verse, rd=ref_display, rk=ref_key:
                        self._on_version_deleted(bk, ch, v, rd, rk),
                    on_memorize_changed=lambda rk=ref_key: self._on_verse_memorize_changed(rk),
                    parent=container,
                )
                container_layout.addWidget(card)

        if not (entry and entry["versions"]):
            empty_lbl = QLabel('No versions saved yet. Click "Add Version" to enter the verse text.')
            empty_lbl.setWordWrap(True)
            empty_lbl.setStyleSheet(
                f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
                f"color: {COLOR_TEXT_MUTED}; background: transparent;"
            )
            container_layout.addWidget(empty_lbl)

        container_layout.addStretch()
        scroll.setWidget(container)
        self._page1_layout.addWidget(scroll, stretch=1)

    def _on_add_version(
        self, book_key: str, chapter: int, verse: int, ref_display: str, ref_key: str
    ) -> None:
        """Insert a new blank VerseVersionCard at the top of the list."""
        if self._verse_list_widget is None:
            return
        layout: QVBoxLayout = self._verse_list_widget.layout()

        # Remove the stretch at the end temporarily
        stretch_item = None
        if layout.count() > 0:
            last = layout.itemAt(layout.count() - 1)
            if last.spacerItem():
                stretch_item = layout.takeAt(layout.count() - 1)

        # Remove the "No versions" label if present
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), QLabel):
                item.widget().deleteLater()
                layout.takeAt(i)
                break

        card = VerseVersionCard(
            book_key, chapter, verse, ref_display,
            self._library, None,
            on_saved=lambda bk=book_key, ch=chapter, v=verse, rd=ref_display, rk=ref_key:
                self._on_version_saved(bk, ch, v, rd, rk),
            on_deleted=lambda bk=book_key, ch=chapter, v=verse, rd=ref_display, rk=ref_key:
                self._on_version_deleted(bk, ch, v, rd, rk),
            on_memorize_changed=lambda rk=ref_key: self._on_verse_memorize_changed(rk),
            parent=self._verse_list_widget,
        )
        layout.insertWidget(0, card)
        if stretch_item:
            layout.addItem(stretch_item)

    def _on_version_saved(
        self, book_key: str, chapter: int, verse: int, ref_display: str, ref_key: str
    ) -> None:
        self._refresh_page1(book_key, chapter, verse, ref_display, ref_key)
        self._stack.setCurrentIndex(1)
        # Update tree item colour
        self._update_tree_item_color(ref_key, True)

    def _on_version_deleted(
        self, book_key: str, chapter: int, verse: int, ref_display: str, ref_key: str
    ) -> None:
        self._refresh_page1(book_key, chapter, verse, ref_display, ref_key)
        self._stack.setCurrentIndex(1)
        has = self._library.has_verse(ref_key)
        self._update_tree_item_color(ref_key, has)

    def _update_tree_item_color(self, ref_key: str, has_text: bool) -> None:
        """Update verse+chapter+book circles after a save or delete.

        Uses a single presence-map scan to recompute all three levels.
        """
        parts = ref_key.split("_")
        try:
            chapter_num = int(parts[-2]) if len(parts) >= 3 else 0
            book_key    = "_".join(parts[:-2]) if len(parts) >= 3 else ""
        except (ValueError, IndexError):
            book_key, chapter_num = "", 0

        # One scan covers all three levels.
        presence    = self._build_presence_map()
        book_presence = presence.get(book_key, {})
        verse_counts  = CANON.get(book_key, [])

        root = self._tree.invisibleRootItem()
        for b_idx in range(root.childCount()):
            book_item = root.child(b_idx)
            b_data = book_item.data(0, Qt.ItemDataRole.UserRole) or {}
            if b_data.get("key") != book_key:
                continue
            # Update book circle.
            book_saved = sum(book_presence.values())
            book_total = sum(verse_counts)
            book_item.setData(0, _CIRCLE_ROLE,
                              self._circle_from_counts(book_saved, book_total))
            for c_idx in range(book_item.childCount()):
                ch_item = book_item.child(c_idx)
                c_data = ch_item.data(0, Qt.ItemDataRole.UserRole) or {}
                if c_data.get("type") == "placeholder" or c_data.get("chapter") != chapter_num:
                    continue
                # Update chapter circle.
                ch_saved = book_presence.get(chapter_num, 0)
                ch_total = verse_counts[chapter_num - 1] if 0 < chapter_num <= len(verse_counts) else 0
                ch_item.setData(0, _CIRCLE_ROLE,
                                self._circle_from_counts(ch_saved, ch_total))
                # Update the specific verse item if the chapter has been expanded.
                for v_idx in range(ch_item.childCount()):
                    v_item = ch_item.child(v_idx)
                    v_data = v_item.data(0, Qt.ItemDataRole.UserRole) or {}
                    if v_data.get("key") == ref_key:
                        self._apply_verse_color(v_item, has_text)
                        v_item.setData(0, _CIRCLE_ROLE,
                                       _CIRCLE_FULL if has_text else _CIRCLE_NONE)
                        v_item.setData(0, _MEMORIZE_ROLE,
                                       self._library.is_memorizing(ref_key))
                        break

    def _on_verse_memorize_changed(self, ref_key: str) -> None:
        """Update tree M indicator when a verse's memorize state is toggled."""
        parts = ref_key.split("_")
        try:
            chapter_num = int(parts[-2]) if len(parts) >= 3 else 0
            book_key    = "_".join(parts[:-2]) if len(parts) >= 3 else ""
        except (ValueError, IndexError):
            return
        is_mem = self._library.is_memorizing(ref_key)
        root = self._tree.invisibleRootItem()
        for b_idx in range(root.childCount()):
            book_item = root.child(b_idx)
            b_data = book_item.data(0, Qt.ItemDataRole.UserRole) or {}
            if b_data.get("key") != book_key:
                continue
            for c_idx in range(book_item.childCount()):
                ch_item = book_item.child(c_idx)
                c_data = ch_item.data(0, Qt.ItemDataRole.UserRole) or {}
                if c_data.get("type") == "placeholder" or c_data.get("chapter") != chapter_num:
                    continue
                for v_idx in range(ch_item.childCount()):
                    v_item = ch_item.child(v_idx)
                    v_data = v_item.data(0, Qt.ItemDataRole.UserRole) or {}
                    if v_data.get("key") == ref_key:
                        v_item.setData(0, _MEMORIZE_ROLE, is_mem)
                        return
                return
            break

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_selected_refs(self) -> list[dict]:
        """Return list of {"key": ..., "display": ...} for selected verse items."""
        result: list[dict] = []
        for item in self._tree.selectedItems():
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if data.get("type") == "verse":
                result.append({"key": data["key"], "display": data["display"]})
        return result
