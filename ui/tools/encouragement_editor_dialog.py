"""Encouragement editor — two-column dialog for creating, editing, and deleting
panic encouragements stored in ``<data_root>/reminders.yaml``.

Open from the main window's Tools → Edit Encouragements menu item.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.panic_reminders import PanicReminders
from styles.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_DARK,
    COLOR_BACKGROUND,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_2,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
    FONT_FAMILY,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
)
from ui.intervention.panic_reason_dialog import REASON_LABELS

# ---------------------------------------------------------------------------
# Subject choices: "general" first, then all reason labels
# ---------------------------------------------------------------------------
_SUBJECT_CHOICES: list[tuple[str, str]] = [("general", "General")] + list(REASON_LABELS)

# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------
_ORANGE = COLOR_WARNING   # #B0894F  — "dirty" indicator
_WHITE_TEXT = COLOR_TEXT

# ---------------------------------------------------------------------------
# Stylesheet helpers
# ---------------------------------------------------------------------------

_FIELD_NORMAL = (
    f"background-color: {COLOR_SURFACE_2};"
    f"color: {COLOR_TEXT};"
    f"border: 1px solid {COLOR_BORDER};"
    f"border-radius: 4px;"
)

_FIELD_DIRTY = (
    f"background-color: {COLOR_SURFACE_2};"
    f"color: {_ORANGE};"
    f"border: 1px solid {_ORANGE};"
    f"border-radius: 4px;"
)

_BTN_SAVE_NORMAL = (
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

_BTN_SAVE_DIRTY = (
    f"QPushButton {{"
    f"  background-color: {_ORANGE};"
    f"  color: #ffffff;"
    f"  border: none;"
    f"  border-radius: 6px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  font-weight: 700;"
    f"  padding: 7px 20px;"
    f"}}"
    f"QPushButton:hover {{ background-color: #8a6035; }}"
    f"QPushButton:disabled {{ background-color: {COLOR_BORDER}; color: {COLOR_TEXT_MUTED}; }}"
)

_BTN_REVERT = (
    f"QPushButton {{"
    f"  background-color: transparent;"
    f"  color: {_ORANGE};"
    f"  border: 1px solid {_ORANGE};"
    f"  border-radius: 6px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  padding: 7px 16px;"
    f"}}"
    f"QPushButton:hover {{ background-color: {COLOR_SURFACE}; }}"
)

_BTN_DELETE = (
    f"QPushButton {{"
    f"  background-color: #C0392B;"
    f"  color: #ffffff;"
    f"  border: none;"
    f"  border-radius: 4px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  font-weight: 700;"
    f"  padding: 8px 12px;"
    f"}}"
    f"QPushButton:hover {{ background-color: #96281B; }}"
    f"QPushButton:disabled {{"
    f"  background-color: {COLOR_BORDER};"
    f"  color: {COLOR_TEXT_MUTED};"
    f"}}"
)

_BTN_CREATE = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  color: {COLOR_TEXT};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 6px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"  font-weight: 700;"
    f"  padding: 8px 12px;"
    f"}}"
    f"QPushButton:hover {{ background-color: {COLOR_SURFACE}; border-color: {COLOR_ACCENT}; }}"
)

_LIST_ITEM_ORANGE = f"color: {_ORANGE};"

_COMBO_NORMAL_STYLE = (
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
_COMBO_DIRTY_STYLE = (
    f"QComboBox {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  color: {_ORANGE};"
    f"  border: 1px solid {_ORANGE};"
    f"  border-radius: 4px;"
    f"  padding: 4px 8px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_NORMAL}pt;"
    f"}}"
    f"QComboBox::drop-down {{ border: none; }}"
)

_BTN_PREVIEW = (
    f"QPushButton {{"
    f"  background-color: {COLOR_SURFACE_2};"
    f"  color: {COLOR_TEXT};"
    f"  border: 1px solid {COLOR_BORDER};"
    f"  border-radius: 6px;"
    f"  font-family: '{FONT_FAMILY}';"
    f"  font-size: {FONT_SIZE_SMALL}pt;"
    f"  padding: 4px 12px;"
    f"}}"
    f"QPushButton:hover {{ background-color: {COLOR_SURFACE}; border-color: {COLOR_ACCENT}; }}"
    f"QPushButton:checked {{"
    f"  background-color: {COLOR_ACCENT};"
    f"  color: #ffffff;"
    f"  border-color: {COLOR_ACCENT_DARK};"
    f"}}"
)

# ---------------------------------------------------------------------------
# Image library
# ---------------------------------------------------------------------------
_BACKGROUNDS_DIR = Path("G:/PURITY_APP/images/backgrounds")
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}


def _get_background_names() -> list[str]:
    """Return sorted list of image filenames from the backgrounds library."""
    if not _BACKGROUNDS_DIR.exists():
        return []
    return sorted(
        p.name for p in _BACKGROUNDS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
    )


# ---------------------------------------------------------------------------
# Preview overlay
# ---------------------------------------------------------------------------

class _BackgroundPreviewOverlay(QWidget):
    """Full-screen image overlay displayed behind the editor dialog during preview."""

    def __init__(self, image_path: Optional[Path]) -> None:
        super().__init__(
            None,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._pixmap = QPixmap()
        if image_path is not None:
            self._pixmap = QPixmap(str(image_path))
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())

    def load_image(self, image_path: Path) -> None:
        """Swap the displayed image without recreating the widget."""
        self._pixmap = QPixmap(str(image_path))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 190))
        if not self._pixmap.isNull():
            # Never upscale — show at natural size.  Only scale *down* if the
            # image is wider or taller than the screen.
            pw, ph = self._pixmap.width(), self._pixmap.height()
            if pw > self.width() or ph > self.height():
                pix = self._pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            else:
                pix = self._pixmap
            x = (self.width() - pix.width()) // 2
            y = (self.height() - pix.height()) // 2
            painter.drawPixmap(x, y, pix)


class EncouragementEditorDialog(QDialog):
    """Two-column dialog: list on the left, detail editor on the right."""

    def __init__(
        self,
        panic_reminders: PanicReminders,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint,
        )
        self.setWindowTitle("Edit Encouragements")
        self.resize(960, 620)
        self.setMinimumSize(760, 480)

        self._reminders = panic_reminders
        self._current_index: Optional[int] = None   # index in get_all(); None = new
        self._original_data: Optional[dict] = None
        self._is_dirty: bool = False
        self._is_new: bool = False           # True after Create, before first save
        self._pending_edits: dict = {}       # int → dict; unsaved edits per reminder index

        # Dirty tracking: map field widget → field key
        self._field_map: dict[QWidget, str] = {}

        self._preview_overlay: Optional[_BackgroundPreviewOverlay] = None

        self._build_ui()
        self._load_list()
        self._set_detail_enabled(False)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(280)
        left.setStyleSheet(
            f"background-color: {COLOR_SURFACE};"
            f"border-right: 1px solid {COLOR_BORDER};"
        )
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 10, 10, 10)
        lv.setSpacing(8)

        self._list_widget = QListWidget()
        self._list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_widget.setStyleSheet(
            f"QListWidget {{"
            f"  background-color: {COLOR_BACKGROUND};"
            f"  border: 1px solid {COLOR_BORDER};"
            f"  border-radius: 4px;"
            f"  font-family: '{FONT_FAMILY}';"
            f"  font-size: {FONT_SIZE_NORMAL}pt;"
            f"  color: {COLOR_TEXT};"
            f"}}"
            f"QListWidget::item {{ padding: 7px 10px; }}"
            f"QListWidget::item:selected {{"
            f"  background-color: {COLOR_ACCENT};"
            f"  color: #ffffff;"
            f"}}"
        )
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.customContextMenuRequested.connect(self._on_list_context_menu)
        self._list_widget.currentItemChanged.connect(self._on_item_selected)
        lv.addWidget(self._list_widget, stretch=1)

        self._create_btn = QPushButton("+ Create Encouragement")
        self._create_btn.setStyleSheet(_BTN_CREATE)
        self._create_btn.clicked.connect(self._on_create)
        lv.addWidget(self._create_btn)

        root.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(18, 14, 18, 14)
        rv.setSpacing(12)

        self._detail_header = QLabel("Encouragement Details")
        self._detail_header.setStyleSheet(
            f"font-family: '{FONT_FAMILY}'; font-size: 13pt; font-weight: 700;"
            f"color: {COLOR_TEXT}; background: transparent;"
        )
        rv.addWidget(self._detail_header)

        # Form
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setSpacing(10)
        form.setContentsMargins(0, 0, 0, 0)

        def _label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt;"
                f"color: {COLOR_TEXT_MUTED}; background: transparent;"
            )
            return lbl

        # Title
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Bold identity headline")
        self._title_edit.setStyleSheet(_FIELD_NORMAL)
        form.addRow(_label("Title"), self._title_edit)
        self._field_map[self._title_edit] = "title"

        # Note
        self._note_edit = QTextEdit()
        self._note_edit.setPlaceholderText("Supporting personal affirmation")
        self._note_edit.setMinimumHeight(80)
        self._note_edit.setMaximumHeight(120)
        self._note_edit.setStyleSheet(_FIELD_NORMAL)
        form.addRow(_label("Note"), self._note_edit)
        self._field_map[self._note_edit] = "note"

        # Verse Reference
        self._verse_ref_edit = QLineEdit()
        self._verse_ref_edit.setPlaceholderText("e.g. 1 Tim. 1:5")
        self._verse_ref_edit.setStyleSheet(_FIELD_NORMAL)
        form.addRow(_label("Verse Reference"), self._verse_ref_edit)
        self._field_map[self._verse_ref_edit] = "verse_ref"

        # Verse Text
        self._verse_text_edit = QTextEdit()
        self._verse_text_edit.setPlaceholderText("Full scripture quote")
        self._verse_text_edit.setMinimumHeight(80)
        self._verse_text_edit.setMaximumHeight(120)
        self._verse_text_edit.setStyleSheet(_FIELD_NORMAL)
        form.addRow(_label("Verse Text"), self._verse_text_edit)
        self._field_map[self._verse_text_edit] = "verse_text"

        # Subject
        self._subject_combo = QComboBox()
        self._subject_combo.setStyleSheet(_COMBO_NORMAL_STYLE)
        for rid, label in _SUBJECT_CHOICES:
            self._subject_combo.addItem(label, userData=rid)
        form.addRow(_label("Subject"), self._subject_combo)
        self._field_map[self._subject_combo] = "subject"

        # Background
        bg_field = QWidget()
        bg_field.setStyleSheet("background: transparent;")
        bg_fl = QHBoxLayout(bg_field)
        bg_fl.setContentsMargins(0, 0, 0, 0)
        bg_fl.setSpacing(6)
        self._background_combo = QComboBox()
        self._background_combo.setStyleSheet(_COMBO_NORMAL_STYLE)
        self._background_combo.addItem("(None)", userData=None)
        for bg_name in _get_background_names():
            self._background_combo.addItem(bg_name, userData=bg_name)
        bg_fl.addWidget(self._background_combo, stretch=1)
        self._preview_btn = QPushButton("Preview")
        self._preview_btn.setCheckable(True)
        self._preview_btn.setStyleSheet(_BTN_PREVIEW)
        self._preview_btn.clicked.connect(self._on_preview_toggle)
        bg_fl.addWidget(self._preview_btn)
        form.addRow(_label("Background"), bg_field)
        self._field_map[self._background_combo] = "background"

        rv.addLayout(form)
        rv.addStretch()

        # Bottom button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._revert_btn = QPushButton("Revert")
        self._revert_btn.setStyleSheet(_BTN_REVERT)
        self._revert_btn.setVisible(False)
        self._revert_btn.clicked.connect(self._on_revert)
        btn_row.addWidget(self._revert_btn)

        self._save_btn = QPushButton("Save Encouragement")
        self._save_btn.setStyleSheet(_BTN_SAVE_NORMAL)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        self._delete_btn = QPushButton("Delete Encouragement")
        self._delete_btn.setStyleSheet(_BTN_DELETE)
        self._delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._delete_btn)

        rv.addLayout(btn_row)

        root.addWidget(right, stretch=1)

        # ── Connect change signals ─────────────────────────────────────
        self._title_edit.textChanged.connect(self._on_any_field_changed)
        self._note_edit.textChanged.connect(self._on_any_field_changed)
        self._verse_ref_edit.textChanged.connect(self._on_any_field_changed)
        self._verse_text_edit.textChanged.connect(self._on_any_field_changed)
        self._subject_combo.currentIndexChanged.connect(self._on_any_field_changed)
        self._background_combo.currentIndexChanged.connect(self._on_background_combo_changed)

        # Keep track of all editable detail widgets for enable/disable toggling
        self._detail_widgets: list[QWidget] = [
            self._title_edit,
            self._note_edit,
            self._verse_ref_edit,
            self._verse_text_edit,
            self._subject_combo,
            self._background_combo,
            self._preview_btn,
            self._save_btn,
            self._delete_btn,
        ]

    # ------------------------------------------------------------------
    # Dialog lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        """Create the overlay (hidden) so it sits below this window in z-order."""
        if self._preview_overlay is None:
            # Build with a placeholder pixmap; real image loaded on first preview.
            self._preview_overlay = _BackgroundPreviewOverlay(None)
            self._preview_overlay.show()   # must show first to establish z-order
            self._preview_overlay.hide()   # then immediately hide
        self.raise_()
        super().showEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._close_preview()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _load_list(self, select_index: Optional[int] = None) -> None:
        """Repopulate QListWidget from the store. Re-select *select_index* if given."""
        # Block signals to avoid spurious _on_item_selected during repopulation
        self._list_widget.blockSignals(True)
        self._list_widget.clear()
        for reminder in self._reminders.get_all():
            item = QListWidgetItem(reminder.get("title") or "(Untitled)")
            self._list_widget.addItem(item)
        # Re-apply orange to items that have unsaved pending edits
        for pending_row in self._pending_edits:
            if isinstance(pending_row, int):
                pending_item = self._list_widget.item(pending_row)
                if pending_item is not None:
                    pending_item.setForeground(QColor(_ORANGE))
        self._list_widget.blockSignals(False)

        if select_index is not None and 0 <= select_index < self._list_widget.count():
            self._list_widget.setCurrentRow(select_index)
        elif self._list_widget.count() > 0:
            pass  # leave selection unchanged
        else:
            self._set_detail_enabled(False)

    def _set_list_item_color_at(self, row: int, dirty: bool) -> None:
        """Colour the list item at *row* orange (dirty) or normal."""
        item = self._list_widget.item(row)
        if item is None:
            return
        item.setForeground(QColor(_ORANGE if dirty else COLOR_TEXT))

    # ------------------------------------------------------------------
    # Detail pane load/clear
    # ------------------------------------------------------------------

    def _load_into_fields(self, reminder: dict) -> None:
        """Populate the form fields from *reminder* without triggering dirty."""
        self._block_change_signals(True)

        self._title_edit.setText(reminder.get("title", ""))
        self._note_edit.setPlainText(reminder.get("note", ""))
        self._verse_ref_edit.setText(reminder.get("verse_ref", ""))
        self._verse_text_edit.setPlainText(reminder.get("verse_text", ""))

        subject = reminder.get("subject", "general") or "general"
        idx = next(
            (i for i in range(self._subject_combo.count())
             if self._subject_combo.itemData(i) == subject),
            0,
        )
        self._subject_combo.setCurrentIndex(idx)

        background = reminder.get("background") or None
        bg_idx = next(
            (i for i in range(self._background_combo.count())
             if self._background_combo.itemData(i) == background),
            0,
        )
        self._background_combo.setCurrentIndex(bg_idx)

        self._block_change_signals(False)

    def _clear_fields(self) -> None:
        """Clear all form fields without triggering dirty."""
        self._block_change_signals(True)
        self._title_edit.clear()
        self._note_edit.clear()
        self._verse_ref_edit.clear()
        self._verse_text_edit.clear()
        self._subject_combo.setCurrentIndex(0)
        self._background_combo.setCurrentIndex(0)
        self._block_change_signals(False)

    def _collect_form_data(self) -> dict:
        return {
            "title":      self._title_edit.text().strip(),
            "note":       self._note_edit.toPlainText().strip(),
            "verse_ref":  self._verse_ref_edit.text().strip(),
            "verse_text": self._verse_text_edit.toPlainText().strip(),
            "subject":    self._subject_combo.currentData() or "general",
            "background": self._background_combo.currentData(),
        }

    def _block_change_signals(self, block: bool) -> None:
        for widget in self._field_map:
            widget.blockSignals(block)

    # ------------------------------------------------------------------
    # Enable / disable detail panel
    # ------------------------------------------------------------------

    def _set_detail_enabled(self, enabled: bool) -> None:
        for w in self._detail_widgets:
            w.setEnabled(enabled)
        if not enabled:
            self._revert_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Dirty state
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        if self._is_dirty:
            return
        self._is_dirty = True
        self._save_btn.setText("Edit Encouragement")
        self._save_btn.setStyleSheet(_BTN_SAVE_DIRTY)
        self._revert_btn.setVisible(True)
        if self._current_index is not None:
            self._set_list_item_color_at(self._current_index, True)

    def _clear_dirty(self) -> None:
        self._is_dirty = False
        self._save_btn.setText("Save Encouragement")
        self._save_btn.setStyleSheet(_BTN_SAVE_NORMAL)
        self._revert_btn.setVisible(False)
        if self._current_index is not None:
            self._set_list_item_color_at(self._current_index, False)
        # Reset all field borders to normal
        self._title_edit.setStyleSheet(_FIELD_NORMAL)
        self._note_edit.setStyleSheet(_FIELD_NORMAL)
        self._verse_ref_edit.setStyleSheet(_FIELD_NORMAL)
        self._verse_text_edit.setStyleSheet(_FIELD_NORMAL)
        self._subject_combo.setStyleSheet(_COMBO_NORMAL_STYLE)
        self._background_combo.setStyleSheet(_COMBO_NORMAL_STYLE)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_selected(
        self,
        current: Optional[QListWidgetItem],
        _previous: Optional[QListWidgetItem],
    ) -> None:
        if current is None:
            self._set_detail_enabled(False)
            return

        row = self._list_widget.row(current)
        reminders = self._reminders.get_all()
        if row < 0 or row >= len(reminders):
            return

        # ── Save edits for the item we're leaving ────────────────────
        if self._is_dirty and self._current_index is not None:
            self._pending_edits[self._current_index] = self._collect_form_data()
            # Leave its list item orange; do NOT call _clear_dirty here.

        # ── Remove (New) placeholder if navigating away from it ──────
        if self._is_new and self._current_index is None:
            new_row = self._list_widget.count() - 1
            if new_row != row:
                self._block_change_signals(True)
                self._list_widget.blockSignals(True)
                placeholder_row = len(reminders)  # one past the last real item
                placeholder_item = self._list_widget.item(placeholder_row)
                if placeholder_item is not None:
                    self._list_widget.takeItem(placeholder_row)
                self._list_widget.blockSignals(False)
                self._block_change_signals(False)
                self._is_new = False

        # ── Switch to the new item ────────────────────────────────────
        self._current_index = row
        self._is_new = False
        reminder = reminders[row]
        self._original_data = dict(reminder)

        if row in self._pending_edits:
            # Restore unsaved edits without discarding them
            self._load_into_fields(self._pending_edits[row])
            self._is_dirty = True
            self._save_btn.setText("Edit Encouragement")
            self._save_btn.setStyleSheet(_BTN_SAVE_DIRTY)
            self._revert_btn.setVisible(True)
            self._set_list_item_color_at(row, True)
            self._apply_field_colors(self._pending_edits[row])
        else:
            self._load_into_fields(reminder)
            # Reset dirty UI without touching any other list item colour
            self._is_dirty = False
            self._save_btn.setText("Save Encouragement")
            self._save_btn.setStyleSheet(_BTN_SAVE_NORMAL)
            self._revert_btn.setVisible(False)
            self._title_edit.setStyleSheet(_FIELD_NORMAL)
            self._note_edit.setStyleSheet(_FIELD_NORMAL)
            self._verse_ref_edit.setStyleSheet(_FIELD_NORMAL)
            self._verse_text_edit.setStyleSheet(_FIELD_NORMAL)
            self._subject_combo.setStyleSheet(_COMBO_NORMAL_STYLE)
            self._background_combo.setStyleSheet(_COMBO_NORMAL_STYLE)

        self._set_detail_enabled(True)
        self._delete_btn.setEnabled(True)

    def _on_create(self) -> None:
        """Add a placeholder list item and clear the form for a new entry."""
        # Add a placeholder item at the bottom of the list
        placeholder = QListWidgetItem("(New)")
        self._list_widget.blockSignals(True)
        self._list_widget.addItem(placeholder)
        self._list_widget.blockSignals(False)
        self._list_widget.setCurrentItem(placeholder)

        self._current_index = None
        self._is_new = True
        self._original_data = {}
        self._clear_fields()
        self._clear_dirty()
        self._set_detail_enabled(True)
        # Disable delete for a not-yet-saved item
        self._delete_btn.setEnabled(False)
        self._title_edit.setFocus()

    def _on_any_field_changed(self) -> None:
        """Called whenever any form field changes value."""
        if self._original_data is None:
            return
        current = self._collect_form_data()

        # Mark dirty if anything differs from the original snapshot
        changed = False
        for key, value in current.items():
            if key == "subject":
                default = "general"
            elif key == "background":
                default = None
            else:
                default = ""
            orig_val = self._original_data.get(key, default)
            if default is not None:
                orig_val = orig_val or default
                value = value or default  # type: ignore[assignment]
            if value != orig_val:
                changed = True
                break

        # Also mark dirty if this is a brand-new item (nothing was set before)
        if self._is_new:
            # Only mark dirty once something has actually been typed
            any_filled = any(v for v in current.values() if v and v != "general")
            if any_filled:
                self._mark_dirty()
                self._apply_field_colors(current)
            return

        if changed:
            self._mark_dirty()
        else:
            self._clear_dirty()

        self._apply_field_colors(current)

    def _apply_field_colors(self, current: dict) -> None:
        """Orange border on fields that differ from original."""
        if not self._is_dirty:
            return
        orig = self._original_data or {}
        for widget, key in self._field_map.items():
            current_val = current.get(key, "")
            if key == "subject":
                default = "general"
            elif key == "background":
                default = None
            else:
                default = ""
            orig_val = orig.get(key, default)
            if default is not None:
                orig_val = orig_val or default
                current_val = current_val or default  # type: ignore[assignment]
            dirty_field = (current_val != orig_val)
            if isinstance(widget, (QLineEdit, QTextEdit)):
                widget.setStyleSheet(_FIELD_DIRTY if dirty_field else _FIELD_NORMAL)
            elif isinstance(widget, QComboBox):
                widget.setStyleSheet(_COMBO_DIRTY_STYLE if dirty_field else _COMBO_NORMAL_STYLE)

    def _on_save(self) -> None:
        data = self._collect_form_data()

        # Validate: all fields required
        missing = [k for k, v in data.items() if k != "subject" and not v]
        if missing:
            QMessageBox.warning(
                self,
                "Required Fields Missing",
                "Please fill in all fields before saving:\n• "
                + "\n• ".join(missing),
            )
            return

        if self._is_new or self._current_index is None:
            self._reminders.add(data)  # type: ignore[arg-type]
            new_index = len(self._reminders.get_all()) - 1
            self._is_new = False
            self._current_index = new_index
            self._load_list(select_index=new_index)
        else:
            self._reminders.update(self._current_index, data)  # type: ignore[arg-type]
            saved_index = self._current_index
            self._load_list(select_index=saved_index)

        self._original_data = dict(data)
        self._pending_edits.pop(self._current_index, None)
        self._clear_dirty()

    def _on_revert(self) -> None:
        if self._original_data is None:
            return
        self._pending_edits.pop(self._current_index, None)
        self._load_into_fields(self._original_data)
        self._clear_dirty()
        if self._is_new:
            # Revert a new item means clearing it back to empty
            self._clear_fields()

    def _on_delete(self) -> None:
        if self._current_index is None:
            return
        if not self._show_delete_confirm():
            return
        idx = self._current_index
        self._reminders.delete(idx)
        self._current_index = None
        self._is_new = False
        self._is_dirty = False
        # Adjust pending-edit indices: remove deleted entry, shift items above it down
        self._pending_edits.pop(idx, None)
        self._pending_edits = {
            (k - 1 if isinstance(k, int) and k > idx else k): v
            for k, v in self._pending_edits.items()
        }
        # Select the item above (or first) after deletion
        new_count = len(self._reminders.get_all())
        select = min(idx, new_count - 1) if new_count > 0 else None
        self._load_list(select_index=select)
        if new_count == 0:
            self._clear_fields()
            self._set_detail_enabled(False)
        else:
            # _load_list will trigger _on_item_selected via currentItemChanged
            pass

    def _show_delete_confirm(self) -> bool:
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Delete Encouragement")
        dlg.setText("Are you sure you want to delete this encouragement?")
        delete_btn = dlg.addButton("DELETE", QMessageBox.ButtonRole.AcceptRole)
        delete_btn.setStyleSheet(
            "QPushButton { background-color: #C0392B; color: #ffffff;"
            " border: none; border-radius: 4px; font-weight: 700;"
            " padding: 6px 16px; }"
            "QPushButton:hover { background-color: #96281B; }"
        )
        dlg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        dlg.setDefaultButton(delete_btn)
        dlg.exec()
        return dlg.clickedButton() is delete_btn

    def _on_list_context_menu(self, pos) -> None:
        item = self._list_widget.itemAt(pos)
        if item is None:
            return
        row = self._list_widget.row(item)
        # Only show delete for saved items (not the (New) placeholder)
        reminders = self._reminders.get_all()
        if row >= len(reminders):
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self._list_widget)
        delete_action = menu.addAction("Delete Encouragement")
        chosen = menu.exec(self._list_widget.mapToGlobal(pos))
        if chosen is delete_action:
            # Select the item first so _current_index is correct
            self._list_widget.setCurrentRow(row)
            self._on_delete()

    # ------------------------------------------------------------------
    # Background combo + preview
    # ------------------------------------------------------------------

    def _on_background_combo_changed(self) -> None:
        """Called when the background combo selection changes."""
        self._on_any_field_changed()
        # If preview is active, refresh with the newly selected image.
        if self._preview_btn.isChecked():
            name = self._background_combo.currentData()
            if name is not None:
                image_path = _BACKGROUNDS_DIR / name
                if image_path.exists() and self._preview_overlay is not None:
                    self._preview_overlay.load_image(image_path)
                    self._preview_overlay.update()
                    self.raise_()
                    self.activateWindow()
                else:
                    self._close_preview()
            else:
                self._close_preview()

    def _on_preview_toggle(self, checked: bool) -> None:
        """Show or hide the full-screen background preview overlay."""
        if checked:
            name = self._background_combo.currentData()
            if name is None:
                self._preview_btn.setChecked(False)
                return
            image_path = _BACKGROUNDS_DIR / name
            if not image_path.exists():
                self._preview_btn.setChecked(False)
                return
            if self._preview_overlay is None:
                self._preview_overlay = _BackgroundPreviewOverlay(None)
                self._preview_overlay.show()
                self._preview_overlay.hide()
            self._preview_overlay.load_image(image_path)
            self._preview_overlay.show()
            self.raise_()
            self.activateWindow()
            self._preview_btn.setText("Close Preview")
        else:
            self._close_preview()

    def _close_preview(self) -> None:
        """Hide the preview overlay and reset the button."""
        if self._preview_overlay is not None:
            self._preview_overlay.hide()
        self._preview_btn.setChecked(False)
        self._preview_btn.setText("Preview")
