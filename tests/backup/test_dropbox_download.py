from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from dropbox.files import FileMetadata, FolderMetadata

from services.backup.destinations.dropbox import download_dropbox_backup


@dataclass
class _Listing:
    entries: list
    has_more: bool = False
    cursor: str = ""


class _FakeClient:
    def __init__(self, tree: dict[str, dict[str, bytes]]) -> None:
        self._tree = tree  # {family_name: {filename: content_bytes}}

    def files_list_folder(self, path: str):
        if path.rstrip("/").count("/") == 0 or path in ("/purityappbackup", "/PurityAppBackup"):
            entries = [
                FolderMetadata(name=family, path_lower=f"/purityappbackup/{family}")
                for family in self._tree
            ]
            return _Listing(entries=entries)
        family = path.rstrip("/").split("/")[-1]
        files = self._tree.get(family, {})
        entries = [
            FileMetadata(
                name=filename,
                path_lower=f"{path}/{filename}",
                content_hash=self._hash(content),
            )
            for filename, content in files.items()
        ]
        return _Listing(entries=entries)

    def files_list_folder_continue(self, cursor: str):
        raise AssertionError("pagination not exercised in this fake")

    def files_download(self, path: str):
        family = path.rstrip("/").split("/")[-2]
        filename = path.rstrip("/").split("/")[-1]
        content = self._tree[family][filename]

        class _Response:
            def __init__(self, data: bytes) -> None:
                self.content = data

        return None, _Response(content)

    @staticmethod
    def _hash(data: bytes) -> str:
        import hashlib

        return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


def test_download_dropbox_backup_writes_files(tmp_path: Path) -> None:
    client = _FakeClient({"bible_library": {"bible_library.json": b'{"a": 1}'}})
    download_root = tmp_path / "download"

    download_dropbox_backup(client, "/PurityAppBackup", download_root)

    downloaded = download_root / "bible_library" / "bible_library.json"
    assert downloaded.exists()
    assert downloaded.read_bytes() == b'{"a": 1}'


def test_download_dropbox_backup_raises_on_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    client = _FakeClient({"notes": {"notes.jsonl": b'{"a": 1}\n'}})

    def _bad_hash(_content: bytes) -> str:
        return "0" * 64

    monkeypatch.setattr(client, "_hash", staticmethod(_bad_hash))

    with pytest.raises(ValueError):
        download_dropbox_backup(client, "/PurityAppBackup", tmp_path / "download")
