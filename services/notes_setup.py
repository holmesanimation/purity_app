"""Singleton notes infrastructure for purity_app.

Exposes the module-level objects consumed across the app:
    notes_store    — NotesStore, the SQLite database (source of truth)
    notes_writer   — NotesWriter for committing new notes ("purity" owner)
    notes_repo     — NotesRepository for browsing existing notes
    notes_registry — NotesRegistry of owners and subjects

The database is ``<data_root>/data/notes.db``.  ``data_root`` is resolved the same
way ``app.main()`` resolves it (``PURITY_DATA_ROOT`` env var, then the saved
setting, then ``~/.purity``).  Nothing touches the disk until the store is first
used, so importing this module is cheap and a second app instance that exits at
the singleton gate never opens the database.
"""
from pathlib import Path
import warnings

from services.notes_paths import notes_db_path, synced_folder_marker
from services.settings_schemas import build_purity_settings_manager, resolve_purity_data_root
from shane_common.notes.notes_writer import NotesWriter
from shane_common.notes.notes_repository import NotesRepository
from shane_common.notes.registry import NotesRegistry, set_default_registry
from shane_common.notes.store import NotesStore


def _resolve_data_root() -> Path:
    try:
        return Path(resolve_purity_data_root(build_purity_settings_manager()))
    except Exception:  # noqa: BLE001 - settings problems must not break importing the app
        return Path.home() / ".purity"


DATA_ROOT = _resolve_data_root()
NOTES_DB_PATH = notes_db_path(DATA_ROOT)

_synced = synced_folder_marker(NOTES_DB_PATH)
if _synced is not None:
    warnings.warn(
        f"The notes database {NOTES_DB_PATH} is inside a cloud-synced folder ({_synced!r}). "
        "Move data_root out of it: a sync client can upload a torn copy of a live SQLite file.",
        stacklevel=1,
    )

# Hardcoded owners: (key, label).  Registered in the database on first open.
# Owners the user creates in the Notes Browser are added to the same table.
BUILTIN_OWNERS = (
    ("journal", "journal"),
    ("Prayer", "Prayer"),
    ("Bible", "Bible"),
    ("Diet", "Diet"),
    ("purity", "purity"),
)

notes_store = NotesStore(NOTES_DB_PATH)


def make_notes_writer(owner: str = "purity") -> NotesWriter:
    """Return a NotesWriter for *owner* on the app-wide store."""
    return NotesWriter(notes_store, owner)


notes_writer = make_notes_writer("purity")
journal_notes_writer = make_notes_writer("journal")
prayer_notes_writer = make_notes_writer("Prayer")
bible_notes_writer = make_notes_writer("Bible")
diet_notes_writer = make_notes_writer("Diet")

notes_repo = NotesRepository(notes_store)

notes_registry = NotesRegistry(notes_store, builtin_owners=BUILTIN_OWNERS)
# NoteDialog / NotesBrowserWindow fall back to this when not given a registry.
set_default_registry(notes_registry)


def writer_for_owner(owner_key: str) -> NotesWriter:
    """Return the session notes writer for *owner_key* (built-in or user-created)."""
    return notes_writer.for_owner(owner_key)
