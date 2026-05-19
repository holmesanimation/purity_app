"""Singleton notes infrastructure for purity_app.

Exposes two module-level objects consumed across the app:
    notes_writer  — NotesWriter for committing new notes
    notes_repo    — NotesRepository for browsing existing notes

The module-level `notes_writer` uses ``run_id="default"`` for backward
compatibility.  Call ``make_notes_writer(run_id=...)`` to get a writer
bound to a specific session run_id.
"""
from pathlib import Path
from shane_common.notes.notes_writer import NotesWriter
from shane_common.notes.notes_repository import NotesRepository

_NOTES_ROOT = Path(__file__).parent.parent / "notes"


def make_notes_writer(run_id: str = "default") -> NotesWriter:
    """Return a NotesWriter bound to the given run_id."""
    return NotesWriter(
        notes_root=str(_NOTES_ROOT),
        owner="purity",
        platform="PurityApp",
        run_id=run_id,
    )


notes_writer = make_notes_writer(run_id="default")

notes_repo = NotesRepository(_NOTES_ROOT)
