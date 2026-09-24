"""Dropbox backup destination.

Mirrors the manifest-aware 4-way refresh logic of
``LocalFilesystemDestination.refresh_or_copy`` but verifies against Dropbox's
own content-hash algorithm (SHA-256 of 4 MiB block hashes) instead of a plain
SHA-256 of a local file, since Dropbox computes and exposes that hash on
every file's metadata.

1. remote absent                                         -> COPIED
2. remote content_hash == source's Dropbox content hash    -> ALREADY_PRESENT_IDENTICAL
3. remote hash differs from source, but remote hash still
   matches the manifest's last-verified hash               -> REFRESHED (overwrite upload)
4. remote hash differs AND doesn't match the manifest       -> DESTINATION_CONFLICT
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from posixpath import join as posix_join

import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import GetMetadataError, WriteMode

from ..models import BackupCopyOutcome, ManifestEntry, RefreshResult

_BLOCK_SIZE = 4 * 1024 * 1024  # Dropbox content-hash block size


def dropbox_content_hash(path: Path) -> str:
    """Reimplements Dropbox's content-hash algorithm for a local file."""
    block_hashes = bytearray()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_BLOCK_SIZE)
            if not chunk:
                break
            block_hashes.extend(hashlib.sha256(chunk).digest())
    return hashlib.sha256(bytes(block_hashes)).hexdigest()


class DropboxAuthInvalidError(Exception):
    """The stored Dropbox credential was rejected by the API (reauth needed)."""


class DropboxDestination:
    def __init__(self, client: "dropbox.Dropbox", remote_folder: str) -> None:
        self._client = client
        self._remote_folder = "/" + remote_folder.strip("/")

    def remote_path(self, family_name: str, source_path: Path) -> str:
        return posix_join(self._remote_folder, family_name, Path(source_path).name)

    def manifest_key(self, family_name: str, source_path: Path) -> str:
        return f"{family_name}/{Path(source_path).name}"

    def _remote_content_hash(self, remote_path: str) -> str | None:
        try:
            metadata = self._client.files_get_metadata(remote_path)
        except ApiError as exc:
            if isinstance(exc.error, GetMetadataError) and exc.error.is_path() and exc.error.get_path().is_not_found():
                return None
            raise
        return getattr(metadata, "content_hash", None)

    def refresh_or_upload(
        self,
        family_name: str,
        source_path: Path,
        manifest: dict[str, ManifestEntry],
    ) -> RefreshResult:
        source_path = Path(source_path)
        remote_path = self.remote_path(family_name, source_path)
        key = self.manifest_key(family_name, source_path)

        try:
            source_hash = dropbox_content_hash(source_path)
            remote_hash = self._remote_content_hash(remote_path)
        except AuthError as exc:
            raise DropboxAuthInvalidError(str(exc)) from exc

        if remote_hash is None:
            return self._upload(source_path, remote_path, source_hash, WriteMode.add)

        if remote_hash == source_hash:
            return RefreshResult(
                outcome=BackupCopyOutcome.ALREADY_PRESENT_IDENTICAL,
                manifest_entry=ManifestEntry(
                    content_hash=remote_hash,
                    size=source_path.stat().st_size,
                    verified_at=_now_iso(),
                ),
                bytes_copied=0,
            )

        recorded = manifest.get(key)
        if recorded is None or recorded.content_hash != remote_hash:
            return RefreshResult(
                outcome=BackupCopyOutcome.DESTINATION_CONFLICT,
                manifest_entry=None,
                bytes_copied=0,
                error=f"{source_path}: destination_conflict",
            )

        return self._upload(source_path, remote_path, source_hash, WriteMode.overwrite, refreshed=True)

    def _upload(
        self,
        source_path: Path,
        remote_path: str,
        expected_hash: str,
        mode: "WriteMode",
        *,
        refreshed: bool = False,
    ) -> RefreshResult:
        try:
            data = source_path.read_bytes()
            uploaded = self._client.files_upload(data, remote_path, mode=mode, mute=True)
        except AuthError as exc:
            raise DropboxAuthInvalidError(str(exc)) from exc
        except ApiError as exc:
            return RefreshResult(
                outcome=BackupCopyOutcome.DESTINATION_CONFLICT,
                manifest_entry=None,
                bytes_copied=0,
                error=f"{source_path}: {exc}",
            )

        actual_hash = getattr(uploaded, "content_hash", None)
        if actual_hash is not None and actual_hash != expected_hash:
            # Source changed between hashing and upload; caller may retry.
            return RefreshResult(
                outcome=BackupCopyOutcome.SOURCE_CHANGED_DURING_COPY,
                manifest_entry=None,
                bytes_copied=0,
            )

        size = len(data)
        outcome = BackupCopyOutcome.REFRESHED if refreshed else BackupCopyOutcome.COPIED
        return RefreshResult(
            outcome=outcome,
            manifest_entry=ManifestEntry(
                content_hash=actual_hash or expected_hash,
                size=size,
                verified_at=_now_iso(),
            ),
            bytes_copied=size,
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def download_dropbox_backup(client: "dropbox.Dropbox", remote_folder: str, download_root: Path) -> None:
    """Downloads every file currently under ``remote_folder`` into
    ``download_root/<family_name>/<filename>``, verifying each downloaded
    file's bytes against Dropbox's own reported content hash.

    This performs a real network download (``files_download``), not just an
    existence/metadata check — used by the disaster-recovery drill to prove
    Dropbox recovery, not merely that Dropbox reports the files exist.
    """
    remote_root = "/" + remote_folder.strip("/")
    download_root = Path(download_root)

    try:
        listing = client.files_list_folder(remote_root)
    except ApiError as exc:
        if (
            isinstance(exc.error, GetMetadataError)
            and exc.error.is_path()
            and exc.error.get_path().is_not_found()
        ):
            return
        raise
    entries = list(listing.entries)
    while listing.has_more:
        listing = client.files_list_folder_continue(listing.cursor)
        entries.extend(listing.entries)

    for family_entry in entries:
        if not isinstance(family_entry, dropbox.files.FolderMetadata):
            continue
        family_name = family_entry.name
        family_listing = client.files_list_folder(family_entry.path_lower)
        file_entries = list(family_listing.entries)
        while family_listing.has_more:
            family_listing = client.files_list_folder_continue(family_listing.cursor)
            file_entries.extend(family_listing.entries)

        target_family_dir = download_root / family_name
        target_family_dir.mkdir(parents=True, exist_ok=True)
        for file_entry in file_entries:
            if not isinstance(file_entry, dropbox.files.FileMetadata):
                continue
            _, response = client.files_download(file_entry.path_lower)
            content = response.content
            target_path = target_family_dir / file_entry.name
            target_path.write_bytes(content)
            expected_hash = getattr(file_entry, "content_hash", None)
            if expected_hash is not None and dropbox_content_hash(target_path) != expected_hash:
                raise ValueError(
                    f"downloaded content hash mismatch for {file_entry.path_lower}"
                )
