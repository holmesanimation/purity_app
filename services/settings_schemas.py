"""Purity-owned app preference schemas and access helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from shane_common.preferences import SettingDefinition, SettingsCategory, SettingsManager


_CATEGORY_ID = "app.general"
_TELEGRAM_CATEGORY_ID = "app.telegram"
_PULSE_CATEGORY_ID = "app.pulse"
_DIET_CATEGORY_ID = "app.diet"
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
            SettingDefinition(
                key="prayer_recipients_per_session",
                type="int",
                default=2,
                label="# of Prayer Recipients per Session",
                description=(
                    "How many prayer recipients are drawn into a new prayer session "
                    "each time a pulse fires."
                ),
            ),
            SettingDefinition(
                key="backup_local_destination",
                type="str",
                default="",
                label="Local Backup Destination",
                description=(
                    "Root directory on a secondary drive where verified local backups are written."
                ),
            ),
            SettingDefinition(
                key="backup_selected_families",
                type="list",
                default=[],
                label="Protected Data Selected For Backup",
                description=(
                    "Family names to include in local/Dropbox backups. Empty means all discovered "
                    "protected data is included."
                ),
            ),
            SettingDefinition(
                key="backup_schedule_enabled",
                type="bool",
                default=False,
                label="Enable Weekly Backup",
                description="When enabled, a local backup runs automatically once per scheduled occurrence.",
            ),
            SettingDefinition(
                key="backup_schedule_weekday",
                type="int",
                default=6,
                label="Backup Weekday",
                description="Day of week for the scheduled backup (0=Monday .. 6=Sunday). Default Sunday.",
            ),
            SettingDefinition(
                key="backup_schedule_time",
                type="str",
                default="02:00",
                label="Backup Time",
                description="Local time of day (HH:MM, 24h) the scheduled backup becomes due.",
            ),
            SettingDefinition(
                key="backup_schedule_timezone",
                type="str",
                default="",
                label="Backup Timezone",
                description="IANA timezone name for the schedule. Empty uses the system's local timezone.",
            ),
            SettingDefinition(
                key="backup_stale_threshold_days",
                type="int",
                default=10,
                label="Backup Stale Threshold (days)",
                description=(
                    "Local/Dropbox backup is flagged STALE if no successful run completed "
                    "within this many days (weekly schedule + buffer, by default)."
                ),
            ),
            SettingDefinition(
                key="dropbox_backup_enabled",
                type="bool",
                default=False,
                label="Enable Dropbox Backup",
                description="When enabled, backups are also uploaded to Dropbox (independent of local backup).",
            ),
            SettingDefinition(
                key="dropbox_app_key",
                type="str",
                default="",
                label="Dropbox App Key",
                description="App key from the Dropbox App Console. Not a secret; app secret is stored securely.",
            ),
            SettingDefinition(
                key="dropbox_remote_folder",
                type="str",
                default="/PurityAppBackup",
                label="Dropbox Remote Folder",
                description="Destination folder path in the Dropbox account for backups.",
            ),
            SettingDefinition(
                key="dropbox_auth_invalid",
                type="bool",
                default=False,
                label="Dropbox Auth Invalid",
                description="Internal flag set when Dropbox reports the stored credential is no longer valid.",
            ),
            SettingDefinition(
                key="backup_recovery_drill_interval_days",
                type="int",
                default=30,
                label="Recovery Drill Interval (days)",
                description=(
                    "Recommended interval between successful disaster-recovery drills for each "
                    "backup destination (LOCAL/DROPBOX independently)."
                ),
            ),
            SettingDefinition(
                key="debug_mode_enabled",
                type="bool",
                default=False,
                label="Debug Mode",
                description=(
                    "When enabled, the app relaunches using python.exe (console attached) instead of "
                    "pythonw.exe. Persists across restarts until toggled back to Live."
                ),
            ),
        ],
    )


def get_purity_telegram_category() -> SettingsCategory:
    return SettingsCategory(
        category_id=_TELEGRAM_CATEGORY_ID,
        label="Telegram",
        definitions=[
            SettingDefinition(
                key="telegram_chat_ids",
                type="str",
                default="",
                label="Telegram Chat IDs",
                description=(
                    "Comma-separated Telegram chat IDs (group or user). "
                    "Token is read from PURITY_TELEGRAM_TOKEN env var."
                ),
            ),
        ],
    )


def get_purity_pulse_category() -> SettingsCategory:
    return SettingsCategory(
        category_id=_PULSE_CATEGORY_ID,
        label="Pulse",
        definitions=[
            SettingDefinition(
                key="morning_time",
                type="str",
                default="09:00",
                label="Morning Pulse Time",
                description="Local time when the Morning Pulse becomes eligible.",
            ),
            SettingDefinition(
                key="afternoon_time",
                type="str",
                default="14:00",
                label="Afternoon Pulse Time",
                description="Local time when the Afternoon Pulse becomes eligible.",
            ),
            SettingDefinition(
                key="evening_start_time",
                type="str",
                default="21:00",
                label="Evening Pulse Start Time",
                description="Local time when the Evening Pulse becomes eligible.",
            ),
        ],
    )


def get_purity_diet_category() -> SettingsCategory:
    return SettingsCategory(
        category_id=_DIET_CATEGORY_ID,
        label="Diet",
        definitions=[
            SettingDefinition(
                key="daily_calories",
                type="int",
                default=2000,
                label="Daily Calorie Budget",
                description="Total calories permitted per day (the 'Y' in the dashboard's calorie label).",
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
    manager.register_category(get_purity_telegram_category())
    manager.register_category(get_purity_pulse_category())
    manager.register_category(get_purity_diet_category())
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


def get_prayer_recipients_per_session(settings_manager: SettingsManager) -> int:
    try:
        return int(settings_manager.get(_CATEGORY_ID, "prayer_recipients_per_session"))
    except (TypeError, ValueError):
        return 2


def get_backup_local_destination(settings_manager: SettingsManager) -> Path | None:
    raw = str(settings_manager.get(_CATEGORY_ID, "backup_local_destination") or "").strip()
    return Path(raw) if raw else None


def get_backup_selected_families(settings_manager: SettingsManager) -> set[str]:
    """Returns the persisted family selection. Empty means "all families"."""
    raw = settings_manager.get(_CATEGORY_ID, "backup_selected_families") or []
    return {str(name) for name in raw}


def set_backup_selected_families(settings_manager: SettingsManager, families: set[str]) -> None:
    settings_manager.set(_CATEGORY_ID, "backup_selected_families", sorted(families))
    settings_manager.save()


def get_backup_schedule_enabled(settings_manager: SettingsManager) -> bool:
    return bool(settings_manager.get(_CATEGORY_ID, "backup_schedule_enabled"))


def get_backup_schedule_weekday(settings_manager: SettingsManager) -> int:
    try:
        return int(settings_manager.get(_CATEGORY_ID, "backup_schedule_weekday"))
    except (TypeError, ValueError):
        return 6


def get_backup_schedule_time(settings_manager: SettingsManager) -> str:
    raw = str(settings_manager.get(_CATEGORY_ID, "backup_schedule_time") or "").strip()
    return raw or "02:00"


def get_backup_schedule_timezone(settings_manager: SettingsManager) -> str:
    return str(settings_manager.get(_CATEGORY_ID, "backup_schedule_timezone") or "").strip()


def get_backup_stale_threshold_days(settings_manager: SettingsManager) -> int:
    try:
        return int(settings_manager.get(_CATEGORY_ID, "backup_stale_threshold_days"))
    except (TypeError, ValueError):
        return 10


def get_dropbox_backup_enabled(settings_manager: SettingsManager) -> bool:
    return bool(settings_manager.get(_CATEGORY_ID, "dropbox_backup_enabled"))


def get_dropbox_app_key(settings_manager: SettingsManager) -> str:
    return str(settings_manager.get(_CATEGORY_ID, "dropbox_app_key") or "").strip()


def get_dropbox_remote_folder(settings_manager: SettingsManager) -> str:
    raw = str(settings_manager.get(_CATEGORY_ID, "dropbox_remote_folder") or "").strip()
    return raw or "/PurityAppBackup"


def get_dropbox_auth_invalid(settings_manager: SettingsManager) -> bool:
    return bool(settings_manager.get(_CATEGORY_ID, "dropbox_auth_invalid"))


def set_dropbox_auth_invalid(settings_manager: SettingsManager, value: bool) -> None:
    settings_manager.set(_CATEGORY_ID, "dropbox_auth_invalid", bool(value))
    settings_manager.save()


def get_backup_recovery_drill_interval_days(settings_manager: SettingsManager) -> int:
    try:
        return int(settings_manager.get(_CATEGORY_ID, "backup_recovery_drill_interval_days"))
    except (TypeError, ValueError):
        return 30


def get_debug_mode_enabled(settings_manager: SettingsManager) -> bool:
    return bool(settings_manager.get(_CATEGORY_ID, "debug_mode_enabled"))


def set_debug_mode_enabled(settings_manager: SettingsManager, value: bool) -> None:
    settings_manager.set(_CATEGORY_ID, "debug_mode_enabled", bool(value))
    settings_manager.save()