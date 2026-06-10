from __future__ import annotations

from pathlib import Path

from shane_common.config.json_config import JsonConfigStore

from services.pulse_models import PulseDayState, PulseRecord


class PulseStore:
    def __init__(self, data_root: str | Path) -> None:
        self._data_root = Path(data_root)
        self._root = self._data_root / "_system" / "purity" / "pulse"

    @property
    def root(self) -> Path:
        return self._root

    def path_for_day(self, day: str) -> Path:
        return self._root / "days" / f"{day}.json"

    def load_day(self, day: str) -> PulseDayState:
        store = self._json_store(day)
        return store.load()

    def save_day(self, state: PulseDayState) -> PulseDayState:
        store = self._json_store(state.day)
        return store.save(state)

    def append_record(self, day: str, record: PulseRecord) -> PulseDayState:
        state = self.load_day(day)
        state.records.append(record)
        return self.save_day(state)

    def update_prompt_state(
        self,
        day: str,
        *,
        pulse_kind: str | None = None,
        prompted_local_ts: str | None = None,
        next_evening_due_local_ts: str | None = None,
        last_activity_local_ts: str | None = None,
    ) -> PulseDayState:
        state = self.load_day(day)
        if pulse_kind is not None:
            state.last_prompted_kind = pulse_kind
        if prompted_local_ts is not None:
            state.last_prompted_local_ts = prompted_local_ts
        if next_evening_due_local_ts is not None:
            state.next_evening_due_local_ts = next_evening_due_local_ts
        if last_activity_local_ts is not None:
            state.last_activity_local_ts = last_activity_local_ts
        return self.save_day(state)

    def _json_store(self, day: str) -> JsonConfigStore:
        return JsonConfigStore(
            path=self.path_for_day(day),
            default_factory=lambda: PulseDayState(day=day),
            normalize=lambda raw: self._normalize_day_state(day, raw),
            to_json_ready=lambda state: state.to_dict(),
        )

    @staticmethod
    def _normalize_day_state(day: str, raw: object) -> PulseDayState:
        if isinstance(raw, PulseDayState):
            return raw
        if isinstance(raw, dict):
            return PulseDayState.from_dict(raw, day=day)
        return PulseDayState(day=day)