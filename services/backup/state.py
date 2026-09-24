"""Durable run-history and manifest persistence for the Purity local backup subsystem.

Run history is stored at ``<data_root>/_system/purity/backup/local_state.json``.
The manifest (per-destination-file verified-hash evidence, used to distinguish
a legitimate source update from an independently modified destination) is
stored at ``<data_root>/_system/purity/backup/local_manifest.json``, parallel
to the existing ``heartbeats/``, ``audit/``, ``pulse/`` convention.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from shane_common.io.atomic import write_json_atomic

from .models import BackupRunResult, ManifestEntry

_STATE_RELATIVE_PATH = ("_system", "purity", "backup", "local_state.json")
_MANIFEST_RELATIVE_PATH = ("_system", "purity", "backup", "local_manifest.json")
_DROPBOX_STATE_RELATIVE_PATH = ("_system", "purity", "backup", "dropbox_state.json")
_DROPBOX_MANIFEST_RELATIVE_PATH = ("_system", "purity", "backup", "dropbox_manifest.json")
_DEFAULT_MAX_HISTORY = 20


def state_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*_STATE_RELATIVE_PATH)


def manifest_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*_MANIFEST_RELATIVE_PATH)


def dropbox_state_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*_DROPBOX_STATE_RELATIVE_PATH)


def dropbox_manifest_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*_DROPBOX_MANIFEST_RELATIVE_PATH)


def _load_manifest_at(path: Path) -> dict[str, ManifestEntry]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        traceback.print_exc()
        return {}
    entries = raw.get("entries", {}) if isinstance(raw, dict) else {}
    return {
        str(key): ManifestEntry.from_dict(value)
        for key, value in entries.items()
        if isinstance(value, dict)
    }


def _save_manifest_at(path: Path, manifest: dict[str, ManifestEntry]) -> None:
    write_json_atomic(
        path,
        {"entries": {key: entry.to_dict() for key, entry in manifest.items()}},
    )


def _load_state_at(path: Path) -> list[BackupRunResult]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        traceback.print_exc()
        return []
    runs = raw.get("runs", []) if isinstance(raw, dict) else []
    return [BackupRunResult.from_dict(r) for r in runs if isinstance(r, dict)]


def _append_run_at(path: Path, result: BackupRunResult, *, max_history: int) -> None:
    runs = _load_state_at(path)
    runs.append(result)
    runs = runs[-max_history:]
    write_json_atomic(path, {"runs": [r.to_dict() for r in runs]})


def load_manifest(data_root: Path) -> dict[str, ManifestEntry]:
    return _load_manifest_at(manifest_path(data_root))


def save_manifest(data_root: Path, manifest: dict[str, ManifestEntry]) -> None:
    _save_manifest_at(manifest_path(data_root), manifest)


def load_state(data_root: Path) -> list[BackupRunResult]:
    return _load_state_at(state_path(data_root))


def append_run(
    data_root: Path,
    result: BackupRunResult,
    *,
    max_history: int = _DEFAULT_MAX_HISTORY,
) -> None:
    _append_run_at(state_path(data_root), result, max_history=max_history)


def load_dropbox_manifest(data_root: Path) -> dict[str, ManifestEntry]:
    return _load_manifest_at(dropbox_manifest_path(data_root))


def save_dropbox_manifest(data_root: Path, manifest: dict[str, ManifestEntry]) -> None:
    _save_manifest_at(dropbox_manifest_path(data_root), manifest)


def load_dropbox_state(data_root: Path) -> list[BackupRunResult]:
    return _load_state_at(dropbox_state_path(data_root))


def append_dropbox_run(
    data_root: Path,
    result: BackupRunResult,
    *,
    max_history: int = _DEFAULT_MAX_HISTORY,
) -> None:
    _append_run_at(dropbox_state_path(data_root), result, max_history=max_history)
