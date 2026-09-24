from __future__ import annotations

from pathlib import Path

from services.backup.destinations.local import LocalFilesystemDestination
from services.backup.restore import load_restore_state, restore_backup
from services.backup.state import save_manifest


def _seed_destination_and_manifest(tmp_path: Path) -> tuple[Path, Path]:
    """Populates a destination_root the way LocalFilesystemDestination.refresh_or_copy would,
    and a data_root with a matching local_manifest.json, using real source files."""
    data_root = tmp_path / "data_root"
    data_root.mkdir()
    destination_root = tmp_path / "dest"

    source_bible = tmp_path / "bible_library.json"
    source_bible.write_text('{"books": ["Genesis"]}', encoding="utf-8")
    source_notes = tmp_path / "purity.jsonl"
    source_notes.write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")
    source_reminders = tmp_path / "reminders.yaml"
    source_reminders.write_text("enabled: true\n", encoding="utf-8")

    destination = LocalFilesystemDestination(destination_root)
    manifest: dict = {}
    for family_name, source in (
        ("bible_library", source_bible),
        ("notes", source_notes),
        ("reminders_override", source_reminders),
    ):
        result = destination.refresh_or_copy(family_name, source, manifest)
        manifest[destination.manifest_key(family_name, source)] = result.manifest_entry

    save_manifest(data_root, manifest)
    return data_root, destination_root


def test_restore_verifies_hashes_and_content(tmp_path: Path) -> None:
    data_root, destination_root = _seed_destination_and_manifest(tmp_path)
    verification_root = tmp_path / "verify"

    result = restore_backup(destination_root, verification_root, data_root)

    assert result.status == "success"
    family_names = {fr.family_name for fr in result.family_results}
    assert family_names == {"bible_library", "notes", "reminders_override"}
    for fr in result.family_results:
        assert fr.files_failed == 0
        assert fr.files_verified >= 1
        assert fr.content_check_passed
        assert fr.content_check_error is None

    assert (verification_root / "bible_library" / "bible_library.json").read_text(
        encoding="utf-8"
    ) == '{"books": ["Genesis"]}'
    assert (verification_root / "notes" / "purity.jsonl").exists()

    history = load_restore_state(data_root)
    assert len(history) == 1
    assert history[0]["run_id"] == result.run_id
    assert history[0]["status"] == "success"


def test_restore_detects_tampered_destination(tmp_path: Path) -> None:
    data_root, destination_root = _seed_destination_and_manifest(tmp_path)
    verification_root = tmp_path / "verify"

    (destination_root / "bible_library" / "bible_library.json").write_text(
        '{"books": ["tampered"]}', encoding="utf-8"
    )

    result = restore_backup(destination_root, verification_root, data_root)

    assert result.status == "partial"
    bible_result = next(fr for fr in result.family_results if fr.family_name == "bible_library")
    assert bible_result.files_failed == 1
    assert bible_result.errors


def test_restore_missing_destination_is_failed(tmp_path: Path) -> None:
    data_root = tmp_path / "data_root"
    data_root.mkdir()
    save_manifest(data_root, {})

    result = restore_backup(tmp_path / "no_such_dest", tmp_path / "verify", data_root)

    assert result.status == "failed"
    assert result.family_results == []
