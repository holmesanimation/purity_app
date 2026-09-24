"""Data models for the Purity local backup subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class RunStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DropboxAuthState(str, Enum):
    """Dropbox credential/connection state, independent of the local backup path."""

    DISABLED = "disabled"
    AUTH_REQUIRED = "auth_required"
    READY = "ready"
    REAUTH_REQUIRED = "reauth_required"


class BackupCopyOutcome(str, Enum):
    """Outcome of a manifest-aware copy/refresh attempt (superset of shane_common's CopyOutcome)."""

    COPIED = "copied"
    ALREADY_PRESENT_IDENTICAL = "already_present_identical"
    REFRESHED = "refreshed"
    DESTINATION_CONFLICT = "destination_conflict"
    SOURCE_CHANGED_DURING_COPY = "source_changed_during_copy"


@dataclass(frozen=True)
class ManifestEntry:
    """Per-destination-file evidence recorded after the last verified copy/refresh."""

    content_hash: str
    size: int
    verified_at: str

    def to_dict(self) -> dict:
        return {
            "content_hash": self.content_hash,
            "size": self.size,
            "verified_at": self.verified_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ManifestEntry":
        return cls(
            content_hash=str(data.get("content_hash", "")),
            size=int(data.get("size", 0)),
            verified_at=str(data.get("verified_at", "")),
        )


@dataclass(frozen=True)
class RefreshResult:
    """Result of ``LocalFilesystemDestination.refresh_or_copy()``."""

    outcome: BackupCopyOutcome
    manifest_entry: ManifestEntry | None
    bytes_copied: int
    error: str | None = None


@dataclass(frozen=True)
class BackupSourceFamily:
    """One named group of source files discovered by ``PurityBackupCatalog``."""

    name: str
    paths: tuple[Path, ...]
    required: bool


@dataclass
class FamilyResult:
    family_name: str
    files_verified: int = 0
    files_failed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "family_name": self.family_name,
            "files_verified": self.files_verified,
            "files_failed": self.files_failed,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FamilyResult":
        return cls(
            family_name=str(data.get("family_name", "")),
            files_verified=int(data.get("files_verified", 0)),
            files_failed=int(data.get("files_failed", 0)),
            errors=list(data.get("errors", [])),
        )


@dataclass
class BackupRunResult:
    run_id: str
    started_at: str
    completed_at: str | None
    status: RunStatus
    file_count: int
    verified_count: int
    failed_count: int
    bytes_copied: int
    last_error: str | None
    family_results: list[FamilyResult]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "file_count": self.file_count,
            "verified_count": self.verified_count,
            "failed_count": self.failed_count,
            "bytes_copied": self.bytes_copied,
            "last_error": self.last_error,
            "family_results": [fr.to_dict() for fr in self.family_results],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupRunResult":
        return cls(
            run_id=str(data.get("run_id", "")),
            started_at=str(data.get("started_at", "")),
            completed_at=data.get("completed_at"),
            status=RunStatus(data.get("status", RunStatus.FAILED.value)),
            file_count=int(data.get("file_count", 0)),
            verified_count=int(data.get("verified_count", 0)),
            failed_count=int(data.get("failed_count", 0)),
            bytes_copied=int(data.get("bytes_copied", 0)),
            last_error=data.get("last_error"),
            family_results=[
                FamilyResult.from_dict(fr) for fr in data.get("family_results", [])
            ],
        )
