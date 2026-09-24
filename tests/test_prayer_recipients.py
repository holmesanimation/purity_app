from __future__ import annotations

from services.prayer_recipients import PrayerRecipientLibrary


def test_add_load_rename_delete_round_trip(tmp_path) -> None:
    library = PrayerRecipientLibrary(tmp_path)

    assert library.load() == []

    mom = library.add("Mom")
    assert mom is not None
    assert [r.name for r in library.load()] == ["Mom"]

    library.rename(mom.id, "Mother")
    assert [r.name for r in library.load()] == ["Mother"]

    library.delete(mom.id)
    assert library.load() == []


def test_add_ignores_blank_name(tmp_path) -> None:
    library = PrayerRecipientLibrary(tmp_path)
    assert library.add("   ") is None
    assert library.load() == []
