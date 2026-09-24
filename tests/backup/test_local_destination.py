from __future__ import annotations

from pathlib import Path

from services.backup.destinations.local import LocalFilesystemDestination
from services.backup.models import BackupCopyOutcome, ManifestEntry
from shane_common.runtime.transfer.hashing import sha256_file


def test_first_copy_is_new_file(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"a": 1}', encoding="utf-8")
    destination = LocalFilesystemDestination(tmp_path / "dest")

    result = destination.refresh_or_copy("fam", source, manifest={})

    assert result.outcome == BackupCopyOutcome.COPIED
    assert result.manifest_entry is not None
    assert result.manifest_entry.content_hash == sha256_file(source)
    assert (tmp_path / "dest" / "fam" / "source.json").read_text(encoding="utf-8") == '{"a": 1}'


def test_unchanged_rerun_is_already_present_identical_zero_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"a": 1}', encoding="utf-8")
    destination = LocalFilesystemDestination(tmp_path / "dest")

    first = destination.refresh_or_copy("fam", source, manifest={})
    manifest = {"fam/source.json": first.manifest_entry}

    second = destination.refresh_or_copy("fam", source, manifest=manifest)

    assert second.outcome == BackupCopyOutcome.ALREADY_PRESENT_IDENTICAL
    assert second.bytes_copied == 0


def test_legitimate_change_refreshes_when_manifest_matches_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"a": 1}', encoding="utf-8")
    destination = LocalFilesystemDestination(tmp_path / "dest")

    first = destination.refresh_or_copy("fam", source, manifest={})
    manifest = {"fam/source.json": first.manifest_entry}

    source.write_text('{"a": 2}', encoding="utf-8")
    second = destination.refresh_or_copy("fam", source, manifest=manifest)

    assert second.outcome == BackupCopyOutcome.REFRESHED
    assert second.manifest_entry.content_hash == sha256_file(source)
    assert (tmp_path / "dest" / "fam" / "source.json").read_text(encoding="utf-8") == '{"a": 2}'


def test_destination_modified_outside_manifest_is_conflict(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"a": 1}', encoding="utf-8")
    destination = LocalFilesystemDestination(tmp_path / "dest")

    first = destination.refresh_or_copy("fam", source, manifest={})
    manifest = {"fam/source.json": first.manifest_entry}

    # Destination tampered with directly, bypassing backup.
    (tmp_path / "dest" / "fam" / "source.json").write_text('{"tampered": true}', encoding="utf-8")
    source.write_text('{"a": 2}', encoding="utf-8")

    result = destination.refresh_or_copy("fam", source, manifest=manifest)

    assert result.outcome == BackupCopyOutcome.DESTINATION_CONFLICT
    assert (tmp_path / "dest" / "fam" / "source.json").read_text(encoding="utf-8") == '{"tampered": true}'


def test_missing_manifest_entry_for_differing_destination_is_conflict(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"a": 1}', encoding="utf-8")
    dest_dir = tmp_path / "dest" / "fam"
    dest_dir.mkdir(parents=True)
    (dest_dir / "source.json").write_text('{"different": true}', encoding="utf-8")

    destination = LocalFilesystemDestination(tmp_path / "dest")
    result = destination.refresh_or_copy("fam", source, manifest={})

    assert result.outcome == BackupCopyOutcome.DESTINATION_CONFLICT


def test_source_changed_during_refresh_reports_source_changed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"a": 1}', encoding="utf-8")
    destination = LocalFilesystemDestination(tmp_path / "dest")

    first = destination.refresh_or_copy("fam", source, manifest={})
    manifest = {"fam/source.json": first.manifest_entry}
    source.write_text('{"a": 2}', encoding="utf-8")

    import services.backup.destinations.local as local_module
    import shutil

    real_copyfile = shutil.copyfile

    def _mutate_then_copy(src, dst, *args, **kwargs):
        Path(src).write_text('{"a": 3}', encoding="utf-8")
        return real_copyfile(src, dst, *args, **kwargs)

    monkeypatch.setattr(local_module.shutil, "copyfile", _mutate_then_copy)

    result = destination.refresh_or_copy("fam", source, manifest=manifest)

    assert result.outcome == BackupCopyOutcome.SOURCE_CHANGED_DURING_COPY
