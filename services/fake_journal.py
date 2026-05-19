import uuid
from datetime import datetime, timedelta
from models.journal import JournalEntry


class FakeJournalService:
    def __init__(self):
        now = datetime.now()
        self._entries: list[JournalEntry] = [
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now - timedelta(days=6),
                entry_type="guided_checkin",
                responses=[
                    "Feeling grateful and focused.",
                    "A moment of distraction mid-afternoon.",
                    "Scripture reading, walked the dog.",
                ],
            ),
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now - timedelta(days=5),
                entry_type="free_journal",
                free_text="Lord, thank You for another day. I want to walk closer with You.",
            ),
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now - timedelta(days=4),
                entry_type="guided_checkin",
                responses=[
                    "Tired but thankful.",
                    "Felt some anxiety in the morning.",
                    "Called a friend, listened to worship music.",
                ],
            ),
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now - timedelta(days=3),
                entry_type="free_journal",
                free_text="Struggled today but held on. His mercies are new every morning.",
            ),
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now - timedelta(days=2),
                entry_type="guided_checkin",
                responses=[
                    "Good energy and clarity.",
                    "None — clean day.",
                    "Workout, Bible study, quality family time.",
                ],
            ),
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now - timedelta(days=1),
                entry_type="free_journal",
                free_text="Grateful for the streak. Asking for strength to keep going.",
            ),
        ]

    def append(self, entry: JournalEntry):
        self._entries.append(entry)

    def get_all(self) -> list[JournalEntry]:
        return sorted(self._entries, key=lambda e: e.timestamp, reverse=True)
