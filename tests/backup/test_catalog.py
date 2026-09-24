from __future__ import annotations

from pathlib import Path

from services.backup.catalog import PurityBackupCatalog
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

    notes_dir = purity_app_root / "notes" / "PurityApp" / "default"
    notes_dir.mkdir(parents=True)
    (notes_dir / "purity.jsonl").write_text("{}", encoding="utf-8")
    (notes_dir / "journal.jsonl").write_text("{}", encoding="utf-8")

    (purity_app_root / "data").mkdir(parents=True)
    (purity_app_root / "data" / "tags.json").write_text("{}", encoding="utf-8")

    data_root.mkdir(parents=True)
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

    assert len(families["notes"].paths) == 2
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
