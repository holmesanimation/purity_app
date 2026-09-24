"""Persistent prayer recipient list backed by ``data/prayer_recipients.json``.

Disk layout::

    <data_root>/data/prayer_recipients.json

Schema::

    {"recipients": [{"id": "...", "name": "..."}, ...]}
"""

from __future__ import annotations

import json
import traceback
import uuid
from pathlib import Path

from shane_common.io.atomic import write_json_atomic

from models.prayer import PrayerPerson


class PrayerRecipientLibrary:
    """CRUD access to the user's persisted prayer recipient list."""

    def __init__(self, data_root: Path | str) -> None:
        self._path: Path = Path(data_root) / "data" / "prayer_recipients.json"
        self._prayed_path: Path = Path(data_root) / "data" / "prayer_prayed.json"

    def load(self) -> list[PrayerPerson]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            traceback.print_exc()
            return []
        recipients = raw.get("recipients", []) if isinstance(raw, dict) else []
        return [
            PrayerPerson(id=str(item.get("id")), name=str(item.get("name")))
            for item in recipients
            if isinstance(item, dict) and item.get("id") and item.get("name")
        ]

    def add(self, name: str) -> PrayerPerson | None:
        name = name.strip()
        if not name:
            return None
        recipients = self.load()
        recipient = PrayerPerson(id=uuid.uuid4().hex, name=name)
        recipients.append(recipient)
        self._save(recipients)
        return recipient

    def rename(self, recipient_id: str, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            return
        recipients = self.load()
        for recipient in recipients:
            if recipient.id == recipient_id:
                recipient.name = new_name
                break
        self._save(recipients)

    def delete(self, recipient_id: str) -> None:
        recipients = [r for r in self.load() if r.id != recipient_id]
        self._save(recipients)

    def _save(self, recipients: list[PrayerPerson]) -> None:
        write_json_atomic(
            self._path,
            {"recipients": [{"id": r.id, "name": r.name} for r in recipients]},
        )

    # -- prayed-for tracking -------------------------------------------------

    def _load_prayed_names(self) -> set[str]:
        if not self._prayed_path.exists():
            return set()
        try:
            raw = json.loads(self._prayed_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            traceback.print_exc()
            return set()
        names = raw.get("prayed_names", []) if isinstance(raw, dict) else []
        return {str(n) for n in names if isinstance(n, str)}

    def _save_prayed_names(self, prayed_names: set[str]) -> None:
        write_json_atomic(self._prayed_path, {"prayed_names": sorted(prayed_names)})

    def mark_prayed(self, name: str) -> None:
        """Record ``name`` as prayed-for in the current rotation cycle."""
        prayed = self._load_prayed_names()
        prayed.add(name)
        self._save_prayed_names(prayed)

    def get_prayed_names(self) -> set[str]:
        """Names already prayed-for in the current rotation cycle."""
        return self._load_prayed_names()

    def get_available_names(self) -> list[str]:
        """Names not yet prayed-for this cycle; resets the cycle once exhausted."""
        names = [r.name for r in self.load()]
        prayed = self._load_prayed_names()
        available = [n for n in names if n not in prayed]
        if not available and names:
            self._save_prayed_names(set())
            available = names
        return available
