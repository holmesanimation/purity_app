"""Calories Dialog — Diet journal entry with tags and manual / ChatGPT-estimated calories."""

from __future__ import annotations

import traceback
import uuid
from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from services.notes_setup import diet_notes_writer, notes_repo
from services.openai_client import CalorieEstimationError, estimate_calories
from services.tag_library import TagLibrary
from shane_common.notes.notes_writer import NoteType
from ui.notes.note_dialog import NoteDialog


def _calories_line_edit() -> QtWidgets.QLineEdit:
    edit = QtWidgets.QLineEdit()
    edit.setFixedWidth(70)
    edit.setPlaceholderText("kcal")
    edit.setValidator(QtGui.QIntValidator(0, 20000, edit))
    return edit


def _estimate_into(parent: QtWidgets.QWidget, text: str, target: QtWidgets.QLineEdit) -> bool:
    """Run the (synchronous) calorie estimate for *text* and fill *target*."""
    try:
        calories = estimate_calories(text)
    except CalorieEstimationError as exc:
        traceback.print_exc()
        QtWidgets.QMessageBox.warning(parent, "Calorie Estimate Failed", str(exc))
        return False
    target.setText(f"{calories:.0f}")
    return True


class _EditCaloriesWidget(QtWidgets.QWidget):
    """Calories field + ChatGPT button shown in the shared edit dialog."""

    def __init__(self, text_source: Callable[[], str]) -> None:
        super().__init__()
        self._text_source = text_source
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        self.calories_edit = _calories_line_edit()
        layout.addWidget(self.calories_edit)
        btn = QtWidgets.QPushButton("ChatGPT")
        btn.clicked.connect(self._on_chatgpt)
        layout.addWidget(btn)

    def _on_chatgpt(self) -> None:
        text = self._text_source().strip()
        if text:
            _estimate_into(self, text, self.calories_edit)


class CaloriesDialog(NoteDialog):
    """Diet journal dialog: note text + tags + manually entered or ChatGPT-estimated calories."""

    def __init__(
        self,
        on_result_changed: Callable[[], None] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        self._on_result_changed = on_result_changed
        self._tag_library = TagLibrary()
        self._selected_tags: list[str] = []
        self._tag_popup: QtWidgets.QWidget | None = None
        super().__init__(
            writer=diet_notes_writer,
            owner="Diet",
            show_type_selector=False,
            history_rows=notes_repo.rows_for_owner("Diet"),
            parent=parent,
        )
        self.setWindowTitle("Calories Dialog")

    # -- UI hooks ----------------------------------------------------------

    def _build_top_extra(self, layout: QtWidgets.QVBoxLayout) -> None:
        row = QtWidgets.QHBoxLayout()
        self._tags_btn = QtWidgets.QPushButton("Tags")
        self._tags_btn.clicked.connect(self._open_tag_picker)
        row.addWidget(self._tags_btn)
        self._tags_label = QtWidgets.QLabel("")
        row.addWidget(self._tags_label, 1)
        layout.addLayout(row)

    def _build_commit_row_extra(self, btn_row: QtWidgets.QHBoxLayout) -> None:
        self._calories_edit = _calories_line_edit()
        btn_row.addWidget(self._calories_edit)
        self._chatgpt_btn = QtWidgets.QPushButton("ChatGPT")
        self._chatgpt_btn.clicked.connect(self._on_chatgpt_clicked)
        btn_row.addWidget(self._chatgpt_btn)

    # -- tags --------------------------------------------------------------

    def _open_tag_picker(self) -> None:
        from ui.left_dock_dashboard import _TagPickerPopup

        self._tag_popup = _TagPickerPopup(
            library=self._tag_library,
            selected=list(self._selected_tags),
            on_changed=self._on_tags_changed,
        )
        self._tag_popup.adjustSize()
        pos = self._tags_btn.mapToGlobal(self._tags_btn.rect().bottomLeft())
        self._tag_popup.move(pos)
        self._tag_popup.show()
        self._tag_popup.raise_()

    def _on_tags_changed(self, tags: list[str]) -> None:
        self._selected_tags = list(tags)
        self._refresh_tags_label()

    def _refresh_tags_label(self) -> None:
        self._tags_label.setText(", ".join(f"#{t}" for t in self._selected_tags))

    # -- calories ----------------------------------------------------------

    @QtCore.Slot()
    def _on_chatgpt_clicked(self) -> None:
        text = self._body_edit.toPlainText().strip()
        if not text:
            self._status_label.setText("Enter note text before estimating calories.")
            return
        _estimate_into(self, text, self._calories_edit)

    @QtCore.Slot()
    def _on_commit(self) -> None:
        text = self._body_edit.toPlainText().strip()
        if not text:
            self._status_label.setText("Note text is empty.")
            return

        context: dict[str, Any] = {"note_id": uuid.uuid4().hex, "revision_num": 1, "op": "create"}
        if self._selected_tags:
            context["tags"] = list(self._selected_tags)
        calories_text = self._calories_edit.text().strip()
        if calories_text:
            context["calories"] = float(calories_text)

        note = self._writer.build_note(note_type=NoteType.GENERAL, text=text, context=context)
        try:
            path = self._writer.commit(note)
        except Exception as exc:
            traceback.print_exc()
            self._status_label.setText(f"Error: {exc}")
            return

        self._last_path = path
        self._open_folder_btn.setEnabled(True)
        self._status_label.setText(f"Saved to {path}")
        self._body_edit.clear()
        self._calories_edit.clear()
        self._selected_tags = []
        self._refresh_tags_label()
        self._record_new_revision(note)
        if self._on_result_changed is not None:
            self._on_result_changed()

    # -- history / edit hooks ------------------------------------------------

    def _history_item_rich_text(self, row: Any) -> str | None:
        calories = (getattr(row, "context", None) or {}).get("calories")
        if calories is None:
            return None
        plain = self._format_history_item(getattr(row, "wall_ts", None), getattr(row, "text", ""))
        return f"{plain} - <b>{int(calories)} calories</b>"

    def _extra_edit_widget_factory(self) -> QtWidgets.QWidget | None:
        # The edit dialog owns its own text box; resolve it lazily from the widget's window.
        def text_source() -> str:
            win = widget.window()
            edit = getattr(win, "_body_edit", None)
            return edit.toPlainText() if edit is not None else ""

        widget = _EditCaloriesWidget(text_source)
        return widget

    def _extra_edit_widget_set_value(self, widget: QtWidgets.QWidget, row: Any) -> None:
        calories = (getattr(row, "context", None) or {}).get("calories")
        if isinstance(widget, _EditCaloriesWidget) and calories is not None:
            widget.calories_edit.setText(f"{calories:.0f}")

    def _extra_edit_widget_get_context(self, widget: QtWidgets.QWidget) -> dict:
        if not isinstance(widget, _EditCaloriesWidget):
            return {}
        text = widget.calories_edit.text().strip()
        # ``None`` explicitly clears calories (edit-merge would otherwise keep the old value).
        return {"calories": float(text) if text else None}

    def _on_note_edited(self, row: Any, new_text: str, new_context: dict) -> None:
        if self._on_result_changed is not None:
            self._on_result_changed()
