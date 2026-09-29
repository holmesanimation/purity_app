"""Where the notes database lives.

Kept separate from ``notes_setup`` (which opens the app-wide store) so the backup
subsystem can locate the live database without importing the app singletons.
"""
from __future__ import annotations

from pathlib import Path

NOTES_DB_FILENAME = "notes.db"

#: Folder names that mark a cloud-synced directory.  The live database (and its
#: -wal/-shm files) must never sit inside one: a sync client can upload a torn copy.
_SYNC_FOLDER_MARKERS = ("dropbox", "onedrive", "google drive", "googledrive", "icloud", "box sync")


def notes_db_path(data_root: str | Path) -> Path:
    """Live notes database: ``<data_root>/data/notes.db`` (beside ``diet_state.json``)."""
    return Path(data_root) / "data" / NOTES_DB_FILENAME


def synced_folder_marker(path: str | Path) -> str | None:
    """Return the cloud-sync folder name *path* appears to be inside, else ``None``."""
    for part in Path(path).parts:
        lowered = part.casefold()
        for marker in _SYNC_FOLDER_MARKERS:
            if lowered == marker or lowered.startswith(marker + " ") or lowered.startswith(marker + "-"):
                return part
    return None
