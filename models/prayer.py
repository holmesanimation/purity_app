from dataclasses import dataclass
from typing import Optional


@dataclass
class PrayerPerson:
    id: str
    name: str
    notes: Optional[str] = None
