"""Shared widget: list of previously saved "Bible"-owner journal notes for a verse."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from services.notes_setup import notes_repo
from styles.theme import COLOR_TEXT_MUTED, FONT_FAMILY, FONT_SIZE_SMALL

_BIBLE_OWNER = "Bible"


class VerseNotesHistoryWidget(QWidget):
    """Read-only list of "Bible"-owner notes tagged with the current verse."""

    def __init__(self, repo=notes_repo, parent=None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._ref_key: Optional[str] = None

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        title = QLabel("Notes for this verse")
        title.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}pt;"
            f"font-weight: 600; font-family: '{FONT_FAMILY}'; background: transparent;"
        )
        vbox.addWidget(title)

        self._list = QListWidget()
        self._list.setSpacing(2)
        vbox.addWidget(self._list)

    def set_verse(self, ref_key: Optional[str]) -> None:
        self._ref_key = ref_key
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        if not self._ref_key:
            return
        rows = [
            row
            for row in self._repo.rows_for_owner(_BIBLE_OWNER)
            if any(
                tagged.get("key") == self._ref_key
                for tagged in (row.context.get("tagged_verses") or [])
            )
        ]
        rows.sort(key=lambda row: row.ts or 0)
        for row in rows:
            ts_label = (
                datetime.fromtimestamp(row.wall_ts).strftime("%b %d %H:%M")
                if row.wall_ts
                else ""
            )
            preview = (row.text or "")[:80]
            self._list.addItem(QListWidgetItem(f"[{ts_label}] {preview}"))
