from __future__ import annotations

from pathlib import Path

from services.backup import recovery_drill
from services.backup.destinations.local import LocalFilesystemDestination
from services.backup.models import DropboxAuthState
from services.backup.restore import load_restore_state
from services.backup.state import save_manifest
from services.settings_schemas import build_purity_settings_manager


def _configure_local_backup(settings_manager, tmp_path: Path) -> Path:
    data_root = tmp_path / "data_root"
    data_root.mkdir()
    settings_manager.set("app.general", "data_root", str(data_root))
    destination_root = tmp_path / "dest"

    source = tmp_path / "bible_library.json"
    source.write_text('{"books": ["Genesis"]}', encoding="utf-8")
    destination = LocalFilesystemDestination(destination_root)
    manifest: dict = {}
    result = destination.refresh_or_copy("bible_library", source, manifest)
    manifest[destination.manifest_key("bible_library", source)] = result.manifest_entry
    save_manifest(data_root, manifest)

    settings_manager.set("app.general", "backup_local_destination", str(destination_root))
    settings_manager.save()
    return data_root


def test_run_local_drill_returns_none_when_not_configured(tmp_path: Path) -> None:
    settings_manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    assert recovery_drill.run_local_drill(settings_manager) is None


def test_run_local_drill_reuses_restore_backup_and_tags_destination(tmp_path: Path) -> None:
    settings_manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    data_root = _configure_local_backup(settings_manager, tmp_path)

    result = recovery_drill.run_local_drill(settings_manager)

    assert result is not None
    assert result.destination == "local"
    assert result.status == "success"

    runs = load_restore_state(data_root)
    assert runs[-1]["destination"] == "local"


def test_run_dropbox_drill_not_configured_when_disabled(tmp_path: Path) -> None:
    settings_manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    result = recovery_drill.run_dropbox_drill(settings_manager)
    assert result == recovery_drill.DROPBOX_NOT_CONFIGURED


def test_run_dropbox_drill_reauth_required(tmp_path: Path, monkeypatch) -> None:
    settings_manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")

    monkeypatch.setattr(
        recovery_drill, "get_dropbox_auth_state", lambda *_a, **_k: DropboxAuthState.REAUTH_REQUIRED
    )

    result = recovery_drill.run_dropbox_drill(settings_manager)
    assert result == recovery_drill.DROPBOX_REAUTH_REQUIRED
