"""Prayer Tool — manage the persisted list of prayer recipients.

Opened from the main window's Tools -> Prayer Tool menu item.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
)

from services.prayer_recipients import PrayerRecipientLibrary
from styles.theme import (
    COLOR_ACCENT,
    COLOR_BACKGROUND,
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_TEXT,
    FONT_FAMILY,
    FONT_SIZE_NORMAL,
)

_ID_ROLE = Qt.ItemDataRole.UserRole


class PrayerToolDialog(QDialog):
    """Add, rename, and delete prayer recipients."""

    def __init__(self, library: PrayerRecipientLibrary, parent=None) -> None:
        super().__init__(parent)
        self._library = library
        self.setWindowTitle("Prayer Tool")
        self.resize(360, 480)
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._list, stretch=1)

        add_row = QHBoxLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("New recipient name\u2026")
        self._name_edit.returnPressed.connect(self._on_add)
        add_row.addWidget(self._name_edit, stretch=1)

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(32)
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(add_btn)

        root.addLayout(add_row)

        self.setStyleSheet(
            f"QDialog {{ background: {COLOR_BACKGROUND}; color: {COLOR_TEXT}; "
            f"font-family: '{FONT_FAMILY}'; font-size: {FONT_SIZE_NORMAL}pt; }}"
            f"QListWidget {{ background: {COLOR_SURFACE}; border: 1px solid {COLOR_BORDER}; }}"
            f"QPushButton {{ background: {COLOR_ACCENT}; color: white; border: none; "
            f"border-radius: 4px; padding: 6px; }}"
        )

    def _reload(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        prayed_names = self._library.get_prayed_names()
        for recipient in self._library.load():
            label = f"\u2713 {recipient.name}" if recipient.name in prayed_names else recipient.name
            item = QListWidgetItem(label)
            item.setData(_ID_ROLE, recipient.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _on_add(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            return
        recipient = self._library.add(name)
        if recipient is None:
            return
        item = QListWidgetItem(recipient.name)
        item.setData(_ID_ROLE, recipient.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._list.addItem(item)
        self._name_edit.clear()

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._list.viewport().mapToGlobal(pos))
        if chosen is edit_action:
            self._list.editItem(item)
        elif chosen is delete_action:
            self._library.delete(item.data(_ID_ROLE))
            self._list.takeItem(self._list.row(item))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        new_name = item.text().strip()
        if new_name.startswith("\u2713 "):
            new_name = new_name[2:].strip()
        if not new_name:
            return
        self._library.rename(item.data(_ID_ROLE), new_name)
        self._reload()
