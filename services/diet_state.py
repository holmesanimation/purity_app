"""Persistent per-day diet tracking backed by ``data/diet_state.json``.

Disk layout::

    <data_root>/data/diet_state.json

Schema::

    {"days": {"YYYY-MM-DD": {
        "water_count": int,
        "vitamins_taken": bool
    }}}

Calories are not stored here; see ``calories_today_from_notes``.
"""

from __future__ import annotations

import json
import traceback
from datetime import date, datetime
from pathlib import Path

from shane_common.io.atomic import write_json_atomic
from shane_common.notes.notes_repository import latest_revisions


def _empty_day() -> dict:
    return {"water_count": 0, "vitamins_taken": False}


class DietState:
    """CRUD access to the user's persisted daily diet tracking data."""

    def __init__(self, data_root: Path | str) -> None:
        self._path: Path = Path(data_root) / "data" / "diet_state.json"

    def today_key(self) -> str:
        return date.today().isoformat()

    def _load_all(self) -> dict:
        if not self._path.exists():
            return {"days": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            traceback.print_exc()
            return {"days": {}}
        if not isinstance(raw, dict) or not isinstance(raw.get("days"), dict):
            return {"days": {}}
        return raw

    def _save_all(self, raw: dict) -> None:
        write_json_atomic(self._path, raw)

    def get_today(self) -> dict:
        raw = self._load_all()
        return raw["days"].get(self.today_key(), _empty_day())

    def _update_today(self, mutate) -> dict:
        raw = self._load_all()
        key = self.today_key()
        day = raw["days"].setdefault(key, _empty_day())
        mutate(day)
        self._save_all(raw)
        return day

    def set_water_count(self, count: int) -> None:
        self._update_today(lambda day: day.__setitem__("water_count", max(0, int(count))))

    def set_vitamins_taken(self, taken: bool) -> None:
        self._update_today(lambda day: day.__setitem__("vitamins_taken", bool(taken)))


def calories_today_from_notes(notes_repo, owner: str = "Diet") -> float:
    """Sum today's calories from *owner*'s notes, latest revision per note only."""
    today = date.today()
    total = 0.0
    for row in latest_revisions(notes_repo.rows_for_owner(owner)):
        if row.wall_ts is None or datetime.fromtimestamp(row.wall_ts).date() != today:
            continue
        calories = (row.context or {}).get("calories")
        if isinstance(calories, (int, float)) and not isinstance(calories, bool):
            total += float(calories)
    return total
