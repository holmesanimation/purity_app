"""Local filesystem backup destination.

Mirrors each source family into ``<destination_root>/<family_name>/<filename>``.

``refresh_or_copy`` distinguishes a legitimate source update from an
independently modified destination using the manifest of previously verified
content hashes (see ``services.backup.state``):

1. destination absent                                  -> COPIED
2. destination content == current source                -> ALREADY_PRESENT_IDENTICAL
3. destination differs from source, but destination hash
   still matches the manifest's last-verified hash       -> REFRESHED (safe replace)
4. destination differs from source AND destination hash
   no longer matches the manifest                        -> DESTINATION_CONFLICT

Case 3 never overwrites the destination in place: the new content is copied
to a temporary sibling file, verified, then atomically swapped in via
``os.replace``. ``copy_file_verified`` itself is never modified or bypassed
for cases 1/2 — it already handles those safely.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from shane_common.runtime.transfer.copy import CopyOutcome, CopyVerifyResult, copy_file_verified
from shane_common.runtime.transfer.hashing import sha256_file

from ..models import BackupCopyOutcome, ManifestEntry, RefreshResult


class LocalFilesystemDestination:
    def __init__(self, destination_root: Path) -> None:
        self._root = Path(destination_root)

    @property
    def root(self) -> Path:
        return self._root

    def target_path(self, family_name: str, source_path: Path) -> Path:
        return self._root / family_name / Path(source_path).name

    def manifest_key(self, family_name: str, source_path: Path) -> str:
        return f"{family_name}/{Path(source_path).name}"

    def put(self, family_name: str, source_path: Path) -> CopyVerifyResult:
        """Legacy plain verified copy (no refresh semantics). Kept for direct use/tests."""
        target = self.target_path(family_name, source_path)
        return copy_file_verified(Path(source_path), target)

    def refresh_or_copy(
        self,
        family_name: str,
        source_path: Path,
        manifest: dict[str, ManifestEntry],
    ) -> RefreshResult:
        source_path = Path(source_path)
        target = self.target_path(family_name, source_path)
        key = self.manifest_key(family_name, source_path)

        if not target.exists():
            copy_result = copy_file_verified(source_path, target)
            if copy_result.outcome == CopyOutcome.COPIED:
                return RefreshResult(
                    outcome=BackupCopyOutcome.COPIED,
                    manifest_entry=ManifestEntry(
                        content_hash=copy_result.destination_hash or "",
                        size=copy_result.destination_size or 0,
                        verified_at=_now_iso(),
                    ),
                    bytes_copied=copy_result.destination_size or 0,
                )
            if copy_result.outcome == CopyOutcome.SOURCE_CHANGED_DURING_COPY:
                return RefreshResult(
                    outcome=BackupCopyOutcome.SOURCE_CHANGED_DURING_COPY,
                    manifest_entry=None,
                    bytes_copied=0,
                )
            # Race: another process created/matched the destination between our
            # exists() check and the copy attempt. Fall through to the
            # existing-destination comparison below for a definitive answer.

        source_hash = sha256_file(source_path)
        dest_hash = sha256_file(target)

        if dest_hash == source_hash:
            return RefreshResult(
                outcome=BackupCopyOutcome.ALREADY_PRESENT_IDENTICAL,
                manifest_entry=ManifestEntry(
                    content_hash=dest_hash,
                    size=target.stat().st_size,
                    verified_at=_now_iso(),
                ),
                bytes_copied=0,
            )

        recorded = manifest.get(key)
        if recorded is None or recorded.content_hash != dest_hash:
            return RefreshResult(
                outcome=BackupCopyOutcome.DESTINATION_CONFLICT,
                manifest_entry=None,
                bytes_copied=0,
                error=f"{source_path}: destination_conflict",
            )

        return self._safe_refresh(source_path, target, source_hash)

    def _safe_refresh(self, source_path: Path, target: Path, source_hash_before: str) -> RefreshResult:
        source_size_before = source_path.stat().st_size
        fd, tmp_name = tempfile.mkstemp(prefix=".transfer_", suffix=".tmp", dir=str(target.parent))
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            shutil.copyfile(source_path, tmp_path)

            source_hash_after = sha256_file(source_path)
            if source_hash_after != source_hash_before or source_path.stat().st_size != source_size_before:
                return RefreshResult(
                    outcome=BackupCopyOutcome.SOURCE_CHANGED_DURING_COPY,
                    manifest_entry=None,
                    bytes_copied=0,
                )

            tmp_hash = sha256_file(tmp_path)
            if tmp_hash != source_hash_before:
                return RefreshResult(
                    outcome=BackupCopyOutcome.DESTINATION_CONFLICT,
                    manifest_entry=None,
                    bytes_copied=0,
                    error=f"{source_path}: refresh verification failed, existing backup left intact",
                )

            tmp_size = tmp_path.stat().st_size
            os.replace(tmp_path, target)
            tmp_path = target  # already moved; skip cleanup below

            return RefreshResult(
                outcome=BackupCopyOutcome.REFRESHED,
                manifest_entry=ManifestEntry(
                    content_hash=tmp_hash,
                    size=tmp_size,
                    verified_at=_now_iso(),
                ),
                bytes_copied=tmp_size,
            )
        finally:
            if tmp_path != target and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

