from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class JournalEntry:
    id: str
    timestamp: datetime
    entry_type: str  # "guided_checkin" | "free_journal"
    responses: list[str] = field(default_factory=list)
    free_text: Optional[str] = None
