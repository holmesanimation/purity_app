"""Orchestrates a single verified Dropbox backup run.

Uploads whatever is currently present in the local backup destination
folder (mirrored per-family by ``LocalFilesystemDestination``), not the
original protected-data sources — Dropbox is a second hop off of the local
backup, not an independent copy of the source files. Uses its own
manifest/run-history files (``dropbox_manifest.json`` / ``dropbox_state.json``)
and never touches ``local_manifest.json`` / ``local_state.json``. A Dropbox
failure (auth, network, API) never raises past this module's boundary and
never affects local backup state or normal Purity operation.
"""

from __future__ import annotations

import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from shane_common.preferences import SettingsManager

from services.settings_schemas import (
    get_backup_local_destination,
    get_dropbox_app_key,
    get_dropbox_auth_invalid,
    get_dropbox_backup_enabled,
    get_dropbox_remote_folder,
    resolve_purity_data_root,
    set_dropbox_auth_invalid,
)

from . import state
from .catalog import PurityBackupCatalog
from .credentials import DropboxCredentialStore
from .destinations.dropbox import DropboxAuthInvalidError, DropboxDestination
from .models import (
    BackupCopyOutcome,
    BackupRunResult,
    BackupSourceFamily,
    DropboxAuthState,
    FamilyResult,
    ManifestEntry,
    RefreshResult,
    RunStatus,
)


def _discover_local_backup_families(destination_root: Path) -> list[BackupSourceFamily]:
    """Mirrors the local backup folder layout: one subfolder per family."""
    families = []
    for family_dir in sorted(p for p in destination_root.iterdir() if p.is_dir()):
        paths = tuple(sorted(p for p in family_dir.iterdir() if p.is_file()))
        if paths:
            families.append(BackupSourceFamily(name=family_dir.name, paths=paths, required=True))
    return families

_MAX_UPLOAD_ATTEMPTS = 3


class DropboxNotReadyError(Exception):
    """Raised when Dropbox isn't configured/authorized for a run."""


def get_dropbox_auth_state(
    settings_manager: SettingsManager,
    credential_store: DropboxCredentialStore | None = None,
) -> DropboxAuthState:
    if not get_dropbox_backup_enabled(settings_manager):
        return DropboxAuthState.DISABLED

    if get_dropbox_auth_invalid(settings_manager):
        return DropboxAuthState.REAUTH_REQUIRED

    store = credential_store or DropboxCredentialStore()
    if not get_dropbox_app_key(settings_manager) or not store.get_refresh_token():
        return DropboxAuthState.AUTH_REQUIRED

    return DropboxAuthState.READY


def _build_client(settings_manager: SettingsManager, credential_store: DropboxCredentialStore):
    import dropbox

    app_key = get_dropbox_app_key(settings_manager)
    refresh_token = credential_store.get_refresh_token()
    if not app_key or not refresh_token:
        raise DropboxNotReadyError("Dropbox is not fully authorized.")
    return dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
    )


def _upload_with_retry(
    destination: DropboxDestination,
    family_name: str,
    source_path,
    manifest: dict[str, ManifestEntry],
    *,
    max_attempts: int = _MAX_UPLOAD_ATTEMPTS,
) -> RefreshResult:
    result = destination.refresh_or_upload(family_name, source_path, manifest)
    attempt = 1
    while result.outcome == BackupCopyOutcome.SOURCE_CHANGED_DURING_COPY and attempt < max_attempts:
        result = destination.refresh_or_upload(family_name, source_path, manifest)
        attempt += 1
    return result


class DropboxBackupService:
    def __init__(
        self,
        *,
        settings_manager: SettingsManager,
        catalog: PurityBackupCatalog | None = None,
        credential_store: DropboxCredentialStore | None = None,
    ) -> None:
        self._settings_manager = settings_manager
        self._catalog = catalog or PurityBackupCatalog(settings_manager=settings_manager)
        self._credential_store = credential_store or DropboxCredentialStore()

    def run(self) -> BackupRunResult:
        run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc).isoformat()
        data_root = resolve_purity_data_root(self._settings_manager)

        auth_state = get_dropbox_auth_state(self._settings_manager, self._credential_store)
        if auth_state != DropboxAuthState.READY:
            result = self._failed_result(run_id, started_at, f"Dropbox not ready: {auth_state.value}")
            state.append_dropbox_run(data_root, result)
            return result

        local_destination = get_backup_local_destination(self._settings_manager)
        if local_destination is None or not local_destination.exists():
            result = self._failed_result(
                run_id,
                started_at,
                "Local backup destination not configured or not found; run a local backup first.",
            )
            state.append_dropbox_run(data_root, result)
            return result

        try:
            client = _build_client(self._settings_manager, self._credential_store)
            families = _discover_local_backup_families(local_destination)
        except Exception as exc:  # noqa: BLE001 - reported below, not swallowed
            traceback.print_exc()
            result = self._failed_result(run_id, started_at, str(exc))
            state.append_dropbox_run(data_root, result)
            return result

        remote_folder = get_dropbox_remote_folder(self._settings_manager)
        destination = DropboxDestination(client, remote_folder)
        manifest = state.load_dropbox_manifest(data_root)
        family_results: list[FamilyResult] = []
        file_count = verified_count = failed_count = 0
        bytes_copied = 0
        last_error: str | None = None
        auth_invalidated = False

        for family in families:
            fr = FamilyResult(family_name=family.name)
            for source_path in family.paths:
                file_count += 1
                key = destination.manifest_key(family.name, source_path)
                try:
                    refresh_result = _upload_with_retry(destination, family.name, source_path, manifest)
                except DropboxAuthInvalidError as exc:
                    auth_invalidated = True
                    failed_count += 1
                    fr.files_failed += 1
                    msg = f"{source_path}: dropbox auth invalid: {exc}"
                    fr.errors.append(msg)
                    last_error = msg
                    continue
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

        state.save_dropbox_manifest(data_root, manifest)

        if auth_invalidated:
            set_dropbox_auth_invalid(self._settings_manager, True)

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
        state.append_dropbox_run(data_root, result)
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
