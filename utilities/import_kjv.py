"""One-off importer: populates the BibleLibrary with the full KJV text.

Source: https://github.com/wldeh/bible-api (raw.githubusercontent.com), which
serves one JSON file per chapter at
``bibles/en-kjv/books/<book>/chapters/<chapter>.json``.

Run with: python -m purity_app.utilities.import_kjv
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.bible_canon import BOOKS, display_ref, normalize_ref  # noqa: E402
from services.bible_library import BibleLibrary  # noqa: E402


def resolve_data_root() -> Path:
    """Mirrors services.web_requests.resolve_data_root without its extra deps."""
    return Path(os.environ.get("PURITY_DATA_ROOT", Path.home() / ".purity"))

_BASE_URL = "https://raw.githubusercontent.com/wldeh/bible-api/main/bibles/en-kjv/books/{book}/chapters/{chapter}.json"
_VERSION_NAME = "KJV"


def _fetch_chapter(book_key: str, chapter: int) -> list[dict]:
    url = _BASE_URL.format(book=book_key, chapter=chapter)
    req = urllib.request.Request(url, headers={"User-Agent": "purity_app-kjv-import"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("data", [])


def main() -> None:
    library = BibleLibrary(resolve_data_root())
    total_verses = 0
    for book_key, _display, verses_per_chapter in BOOKS:
        for chapter_num in range(1, len(verses_per_chapter) + 1):
            try:
                entries = _fetch_chapter(book_key, chapter_num)
            except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
                traceback.print_exc()
                continue
            seen_verses: set[str] = set()
            for entry in entries:
                verse_str = entry.get("verse")
                text = entry.get("text")
                if not verse_str or not text or verse_str in seen_verses:
                    continue
                seen_verses.add(verse_str)
                verse_num = int(verse_str)
                key = normalize_ref(book_key, chapter_num, verse_num)
                display = display_ref(book_key, chapter_num, verse_num)
                # Bypass BibleLibrary.set_version's per-call disk write; save once at the end instead.
                entry_data = library._data.setdefault(key, {"display": display, "versions": []})
                entry_data["display"] = display
                versions = entry_data["versions"]
                for v in versions:
                    if v.get("version") == _VERSION_NAME:
                        v["text"] = text
                        break
                else:
                    versions.append({"version": _VERSION_NAME, "text": text})
                total_verses += 1
            print(f"{book_key} {chapter_num}: {len(seen_verses)} verses")
            time.sleep(0.05)
        library._save()
    print(f"Done. Imported {total_verses} verses.")


if __name__ == "__main__":
    main()
