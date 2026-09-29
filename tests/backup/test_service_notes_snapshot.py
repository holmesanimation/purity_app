"""BackupService with the notes database: snapshot step, reuse, retention, safety rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.backup import snapshot as snapshot_module
from services.backup.catalog import PurityBackupCatalog
from services.backup.destinations.local import LocalFilesystemDestination
from services.backup.models import RunStatus
from services.backup.retention import RetentionPolicy
from services.backup.service import BackupService
from services.backup.snapshot import SnapshotError, staging_dir, verify_snapshot_file
from services.backup.state import load_manifest, load_state
from services.notes_paths import notes_db_path
from services.settings_schemas import build_purity_settings_manager
from shane_common.notes.store import NotesStore
from tests.backup._notes import add_note
from tests.backup.test_service import _build_source_tree, _service


def _db_files(destination_root: Path) -> list[str]:
    return sorted(p.name for p in (destination_root / "notes_db").glob("notes-*.db"))


def _service_with(tmp_path: Path, data_root: Path, purity_app_root: Path, **kwargs) -> BackupService:
    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    manager.set("app.general", "data_root", str(data_root))
    catalog = PurityBackupCatalog(
        settings_manager=manager,
        purity_app_root=purity_app_root,
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )
    return BackupService(settings_manager=manager, catalog=catalog, **kwargs)


# -- happy path ------------------------------------------------------------------------

def test_backup_run_uploads_a_verified_snapshot_and_restorable_copy(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    result = _service(tmp_path, data_root, app_root).run(dest)

    assert result.status == RunStatus.SUCCESS
    (name,) = _db_files(dest)
    facts = verify_snapshot_file(dest / "notes_db" / name)
    assert facts.counts["revisions"] == 1
    # the snapshot is recorded in the manifest with its verified hash
    assert f"notes_db/{name}" in load_manifest(data_root)


def test_live_database_files_never_appear_in_the_destination(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    store = NotesStore(notes_db_path(data_root))
    store.owners()  # a live connection keeps -wal / -shm around during the run
    try:
        _service(tmp_path, data_root, app_root).run(dest)
    finally:
        store.close()

    leaked = [p for p in dest.rglob("*") if p.is_file() and p.name.startswith("notes.db")]
    assert leaked == []
    assert all(p.suffix in (".db", ".jsonl", ".json", ".yaml") for p in dest.rglob("*") if p.is_file())


def test_no_live_database_yet_is_not_an_error(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    notes_db_path(data_root).unlink()
    for sidecar in notes_db_path(data_root).parent.glob("notes.db-*"):
        sidecar.unlink()
    result = _service(tmp_path, data_root, app_root).run(tmp_path / "dest")
    assert result.status == RunStatus.SUCCESS
    assert not (tmp_path / "dest" / "notes_db").exists()


def test_restricting_families_without_notes_db_makes_no_snapshot(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    result = _service(tmp_path, data_root, app_root).run(tmp_path / "dest", {"tag_library"})
    assert result.status == RunStatus.SUCCESS
    assert not staging_dir(data_root).exists()
    assert not (tmp_path / "dest" / "notes_db").exists()


# -- unchanged / changed -----------------------------------------------------------------

def test_unchanged_database_uploads_nothing_new_and_a_new_note_does(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    service = _service(tmp_path, data_root, app_root)

    assert service.run(dest).status == RunStatus.SUCCESS
    second = service.run(dest)
    assert second.status == RunStatus.SUCCESS and second.bytes_copied == 0
    assert len(_db_files(dest)) == 1  # reused: no second snapshot

    add_note(data_root, "a second note")
    third = service.run(dest)
    assert third.status == RunStatus.SUCCESS and third.bytes_copied > 0
    assert len(_db_files(dest)) == 2


def test_two_runs_on_the_same_day_keep_two_distinct_snapshots(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    service = _service(tmp_path, data_root, app_root)

    service.run(dest)
    (first_name,) = _db_files(dest)
    first_bytes = (dest / "notes_db" / first_name).read_bytes()
    add_note(data_root, "later the same day")
    service.run(dest)

    names = _db_files(dest)
    assert len(names) == 2 and first_name in names and names[0] == first_name
    assert (dest / "notes_db" / first_name).read_bytes() == first_bytes  # never overwritten
    assert all(fr.files_failed == 0 for fr in load_state(data_root)[-1].family_results)


# -- failure --------------------------------------------------------------------------------

def test_failed_snapshot_fails_the_run_and_changes_nothing_at_the_destination(tmp_path: Path, monkeypatch) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    good_service = _service(tmp_path, data_root, app_root)
    assert good_service.run(dest).status == RunStatus.SUCCESS
    before = sorted((str(p.relative_to(dest)), p.read_bytes()) for p in dest.rglob("*") if p.is_file())
    manifest_before = load_manifest(data_root)

    add_note(data_root, "written after the good backup")
    (data_root / "bible_library.json").write_text('{"b": 2}', encoding="utf-8")  # would refresh if the run got that far

    def bad_copy(live: Path, tmp: Path):
        raise SnapshotError("simulated corruption")

    monkeypatch.setattr(snapshot_module, "_copy_consistently", bad_copy)
    result = good_service.run(dest)

    assert result.status == RunStatus.FAILED
    assert "Notes snapshot failed" in (result.last_error or "") and "simulated corruption" in result.last_error
    assert result.verified_count == 0 and result.family_results == []
    after = sorted((str(p.relative_to(dest)), p.read_bytes()) for p in dest.rglob("*") if p.is_file())
    assert after == before  # nothing uploaded, nothing refreshed, nothing pruned
    assert load_manifest(data_root) == manifest_before
    assert load_state(data_root)[-1].status == RunStatus.FAILED


def test_corrupt_live_database_fails_the_run_without_touching_the_destination(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    for sidecar in notes_db_path(data_root).parent.glob("notes.db-*"):
        sidecar.unlink()
    notes_db_path(data_root).write_bytes(b"garbage" * 1000)

    result = _service(tmp_path, data_root, app_root).run(dest)
    assert result.status == RunStatus.FAILED and "Notes snapshot failed" in (result.last_error or "")
    assert not dest.exists()


# -- retention -----------------------------------------------------------------------------------

def test_retention_prunes_old_snapshots_after_a_verified_upload(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    service = _service_with(tmp_path, data_root, app_root, retention=RetentionPolicy(keep_newest=2, keep_monthly=0))
    (dest / "notes_db").mkdir(parents=True)
    (dest / "notes_db" / "README.txt").write_text("keep me", encoding="utf-8")

    names_seen = []
    for i in range(4):
        add_note(data_root, f"note {i}")
        assert service.run(dest).status == RunStatus.SUCCESS
        names_seen.append(_db_files(dest)[-1])

    kept = _db_files(dest)
    assert kept == names_seen[-2:]                         # the newest two
    assert (dest / "notes_db" / "README.txt").read_text(encoding="utf-8") == "keep me"
    manifest = load_manifest(data_root)
    assert {k for k in manifest if k.startswith("notes_db/notes-")} == {f"notes_db/{n}" for n in kept}
    verify_snapshot_file(dest / "notes_db" / kept[-1])     # and the newest is intact


def test_pre_existing_old_snapshots_in_the_destination_are_pruned_by_date_not_by_upload_order(tmp_path: Path) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    folder = dest / "notes_db"
    folder.mkdir(parents=True)
    for n in ("notes-20200101T000000Z.db", "notes-20200102T000000Z.db", "notes-20200103T000000Z.db"):
        (folder / n).write_bytes(b"old")
    service = _service_with(tmp_path, data_root, app_root, retention=RetentionPolicy(keep_newest=1, keep_monthly=0))

    assert service.run(dest).status == RunStatus.SUCCESS
    remaining = _db_files(dest)
    assert len(remaining) == 1 and remaining[0] > "notes-2026"        # only the fresh snapshot remains


def test_no_pruning_when_the_snapshot_upload_did_not_verify(tmp_path: Path, monkeypatch) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    folder = dest / "notes_db"
    folder.mkdir(parents=True)
    old = ["notes-20200101T000000Z.db", "notes-20200102T000000Z.db"]
    for n in old:
        (folder / n).write_bytes(b"old")
    service = _service_with(tmp_path, data_root, app_root, retention=RetentionPolicy(keep_newest=1, keep_monthly=0))

    real = LocalFilesystemDestination.refresh_or_copy

    def failing(self, family_name, source_path, manifest):
        if family_name == "notes_db":
            raise OSError("simulated upload failure")
        return real(self, family_name, source_path, manifest)

    monkeypatch.setattr(LocalFilesystemDestination, "refresh_or_copy", failing)
    result = service.run(dest)

    assert result.status == RunStatus.PARTIAL
    assert _db_files(dest) == old  # nothing new arrived, so nothing may be pruned


def test_pruning_failure_never_fails_the_backup(tmp_path: Path, monkeypatch) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    dest = tmp_path / "dest"
    service = _service_with(tmp_path, data_root, app_root, retention=RetentionPolicy(keep_newest=1, keep_monthly=0))

    def boom(self, *a, **k):
        raise OSError("cannot list")

    monkeypatch.setattr(LocalFilesystemDestination, "prune_family", boom)
    result = service.run(dest)
    assert result.status == RunStatus.SUCCESS
    notes_family = next(fr for fr in result.family_results if fr.family_name == "notes_db")
    assert notes_family.files_failed == 0 and any("prune skipped" in e for e in notes_family.errors)


def test_saved_selection_naming_the_old_notes_families_still_covers_the_notes_database(tmp_path: Path) -> None:
    from services.settings_schemas import get_backup_selected_families

    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    manager.set("app.general", "backup_selected_families", ["notes", "notes_registry", "bible_library"])
    assert get_backup_selected_families(manager) == {"notes_db", "notes_export", "bible_library"}


# -- the destination may not be the database's own folder ---------------------------------------------

@pytest.mark.parametrize("sub", ["data", "data/backups"])
def test_destination_inside_the_live_database_folder_is_refused(tmp_path: Path, sub: str) -> None:
    data_root, app_root = _build_source_tree(tmp_path)
    result = _service(tmp_path, data_root, app_root).run(data_root / sub)
    assert result.status == RunStatus.FAILED
    assert "recursive self-backup" in (result.last_error or "")
