from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import GetMetadataError
from dropbox.files import LookupError as DbxLookupError

from services.backup.destinations.dropbox import (
    DropboxAuthInvalidError,
    DropboxDestination,
    dropbox_content_hash,
)
from services.backup.models import BackupCopyOutcome, ManifestEntry


@dataclass
class _FakeMetadata:
    content_hash: str


class _FakeDropboxClient:
    """Duck-typed stand-in for dropbox.Dropbox, no network calls."""

    def __init__(self) -> None:
        self.remote: dict[str, tuple[str, bytes]] = {}
        self.raise_auth_error = False

    def files_get_metadata(self, path: str):
        if self.raise_auth_error:
            raise AuthError("req-id", "invalid_access_token")
        if path not in self.remote:
            error = GetMetadataError.path(DbxLookupError.not_found)
            raise ApiError("req-id", error, "not found", "en")
        content_hash, _data = self.remote[path]
        return _FakeMetadata(content_hash=content_hash)

    def files_upload(self, data: bytes, path: str, mode=None, mute=True):
        if self.raise_auth_error:
            raise AuthError("req-id", "invalid_access_token")
        content_hash = _dropbox_hash_bytes(data)
        self.remote[path] = (content_hash, data)
        return _FakeMetadata(content_hash=content_hash)


def _dropbox_hash_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


@pytest.fixture()
def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "source.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    return path


def test_upload_when_remote_absent(source_file: Path) -> None:
    client = _FakeDropboxClient()
    destination = DropboxDestination(client, "/PurityAppBackup")
    manifest: dict[str, ManifestEntry] = {}

    result = destination.refresh_or_upload("notes", source_file, manifest)

    assert result.outcome == BackupCopyOutcome.COPIED
    assert result.manifest_entry is not None
    assert result.bytes_copied == source_file.stat().st_size


def test_already_present_identical(source_file: Path) -> None:
    client = _FakeDropboxClient()
    destination = DropboxDestination(client, "/PurityAppBackup")
    manifest: dict[str, ManifestEntry] = {}

    first = destination.refresh_or_upload("notes", source_file, manifest)
    manifest[destination.manifest_key("notes", source_file)] = first.manifest_entry

    second = destination.refresh_or_upload("notes", source_file, manifest)
    assert second.outcome == BackupCopyOutcome.ALREADY_PRESENT_IDENTICAL
    assert second.bytes_copied == 0


def test_legitimate_source_update_refreshes(source_file: Path) -> None:
    client = _FakeDropboxClient()
    destination = DropboxDestination(client, "/PurityAppBackup")
    manifest: dict[str, ManifestEntry] = {}

    first = destination.refresh_or_upload("notes", source_file, manifest)
    key = destination.manifest_key("notes", source_file)
    manifest[key] = first.manifest_entry

    source_file.write_text('{"a": 2}', encoding="utf-8")
    second = destination.refresh_or_upload("notes", source_file, manifest)

    assert second.outcome == BackupCopyOutcome.REFRESHED
    assert second.manifest_entry.content_hash == dropbox_content_hash(source_file)


def test_independent_modification_is_conflict_not_overwritten(source_file: Path) -> None:
    client = _FakeDropboxClient()
    destination = DropboxDestination(client, "/PurityAppBackup")
    manifest: dict[str, ManifestEntry] = {}

    first = destination.refresh_or_upload("notes", source_file, manifest)
    manifest[destination.manifest_key("notes", source_file)] = first.manifest_entry

    # Simulate someone changing the remote file directly (not via our manifest).
    remote_path = destination.remote_path("notes", source_file)
    client.remote[remote_path] = ("independently-modified-hash", b"tampered")

    source_file.write_text('{"a": 3}', encoding="utf-8")
    result = destination.refresh_or_upload("notes", source_file, manifest)

    assert result.outcome == BackupCopyOutcome.DESTINATION_CONFLICT
    assert client.remote[remote_path] == ("independently-modified-hash", b"tampered")


def test_auth_error_raises_dropbox_auth_invalid(source_file: Path) -> None:
    client = _FakeDropboxClient()
    client.raise_auth_error = True
    destination = DropboxDestination(client, "/PurityAppBackup")

    with pytest.raises(DropboxAuthInvalidError):
        destination.refresh_or_upload("notes", source_file, {})
