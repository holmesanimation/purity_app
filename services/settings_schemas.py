"""Purity-owned app preference schemas and access helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from shane_common.preferences import SettingDefinition, SettingsCategory, SettingsManager


_CATEGORY_ID = "app.general"
_DEFAULT_PERMITTED_BROWSERS = ["chrome.exe"]


def _default_data_root() -> Path:
    return Path.home() / ".purity"


def get_purity_general_category() -> SettingsCategory:
    return SettingsCategory(
        category_id=_CATEGORY_ID,
        label="General",
        definitions=[
            SettingDefinition(
                key="data_root",
                type="str",
                default=str(_default_data_root()),
                label="Data Root",
                description=(
                    "Root directory for Purity runtime data. Changes take effect on next launch."
                ),
            ),
            SettingDefinition(
                key="permitted_browsers",
                type="list",
                default=list(_DEFAULT_PERMITTED_BROWSERS),
                label="Permitted Browsers",
                description="Executable names that Purity allows to remain open.",
            ),
            SettingDefinition(
                key="kill_browsers_on_startup",
                type="bool",
                default=True,
                label="Kill Browsers On Startup",
                description=(
                    "When enabled, watched browsers are closed during startup so the watcher starts clean."
                ),
            ),
            SettingDefinition(
                key="web_session_timeout_seconds",
                type="int",
                default=300,
                label="Web Session Timeout (seconds)",
                description=(
                    "How long (in seconds) a permitted browser session is allowed before Purity "
                    "automatically closes it. Default is 300 (5 minutes)."
                ),
            ),
            SettingDefinition(
                key="panic_cooldown_seconds",
                type="int",
                default=300,
                label="Panic Cooldown (seconds)",
                description=(
                    "Minimum recovery countdown duration in seconds after a panic intervention."
                ),
            ),
            SettingDefinition(
                key="panic_auto_accountability_enabled",
                type="bool",
                default=True,
                label="Panic Auto Accountability",
                description=(
                    "When enabled, accountability notifications will be sent automatically "
                    "after a panic session. (Stub — not yet wired to outbound infrastructure.)"
                ),
            ),
        ],
    )


def build_purity_settings_manager(
    *,
    app_id: str = "purity_app",
    path: str | Path | None = None,
) -> SettingsManager:
    if path is not None:
        manager = SettingsManager(path=path)
    else:
        manager = SettingsManager(app_id=app_id)
    manager.register_category(get_purity_general_category())
    manager.load()
    return manager


def resolve_purity_data_root(
    settings_manager: SettingsManager,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    source_env = os.environ if environ is None else environ
    env_value = str(source_env.get("PURITY_DATA_ROOT") or "").strip()
    if env_value:
        return Path(env_value)

    saved_value = str(settings_manager.get(_CATEGORY_ID, "data_root") or "").strip()
    if saved_value:
        return Path(saved_value)

    return _default_data_root()


def get_permitted_browsers(settings_manager: SettingsManager) -> frozenset[str]:
    raw_values = settings_manager.get(_CATEGORY_ID, "permitted_browsers")
    normalized = {
        str(value).strip().lower()
        for value in raw_values
        if str(value).strip()
    }
    return frozenset(normalized)


def get_kill_browsers_on_startup(settings_manager: SettingsManager) -> bool:
    return bool(settings_manager.get(_CATEGORY_ID, "kill_browsers_on_startup"))


def get_web_session_timeout_seconds(settings_manager: SettingsManager) -> int:
    try:
        return int(settings_manager.get(_CATEGORY_ID, "web_session_timeout_seconds"))
    except (TypeError, ValueError):
        return 300