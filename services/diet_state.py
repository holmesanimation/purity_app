"""Persistent per-day diet tracking backed by ``data/diet_state.json``.

Disk layout::

    <data_root>/data/diet_state.json

Schema::

    {"days": {"YYYY-MM-DD": {
        "water_count": int,
        "vitamins_taken": bool,
        "calorie_entries": [
            {"entry_id": str, "note_id": str, "text": str,
             "calories": float | null, "status": "pending"|"done"|"failed",
             "created_ts": float}
        ]
    }}}
"""

from __future__ import annotations

import json
import time
import traceback
import uuid
from datetime import date
from pathlib import Path

from shane_common.io.atomic import write_json_atomic


def _empty_day() -> dict:
    return {"water_count": 0, "vitamins_taken": False, "calorie_entries": []}


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

    def add_calorie_entry(self, text: str, note_id: str = "") -> str:
        entry_id = uuid.uuid4().hex
        entry = {
            "entry_id": entry_id,
            "note_id": note_id,
            "text": text,
            "calories": None,
            "status": "pending",
            "created_ts": time.time(),
        }
        self._update_today(lambda day: day["calorie_entries"].append(entry))
        return entry_id

    def resolve_calorie_entry(self, entry_id: str, calories: float) -> None:
        def _mutate(day: dict) -> None:
            for entry in day["calorie_entries"]:
                if entry["entry_id"] == entry_id:
                    entry["calories"] = float(calories)
                    entry["status"] = "done"
                    break

        self._update_today(_mutate)

    def fail_calorie_entry(self, entry_id: str) -> None:
        def _mutate(day: dict) -> None:
            for entry in day["calorie_entries"]:
                if entry["entry_id"] == entry_id:
                    entry["status"] = "failed"
                    break

        self._update_today(_mutate)

    def total_calories_today(self) -> float:
        day = self.get_today()
        return sum(
            float(entry["calories"])
            for entry in day["calorie_entries"]
            if entry["status"] == "done" and entry["calories"] is not None
        )

    def has_failed_entries_today(self) -> bool:
        day = self.get_today()
        return any(entry["status"] == "failed" for entry in day["calorie_entries"])

    def pending_or_failed_entries_today(self) -> list[dict]:
        day = self.get_today()
        return [entry for entry in day["calorie_entries"] if entry["status"] in ("pending", "failed")]
