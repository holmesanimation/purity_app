"""Consistent, verified, dated snapshots of the notes database for backup.

The live ``notes.db`` (and its ``-wal`` / ``-shm`` files) is **never copied**:
copying a live SQLite file can produce a torn or incomplete backup.  Instead,
each backup run

1. opens the live database read-only-ish (``PRAGMA query_only``) and pins one read
   transaction, so the row counts / ``write_seq`` it records describe exactly the
   state the backup API copies;
2. uses :meth:`sqlite3.Connection.backup` to write that point-in-time state into a
   temporary file in the staging folder (``<data_root>/_system/purity/backup/staging``);
3. verifies the temporary file (``integrity_check``, ``foreign_key_check``, schema
   version, counts and ``write_seq`` equal to the source's, readable through
   ``NotesStore``).  On any failure the temporary file is deleted and
   :class:`SnapshotError` is raised: nothing is promoted, uploaded or pruned;
4. skips all of the above when ``meta.write_seq`` is unchanged since the last good
   snapshot (the previous staged snapshot is reused);
5. otherwise renames the file to ``notes-YYYYMMDDTHHMMSSZ.db`` — a brand-new name
   every time, so no earlier snapshot is ever overwritten — and records
   ``write_seq``, size and hash in ``notes_snapshot.json``;
6. writes a human-readable ``notes-export-YYYYMMDD.jsonl`` from the *verified
   snapshot* (never the live database).

Only the newest snapshot and export are kept in staging; the backup destinations
hold the history (see ``retention.py``).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shane_common.io.atomic import write_json_atomic
from shane_common.notes.db import SCHEMA_VERSION, NotesDbError, read_schema_version, read_write_seq
from shane_common.notes.store import NotesStore
from shane_common.runtime.transfer.hashing import sha256_file

from services.notes_paths import notes_db_path

from .retention import (
    NOTES_DB_FAMILY,
    NOTES_EXPORT_FAMILY,
    export_filename,
    parse_export_time,
    parse_snapshot_time,
    snapshot_filename,
)

_STAGING_RELATIVE_PATH = ("_system", "purity", "backup", "staging")
_STATE_RELATIVE_PATH = ("_system", "purity", "backup", "notes_snapshot.json")

_COUNT_TABLES = ("owners", "subjects", "notes", "revisions", "correlations", "correlation_notes")
_TEMP_PREFIX = ".notes-"
_TEMP_SUFFIX = ".tmp"


class SnapshotError(Exception):
    """A snapshot could not be created or did not verify.  Nothing was promoted."""


@dataclass(frozen=True)
class SnapshotFacts:
    """What a database file contains, for comparing a snapshot with its source."""

    write_seq: int
    schema_version: int
    counts: dict[str, int]


@dataclass(frozen=True)
class SnapshotInfo:
    path: Path
    name: str
    write_seq: int
    size: int
    sha256: str
    schema_version: int
    created_at: str
    reused: bool
    export_path: Path | None = None


# ---------------------------------------------------------------------------
# Paths and state
# ---------------------------------------------------------------------------

def staging_dir(data_root: Path) -> Path:
    return Path(data_root).joinpath(*_STAGING_RELATIVE_PATH)


def snapshot_state_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*_STATE_RELATIVE_PATH)


def _staged_in(folder: Path, parse) -> list[Path]:
    if not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and parse(p.name) is not None]
    return sorted(files, key=lambda p: (parse(p.name), p.name))


def newest_staged_snapshot(data_root: Path) -> Path | None:
    """The newest ``notes-*.db`` in staging, or ``None``."""
    files = _staged_in(staging_dir(data_root), parse_snapshot_time)
    return files[-1] if files else None


def newest_staged_export(data_root: Path) -> Path | None:
    files = _staged_in(staging_dir(data_root), parse_export_time)
    return files[-1] if files else None


def load_snapshot_state(data_root: Path) -> dict:
    path = snapshot_state_path(data_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


# ---------------------------------------------------------------------------
# Reading and verifying
# ---------------------------------------------------------------------------

def _read_facts(conn: sqlite3.Connection) -> SnapshotFacts:
    return SnapshotFacts(
        write_seq=read_write_seq(conn),
        schema_version=read_schema_version(conn),
        counts={t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _COUNT_TABLES},
    )


def verify_snapshot_file(path: Path, *, expected: SnapshotFacts | None = None) -> SnapshotFacts:
    """Check that *path* is a healthy, readable notes database; return its facts.

    Opens the file read-only.  Raises :class:`SnapshotError` on any problem,
    including a mismatch with *expected* (the source's facts at snapshot time).
    """
    path = Path(path)
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise SnapshotError(f"{path.name}: cannot open: {exc}") from exc
    try:
        integrity = [r[0] for r in conn.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise SnapshotError(f"{path.name}: integrity_check failed: {integrity[:3]}")
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            raise SnapshotError(f"{path.name}: foreign_key_check found {len(fk)} violation(s)")
        facts = _read_facts(conn)
    except sqlite3.Error as exc:
        raise SnapshotError(f"{path.name}: not a readable notes database: {exc}") from exc
    finally:
        conn.close()

    if facts.schema_version < 1 or facts.schema_version > SCHEMA_VERSION:
        raise SnapshotError(
            f"{path.name}: unsupported schema_version {facts.schema_version} "
            f"(this app understands up to {SCHEMA_VERSION})"
        )
    if expected is not None and facts != expected:
        raise SnapshotError(
            f"{path.name}: contents do not match the source at snapshot time "
            f"(snapshot {facts}, source {expected})"
        )

    # Prove the data is usable through the real read path, not just structurally sound.
    store = NotesStore.open_readonly(path)
    try:
        store.owners()
        store.subjects()
        store.recent_rows(25)
    except (NotesDbError, sqlite3.Error) as exc:
        raise SnapshotError(f"{path.name}: cannot be read through NotesStore: {exc}") from exc
    finally:
        store.close()
    return facts


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------

def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _copy_consistently(live_db: Path, tmp_path: Path) -> SnapshotFacts:
    """Back up *live_db* into *tmp_path*; return the source's facts at that instant."""
    try:
        src = sqlite3.connect(str(live_db), isolation_level=None, timeout=10.0)
    except sqlite3.Error as exc:
        raise SnapshotError(f"cannot open the live notes database: {exc}") from exc
    dest = None
    try:
        src.execute("PRAGMA query_only = ON")
        src.execute("BEGIN")  # pin one read snapshot for both the facts and the copy
        try:
            facts = _read_facts(src)
            dest = sqlite3.connect(str(tmp_path), isolation_level=None)
            src.backup(dest)
        finally:
            src.execute("COMMIT")
        # The copy inherits WAL mode from the source; make it one self-contained file.
        mode = dest.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
        if str(mode).lower() != "delete":
            raise SnapshotError(f"could not switch the snapshot to a single file (mode {mode})")
        return facts
    except sqlite3.Error as exc:
        raise SnapshotError(f"the live notes database could not be read: {exc}") from exc
    finally:
        if dest is not None:
            dest.close()
        src.close()


def _sha256_of(path: Path) -> str:
    return sha256_file(path)


def prepare_notes_snapshot(
    data_root: Path,
    *,
    now: datetime | None = None,
    live_db: Path | None = None,
) -> SnapshotInfo | None:
    """Make (or reuse) the verified staged snapshot for this backup run.

    Returns ``None`` when there is no live database yet.  Raises
    :class:`SnapshotError` when the snapshot fails verification; in that case the
    staging folder still holds the previous good snapshot (if any) and the caller
    must not upload or prune anything.
    """
    data_root = Path(data_root)
    live = Path(live_db) if live_db is not None else notes_db_path(data_root)
    if not live.exists():
        return None

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    folder = staging_dir(data_root)
    folder.mkdir(parents=True, exist_ok=True)
    state = load_snapshot_state(data_root)

    # -- unchanged since the last good snapshot? -> reuse, do no work ------------
    reusable = _try_reuse(data_root, folder, state, live)
    if reusable is not None:
        return reusable

    tmp_path = folder / f"{_TEMP_PREFIX}{uuid.uuid4().hex}{_TEMP_SUFFIX}"
    try:
        facts = _copy_consistently(live, tmp_path)
        verify_snapshot_file(tmp_path, expected=facts)
    except BaseException:
        _remove(tmp_path)
        raise

    # Every snapshot gets a brand-new, strictly increasing name.
    latest = max(
        (t for t in (
            parse_snapshot_time(str(state.get("name", ""))),
            *(parse_snapshot_time(p.name) for p in _staged_in(folder, parse_snapshot_time)),
        ) if t is not None),
        default=None,
    )
    moment = now if latest is None or now > latest else latest + timedelta(seconds=1)
    final = folder / snapshot_filename(moment)
    os.replace(tmp_path, final)

    size = final.stat().st_size
    digest = _sha256_of(final)
    created_at = moment.isoformat()
    write_json_atomic(
        snapshot_state_path(data_root),
        {
            "name": final.name,
            "write_seq": facts.write_seq,
            "schema_version": facts.schema_version,
            "size": size,
            "sha256": digest,
            "created_at": created_at,
            "counts": facts.counts,
        },
    )

    export_path = _write_export(final, folder / export_filename(moment))
    _prune_staging(folder, keep_snapshot=final, keep_export=export_path)

    return SnapshotInfo(
        path=final,
        name=final.name,
        write_seq=facts.write_seq,
        size=size,
        sha256=digest,
        schema_version=facts.schema_version,
        created_at=created_at,
        reused=False,
        export_path=export_path,
    )


def _try_reuse(data_root: Path, folder: Path, state: dict, live: Path) -> SnapshotInfo | None:
    name = str(state.get("name", ""))
    staged = folder / name
    if not name or parse_snapshot_time(name) is None or not staged.is_file():
        return None
    try:
        conn = sqlite3.connect(str(live), isolation_level=None, timeout=10.0)
        try:
            conn.execute("PRAGMA query_only = ON")
            current_seq = read_write_seq(conn)
        finally:
            conn.close()
    except sqlite3.Error:
        return None  # let the full path report the problem
    if current_seq != state.get("write_seq"):
        return None
    if staged.stat().st_size != state.get("size") or _sha256_of(staged) != state.get("sha256"):
        return None  # the staged file was altered: rebuild rather than trust it
    export = newest_staged_export(data_root)
    return SnapshotInfo(
        path=staged,
        name=name,
        write_seq=int(state["write_seq"]),
        size=int(state["size"]),
        sha256=str(state["sha256"]),
        schema_version=int(state.get("schema_version", SCHEMA_VERSION)),
        created_at=str(state.get("created_at", "")),
        reused=True,
        export_path=export,
    )


def _prune_staging(folder: Path, *, keep_snapshot: Path, keep_export: Path | None) -> None:
    """Keep only the newest snapshot/export (and nothing half-written) in staging."""
    for p in folder.iterdir():
        if not p.is_file() or p == keep_snapshot or p == keep_export:
            continue
        if (
            parse_snapshot_time(p.name) is not None
            or parse_export_time(p.name) is not None
            or (p.name.startswith(_TEMP_PREFIX) and p.name.endswith(_TEMP_SUFFIX))
        ):
            _remove(p)


# ---------------------------------------------------------------------------
# JSONL export (from the verified snapshot, never the live database)
# ---------------------------------------------------------------------------

def _write_export(snapshot: Path, out_path: Path) -> Path | None:
    """Write every owner, subject, note revision and correlation as JSON lines.

    Returns ``None`` (and leaves nothing behind) if the export could not be
    written: the export is an extra independent copy, so it never fails a backup.
    """
    tmp = out_path.with_name(f"{_TEMP_PREFIX}{uuid.uuid4().hex}{_TEMP_SUFFIX}")
    store = NotesStore.open_readonly(snapshot)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            def emit(kind: str, payload: dict) -> None:
                fh.write(json.dumps({"kind": kind, **payload}, ensure_ascii=False, default=str) + "\n")

            for o in store.owners():
                emit("owner", {"key": o.key, "label": o.label, "builtin": o.builtin})
            for s in store.subjects():
                emit("subject", {"id": s.id, "label": s.label, "owner": s.owner_key})
            for row in store.all_rows():
                emit("note_revision", asdict(row))
            for c in store.all_correlations():
                emit("correlation", asdict(c))
        os.replace(tmp, out_path)
        return out_path
    except (OSError, sqlite3.Error, NotesDbError):
        _remove(tmp)
        return None
    finally:
        store.close()


__all__ = [
    "NOTES_DB_FAMILY",
    "NOTES_EXPORT_FAMILY",
    "SnapshotError",
    "SnapshotFacts",
    "SnapshotInfo",
    "load_snapshot_state",
    "newest_staged_export",
    "newest_staged_snapshot",
    "prepare_notes_snapshot",
    "snapshot_state_path",
    "staging_dir",
    "verify_snapshot_file",
]
