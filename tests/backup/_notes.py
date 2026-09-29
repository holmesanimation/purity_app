"""Helpers that build a real notes database / snapshot for the backup tests."""

from __future__ import annotations

from pathlib import Path

from services.backup.snapshot import SnapshotInfo, prepare_notes_snapshot
from services.notes_paths import notes_db_path
from shane_common.notes.notes_writer import NotesWriter
from shane_common.notes.store import NotesStore


def add_note(data_root: Path, text: str, owner: str = "journal", **kwargs) -> str:
    """Write a note to the live notes database under *data_root*; return its note_id."""
    store = NotesStore(notes_db_path(data_root))
    try:
        writer = NotesWriter(store, owner)
        note = writer.build_note(text=text, **kwargs)
        writer.commit(note)
        return note.note_id
    finally:
        store.close()


def make_empty_db(data_root: Path) -> Path:
    """Create the live notes database with a schema but no notes."""
    store = NotesStore(notes_db_path(data_root))
    try:
        store.owners()
    finally:
        store.close()
    return notes_db_path(data_root)


def make_snapshot(data_root: Path, *notes: str) -> SnapshotInfo:
    """Create a live database holding *notes* and return a verified staged snapshot of it."""
    for text in notes or ("a note",):
        add_note(data_root, text)
    info = prepare_notes_snapshot(data_root)
    assert info is not None
    return info
