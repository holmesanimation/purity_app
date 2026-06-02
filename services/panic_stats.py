"""Lightweight panic reason aggregate store.

Persists reason_id → {count, last_seen_ts} to disk.
Never stores reflection text.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from shane_common.io.atomic import write_json_atomic


class PanicStats:
    """
    Tracks how often each reason_id has been selected across panic sessions.

    Schema on disk::

        {
          "reason_id": {"count": int, "last_seen_ts": float},
          ...
        }

    Reflection text is never written here.
    """

    def __init__(self, data_root: Path) -> None:
        self._path: Path = Path(data_root) / "data" / "panic" / "reason_counts.json"
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        write_json_atomic(self._path, self._data)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_reasons(self, reason_ids: list[str]) -> None:
        """Increment counts for each *reason_id* and update last_seen_ts."""
        now = time.time()
        for reason_id in reason_ids:
            entry = self._data.get(reason_id)
            if entry is None:
                self._data[reason_id] = {"count": 1, "last_seen_ts": now}
            else:
                entry["count"] = int(entry.get("count", 0)) + 1
                entry["last_seen_ts"] = now
        self._save()

    def get_top_reasons(self, n: int) -> list[str]:
        """Return up to *n* reason_ids sorted by count descending."""
        sorted_ids = sorted(
            self._data.keys(),
            key=lambda rid: int(self._data[rid].get("count", 0)),
            reverse=True,
        )
        return sorted_ids[:n]

    def get_count(self, reason_id: str) -> int:
        """Return the count for *reason_id*, or 0 if not present."""
        return int((self._data.get(reason_id) or {}).get("count", 0))
