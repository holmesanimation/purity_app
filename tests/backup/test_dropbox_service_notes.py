"""DropboxBackupService with dated notes snapshots: upload, retention, no re-upload churn."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dropbox.exceptions import ApiError
from dropbox.files import FileMetadata, GetMetadataError, ListFolderError
from dropbox.files import LookupError as DbxLookupError

import services.backup.dropbox_service as dropbox_service_module
from services.backup.catalog import PurityBackupCatalog
from services.backup.credentials import DropboxCredentialStore
from services.backup.dropbox_service import DropboxBackupService
from services.backup.models import RunStatus
from services.backup.retention import RetentionPolicy
from services.backup.service import BackupService
from services.backup.state import load_dropbox_manifest
from services.settings_schemas import build_purity_settings_manager
from tests.backup._notes import add_note
from tests.backup.test_dropbox_service import _FakeSecretStore
from tests.backup.test_service import _build_source_tree

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


@dataclass
class _Listing:
    entries: list
    has_more: bool = False
    cursor: str | None = None


@dataclass
class _Meta:
    content_hash: str


class _FakeDropbox:
    """Duck-typed dropbox.Dropbox: get_metadata, upload, list_folder, delete_v2."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.uploads: list[str] = []
        self.deleted: list[str] = []

    @staticmethod
    def _hash(data: bytes) -> str:
        return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()

    def files_get_metadata(self, path: str):
        if path not in self.files:
            raise ApiError("req", GetMetadataError.path(DbxLookupError.not_found), "not found", "en")
        return _Meta(self._hash(self.files[path]))

    def files_upload(self, data: bytes, path: str, mode=None, mute=True):
        self.files[path] = data
        self.uploads.append(path)
        return _Meta(self._hash(data))

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


def _setup(tmp_path: Path, monkeypatch, retention: RetentionPolicy):
    data_root, app_root = _build_source_tree(tmp_path)
    local_dest = tmp_path / "local_backup"
    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    manager.set("app.general", "data_root", str(data_root))
    manager.set("app.general", "backup_local_destination", str(local_dest))
    manager.set("app.general", "dropbox_backup_enabled", True)
    manager.set("app.general", "dropbox_app_key", "app-key")
    catalog = PurityBackupCatalog(
        settings_manager=manager, purity_app_root=app_root,
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )
    creds = DropboxCredentialStore(store=_FakeSecretStore(), namespace="test.purity_app.dropbox")
    creds.set_refresh_token("refresh")
    client = _FakeDropbox()
    monkeypatch.setattr(dropbox_service_module, "_build_client", lambda *_a, **_k: client)
    local = BackupService(settings_manager=manager, catalog=catalog, retention=retention)
    remote = DropboxBackupService(
        settings_manager=manager, catalog=catalog, credential_store=creds, retention=retention
    )
    return data_root, local_dest, client, local, remote


def _remote_snapshots(client: _FakeDropbox) -> list[str]:
    return sorted(p.rsplit("/", 1)[1] for p in client.files if "/notes_db/notes-" in p)


def test_dropbox_gets_dated_snapshots_and_prunes_them_like_the_local_destination(
    tmp_path: Path, monkeypatch
) -> None:
    policy = RetentionPolicy(keep_newest=2, keep_monthly=0)
    data_root, local_dest, client, local, remote = _setup(tmp_path, monkeypatch, policy)

    for i in range(4):
        add_note(data_root, f"note {i}")
        assert local.run(local_dest).status == RunStatus.SUCCESS
        result = remote.run()
        assert result.status == RunStatus.SUCCESS and result.failed_count == 0

    local_names = sorted(p.name for p in (local_dest / "notes_db").glob("notes-*.db"))
    assert len(local_names) == 2
    assert _remote_snapshots(client) == local_names            # same policy, same survivors
    assert len(client.deleted) >= 2 and all("/notes_db/notes-" in p for p in client.deleted)
    manifest = load_dropbox_manifest(data_root)
    assert {k for k in manifest if k.startswith("notes_db/notes-")} == {f"notes_db/{n}" for n in local_names}


def test_an_unchanged_database_causes_no_new_upload_and_no_churn(tmp_path: Path, monkeypatch) -> None:
    policy = RetentionPolicy(keep_newest=2, keep_monthly=0)
    data_root, local_dest, client, local, remote = _setup(tmp_path, monkeypatch, policy)
    local.run(local_dest)
    remote.run()
    uploads_before = len(client.uploads)

    local.run(local_dest)          # nothing changed: reused snapshot
    second = remote.run()

    assert second.status == RunStatus.SUCCESS and second.bytes_copied == 0
    assert len(client.uploads) == uploads_before and client.deleted == []


def test_remote_files_that_do_not_match_the_pattern_are_never_deleted(tmp_path: Path, monkeypatch) -> None:
    policy = RetentionPolicy(keep_newest=1, keep_monthly=0)
    data_root, local_dest, client, local, remote = _setup(tmp_path, monkeypatch, policy)
    client.files["/PurityAppBackup/notes_db/README.txt"] = b"mine"
    client.files["/PurityAppBackup/notes_db/notes-20200101T000000Z.db"] = b"ancient"

    local.run(local_dest)
    assert remote.run().status == RunStatus.SUCCESS

    assert "/PurityAppBackup/notes_db/README.txt" in client.files
    assert "/PurityAppBackup/notes_db/notes-20200101T000000Z.db" not in client.files   # dated + old: pruned
    assert len(_remote_snapshots(client)) == 1


def test_no_remote_pruning_when_the_upload_failed(tmp_path: Path, monkeypatch) -> None:
    policy = RetentionPolicy(keep_newest=1, keep_monthly=0)
    data_root, local_dest, client, local, remote = _setup(tmp_path, monkeypatch, policy)
    client.files["/PurityAppBackup/notes_db/notes-20200101T000000Z.db"] = b"ancient"
    local.run(local_dest)

    real_upload = client.files_upload

    def failing_upload(data, path, mode=None, mute=True):
        if "/notes_db/" in path:
            raise ApiError("req", "boom", "upload failed", "en")
        return real_upload(data, path, mode, mute)

    monkeypatch.setattr(client, "files_upload", failing_upload)
    result = remote.run()

    assert result.status == RunStatus.PARTIAL
    assert "/PurityAppBackup/notes_db/notes-20200101T000000Z.db" in client.files
    assert client.deleted == []
