from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from services.backup.destinations.local import LocalFilesystemDestination
from services.backup.restore import load_restore_state, restore_backup
from services.backup.snapshot import prepare_notes_snapshot
from services.backup.state import save_manifest
from services.notes_paths import notes_db_path
from shane_common.notes.notes_writer import NotesWriter
from shane_common.notes.store import NotesStore
from tests.backup._notes import add_note, make_snapshot


def _seed_destination_and_manifest(tmp_path: Path) -> tuple[Path, Path]:
    """Populates a destination_root the way LocalFilesystemDestination.refresh_or_copy would,
    and a data_root with a matching local_manifest.json, using real source files."""
    data_root = tmp_path / "data_root"
    data_root.mkdir()
    destination_root = tmp_path / "dest"

    source_bible = tmp_path / "bible_library.json"
    source_bible.write_text('{"books": ["Genesis"]}', encoding="utf-8")
    source_notes = make_snapshot(tmp_path / "live_root", "restore me").path
    source_reminders = tmp_path / "reminders.yaml"
    source_reminders.write_text("enabled: true\n", encoding="utf-8")

    destination = LocalFilesystemDestination(destination_root)
    manifest: dict = {}
    for family_name, source in (
        ("bible_library", source_bible),
        ("notes_db", source_notes),
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
    assert family_names == {"bible_library", "notes_db", "reminders_override"}
    for fr in result.family_results:
        assert fr.files_failed == 0
        assert fr.files_verified >= 1
        assert fr.content_check_passed
        assert fr.content_check_error is None

    assert (verification_root / "bible_library" / "bible_library.json").read_text(
        encoding="utf-8"
    ) == '{"books": ["Genesis"]}'
    (restored_db,) = (verification_root / "notes_db").glob("notes-*.db")
    restored = NotesStore.open_readonly(restored_db)
    assert [r.text for r in restored.recent_rows()] == ["restore me"]
    restored.close()

    history = load_restore_state(data_root)
    assert len(history) == 1
    assert history[0]["run_id"] == result.run_id
    assert history[0]["status"] == "success"


def _backup_and_restore(tmp_path: Path, families: dict[str, list[Path]]):
    """Back up {family: [source files]} through the real destination, then restore."""
    data_root = tmp_path / "data_root"
    data_root.mkdir(exist_ok=True)
    destination = LocalFilesystemDestination(tmp_path / "dest")
    manifest: dict = {}
    for family, sources in families.items():
        for source in sources:
            result = destination.refresh_or_copy(family, source, manifest)
            manifest[destination.manifest_key(family, source)] = result.manifest_entry
    save_manifest(data_root, manifest)
    return restore_backup(tmp_path / "dest", tmp_path / "verify", data_root)


def _text_file(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / "src" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_restore_opens_the_newest_snapshot_and_reads_notes_owners_and_subjects(tmp_path: Path) -> None:
    live = tmp_path / "live_root"
    store = NotesStore(notes_db_path(live))
    store.add_owner("sleep_log", "Sleep Log")
    sub = store.add_subject("subj_1", "Dreams", "sleep_log")
    w = NotesWriter(store, "sleep_log")
    w.commit(w.build_note(text="slept badly", title="Night", subject=sub.id))
    store.close()
    older = prepare_notes_snapshot(live, now=datetime(2026, 1, 1, tzinfo=timezone.utc)).path
    older_copy = tmp_path / "src" / older.name
    older_copy.parent.mkdir()
    older_copy.write_bytes(older.read_bytes())
    add_note(live, "second")
    newest = prepare_notes_snapshot(live, now=datetime(2026, 2, 1, tzinfo=timezone.utc)).path

    result = _backup_and_restore(tmp_path, {"notes_db": [older_copy, newest]})

    assert result.status == "success"
    (fr,) = result.family_results
    assert fr.files_verified == 2 and fr.content_check_passed and fr.content_check_error is None
    restored = NotesStore.open_readonly(tmp_path / "verify" / "notes_db" / newest.name)
    assert sorted(r.text for r in restored.recent_rows()) == ["second", "slept badly"]
    assert [(o.key, o.label) for o in restored.owners() if o.key == "sleep_log"] == [("sleep_log", "Sleep Log")]
    assert [(s.id, s.label) for s in restored.subjects()] == [("subj_1", "Dreams")]
    restored.close()


def test_restore_flags_a_corrupt_snapshot(tmp_path: Path) -> None:
    good = make_snapshot(tmp_path / "live_root", "x").path
    corrupt = _text_file(tmp_path, "notes-20991231T000000Z.db", "definitely not a database" * 100)  # newest by name
    result = _backup_and_restore(tmp_path, {"notes_db": [good, corrupt]})

    assert result.status == "partial"  # copied and hash-verified, but the newest snapshot is unusable
    (fr,) = result.family_results
    assert fr.files_verified == 2 and not fr.content_check_passed
    assert "notes-20991231T000000Z.db" in fr.content_check_error


def test_restore_flags_a_snapshot_with_broken_references(tmp_path: Path) -> None:
    import sqlite3

    good = make_snapshot(tmp_path / "live_root", "x").path
    broken = tmp_path / "src" / "notes-20991231T000000Z.db"
    broken.parent.mkdir(exist_ok=True)
    broken.write_bytes(good.read_bytes())
    conn = sqlite3.connect(broken)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("UPDATE revisions SET subject_id = 'subj_missing'")
    conn.commit()
    conn.close()

    result = _backup_and_restore(tmp_path, {"notes_db": [broken]})
    (fr,) = result.family_results
    assert not fr.content_check_passed and "foreign_key_check" in fr.content_check_error


def test_restore_with_no_snapshot_in_the_family_is_flagged(tmp_path: Path) -> None:
    stray = _text_file(tmp_path, "notes.db", "not a dated snapshot")
    result = _backup_and_restore(tmp_path, {"notes_db": [stray]})
    (fr,) = result.family_results
    assert not fr.content_check_passed and "no notes snapshot" in fr.content_check_error


def test_restore_checks_the_jsonl_export(tmp_path: Path) -> None:
    ok = _text_file(tmp_path, "notes-export-20260929.jsonl", '{"kind": "owner", "key": "journal"}\n')
    result = _backup_and_restore(tmp_path, {"notes_export": [ok]})
    assert result.status == "success" and result.family_results[0].content_check_passed


def test_restore_flags_a_malformed_export(tmp_path: Path) -> None:
    bad = _text_file(tmp_path, "notes-export-20260929.jsonl", '{"kind": "owner"}\n{"no_kind": true}\n')
    result = _backup_and_restore(tmp_path, {"notes_export": [bad]})
    (fr,) = result.family_results
    assert not fr.content_check_passed and "'kind'" in fr.content_check_error


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
