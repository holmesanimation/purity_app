"""Loads user-editable panic reminders from YAML.

Resolution order:
  1. ``<data_root>/reminders.yaml``     — user-managed; takes priority
  2. ``<repo_root>/data/reminders.yaml`` — bundled default shipped with the app

If neither path exists (or YAML cannot be parsed), ``get_random()`` returns
``None`` and the reminder banner in the panic dialog is silently hidden.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional, TypedDict

import yaml


class Reminder(TypedDict, total=False):
    """One entry from reminders.yaml."""

    title: str       # bold headline — identity/calling statement
    note: str        # regular-weight supporting affirmation
    verse_ref: str   # scripture reference (bold in dialog)
    verse_text: str  # full scripture quote (italic in dialog)
    subject: str     # optional reason ID (e.g. "tired") or "general"
    background: str  # optional filename from the image library (e.g. "forest.jpg")


# Bundled default lives alongside the rest of the app's static data.
_BUNDLED_DEFAULT = Path(__file__).parent.parent / "data" / "reminders.yaml"


class PanicReminders:
    """Loads and randomly selects a reminder to display in the panic dialog."""

    def __init__(self, data_root: Path) -> None:
        self._user_path = Path(data_root) / "reminders.yaml"
        self._reminders: list[Reminder] = []
        self._load()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Try user path first, then bundled default."""
        for path in (self._user_path, _BUNDLED_DEFAULT):
            if not path.exists():
                continue
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                items = (raw or {}).get("reminders", [])
                if items:
                    self._reminders = [dict(r) for r in items]  # type: ignore[misc]
                    return
            except Exception:
                continue  # corrupt file — try the next path

    def _save(self) -> None:
        """Persist ``self._reminders`` to the user-managed path."""
        self._user_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"reminders": [dict(r) for r in self._reminders]}
        self._user_path.write_text(
            yaml.dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_random(self) -> Optional[Reminder]:
        """Return a randomly chosen reminder, or ``None`` if none are loaded."""
        if not self._reminders:
            return None
        return random.choice(self._reminders)  # type: ignore[return-value]

    def get_all(self) -> list[Reminder]:
        """Return a copy of all loaded reminders."""
        return list(self._reminders)

    def add(self, reminder: Reminder) -> None:
        """Append *reminder* and persist to disk."""
        self._reminders.append(dict(reminder))  # type: ignore[arg-type]
        self._save()

    def update(self, index: int, reminder: Reminder) -> None:
        """Replace the reminder at *index* and persist to disk."""
        self._reminders[index] = dict(reminder)  # type: ignore[assignment]
        self._save()

    def delete(self, index: int) -> None:
        """Remove the reminder at *index* and persist to disk."""
        del self._reminders[index]
        self._save()
