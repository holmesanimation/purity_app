"""Retention policy and ``prune_family`` on the local and Dropbox destinations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from dropbox.exceptions import ApiError
from dropbox.files import FileMetadata, ListFolderError
from dropbox.files import LookupError as DbxLookupError

from services.backup.destinations.dropbox import DropboxDestination
from services.backup.destinations.local import LocalFilesystemDestination
from services.backup.retention import (
    NOTES_DB_FAMILY,
    NOTES_EXPORT_FAMILY,
    RetentionPolicy,
    export_filename,
    parse_snapshot_time,
    plan_prune,
    snapshot_filename,
)

NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


def _names(days_ago: list[int], *, hour: int = 8) -> list[str]:
    return [snapshot_filename((NOW - timedelta(days=d)).replace(hour=hour)) for d in days_ago]


# -- policy ----------------------------------------------------------------------------

def test_file_name_round_trip() -> None:
    name = snapshot_filename(NOW)
    assert name == "notes-20260929T120000Z.db"
    assert parse_snapshot_time(name) == NOW
    assert parse_snapshot_time("notes-export-20260929.jsonl") is None
    assert parse_snapshot_time("notes.db") is None
    assert export_filename(NOW) == "notes-export-20260929.jsonl"


def test_fewer_files_than_the_limit_are_all_kept() -> None:
    names = _names(list(range(5)))
    keep, delete = plan_prune(NOTES_DB_FAMILY, names, now=NOW)
    assert sorted(keep) == sorted(names) and delete == []


def test_keeps_newest_n_plus_newest_of_each_of_the_last_months() -> None:
    # 30 daily snapshots (Aug 31 .. Sep 29), one per day at 08:00, plus old monthly leftovers.
    daily = _names(list(range(30)))
    old = [
        "notes-20260615T080000Z.db", "notes-20260618T080000Z.db",   # June: newest is the 18th
        "notes-20250901T080000Z.db",                                  # 13 months back: outside the window
    ]
    policy = RetentionPolicy(keep_newest=14, keep_monthly=12)
    keep, delete = plan_prune(NOTES_DB_FAMILY, daily + old, policy, now=NOW)

    assert "notes-20260615T080000Z.db" in delete                      # not June's newest
    assert "notes-20250901T080000Z.db" in delete                      # outside the 12-month window
    # exactly: the 14 newest (Sep 16-29), September's newest (already among them),
    # August's newest (Aug 31) and June's newest (Jun 18); July has no snapshots
    assert set(keep) == set(_names(list(range(14)))) | {"notes-20260831T080000Z.db", "notes-20260618T080000Z.db"}
    assert len(delete) == len(daily + old) - len(keep)


def test_the_newest_file_is_never_pruned_whatever_the_numbers() -> None:
    names = _names([400, 500, 600])
    keep, delete = plan_prune(NOTES_DB_FAMILY, names, RetentionPolicy(keep_newest=1, keep_monthly=0), now=NOW)
    assert keep == [names[0]] and set(delete) == set(names[1:])


def test_protected_names_survive() -> None:
    names = _names(list(range(5)))
    keep, delete = plan_prune(
        NOTES_DB_FAMILY, names, RetentionPolicy(keep_newest=1, keep_monthly=0), protect=[names[3]], now=NOW
    )
    assert names[0] in keep and names[3] in keep and names[3] not in delete


def test_names_that_do_not_match_the_pattern_are_ignored() -> None:
    names = _names([0, 1, 2]) + ["notes.db", "notes.db-wal", "notes-latest.db", "README.txt", "notes-export-20260101.jsonl"]
    keep, delete = plan_prune(NOTES_DB_FAMILY, names, RetentionPolicy(keep_newest=1, keep_monthly=0), now=NOW)
    for stranger in ("notes.db", "notes.db-wal", "notes-latest.db", "README.txt", "notes-export-20260101.jsonl"):
        assert stranger not in keep and stranger not in delete


def test_export_family_uses_the_same_policy_with_its_own_pattern() -> None:
    names = [export_filename(NOW - timedelta(days=d)) for d in range(5)] + ["notes-20260101T000000Z.db"]
    keep, delete = plan_prune(NOTES_EXPORT_FAMILY, names, RetentionPolicy(keep_newest=2, keep_monthly=0), now=NOW)
    assert keep == names[:2][::-1] and "notes-20260101T000000Z.db" not in delete


def test_unknown_family_prunes_nothing() -> None:
    assert plan_prune("bible_library", ["a.json", "b.json"], now=NOW) == ([], [])


def test_invalid_policy_is_rejected() -> None:
    with pytest.raises(ValueError):
        RetentionPolicy(keep_newest=0)


# -- local destination -------------------------------------------------------------------

def _seed_local(tmp_path: Path, names: list[str], extra: tuple[str, ...] = ()) -> LocalFilesystemDestination:
    folder = tmp_path / "dest" / NOTES_DB_FAMILY
    folder.mkdir(parents=True)
    for n in (*names, *extra):
        (folder / n).write_bytes(b"x")
    return LocalFilesystemDestination(tmp_path / "dest")


def test_local_prune_deletes_only_dropped_managed_files(tmp_path: Path) -> None:
    names = _names(list(range(6)))
    dest = _seed_local(tmp_path, names, extra=("README.txt", "notes.db"))
    result = dest.prune_family(NOTES_DB_FAMILY, RetentionPolicy(keep_newest=2, keep_monthly=0), now=NOW)

    remaining = sorted(p.name for p in (tmp_path / "dest" / NOTES_DB_FAMILY).iterdir())
    assert remaining == sorted([*names[:2], "README.txt", "notes.db"])
    assert sorted(result.deleted) == sorted(names[2:]) and result.errors == []


def test_local_prune_never_deletes_the_protected_new_snapshot_even_if_it_sorts_old(tmp_path: Path) -> None:
    names = _names([0, 1, 2])
    dest = _seed_local(tmp_path, names)
    result = dest.prune_family(
        NOTES_DB_FAMILY, RetentionPolicy(keep_newest=1, keep_monthly=0), protect=[names[2]], now=NOW
    )
    assert (tmp_path / "dest" / NOTES_DB_FAMILY / names[2]).exists()
    assert names[2] not in result.deleted


def test_local_prune_of_a_missing_folder_is_a_no_op(tmp_path: Path) -> None:
    result = LocalFilesystemDestination(tmp_path / "nowhere").prune_family(NOTES_DB_FAMILY)
    assert (result.deleted, result.kept, result.errors) == ([], [], [])


def test_local_prune_reports_files_it_could_not_delete(tmp_path: Path, monkeypatch) -> None:
    names = _names(list(range(4)))
    dest = _seed_local(tmp_path, names)
    real_unlink = Path.unlink

    def flaky_unlink(self, *a, **k):
        if self.name == names[3]:
            raise PermissionError("locked")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    result = dest.prune_family(NOTES_DB_FAMILY, RetentionPolicy(keep_newest=1, keep_monthly=0), now=NOW)
    assert names[3] not in result.deleted and any(names[3] in e for e in result.errors)
    assert (tmp_path / "dest" / NOTES_DB_FAMILY / names[3]).exists()


# -- dropbox destination (fake client) ---------------------------------------------------

class _Listing:
    def __init__(self, entries):
        self.entries, self.has_more, self.cursor = entries, False, None


class _FakeDropbox:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = dict(files)
        self.deleted: list[str] = []

    def files_list_folder(self, path: str):
        prefix = path.rstrip("/") + "/"
        entries = [
            FileMetadata(name=p[len(prefix):], id="id", client_modified=NOW, server_modified=NOW,
                         rev="0123456789", size=len(d))
            for p, d in self.files.items()
            if p.startswith(prefix) and "/" not in p[len(prefix):]
        ]
        if not entries:
            raise ApiError("req", ListFolderError.path(DbxLookupError.not_found), "not found", "en")
        return _Listing(entries)

    def files_delete_v2(self, path: str):
        self.deleted.append(path)
        del self.files[path]


def test_dropbox_prune_applies_the_same_policy_and_uses_delete_v2() -> None:
    names = _names(list(range(6)))
    client = _FakeDropbox({f"/PurityAppBackup/{NOTES_DB_FAMILY}/{n}": b"x" for n in names}
                          | {f"/PurityAppBackup/{NOTES_DB_FAMILY}/README.txt": b"x",
                             "/PurityAppBackup/tag_library/tags.json": b"x"})
    dest = DropboxDestination(client, "/PurityAppBackup")

    result = dest.prune_family(NOTES_DB_FAMILY, RetentionPolicy(keep_newest=2, keep_monthly=0), now=NOW)

    assert sorted(result.deleted) == sorted(names[2:])
    assert sorted(client.deleted) == sorted(f"/PurityAppBackup/{NOTES_DB_FAMILY}/{n}" for n in names[2:])
    assert f"/PurityAppBackup/{NOTES_DB_FAMILY}/README.txt" in client.files      # foreign file untouched
    assert "/PurityAppBackup/tag_library/tags.json" in client.files              # other families untouched
    assert all(f"/PurityAppBackup/{NOTES_DB_FAMILY}/{n}" in client.files for n in names[:2])


def test_dropbox_prune_of_a_missing_folder_is_a_no_op() -> None:
    dest = DropboxDestination(_FakeDropbox({}), "/PurityAppBackup")
    assert dest.prune_family(NOTES_DB_FAMILY).deleted == []


def test_local_and_dropbox_prune_agree() -> None:
    names = _names(list(range(20)))
    policy = RetentionPolicy(keep_newest=5, keep_monthly=3)
    client = _FakeDropbox({f"/B/{NOTES_DB_FAMILY}/{n}": b"x" for n in names})
    remote = DropboxDestination(client, "/B").prune_family(NOTES_DB_FAMILY, policy, now=NOW)
    keep, delete = plan_prune(NOTES_DB_FAMILY, names, policy, now=NOW)
    assert sorted(remote.deleted) == sorted(delete) and sorted(remote.kept) == sorted(keep)
