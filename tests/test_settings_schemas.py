from __future__ import annotations

from pathlib import Path

from services.settings_schemas import (
    build_purity_settings_manager,
    get_kill_browsers_on_startup,
    get_permitted_browsers,
    resolve_purity_data_root,
)


def test_resolve_data_root_prefers_env_override(tmp_path: Path) -> None:
    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    manager.set("app.general", "data_root", str(tmp_path / "saved_root"))

    resolved = resolve_purity_data_root(
        manager,
        environ={"PURITY_DATA_ROOT": str(tmp_path / "env_root")},
    )

    assert resolved == tmp_path / "env_root"


def test_resolve_data_root_uses_saved_setting_when_env_absent(tmp_path: Path) -> None:
    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    manager.set("app.general", "data_root", str(tmp_path / "saved_root"))

    resolved = resolve_purity_data_root(manager, environ={})

    assert resolved == tmp_path / "saved_root"


def test_build_manager_loads_saved_browser_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    manager = build_purity_settings_manager(path=settings_path)
    manager.set("app.general", "permitted_browsers", ["chrome.exe", "msedge.exe"])
    manager.set("app.general", "kill_browsers_on_startup", False)
    manager.save()

    reloaded = build_purity_settings_manager(path=settings_path)

    assert get_permitted_browsers(reloaded) == frozenset({"chrome.exe", "msedge.exe"})
    assert get_kill_browsers_on_startup(reloaded) is False


def test_resolve_data_root_falls_back_to_default(tmp_path: Path, monkeypatch) -> None:
    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")
    manager.set("app.general", "data_root", "")
    monkeypatch.setattr("services.settings_schemas.Path.home", lambda: tmp_path)

    resolved = resolve_purity_data_root(manager, environ={})

    assert resolved == tmp_path / ".purity"


def test_build_manager_exposes_pulse_schedule_defaults(tmp_path: Path) -> None:
    manager = build_purity_settings_manager(path=tmp_path / "settings.yaml")

    assert manager.get("app.pulse", "morning_time") == "09:00"
    assert manager.get("app.pulse", "afternoon_time") == "14:00"
    assert manager.get("app.pulse", "evening_start_time") == "21:00"


def test_build_manager_persists_saved_pulse_schedule_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    manager = build_purity_settings_manager(path=settings_path)
    manager.set("app.pulse", "morning_time", "08:30")
    manager.set("app.pulse", "afternoon_time", "13:45")
    manager.set("app.pulse", "evening_start_time", "20:30")
    manager.save()

    reloaded = build_purity_settings_manager(path=settings_path)

    assert reloaded.get("app.pulse", "morning_time") == "08:30"
    assert reloaded.get("app.pulse", "afternoon_time") == "13:45"
    assert reloaded.get("app.pulse", "evening_start_time") == "20:30"