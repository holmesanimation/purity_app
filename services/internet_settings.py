from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlparse

from shane_common.io.atomic import write_json_atomic

# Path to the default (hidden) blocklist relative to this file's location.
# Lives in browser_extension/config/ alongside other extension configs.
_DEFAULT_BLACKLIST_PATH = (
    Path(__file__).parent.parent
    / "browser_extension"
    / "config"
    / "default_blacklist.json"
)


def _settings_path(data_root: Path) -> Path:
    return Path(data_root) / "data" / "internet_settings.json"


def _load_default_blacklist() -> list[str]:
    """Load the hardcoded default blocklist. Returns empty list on any error."""
    try:
        raw = _DEFAULT_BLACKLIST_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            domains = data.get("blacklisted_domains", [])
            if isinstance(domains, list):
                return [str(d) for d in domains if isinstance(d, str) and d.strip()]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _parse_domain(entry: str) -> str | None:
    """Extract a valid hostname from a domain name or URL string.

    Returns None if the entry is blank or cannot be parsed.
    """
    entry = entry.strip()
    if not entry:
        return None
    if "://" not in entry:
        entry = f"https://{entry}"
    try:
        parsed = urlparse(entry)
        host = (parsed.hostname or "").strip().lower()
        return host if host else None
    except Exception:
        return None


class InternetSettingsService:
    """Persists and serves the blacklisted domains list.

    Two separate lists exist:
    - **default blacklist** — loaded from ``default_blacklist.json`` in the
      extension config directory; never shown to the user.
    - **user blacklist** — stored in ``<data_root>/data/internet_settings.json``;
      shown and edited in the Internet Settings dialog.

    ``load_merged_domains()`` returns both combined (for the API / extension).
    ``load_user_domains()`` returns only the user's list (for the dialog).
    """

    def __init__(self, data_root: Path) -> None:
        self._data_root = Path(data_root)
        self._lock = threading.Lock()
        self._path = _settings_path(self._data_root)
        self._default_domains: list[str] = _load_default_blacklist()

    def load_merged_domains(self) -> list[str]:
        """Return default + user domains, deduplicated, for use by the extension."""
        with self._lock:
            user = self._read_user_unlocked()
        seen: set[str] = set()
        merged: list[str] = []
        for domain in self._default_domains + user:
            if domain not in seen:
                seen.add(domain)
                merged.append(domain)
        return merged

    # Kept for backwards compat — callers that used load_blacklisted_domains
    # previously get the full merged list (same behaviour as before this split).
    def load_blacklisted_domains(self) -> list[str]:
        return self.load_merged_domains()

    def load_user_domains(self) -> list[str]:
        """Return only the user-managed domain list (for the settings dialog)."""
        with self._lock:
            return self._read_user_unlocked()

    def save_blacklisted_domains(self, domains: list[str]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(self._path, {"blacklisted_domains": domains})

    def _read_user_unlocked(self) -> list[str]:
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                domains = data.get("blacklisted_domains", [])
                if isinstance(domains, list):
                    return [
                        str(d) for d in domains if isinstance(d, str) and d.strip()
                    ]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        return []

    @staticmethod
    def parse_raw_input(raw_text: str) -> list[str]:
        """Parse raw user input (one entry per line) into a deduplicated domain list.

        Accepts plain hostnames (``example.com``) or full URLs
        (``https://example.com/path``).  Blank lines and lines starting with
        ``#`` are silently skipped.  Invalid entries are also skipped.
        """
        domains: list[str] = []
        seen: set[str] = set()
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            domain = _parse_domain(stripped)
            if domain is None:
                continue
            if domain not in seen:
                seen.add(domain)
                domains.append(domain)
        return domains
