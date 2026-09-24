from __future__ import annotations

from pathlib import Path

from services.backup.credentials import DropboxCredentialStore
from services.backup.dropbox_service import DropboxBackupService, get_dropbox_auth_state
from services.backup.models import DropboxAuthState, RunStatus
from services.backup.service import BackupService
from services.backup.state import load_state
from services.settings_schemas import build_purity_settings_manager


class _FakeSecretStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def set_secret(self, namespace: str, name: str, value: str) -> None:
        self._data[(namespace, name)] = value

    def get_secret(self, namespace: str, name: str) -> str | None:
        return self._data.get((namespace, name))

    def delete_secret(self, namespace: str, name: str) -> None:
        self._data.pop((namespace, name), None)


def _manager(tmp_path: Path):
    return build_purity_settings_manager(path=tmp_path / "settings.yaml")


def _credential_store() -> DropboxCredentialStore:
    return DropboxCredentialStore(store=_FakeSecretStore(), namespace="test.purity_app.dropbox")


def test_auth_state_missing_refresh_token(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.set("app.general", "dropbox_backup_enabled", True)
    manager.set("app.general", "dropbox_app_key", "app-key")
    store = _credential_store()

    assert get_dropbox_auth_state(manager, store) == DropboxAuthState.AUTH_REQUIRED


def test_auth_state_ready_with_valid_refresh_token(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.set("app.general", "dropbox_backup_enabled", True)
    manager.set("app.general", "dropbox_app_key", "app-key")
    store = _credential_store()
    store.set_refresh_token("refresh-abc")

    assert get_dropbox_auth_state(manager, store) == DropboxAuthState.READY


def test_dropbox_auth_failure_does_not_affect_local_backup_state(tmp_path: Path) -> None:
    data_root = tmp_path / "data_root"
    purity_app_root = tmp_path / "purity_app"
    notes_dir = purity_app_root / "notes" / "PurityApp" / "default"
    notes_dir.mkdir(parents=True)
    (notes_dir / "purity.jsonl").write_text('{"a": 1}', encoding="utf-8")
    (purity_app_root / "data").mkdir(parents=True)
    (purity_app_root / "data" / "tags.json").write_text('{"tags": ["x"]}', encoding="utf-8")
    data_root.mkdir(parents=True)
    (data_root / "bible_library.json").write_text('{"b": 1}', encoding="utf-8")
    (data_root / "data").mkdir(parents=True)
    (data_root / "data" / "prayer_recipients.json").write_text("{}", encoding="utf-8")
    (data_root / "data" / "prayer_prayed.json").write_text("{}", encoding="utf-8")

    from services.backup.catalog import PurityBackupCatalog

    manager = _manager(tmp_path)
    manager.set("app.general", "data_root", str(data_root))
    catalog = PurityBackupCatalog(
        settings_manager=manager,
        purity_app_root=purity_app_root,
        user_preferences_path=tmp_path / "no_such_prefs.yaml",
    )

    local_service = BackupService(settings_manager=manager, catalog=catalog)
    local_destination_root = tmp_path / "dest"
    local_result = local_service.run(local_destination_root)
    assert local_result.status == RunStatus.SUCCESS

    # Dropbox is enabled but never authorized -> a run must fail without
    # touching local_state.json.
    manager.set("app.general", "dropbox_backup_enabled", True)
    manager.set("app.general", "dropbox_app_key", "app-key")
    dropbox_service = DropboxBackupService(
        settings_manager=manager,
        catalog=catalog,
        credential_store=_credential_store(),
    )
    dropbox_result = dropbox_service.run()
    assert dropbox_result.status == RunStatus.FAILED

    local_state_after = load_state(data_root)
    assert len(local_state_after) == 1
    assert local_state_after[0].run_id == local_result.run_id
