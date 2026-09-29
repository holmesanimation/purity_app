"""Notes snapshots: consistency, verification, reuse, naming, export."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.backup import snapshot as snapshot_module
from services.backup.snapshot import (
    SnapshotError,
    load_snapshot_state,
    newest_staged_export,
    newest_staged_snapshot,
    prepare_notes_snapshot,
    staging_dir,
    verify_snapshot_file,
)
from services.notes_paths import notes_db_path
from shane_common.notes.store import NotesStore
from tests.backup._notes import add_note, make_empty_db, make_snapshot

NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


def _data_root(tmp_path: Path) -> Path:
    return tmp_path / "data_root"


# -- creating -------------------------------------------------------------------

def test_no_live_database_means_no_snapshot(tmp_path: Path) -> None:
    assert prepare_notes_snapshot(_data_root(tmp_path), now=NOW) is None
    assert not staging_dir(_data_root(tmp_path)).exists() or newest_staged_snapshot(_data_root(tmp_path)) is None


def test_snapshot_of_an_empty_database_works(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    make_empty_db(dr)
    info = prepare_notes_snapshot(dr, now=NOW)

    assert info is not None and info.name == "notes-20260929T120000Z.db" and not info.reused
    facts = verify_snapshot_file(info.path)
    assert facts.counts["revisions"] == 0 and facts.counts["notes"] == 0


def test_snapshot_is_a_single_self_contained_file_with_verified_contents(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    note_id = add_note(dr, "hello")
    info = prepare_notes_snapshot(dr, now=NOW)

    staged = sorted(p.name for p in staging_dir(dr).iterdir())
    assert staged == [info.name, "notes-export-20260929.jsonl"]  # no -wal/-shm, no temp files
    ro = NotesStore.open_readonly(info.path)
    assert [r.note_id for r in ro.recent_rows()] == [note_id]
    ro.close()

    state = load_snapshot_state(dr)
    assert state["name"] == info.name and state["write_seq"] == info.write_seq
    assert state["sha256"] == info.sha256 and state["size"] == info.size == info.path.stat().st_size


def test_snapshot_is_consistent_while_another_thread_writes(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    add_note(dr, "seed")
    stop = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        store = NotesStore(notes_db_path(dr))
        try:
            from shane_common.notes.notes_writer import NotesWriter

            w = NotesWriter(store, "journal")
            i = 0
            while not stop.is_set():
                w.commit(w.build_note(text=f"n{i}"))
                i += 1
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            store.close()

    t = threading.Thread(target=writer)
    t.start()
    try:
        infos = []
        for i in range(5):
            # verify_snapshot_file(expected=...) inside prepare compares the copy with the
            # source's counts/write_seq taken in the same read transaction.
            infos.append(prepare_notes_snapshot(dr, now=NOW + timedelta(seconds=i)))
    finally:
        stop.set()
        t.join()

    assert errors == []
    assert all(info is not None for info in infos)
    verify_snapshot_file(infos[-1].path)


# -- verification failures --------------------------------------------------------

def test_corrupted_snapshot_fails_verification_and_nothing_is_promoted(tmp_path: Path, monkeypatch) -> None:
    dr = _data_root(tmp_path)
    good = make_snapshot(dr, "first")
    add_note(dr, "second")  # the DB changed, so a new snapshot is attempted

    real_copy = snapshot_module._copy_consistently

    def corrupting_copy(live: Path, tmp: Path):
        facts = real_copy(live, tmp)
        data = bytearray(tmp.read_bytes())
        for i in range(len(data) // 2, len(data)):
            data[i] = 0xFF
        tmp.write_bytes(bytes(data))
        return facts

    monkeypatch.setattr(snapshot_module, "_copy_consistently", corrupting_copy)
    with pytest.raises(SnapshotError):
        prepare_notes_snapshot(dr, now=NOW + timedelta(hours=1))

    # the previous good snapshot is untouched, and no half-written file is left behind
    assert sorted(p.name for p in staging_dir(dr).iterdir() if p.suffix == ".db") == [good.name]
    assert not [p for p in staging_dir(dr).iterdir() if p.name.endswith(".tmp")]
    assert load_snapshot_state(dr)["name"] == good.name


def test_truncated_snapshot_fails_verification(tmp_path: Path, monkeypatch) -> None:
    dr = _data_root(tmp_path)
    add_note(dr, "x")
    real_copy = snapshot_module._copy_consistently

    def truncating_copy(live: Path, tmp: Path):
        facts = real_copy(live, tmp)
        tmp.write_bytes(tmp.read_bytes()[:100])
        return facts

    monkeypatch.setattr(snapshot_module, "_copy_consistently", truncating_copy)
    with pytest.raises(SnapshotError):
        prepare_notes_snapshot(dr, now=NOW)
    assert newest_staged_snapshot(dr) is None


def test_count_mismatch_with_the_source_fails_verification(tmp_path: Path, monkeypatch) -> None:
    dr = _data_root(tmp_path)
    add_note(dr, "x")
    real_copy = snapshot_module._copy_consistently

    def lying_copy(live: Path, tmp: Path):
        facts = real_copy(live, tmp)
        conn = sqlite3.connect(tmp)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM revisions")  # silently drops data from the copy
        conn.commit()
        conn.close()
        return facts

    monkeypatch.setattr(snapshot_module, "_copy_consistently", lying_copy)
    with pytest.raises(SnapshotError, match="do not match"):
        prepare_notes_snapshot(dr, now=NOW)


def test_verify_rejects_garbage_and_foreign_key_violations(tmp_path: Path) -> None:
    garbage = tmp_path / "notes-20260101T000000Z.db"
    garbage.write_bytes(b"this is not sqlite" * 50)
    with pytest.raises(SnapshotError):
        verify_snapshot_file(garbage)

    dr = _data_root(tmp_path)
    make_snapshot(dr, "a")
    good = newest_staged_snapshot(dr)
    broken = tmp_path / "broken.db"
    broken.write_bytes(good.read_bytes())
    conn = sqlite3.connect(broken)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("UPDATE revisions SET subject_id = 'subj_missing'")
    conn.commit()
    conn.close()
    with pytest.raises(SnapshotError, match="foreign_key_check"):
        verify_snapshot_file(broken)


def test_verify_rejects_a_newer_schema(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    make_snapshot(dr, "a")
    newer = tmp_path / "newer.db"
    newer.write_bytes(newest_staged_snapshot(dr).read_bytes())
    conn = sqlite3.connect(newer)
    conn.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()
    with pytest.raises(SnapshotError, match="schema_version"):
        verify_snapshot_file(newer)


# -- reuse and naming ---------------------------------------------------------------

def test_unchanged_database_reuses_the_previous_snapshot(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    add_note(dr, "one")
    first = prepare_notes_snapshot(dr, now=NOW)
    second = prepare_notes_snapshot(dr, now=NOW + timedelta(hours=5))

    assert second.reused and second.path == first.path and second.name == first.name
    assert [p.name for p in staging_dir(dr).iterdir() if p.suffix == ".db"] == [first.name]

    add_note(dr, "two")
    third = prepare_notes_snapshot(dr, now=NOW + timedelta(hours=6))
    assert not third.reused and third.name != first.name and third.write_seq > first.write_seq
    assert [p.name for p in staging_dir(dr).iterdir() if p.suffix == ".db"] == [third.name]  # only newest staged


def test_two_snapshots_in_the_same_second_get_distinct_names(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    add_note(dr, "one")
    a = prepare_notes_snapshot(dr, now=NOW)
    add_note(dr, "two")
    b = prepare_notes_snapshot(dr, now=NOW)  # same instant
    add_note(dr, "three")
    c = prepare_notes_snapshot(dr, now=NOW - timedelta(days=1))  # clock went backwards

    assert len({a.name, b.name, c.name}) == 3
    assert a.name < b.name < c.name  # strictly increasing, so newest-by-name is newest-by-time


def test_tampered_staged_snapshot_is_rebuilt_not_reused(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    add_note(dr, "one")
    first = prepare_notes_snapshot(dr, now=NOW)
    first.path.write_bytes(first.path.read_bytes() + b"tamper")

    again = prepare_notes_snapshot(dr, now=NOW + timedelta(hours=1))
    assert not again.reused
    verify_snapshot_file(again.path)


# -- live database is never touched ----------------------------------------------------

def test_the_live_database_files_are_never_copied_or_changed(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    add_note(dr, "one")
    live = notes_db_path(dr)
    store = NotesStore(live)
    store.owners()  # keep a connection open so -wal / -shm exist while we snapshot
    try:
        before = store.rows_for_owner("journal")
        info = prepare_notes_snapshot(dr, now=NOW)
        after = store.rows_for_owner("journal")
    finally:
        store.close()

    assert before == after
    names = {p.name for p in staging_dir(dr).iterdir()}
    assert not any(n.startswith("notes.db") for n in names)
    assert info.path.name in names


# -- export ------------------------------------------------------------------------------

def test_export_is_written_from_the_verified_snapshot(tmp_path: Path) -> None:
    dr = _data_root(tmp_path)
    store = NotesStore(notes_db_path(dr))
    store.add_owner("sleep_log", "Sleep Log")
    sub = store.add_subject("subj_1", "Dreams", "sleep_log")
    from shane_common.notes.notes_writer import NotesWriter

    w = NotesWriter(store, "sleep_log")
    note = w.build_note(text="slept badly", title="Night", subject=sub.id, context={"tags": ["x"]})
    w.commit(note)
    w.commit_correlation(w.build_correlation(note_ids=[note.note_id], relation_type="other"))
    store.close()

    info = prepare_notes_snapshot(dr, now=NOW)
    assert info.export_path == newest_staged_export(dr) and info.export_path.name == "notes-export-20260929.jsonl"
    lines = [json.loads(l) for l in info.export_path.read_text(encoding="utf-8").splitlines()]
    kinds = [l["kind"] for l in lines]
    assert kinds == ["owner", "subject", "note_revision", "correlation"]
    revision = lines[2]
    assert (revision["text"], revision["title"], revision["subject"], revision["owner_key"]) == (
        "slept badly", "Night", "subj_1", "sleep_log",
    )
    assert revision["context"] == {"tags": ["x"]}
