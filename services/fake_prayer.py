import random
from models.prayer import PrayerPerson


_PRAYER_POOL_SOURCE = [
    PrayerPerson(id="p1",  name="Mom",           notes="Health and peace of mind"),
    PrayerPerson(id="p2",  name="Dad",            notes="Strength and guidance"),
    PrayerPerson(id="p3",  name="Sarah",          notes="Wisdom in her new job"),
    PrayerPerson(id="p4",  name="Pastor James",   notes="Sermon preparation"),
    PrayerPerson(id="p5",  name="Uncle Mike",     notes="Recovery and faith"),
    PrayerPerson(id="p6",  name="Jake",           notes="Salvation"),
    PrayerPerson(id="p7",  name="Emily",          notes="Marriage and family"),
    PrayerPerson(id="p8",  name="The Hendersons", notes="Financial provision"),
    PrayerPerson(id="p9",  name="Brother Chris",  notes="Spiritual growth"),
    PrayerPerson(id="p10", name="Neighbor Diane", notes="Healing from illness"),
]


class FakePrayerService:
    def __init__(self):
        self._total = len(_PRAYER_POOL_SOURCE)
        self._pool: list[PrayerPerson] = []
        self._prayed_count = 0
        self._refill()

    def _refill(self):
        self._pool = list(_PRAYER_POOL_SOURCE)
        random.shuffle(self._pool)
        self._prayed_count = 0

    def current(self) -> PrayerPerson:
        return self._pool[0] if self._pool else _PRAYER_POOL_SOURCE[0]

    def mark_prayed(self):
        if self._pool:
            self._pool.pop(0)
            self._prayed_count += 1
        if not self._pool:
            self._refill()

    def skip(self):
        if len(self._pool) > 1:
            person = self._pool.pop(0)
            self._pool.append(person)

    def progress(self) -> tuple[int, int]:
        return (self._prayed_count, self._total)
