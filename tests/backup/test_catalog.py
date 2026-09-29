from __future__ import annotations

from pathlib import Path

from services.backup.catalog import PurityBackupCatalog
from services.backup.snapshot import staging_dir
from services.notes_paths import notes_db_path
from services.settings_schemas import build_purity_settings_manager


def _manager(tmp_path: Path, data_root: Path):
    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    manager.set("app.general", "data_root", str(data_root))
    return manager


def _family_map(families):
    return {f.name: f for f in families}


def test_discover_resolves_expected_families(tmp_path: Path) -> None:
    data_root = tmp_path / "data_root"
    purity_app_root = tmp_path / "purity_app"
    manager = _manager(tmp_path, data_root)

    staging = staging_dir(data_root)
    staging.mkdir(parents=True)
    (staging / "notes-20260929T101500Z.db").write_bytes(b"old")
    (staging / "notes-20260929T101600Z.db").write_bytes(b"new")
    (staging / "notes-export-20260929.jsonl").write_text("{}", encoding="utf-8")

    (purity_app_root / "data").mkdir(parents=True)
    (purity_app_root / "data" / "tags.json").write_text("{}", encoding="utf-8")

    (data_root / "bible_library.json").write_text("{}", encoding="utf-8")
    (data_root / "bible_memorizing.json").write_text("[]", encoding="utf-8")
    (data_root / "data").mkdir(parents=True)
    (data_root / "data" / "prayer_recipients.json").write_text("{}", encoding="utf-8")
    (data_root / "data" / "prayer_prayed.json").write_text("{}", encoding="utf-8")

    catalog = PurityBackupCatalog(
        settings_manager=manager,
        purity_app_root=purity_app_root,
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )

    families = _family_map(catalog.discover())

    assert "notes" not in families and "notes_registry" not in families  # replaced by notes_db
    assert families["notes_db"].paths == (staging / "notes-20260929T101600Z.db",)  # newest snapshot only
    assert families["notes_db"].required is True
    assert families["notes_export"].paths == (staging / "notes-export-20260929.jsonl",)
    assert families["notes_export"].required is False
    assert families["bible_library"].paths == (data_root / "bible_library.json",)
    assert families["bible_memorizing"].paths == (data_root / "bible_memorizing.json",)
    assert families["prayer_recipients"].paths == (
        data_root / "data" / "prayer_recipients.json",
    )
    assert families["prayer_prayed"].paths == (data_root / "data" / "prayer_prayed.json",)
    assert families["tag_library"].paths == (purity_app_root / "data" / "tags.json",)
    assert families["reminders_override"].paths == ()
    assert families["reminders_override"].required is False
    assert families["user_preferences"].paths == ()
    assert families["user_preferences"].required is False


def test_discover_notes_db_family_is_empty_until_a_snapshot_is_staged(tmp_path: Path) -> None:
    data_root = tmp_path / "data_root"
    data_root.mkdir(parents=True)
    catalog = PurityBackupCatalog(
        settings_manager=_manager(tmp_path, data_root),
        purity_app_root=tmp_path / "purity_app",
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )

    assert _family_map(catalog.discover())["notes_db"].paths == ()

    snapshot = staging_dir(data_root) / "notes-20260929T101500Z.db"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"x")
    assert _family_map(catalog.discover())["notes_db"].paths == (snapshot,)


def test_catalog_never_points_at_the_live_database(tmp_path: Path) -> None:
    data_root = tmp_path / "data_root"
    live = notes_db_path(data_root)
    live.parent.mkdir(parents=True)
    for name in (live.name, live.name + "-wal", live.name + "-shm"):
        (live.parent / name).write_bytes(b"live")
    catalog = PurityBackupCatalog(
        settings_manager=_manager(tmp_path, data_root),
        purity_app_root=tmp_path / "purity_app",
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )

    for family in catalog.discover():
        assert not any(p.parent == live.parent and p.name.startswith("notes.db") for p in family.paths)


def test_notes_db_path_matches_app_location() -> None:
    """The backup and the app must agree on where the live database lives."""
    from services.notes_setup import DATA_ROOT, NOTES_DB_PATH

    assert NOTES_DB_PATH == notes_db_path(DATA_ROOT)
    assert NOTES_DB_PATH.name == "notes.db" and NOTES_DB_PATH.parent.name == "data"

def test_discover_includes_reminders_override_only_if_present(tmp_path: Path) -> None:
    data_root = tmp_path / "data_root"
    data_root.mkdir(parents=True)
    manager = _manager(tmp_path, data_root)

    catalog = PurityBackupCatalog(
        settings_manager=manager,
        purity_app_root=tmp_path / "purity_app",
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )

    families = _family_map(catalog.discover())
    assert families["reminders_override"].paths == ()

    (data_root / "reminders.yaml").write_text("reminders: []", encoding="utf-8")

    families = _family_map(catalog.discover())
    assert families["reminders_override"].paths == (data_root / "reminders.yaml",)


def test_discover_includes_user_preferences_when_present(tmp_path: Path) -> None:
    data_root = tmp_path / "data_root"
    data_root.mkdir(parents=True)
    manager = _manager(tmp_path, data_root)

    prefs_path = tmp_path / "settings.yaml"
    manager.save()
    assert prefs_path.exists()
    catalog = PurityBackupCatalog(
        settings_manager=manager,
        purity_app_root=tmp_path / "purity_app",
        user_preferences_path=prefs_path,
    )

    families = _family_map(catalog.discover())
    assert families["user_preferences"].paths == (prefs_path,)


def test_discover_reresolves_data_root_on_each_call(tmp_path: Path) -> None:
    manager = _manager(tmp_path, tmp_path / "data_root_1")
    catalog = PurityBackupCatalog(
        settings_manager=manager,
        purity_app_root=tmp_path / "purity_app",
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )

    assert catalog.resolve_data_root() == tmp_path / "data_root_1"

    manager.set("app.general", "data_root", str(tmp_path / "data_root_2"))
    assert catalog.resolve_data_root() == tmp_path / "data_root_2"
