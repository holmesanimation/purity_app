"""Calories Dialog — Diet journal entry that also estimates calories via OpenAI."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6 import QtCore, QtWidgets

from services.diet_state import DietState
from services.notes_setup import diet_notes_writer, notes_repo
from services.openai_client import CalorieEstimationError, estimate_calories
from shane_common.notes.notes_writer import NoteType
from ui.notes.note_dialog import NoteDialog


class _CalorieWorker(QtCore.QObject):
    """Runs ``estimate_calories`` on a background thread."""

    succeeded = QtCore.Signal(str, float)
    failed = QtCore.Signal(str)

    def __init__(self, entry_id: str, text: str) -> None:
        super().__init__()
        self._entry_id = entry_id
        self._text = text

    @QtCore.Slot()
    def run(self) -> None:
        try:
            calories = estimate_calories(self._text)
        except CalorieEstimationError:
            traceback.print_exc()
            self.failed.emit(self._entry_id)
            return
        self.succeeded.emit(self._entry_id, calories)


class CaloriesDialog(NoteDialog):
    """Diet journal dialog: commits a note, then estimates calories asynchronously."""

    def __init__(
        self,
        diet_state: DietState,
        on_result_changed: Callable[[], None] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        self._diet_state = diet_state
        self._on_result_changed = on_result_changed
        self._threads: list[QtCore.QThread] = []
        super().__init__(
            writer=diet_notes_writer,
            owner="Diet",
            show_type_selector=False,
            history_rows=notes_repo.rows_for_owner("Diet"),
            parent=parent,
        )
        self.setWindowTitle("Calories Dialog")

    @QtCore.Slot()
    def _on_commit(self) -> None:
        text = self._body_edit.toPlainText().strip()
        if not text:
            self._status_label.setText("Note text is empty.")
            return

        note = self._writer.build_note(note_type=NoteType.GENERAL, text=text)
        try:
            path = self._writer.commit(note)
        except Exception as exc:
            traceback.print_exc()
            self._status_label.setText(f"Error: {exc}")
            return

        self._last_path = path
        self._open_folder_btn.setEnabled(True)
        self._status_label.setText(f"Saved to {path} \u2014 estimating calories\u2026")
        self._body_edit.clear()
        if self._history_list is not None:
            self._history_list.insertItem(0, self._format_history_item(note.wall_ts, note.text))

        entry_id = self._diet_state.add_calorie_entry(text)
        if self._on_result_changed is not None:
            self._on_result_changed()
        self._start_estimate(entry_id, text)

    def _start_estimate(self, entry_id: str, text: str) -> None:
        thread = QtCore.QThread(self)
        worker = _CalorieWorker(entry_id, text)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._on_estimate_succeeded)
        worker.failed.connect(self._on_estimate_failed)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        self._threads.append(thread)
        # Keep worker alive for the thread's lifetime.
        thread._worker = worker  # type: ignore[attr-defined]
        thread.start()

    @QtCore.Slot(str, float)
    def _on_estimate_succeeded(self, entry_id: str, calories: float) -> None:
        self._diet_state.resolve_calorie_entry(entry_id, calories)
        self._status_label.setText(f"Estimated {calories:.0f} calories.")
        if self._on_result_changed is not None:
            self._on_result_changed()

    @QtCore.Slot(str)
    def _on_estimate_failed(self, entry_id: str) -> None:
        self._diet_state.fail_calorie_entry(entry_id)
        self._status_label.setText("Calorie estimation failed \u2014 will retry on next pulse.")
        if self._on_result_changed is not None:
            self._on_result_changed()
