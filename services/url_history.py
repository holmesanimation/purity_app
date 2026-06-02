"""Persistent URL usage-count history for the web-session popup."""

from __future__ import annotations

import json
from pathlib import Path

from shane_common.io.atomic import write_json_atomic


def url_history_path(data_root: Path) -> Path:
    return Path(data_root) / "data" / "url_history.json"


class UrlHistory:
    """Records how many times each URL has been used in a web session."""

    def __init__(self, data_root: Path) -> None:
        self._path = url_history_path(Path(data_root))

    def record_urls(self, urls: list[str]) -> None:
        """Increment the usage count for every URL in *urls*."""
        data = self._load()
        for url in urls:
            data[url] = data.get(url, 0) + 1
        self._save(data)

    def get_top_urls(self, n: int = 6) -> list[str]:
        """Return up to *n* URLs ordered by descending usage count."""
        data = self._load()
        sorted_items = sorted(data.items(), key=lambda kv: kv[1], reverse=True)
        return [url for url, _ in sorted_items[:n]]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, int]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {k: int(v) for k, v in raw.items() if isinstance(k, str)}
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return {}

    def _save(self, data: dict[str, int]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self._path, data)
