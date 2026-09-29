"""Left-dock journal: Owner dropdown, Subject button, Title line edit."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QTextEdit

import ui.left_dock_dashboard as ldd
from services.fake_journal import FakeJournalService
from shane_common.notes.notes_repository import NotesRepository, latest_revisions
from shane_common.notes.notes_writer import UNSET_SUBJECT, NotesWriter
from shane_common.notes.registry import NotesRegistry
from shane_common.notes.store import NotesStore
from ui.left_dock_dashboard import _FreeJournalWidget

BUILTINS = (("journal", "journal"), ("Prayer", "Prayer"), ("Bible", "Bible"))


@pytest.fixture(scope="module", autouse=True)
def _app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    store = NotesStore(tmp_path / "notes.db")
    registry = NotesRegistry(store, builtin_owners=BUILTINS)
    base = NotesWriter(store, "journal")
    monkeypatch.setattr(ldd, "notes_registry", registry)
    monkeypatch.setattr(ldd, "writer_for_owner", base.for_owner)

    class Env:
        pass

    e = Env()
    e.store, e.registry, e.writer, e.repo = store, registry, base, NotesRepository(store)
    e.widget = _FreeJournalWidget(
        journal_service=FakeJournalService(),
        notes_writer=base,
        prayer_notes_writer=base.for_owner("Prayer"),
        prayer_recipient_name="Mom",
    )
    yield e
    store.close()


def _rows(e, owner):
    return latest_revisions(e.repo.rows_for_owner(owner))


def test_layout_owner_row_then_title_then_journal_text(env) -> None:
    w = env.widget
    layout = w.layout()
    items = [layout.itemAt(i) for i in range(layout.count())]
    idx_owner_row = next(
        i for i, it in enumerate(items) if it.layout() is not None and it.layout().indexOf(w._owner_combo) >= 0
    )
    idx_title = next(i for i, it in enumerate(items) if it.widget() is w._title_edit)
    idx_text = next(i for i, it in enumerate(items) if it.widget() is w._free_input)
    assert idx_owner_row + 1 == idx_title and idx_title + 1 == idx_text
    assert isinstance(w._title_edit, QLineEdit) and isinstance(w._free_input, QTextEdit)
    assert isinstance(items[idx_owner_row].layout(), QHBoxLayout)
    assert w._subject_btn.text() == "Subject"
    assert w._title_edit.text() == ""


def test_owner_dropdown_lists_all_owners_and_defaults_to_journal(env) -> None:
    env.registry.add_owner("Sleep Log")
    combo = env.widget._owner_combo
    assert combo.current_key() == "journal"
    combo.showPopup  # noqa: B018 - method exists; reload happens on open
    combo.reload()
    keys = [combo.itemData(i) for i in range(combo.count())]
    assert keys == ["journal", "Prayer", "Bible", "sleep_log"]


def test_save_writes_title_subject_and_owner_file(env) -> None:
    w = env.widget
    sub = env.registry.add_subject("Anxiety", "journal")
    w._title_edit.setText("Rough day")
    w._set_subject(sub.id)
    w._free_input.setPlainText("body text")
    w._save_free()

    (row,) = _rows(env, "journal")
    assert (row.title, row.subject, row.text) == ("Rough day", sub.id, "body text")
    # form resets like the tags do
    assert w._title_edit.text() == "" and w._subject == UNSET_SUBJECT and w._subject_btn.text() == "Subject"


def test_save_without_title_or_subject_uses_none_and_unset(env) -> None:
    w = env.widget
    w._free_input.setPlainText("plain")
    w._save_free()
    (row,) = _rows(env, "journal")
    assert row.title is None and row.subject == UNSET_SUBJECT
    stored = env.store._db.connection().execute("SELECT title, subject_id FROM revisions").fetchone()
    assert tuple(stored) == (None, None)  # UNSET is stored as NULL


def test_changing_owner_redirects_note_to_that_owner(env) -> None:
    w = env.widget
    env.registry.add_owner("Sleep Log")
    w._owner_combo.reload()
    w._owner_combo.setCurrentIndex(w._owner_combo.findData("sleep_log"))
    w._free_input.setPlainText("slept badly")
    w._save_free()
    assert [r.text for r in _rows(env, "sleep_log")] == ["slept badly"]
    assert _rows(env, "journal") == []


def test_subject_scoped_to_other_owner_is_cleared_on_owner_change(env) -> None:
    w = env.widget
    mine = env.registry.add_subject("JournalOnly", "journal")
    shared = env.registry.add_subject("Shared", None)

    w._set_subject(shared.id)
    w._owner_combo.setCurrentIndex(w._owner_combo.findData("Bible"))
    assert w._subject == shared.id  # all-owner subjects carry over

    w._owner_combo.setCurrentIndex(w._owner_combo.findData("journal"))
    w._set_subject(mine.id)
    w._owner_combo.setCurrentIndex(w._owner_combo.findData("Bible"))
    assert w._subject == UNSET_SUBJECT and w._subject_btn.text() == "Subject"


def test_tag_prayer_saves_subject_as_unset_if_prayer_cannot_use_it(env) -> None:
    w = env.widget
    mine = env.registry.add_subject("JournalOnly", "journal")
    w._set_subject(mine.id)
    w._tag_prayer_btn.setChecked(True)
    w._free_input.setPlainText("pray")
    w._save_free()
    (row,) = _rows(env, "Prayer")
    assert row.subject == UNSET_SUBJECT


def test_subject_button_text_shows_chosen_subject(env) -> None:
    sub = env.registry.add_subject("Anxiety", "journal")
    env.widget._set_subject(sub.id)
    assert env.widget._subject_btn.text() == "Subject: Anxiety"
