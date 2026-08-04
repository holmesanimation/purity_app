"""Simple tag library backed by data/tags.json."""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "tags.json"


class TagLibrary:
    """Persistent list of user-defined journal tags stored in a JSON file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(str(path)) if path is not None else _DEFAULT_PATH

    def load(self) -> list[str]:
        """Return sorted list of tags from disk."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return sorted(set(str(t) for t in data.get("tags", [])))
        except (OSError, json.JSONDecodeError, KeyError):
            return []

    def add(self, tag: str) -> None:
        """Add *tag* to the library if not already present."""
        tag = tag.strip().lower()
        if not tag:
            return
        tags = self.load()
        if tag not in tags:
            tags.append(tag)
            self._save(sorted(tags))

    def _save(self, tags: list[str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"tags": tags}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
