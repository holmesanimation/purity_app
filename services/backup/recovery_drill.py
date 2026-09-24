"""Monthly disaster-recovery drill — operational layer on top of completed P6.

Reuses P6's ``restore_backup()`` unchanged for both destinations. For LOCAL,
``destination_root`` is the configured local backup folder. For DROPBOX, the
backup is actually downloaded (real network transfer, not a metadata/existence
check) into a temporary staging folder that mirrors the same
``<family>/<filename>`` layout, which then becomes the ``destination_root``
passed into the same ``restore_backup()`` call — so Dropbox recovery is
verified by the identical hash + content-readability checks as LOCAL, with no
second verification engine.

No production data is read from or written to; only the already-existing
local backup folder and Dropbox remote folder are read, into fresh temporary
directories that are removed when the drill finishes.
"""

from __future__ import annotations

import tempfile
import traceback
from pathlib import Path

from shane_common.preferences import SettingsManager

from services.settings_schemas import (
    get_backup_local_destination,
    get_dropbox_remote_folder,
    resolve_purity_data_root,
)

from .credentials import DropboxCredentialStore
from .destinations.dropbox import download_dropbox_backup
from .dropbox_service import DropboxNotReadyError, _build_client, get_dropbox_auth_state
from .models import DropboxAuthState
from .restore import RestoreResult, restore_backup

# Non-run outcomes for the Dropbox drill, mirroring DropboxAuthState values
# that mean "there is nothing to verify yet", not "verification failed".
DROPBOX_NOT_CONFIGURED = "not_configured"
DROPBOX_REAUTH_REQUIRED = "reauth_required"


def run_local_drill(settings_manager: SettingsManager) -> RestoreResult | None:
    """Runs the existing P6 restore-verification against the local backup
    destination. Returns ``None`` if no local destination is configured.
    """
    destination = get_backup_local_destination(settings_manager)
    if destination is None or not destination.exists():
        return None

    data_root = resolve_purity_data_root(settings_manager)
    with tempfile.TemporaryDirectory(prefix="purity_recovery_drill_local_") as tmp:
        return restore_backup(destination, Path(tmp), data_root, destination="local")


def run_dropbox_drill(
    settings_manager: SettingsManager,
    *,
    credential_store: DropboxCredentialStore | None = None,
) -> RestoreResult | str:
    """Downloads the current Dropbox backup and runs the existing P6
    restore-verification against it. Returns a status string
    (``DROPBOX_NOT_CONFIGURED`` / ``DROPBOX_REAUTH_REQUIRED``) instead of a
    ``RestoreResult`` when Dropbox isn't ready to be drilled.
    """
    store = credential_store or DropboxCredentialStore()
    auth_state = get_dropbox_auth_state(settings_manager, store)
    if auth_state == DropboxAuthState.DISABLED or auth_state == DropboxAuthState.AUTH_REQUIRED:
        return DROPBOX_NOT_CONFIGURED
    if auth_state == DropboxAuthState.REAUTH_REQUIRED:
        return DROPBOX_REAUTH_REQUIRED

    data_root = resolve_purity_data_root(settings_manager)
    remote_folder = get_dropbox_remote_folder(settings_manager)
    try:
        client = _build_client(settings_manager, store)
    except DropboxNotReadyError:
        return DROPBOX_NOT_CONFIGURED

    with tempfile.TemporaryDirectory(prefix="purity_recovery_drill_dropbox_download_") as download_tmp:
        try:
            download_dropbox_backup(client, remote_folder, Path(download_tmp))
        except Exception:  # noqa: BLE001 - reported, not swallowed
            traceback.print_exc()
            raise

        with tempfile.TemporaryDirectory(prefix="purity_recovery_drill_dropbox_verify_") as verify_tmp:
            return restore_backup(
                Path(download_tmp), Path(verify_tmp), data_root, destination="dropbox"
            )
