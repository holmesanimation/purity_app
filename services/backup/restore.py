"""Restores a verified local backup into a temporary verification root.

Never restores in-place and never mutates the backup destination or any
production source path — this is proof-of-restore only, not a production
restore feature. Reads whatever is currently present in the local backup
destination folder (the same ``<destination_root>/<family_name>/<filename>``
layout ``LocalFilesystemDestination`` writes), copies each file into
``<verification_root>/<family_name>/<filename>`` via the same verified-copy
primitive backups use, cross-checks the copied hash against the local
manifest's last-verified hash when an entry exists, and then opens/parses
representative content per family to prove the restored data is actually
usable, not just byte-identical.
"""

from __future__ import annotations

import json
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from shane_common.io.atomic import write_json_atomic
from shane_common.runtime.transfer.copy import copy_file_verified
from shane_common.runtime.transfer.hashing import sha256_file

from . import state

_RESTORE_STATE_RELATIVE_PATH = ("_system", "purity", "backup", "restore_state.json")
_DEFAULT_MAX_HISTORY = 20


@dataclass
class FamilyRestoreResult:
    family_name: str
    files_verified: int = 0
    files_failed: int = 0
    errors: list[str] = field(default_factory=list)
    content_check_passed: bool = False
    content_check_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "family_name": self.family_name,
            "files_verified": self.files_verified,
            "files_failed": self.files_failed,
            "errors": list(self.errors),
            "content_check_passed": self.content_check_passed,
            "content_check_error": self.content_check_error,
        }


@dataclass
class RestoreResult:
    run_id: str
    started_at: str
    completed_at: str | None
    destination_root: str
    verification_root: str
    status: str  # "success" | "partial" | "failed"
    family_results: list[FamilyRestoreResult]
    destination: str = "local"  # "local" | "dropbox" — which backup destination this proves

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "destination_root": self.destination_root,
            "verification_root": self.verification_root,
            "status": self.status,
            "family_results": [fr.to_dict() for fr in self.family_results],
            "destination": self.destination,
        }


def restore_state_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*_RESTORE_STATE_RELATIVE_PATH)


def load_restore_state(data_root: Path) -> list[dict]:
    path = restore_state_path(data_root)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        traceback.print_exc()
        return []
    runs = raw.get("runs", []) if isinstance(raw, dict) else []
    return [r for r in runs if isinstance(r, dict)]


def append_restore_result(
    data_root: Path,
    result: RestoreResult,
    *,
    max_history: int = _DEFAULT_MAX_HISTORY,
) -> None:
    runs = load_restore_state(data_root)
    runs.append(result.to_dict())
    runs = runs[-max_history:]
    write_json_atomic(restore_state_path(data_root), {"runs": runs})


def _check_single_json(family_dir: Path) -> None:
    files = sorted(p for p in family_dir.iterdir() if p.is_file())
    if not files:
        raise ValueError("no files present to verify")
    json.loads(files[0].read_text(encoding="utf-8"))


def _check_single_yaml(family_dir: Path) -> None:
    files = sorted(p for p in family_dir.iterdir() if p.is_file())
    if not files:
        raise ValueError("no files present to verify")
    yaml.safe_load(files[0].read_text(encoding="utf-8"))


def _check_notes(family_dir: Path) -> None:
    files = sorted(family_dir.glob("*.jsonl"))
    if not files:
        raise ValueError("no notes files present to verify")
    for jsonl_path in files:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                json.loads(line)


_CONTENT_CHECKS = {
    "notes": _check_notes,
    "bible_library": _check_single_json,
    "bible_memorizing": _check_single_json,
    "prayer_recipients": _check_single_json,
    "prayer_prayed": _check_single_json,
    "tag_library": _check_single_json,
    "diet_state": _check_single_json,
    "reminders_override": _check_single_yaml,
    "user_preferences": _check_single_yaml,
}


def restore_backup(
    destination_root: Path,
    verification_root: Path,
    data_root: Path,
    *,
    destination: str = "local",
) -> RestoreResult:
    """Restore everything currently present under ``destination_root`` into
    ``verification_root`` (created fresh) and verify hashes + representative
    content per family. Records the outcome as durable evidence under
    ``data_root``.

    ``destination`` tags which backup destination ("local"/"dropbox") this
    restore proves, so callers can derive independent recovery health per
    destination from the shared ``restore_state.json`` history.
    """
    destination_root = Path(destination_root)
    verification_root = Path(verification_root)
    run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()

    manifest = state.load_manifest(data_root)
    family_results: list[FamilyRestoreResult] = []
    any_failed = False
    any_verified = False

    if destination_root.exists():
        family_dirs = sorted(p for p in destination_root.iterdir() if p.is_dir())
        for family_dir in family_dirs:
            family_name = family_dir.name
            fr = FamilyRestoreResult(family_name=family_name)
            target_family_dir = verification_root / family_name

            for source_file in sorted(p for p in family_dir.iterdir() if p.is_file()):
                target_file = target_family_dir / source_file.name
                try:
                    copy_result = copy_file_verified(source_file, target_file)
                except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                    traceback.print_exc()
                    fr.files_failed += 1
                    fr.errors.append(f"{source_file}: {exc}")
                    continue

                dest_hash = copy_result.destination_hash or sha256_file(target_file)
                recorded = manifest.get(f"{family_name}/{source_file.name}")
                if recorded is not None and recorded.content_hash != dest_hash:
                    fr.files_failed += 1
                    fr.errors.append(
                        f"{source_file}: restored hash does not match last-verified manifest record"
                    )
                    continue
                fr.files_verified += 1

            check_fn = _CONTENT_CHECKS.get(family_name)
            try:
                if check_fn is not None and target_family_dir.exists():
                    check_fn(target_family_dir)
                fr.content_check_passed = True
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                traceback.print_exc()
                fr.content_check_passed = False
                fr.content_check_error = str(exc)

            if fr.files_failed or fr.content_check_error:
                any_failed = True
            if fr.files_verified:
                any_verified = True
            family_results.append(fr)

    if not family_results:
        status = "failed"
    elif any_failed and any_verified:
        status = "partial"
    elif any_failed:
        status = "failed"
    else:
        status = "success"

    result = RestoreResult(
        run_id=run_id,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc).isoformat(),
        destination_root=str(destination_root),
        verification_root=str(verification_root),
        status=status,
        family_results=family_results,
        destination=destination,
    )
    append_restore_result(data_root, result)
    return result
