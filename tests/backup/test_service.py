from __future__ import annotations

import string
from pathlib import Path

from services.backup.models import RunStatus
from services.backup.service import BackupService
from services.backup.state import load_state
from services.settings_schemas import build_purity_settings_manager


def _build_source_tree(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data_root"
    purity_app_root = tmp_path / "purity_app"

    notes_dir = purity_app_root / "notes" / "PurityApp" / "default"
    notes_dir.mkdir(parents=True)
    (notes_dir / "purity.jsonl").write_text('{"a": 1}', encoding="utf-8")

    (purity_app_root / "data").mkdir(parents=True)
    (purity_app_root / "data" / "tags.json").write_text('{"tags": ["x"]}', encoding="utf-8")

    data_root.mkdir(parents=True)
    (data_root / "bible_library.json").write_text('{"b": 1}', encoding="utf-8")
    (data_root / "data").mkdir(parents=True)
    (data_root / "data" / "prayer_recipients.json").write_text("{}", encoding="utf-8")
    (data_root / "data" / "prayer_prayed.json").write_text("{}", encoding="utf-8")

    return data_root, purity_app_root


def _service(tmp_path: Path, data_root: Path, purity_app_root: Path) -> BackupService:
    from services.backup.catalog import PurityBackupCatalog

    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    manager.set("app.general", "data_root", str(data_root))
    catalog = PurityBackupCatalog(
        settings_manager=manager,
        purity_app_root=purity_app_root,
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )
    return BackupService(settings_manager=manager, catalog=catalog)


def test_run_copies_and_verifies_all_families(tmp_path: Path) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    destination_root = tmp_path / "dest"
    service = _service(tmp_path, data_root, purity_app_root)

    result = service.run(destination_root)

    assert result.status == RunStatus.SUCCESS
    assert result.failed_count == 0
    assert result.verified_count == result.file_count
    assert result.file_count > 0
    assert (destination_root / "bible_library" / "bible_library.json").read_text(
        encoding="utf-8"
    ) == '{"b": 1}'
    assert (destination_root / "notes" / "purity.jsonl").exists()
    assert (destination_root / "tag_library" / "tags.json").exists()

    history = load_state(data_root)
    assert len(history) == 1
    assert history[0].run_id == result.run_id


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    destination_root = tmp_path / "dest"
    service = _service(tmp_path, data_root, purity_app_root)

    first = service.run(destination_root)
    second = service.run(destination_root)

    assert first.status == RunStatus.SUCCESS
    assert second.status == RunStatus.SUCCESS
    assert second.failed_count == 0
    assert second.bytes_copied == 0  # nothing new to copy, all already-present-identical

    history = load_state(data_root)
    assert len(history) == 2


def test_destination_conflict_surfaces_as_failure(tmp_path: Path) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    destination_root = tmp_path / "dest"
    conflicting_file = destination_root / "bible_library" / "bible_library.json"
    conflicting_file.parent.mkdir(parents=True)
    conflicting_file.write_text('{"different": true}', encoding="utf-8")

    service = _service(tmp_path, data_root, purity_app_root)
    result = service.run(destination_root)

    assert result.failed_count >= 1
    bible_family = next(fr for fr in result.family_results if fr.family_name == "bible_library")
    assert bible_family.files_failed == 1
    assert "destination_conflict" in bible_family.errors[0]


def test_missing_destination_drive_fails_visibly(tmp_path: Path) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    service = _service(tmp_path, data_root, purity_app_root)

    used_drives = {f"{d}:\\" for d in string.ascii_uppercase}
    unavailable = next(d for d in used_drives if not Path(d).exists())

    result = service.run(Path(unavailable) / "purity_backup")

    assert result.status == RunStatus.FAILED
    assert result.file_count == 0
    assert "not available" in (result.last_error or "")

    history = load_state(data_root)
    assert len(history) == 1
    assert history[0].status == RunStatus.FAILED


def test_recursive_self_backup_is_prevented(tmp_path: Path) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    service = _service(tmp_path, data_root, purity_app_root)

    result = service.run(data_root / "backup_subdir")

    assert result.status == RunStatus.FAILED
    assert "recursive self-backup" in (result.last_error or "")


def test_legitimate_source_change_refreshes_known_good_destination(tmp_path: Path) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    destination_root = tmp_path / "dest"
    tag_library_source = purity_app_root / "data" / "tags.json"
    service = _service(tmp_path, data_root, purity_app_root)

    first = service.run(destination_root)
    assert first.status == RunStatus.SUCCESS

    tag_library_source.write_text('{"tags": ["x", "y"]}', encoding="utf-8")
    second = service.run(destination_root)

    assert second.status == RunStatus.SUCCESS
    assert second.failed_count == 0
    tag_family = next(fr for fr in second.family_results if fr.family_name == "tag_library")
    assert tag_family.files_failed == 0
    assert tag_family.files_verified == 1

    dest_path = destination_root / "tag_library" / "tags.json"
    assert dest_path.read_text(encoding="utf-8") == '{"tags": ["x", "y"]}'

    third = service.run(destination_root)
    assert third.status == RunStatus.SUCCESS
    assert third.bytes_copied == 0  # back to idempotent after the refresh


def test_manifest_updates_to_new_verified_hash_after_refresh(tmp_path: Path) -> None:
    from services.backup.state import load_manifest

    data_root, purity_app_root = _build_source_tree(tmp_path)
    destination_root = tmp_path / "dest"
    tag_library_source = purity_app_root / "data" / "tags.json"
    service = _service(tmp_path, data_root, purity_app_root)

    service.run(destination_root)
    tag_library_source.write_text('{"tags": ["x", "y"]}', encoding="utf-8")
    service.run(destination_root)

    from shane_common.runtime.transfer.hashing import sha256_file

    manifest = load_manifest(data_root)
    entry = manifest["tag_library/tags.json"]
    assert entry.content_hash == sha256_file(tag_library_source)


def test_independent_destination_modification_is_conflict_not_overwritten(tmp_path: Path) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    destination_root = tmp_path / "dest"
    tag_library_source = purity_app_root / "data" / "tags.json"
    service = _service(tmp_path, data_root, purity_app_root)

    service.run(destination_root)

    # Someone/something edits the destination copy directly (not through backup).
    dest_path = destination_root / "tag_library" / "tags.json"
    dest_path.write_text('{"tags": ["tampered"]}', encoding="utf-8")

    tag_library_source.write_text('{"tags": ["x", "y"]}', encoding="utf-8")
    result = service.run(destination_root)

    tag_family = next(fr for fr in result.family_results if fr.family_name == "tag_library")
    assert tag_family.files_failed == 1
    assert "destination_conflict" in tag_family.errors[0]
    # destination left untouched — still the tampered content, not source, not refreshed
    assert dest_path.read_text(encoding="utf-8") == '{"tags": ["tampered"]}'


def test_failed_refresh_leaves_previous_verified_destination_intact(tmp_path: Path, monkeypatch) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    destination_root = tmp_path / "dest"
    tag_library_source = purity_app_root / "data" / "tags.json"
    service = _service(tmp_path, data_root, purity_app_root)

    service.run(destination_root)
    dest_path = destination_root / "tag_library" / "tags.json"
    original_dest_content = dest_path.read_text(encoding="utf-8")

    tag_library_source.write_text('{"tags": ["x", "y"]}', encoding="utf-8")

    import services.backup.destinations.local as local_module

    def _boom(*args, **kwargs):
        raise OSError("simulated disk failure during refresh")

    monkeypatch.setattr(local_module.shutil, "copyfile", _boom)

    result = service.run(destination_root)

    tag_family = next(fr for fr in result.family_results if fr.family_name == "tag_library")
    assert tag_family.files_failed == 1
    assert dest_path.read_text(encoding="utf-8") == original_dest_content


def test_copy_only_invariant_source_untouched_across_refresh(tmp_path: Path) -> None:
    data_root, purity_app_root = _build_source_tree(tmp_path)
    destination_root = tmp_path / "dest"
    tag_library_source = purity_app_root / "data" / "tags.json"
    service = _service(tmp_path, data_root, purity_app_root)

    service.run(destination_root)
    tag_library_source.write_text('{"tags": ["x", "y"]}', encoding="utf-8")
    before_refresh = tag_library_source.read_text(encoding="utf-8")

    service.run(destination_root)

    assert tag_library_source.read_text(encoding="utf-8") == before_refresh
