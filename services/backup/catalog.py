"""Resolves the fixed P1 Purity backup source family list.

The catalog never caches ``data_root`` at import/construction time — it is
re-resolved from the settings manager on every ``discover()`` call, since
the user can change ``data_root`` between runs.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from shane_common.preferences import SettingsManager
from shane_common.preferences.paths import app_settings_path

from services.settings_schemas import resolve_purity_data_root

from .models import BackupSourceFamily

# services/backup/catalog.py -> services/backup -> services -> purity_app
_PURITY_APP_ROOT = Path(__file__).resolve().parents[2]


def _family(name: str, candidate_paths: Iterable[Path], *, required: bool) -> BackupSourceFamily:
    existing = tuple(p for p in candidate_paths if p.exists())
    return BackupSourceFamily(name=name, paths=existing, required=required)


class PurityBackupCatalog:
    """Discovers the restore-required Purity backup source families."""

    def __init__(
        self,
        *,
        settings_manager: SettingsManager,
        purity_app_root: Path | None = None,
        user_preferences_path: Path | None = None,
    ) -> None:
        self._settings_manager = settings_manager
        self._purity_app_root = (
            Path(purity_app_root) if purity_app_root is not None else _PURITY_APP_ROOT
        )
        self._user_preferences_path = (
            Path(user_preferences_path) if user_preferences_path is not None else None
        )

    @property
    def purity_app_root(self) -> Path:
        return self._purity_app_root

    def resolve_data_root(self) -> Path:
        return resolve_purity_data_root(self._settings_manager)

    def discover(self) -> list[BackupSourceFamily]:
        data_root = self.resolve_data_root()

        notes_dir = self._purity_app_root / "notes" / "PurityApp" / "default"
        notes_paths = sorted(notes_dir.glob("*.jsonl")) if notes_dir.exists() else []

        families = [
            _family("notes", notes_paths, required=True),
            _family("bible_library", [data_root / "bible_library.json"], required=True),
            _family("bible_memorizing", [data_root / "bible_memorizing.json"], required=True),
            _family(
                "prayer_recipients",
                [data_root / "data" / "prayer_recipients.json"],
                required=True,
            ),
            _family(
                "prayer_prayed",
                [data_root / "data" / "prayer_prayed.json"],
                required=True,
            ),
            _family(
                "tag_library",
                [self._purity_app_root / "data" / "tags.json"],
                required=True,
            ),
            _family("diet_state", [data_root / "data" / "diet_state.json"], required=True),
            _family("reminders_override", [data_root / "reminders.yaml"], required=False),
        ]

        families.append(_family("user_preferences", self._user_preferences_paths(), required=False))
        return families

    def _user_preferences_paths(self) -> list[Path]:
        if self._user_preferences_path is not None:
            return [self._user_preferences_path]
        try:
            return [app_settings_path("purity_app")]
        except (RuntimeError, ValueError):
            return []
