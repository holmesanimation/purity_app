"""Orchestrates a single verified local backup run.

Never raises past its own boundary: any failure is reported (traceback
printed) and recorded as a FAILED ``BackupRunResult`` instead.
"""

from __future__ import annotations

import os
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from shane_common.preferences import SettingsManager

from services.settings_schemas import resolve_purity_data_root

from . import state
from .catalog import PurityBackupCatalog
from .destinations.local import LocalFilesystemDestination
from .models import BackupCopyOutcome, BackupRunResult, FamilyResult, ManifestEntry, RefreshResult, RunStatus

_MAX_COPY_ATTEMPTS = 3


class BackupValidationError(Exception):
    """Raised when the destination cannot be used for this run."""


def _refresh_with_retry(
    destination: LocalFilesystemDestination,
    family_name: str,
    source_path: Path,
    manifest: dict[str, ManifestEntry],
    *,
    max_attempts: int = _MAX_COPY_ATTEMPTS,
) -> RefreshResult:
    """Retry a bounded number of times on SOURCE_CHANGED_DURING_COPY.

    Covers non-atomic writers (BibleLibrary, TagLibrary) whose ``_save()``
    can leave a torn file mid-write; a retry gives the writer a chance to
    finish before the backup gives up on this file.
    """
    result = destination.refresh_or_copy(family_name, source_path, manifest)
    attempt = 1
    while result.outcome == BackupCopyOutcome.SOURCE_CHANGED_DURING_COPY and attempt < max_attempts:
        result = destination.refresh_or_copy(family_name, source_path, manifest)
        attempt += 1
    return result


class BackupService:
    def __init__(
        self,
        *,
        settings_manager: SettingsManager,
        catalog: PurityBackupCatalog | None = None,
    ) -> None:
        self._settings_manager = settings_manager
        self._catalog = catalog or PurityBackupCatalog(settings_manager=settings_manager)

    def run(self, destination_root: Path, family_names: set[str] | None = None) -> BackupRunResult:
        destination_root = Path(destination_root)
        run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc).isoformat()
        data_root = resolve_purity_data_root(self._settings_manager)

        try:
            self._validate_destination(destination_root, data_root)
            families = self._catalog.discover()
            if family_names is not None:
                families = [f for f in families if f.name in family_names]
        except BackupValidationError as exc:
            result = self._failed_result(run_id, started_at, str(exc))
            state.append_run(data_root, result)
            return result
        except Exception as exc:  # noqa: BLE001 - reported below, not swallowed
            traceback.print_exc()
            result = self._failed_result(run_id, started_at, str(exc))
            state.append_run(data_root, result)
            return result

        destination = LocalFilesystemDestination(destination_root)
        manifest = state.load_manifest(data_root)
        family_results: list[FamilyResult] = []
        file_count = verified_count = failed_count = 0
        bytes_copied = 0
        last_error: str | None = None

        for family in families:
            fr = FamilyResult(family_name=family.name)
            for source_path in family.paths:
                file_count += 1
                key = destination.manifest_key(family.name, source_path)
                try:
                    refresh_result = _refresh_with_retry(
                        destination, family.name, source_path, manifest
                    )
                except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                    traceback.print_exc()
                    failed_count += 1
                    fr.files_failed += 1
                    msg = f"{source_path}: {exc}"
                    fr.errors.append(msg)
                    last_error = msg
                    continue

                if refresh_result.outcome in (
                    BackupCopyOutcome.COPIED,
                    BackupCopyOutcome.ALREADY_PRESENT_IDENTICAL,
                    BackupCopyOutcome.REFRESHED,
                ):
                    verified_count += 1
                    fr.files_verified += 1
                    bytes_copied += refresh_result.bytes_copied
                    if refresh_result.manifest_entry is not None:
                        manifest[key] = refresh_result.manifest_entry
                else:
                    failed_count += 1
                    fr.files_failed += 1
                    msg = refresh_result.error or f"{source_path}: {refresh_result.outcome.value}"
                    fr.errors.append(msg)
                    last_error = msg
            family_results.append(fr)

        state.save_manifest(data_root, manifest)

        if failed_count and verified_count:
            status = RunStatus.PARTIAL
        elif failed_count:
            status = RunStatus.FAILED
        else:
            status = RunStatus.SUCCESS

        result = BackupRunResult(
            run_id=run_id,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            file_count=file_count,
            verified_count=verified_count,
            failed_count=failed_count,
            bytes_copied=bytes_copied,
            last_error=last_error,
            family_results=family_results,
        )
        state.append_run(data_root, result)
        return result

    def _failed_result(self, run_id: str, started_at: str, error: str) -> BackupRunResult:
        return BackupRunResult(
            run_id=run_id,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            status=RunStatus.FAILED,
            file_count=0,
            verified_count=0,
            failed_count=0,
            bytes_copied=0,
            last_error=error,
            family_results=[],
        )

    def _validate_destination(self, destination_root: Path, data_root: Path) -> None:
        anchor = destination_root.anchor
        if anchor and not Path(anchor).exists():
            raise BackupValidationError(
                f"Destination is not available: drive {anchor!r} does not exist"
            )

        resolved_destination = Path(
            os.path.normpath(
                str(destination_root.resolve())
                if destination_root.exists()
                else str(destination_root)
            )
        )

        source_roots = [Path(data_root).resolve(), self._catalog.purity_app_root.resolve()]
        for source_root in source_roots:
            if resolved_destination == source_root or _is_relative_to(
                resolved_destination, source_root
            ):
                raise BackupValidationError(
                    f"Destination {destination_root} resolves inside source path "
                    f"{source_root}; refusing to run (recursive self-backup)"
                )


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False
