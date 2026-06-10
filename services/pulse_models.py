from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PulseKind(str, Enum):
    MANUAL = "manual"
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class EveningPulseDuration(str, Enum):
    MINUTES_5 = "5m"
    MINUTES_10 = "10m"
    MINUTES_30 = "30m"
    HOUR_1 = "1h"
    HOURS_2 = "2h"


@dataclass(slots=True)
class PulseSliders:
    energy: int = 0
    faith: int = 0
    encouragement: int = 0
    temptation: int = 0

    def __post_init__(self) -> None:
        for value in (
            self.energy,
            self.faith,
            self.encouragement,
            self.temptation,
        ):
            if value < -5 or value > 5:
                raise ValueError("Pulse slider values must be between -5 and 5.")

    def any_negative(self) -> bool:
        return any(value < 0 for _, value in self.items())

    def negative_items(self) -> list[tuple[str, int]]:
        return [(label, value) for label, value in self.items() if value < 0]

    def items(self) -> list[tuple[str, int]]:
        return [
            ("Energy", self.energy),
            ("Faith", self.faith),
            ("Encouragement", self.encouragement),
            ("Temptation", self.temptation),
        ]

    def to_dict(self) -> dict[str, int]:
        return {
            "energy": self.energy,
            "faith": self.faith,
            "encouragement": self.encouragement,
            "temptation": self.temptation,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "PulseSliders":
        raw = raw or {}
        return cls(
            energy=int(raw.get("energy", 0)),
            faith=int(raw.get("faith", 0)),
            encouragement=int(raw.get("encouragement", 0)),
            temptation=int(raw.get("temptation", 0)),
        )


@dataclass(slots=True)
class PulseRecord:
    pulse_id: str
    pulse_kind: PulseKind
    submitted_local_ts: str
    sliders: PulseSliders
    answers: dict[str, Any] = field(default_factory=dict)
    note_text: str = ""
    reach_out_text: str = ""
    reach_out_sent: bool = False
    evening_duration_choice: str | None = None
    prompted_local_ts: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "pulse_kind": self.pulse_kind.value,
            "submitted_local_ts": self.submitted_local_ts,
            "sliders": self.sliders.to_dict(),
            "answers": dict(self.answers),
            "note_text": self.note_text,
            "reach_out_text": self.reach_out_text,
            "reach_out_sent": bool(self.reach_out_sent),
            "evening_duration_choice": self.evening_duration_choice,
            "prompted_local_ts": self.prompted_local_ts,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PulseRecord":
        return cls(
            pulse_id=str(raw.get("pulse_id") or ""),
            pulse_kind=PulseKind(str(raw.get("pulse_kind") or PulseKind.MORNING.value)),
            submitted_local_ts=str(raw.get("submitted_local_ts") or ""),
            sliders=PulseSliders.from_dict(raw.get("sliders") or {}),
            answers=dict(raw.get("answers") or {}),
            note_text=str(raw.get("note_text") or ""),
            reach_out_text=str(raw.get("reach_out_text") or ""),
            reach_out_sent=bool(raw.get("reach_out_sent", False)),
            evening_duration_choice=(
                None
                if raw.get("evening_duration_choice") in (None, "")
                else str(raw.get("evening_duration_choice"))
            ),
            prompted_local_ts=(
                None
                if raw.get("prompted_local_ts") in (None, "")
                else str(raw.get("prompted_local_ts"))
            ),
        )


@dataclass(slots=True)
class PulseDayState:
    day: str
    records: list[PulseRecord] = field(default_factory=list)
    last_prompted_kind: str | None = None
    last_prompted_local_ts: str | None = None
    next_evening_due_local_ts: str | None = None
    last_activity_local_ts: str | None = None

    def has_completed(self, pulse_kind: PulseKind) -> bool:
        if pulse_kind is PulseKind.EVENING:
            return any(record.pulse_kind is PulseKind.EVENING for record in self.records)
        return any(record.pulse_kind is pulse_kind for record in self.records)

    def evening_records(self) -> list[PulseRecord]:
        return [record for record in self.records if record.pulse_kind is PulseKind.EVENING]

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "records": [record.to_dict() for record in self.records],
            "last_prompted_kind": self.last_prompted_kind,
            "last_prompted_local_ts": self.last_prompted_local_ts,
            "next_evening_due_local_ts": self.next_evening_due_local_ts,
            "last_activity_local_ts": self.last_activity_local_ts,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None, *, day: str | None = None) -> "PulseDayState":
        raw = raw or {}
        resolved_day = str(raw.get("day") or day or "")
        return cls(
            day=resolved_day,
            records=[
                PulseRecord.from_dict(item)
                for item in list(raw.get("records") or [])
                if isinstance(item, dict)
            ],
            last_prompted_kind=(
                None if raw.get("last_prompted_kind") in (None, "") else str(raw.get("last_prompted_kind"))
            ),
            last_prompted_local_ts=(
                None if raw.get("last_prompted_local_ts") in (None, "") else str(raw.get("last_prompted_local_ts"))
            ),
            next_evening_due_local_ts=(
                None
                if raw.get("next_evening_due_local_ts") in (None, "")
                else str(raw.get("next_evening_due_local_ts"))
            ),
            last_activity_local_ts=(
                None if raw.get("last_activity_local_ts") in (None, "") else str(raw.get("last_activity_local_ts"))
            ),
        )


@dataclass(slots=True)
class PendingPulse:
    pulse_id: str
    pulse_kind: PulseKind
    day: str
    prompted_local_ts: str
    is_repeat: bool = False