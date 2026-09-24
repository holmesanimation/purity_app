"""Persistent purity-streak day counter."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from shane_common.io.atomic import write_json_atomic


def streak_path(data_root: Path) -> Path:
    return Path(data_root) / "data" / "streak.json"


class PurityStreak:
    """Tracks days elapsed since the last reset, persisted to disk."""

    def __init__(self, data_root: Path) -> None:
        self._path = streak_path(Path(data_root))

    def get_days(self) -> int:
        start = self._load_start_date()
        if start is None:
            start = date.today()
            self._save_start_date(start)
        return (date.today() - start).days

    def reset(self) -> None:
        self._save_start_date(date.today())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_start_date(self) -> date | None:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return date.fromisoformat(raw["start_date"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return None

    def _save_start_date(self, start: date) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self._path, {"start_date": start.isoformat()})
