from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Goal:
    id: str
    title: str
    why: str
    daily_actions: list[str] = field(default_factory=list)
    completed_today: bool = False
