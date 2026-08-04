"""Persistent store for user-typed Bible verse text.

Stores a single JSON file at ``<data_root>/bible_library.json``.

Schema::

    {
        "john_3_16": {
            "display": "John 3:16",
            "versions": [
                {"version": "NIV", "text": "For God so loved the world..."},
                {"version": "ESV", "text": "For God so loved the world..."}
            ]
        },
        ...
    }

The ``versions`` list is ordered by insertion time; the last entry is treated
as the most recently saved version (used for tooltip previews).
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Optional


class BibleLibrary:
    """Load, query, and persist user-typed Bible verse text."""

    def __init__(self, data_root: Path) -> None:
        self._path = Path(data_root) / "bible_library.json"
        self._memorizing_path = Path(data_root) / "bible_memorizing.json"
        self._data: dict[str, dict] = {}
        self._memorizing: set[str] = set()
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load from disk; silently start empty if missing or corrupt."""
        if not self._path.exists():
            self._data = {}
        else:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                self._data = raw if isinstance(raw, dict) else {}
            except Exception:
                traceback.print_exc()
                self._data = {}
        if not self._memorizing_path.exists():
            self._memorizing = set()
        else:
            try:
                raw_m = json.loads(self._memorizing_path.read_text(encoding="utf-8"))
                self._memorizing = set(raw_m) if isinstance(raw_m, list) else set()
            except Exception:
                traceback.print_exc()
                self._memorizing = set()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_memorizing(self) -> None:
        self._memorizing_path.parent.mkdir(parents=True, exist_ok=True)
        self._memorizing_path.write_text(
            json.dumps(sorted(self._memorizing), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def has_verse(self, key: str) -> bool:
        """Return True if at least one version is saved for *key*."""
        entry = self._data.get(key)
        return bool(entry and entry.get("versions"))

    def get_verse(self, key: str) -> Optional[dict]:
        """Return the full entry dict or None if not present.

        Returned dict shape::

            {"display": "John 3:16", "versions": [{"version": "NIV", "text": "..."}]}
        """
        return self._data.get(key)

    def get_latest_version(self, key: str) -> Optional[dict]:
        """Return the most recently saved ``{"version": ..., "text": ...}`` or None."""
        entry = self._data.get(key)
        if not entry:
            return None
        versions = entry.get("versions", [])
        return versions[-1] if versions else None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def set_version(
        self, key: str, display: str, version_name: str, text: str
    ) -> None:
        """Upsert a version entry for the verse identified by *key*.

        If a version with the same *version_name* already exists it is updated
        in place (text changed, position preserved in list).  New versions are
        appended so the last item is always the most recently added.
        """
        if key not in self._data:
            self._data[key] = {"display": display, "versions": []}
        else:
            # Preserve the canonical display name (may differ in case).
            self._data[key]["display"] = display

        versions: list[dict] = self._data[key]["versions"]
        for entry in versions:
            if entry.get("version") == version_name:
                entry["text"] = text
                self._save()
                return
        # New version — append so it becomes the latest.
        versions.append({"version": version_name, "text": text})
        self._save()

    def delete_version(self, key: str, version_name: str) -> None:
        """Remove the version with *version_name* from the verse at *key*.

        Removes the top-level key entirely if no versions remain.
        """
        entry = self._data.get(key)
        if not entry:
            return
        entry["versions"] = [v for v in entry["versions"] if v.get("version") != version_name]
        if not entry["versions"]:
            del self._data[key]
        self._save()

    # ------------------------------------------------------------------
    # Memorizing
    # ------------------------------------------------------------------

    def is_memorizing(self, key: str) -> bool:
        """Return True if the verse is marked for memorization."""
        return key in self._memorizing

    def set_memorizing(self, key: str, memorizing: bool) -> None:
        """Set memorize state explicitly and persist."""
        if memorizing:
            self._memorizing.add(key)
        else:
            self._memorizing.discard(key)
        self._save_memorizing()

    def toggle_memorizing(self, key: str) -> bool:
        """Toggle memorize state. Returns new state (True = memorizing)."""
        if key in self._memorizing:
            self._memorizing.discard(key)
            self._save_memorizing()
            return False
        self._memorizing.add(key)
        self._save_memorizing()
        return True

    def get_memorizing_list(self) -> list[str]:
        """Return a sorted list of verse keys marked for memorization."""
        return sorted(self._memorizing)

    def random_verse_text(self) -> str | None:
        """Return a randomly chosen verse as a formatted string, or None if the library is empty."""
        import random

        entries = [v for v in self._data.values() if v.get("versions")]
        if not entries:
            return None
        entry = random.choice(entries)
        versions = entry.get("versions", [])
        text = versions[-1].get("text", "") if versions else ""
        display = entry.get("display", "")
        if not text:
            return None
        return f'"{text}" \u2014 {display}'
