"""Retention policy for dated notes snapshots (pure logic, no I/O).

A family's folder holds files named ``notes-YYYYMMDDTHHMMSSZ.db`` (database
snapshots) or ``notes-export-YYYYMMDD.jsonl`` (JSONL exports).  The policy keeps

* the newest ``keep_newest`` files, plus
* the newest file of each of the last ``keep_monthly`` calendar months,
* plus anything the caller ``protect``s (the snapshot just uploaded and verified),
* and always the single newest file, whatever the numbers say.

Only names matching the family's pattern are ever considered.  Anything else in
the folder is left strictly alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

_SNAPSHOT_RE = re.compile(r"^notes-(\d{8}T\d{6}Z)\.db$")
_EXPORT_RE = re.compile(r"^notes-export-(\d{8})\.jsonl$")

NOTES_DB_FAMILY = "notes_db"
NOTES_EXPORT_FAMILY = "notes_export"


@dataclass(frozen=True)
class RetentionPolicy:
    """How many dated files to keep (see the module docstring)."""

    keep_newest: int = 14
    keep_monthly: int = 12

    def __post_init__(self) -> None:
        if self.keep_newest < 1 or self.keep_monthly < 0:
            raise ValueError("keep_newest must be >= 1 and keep_monthly >= 0")


DEFAULT_POLICY = RetentionPolicy()


def snapshot_filename(moment: datetime) -> str:
    return f"notes-{moment.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}.db"


def export_filename(moment: datetime) -> str:
    return f"notes-export-{moment.astimezone(timezone.utc):%Y%m%d}.jsonl"


def parse_snapshot_time(name: str) -> datetime | None:
    """Time encoded in a snapshot file name, or ``None`` if it is not one."""
    m = _SNAPSHOT_RE.match(name)
    if m is None:
        return None
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def parse_export_time(name: str) -> datetime | None:
    m = _EXPORT_RE.match(name)
    if m is None:
        return None
    return datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)


def parser_for_family(family_name: str):
    """Return the file-name parser for a retention-managed family, or ``None``."""
    return {
        NOTES_DB_FAMILY: parse_snapshot_time,
        NOTES_EXPORT_FAMILY: parse_export_time,
    }.get(family_name)


def is_managed_name(family_name: str, name: str) -> bool:
    parser = parser_for_family(family_name)
    return parser is not None and parser(name) is not None


def _month_index(moment: datetime) -> int:
    return moment.year * 12 + (moment.month - 1)


def select_to_keep(
    names: Iterable[str],
    parse,
    policy: RetentionPolicy = DEFAULT_POLICY,
    *,
    protect: Iterable[str] = (),
    now: datetime | None = None,
) -> set[str]:
    """Return the subset of *names* (those *parse* accepts) that must be kept."""
    dated = sorted(
        ((parse(n), n) for n in names if parse(n) is not None),
        key=lambda pair: (pair[0], pair[1]),
        reverse=True,
    )  # newest first
    if not dated:
        return set()
    now = now or datetime.now(timezone.utc)

    keep: set[str] = {dated[0][1]}
    keep.update(n for _, n in dated[: policy.keep_newest])

    oldest_month = _month_index(now) - (policy.keep_monthly - 1)
    seen_months: set[int] = set()
    for moment, name in dated:  # newest first, so the first seen per month is that month's newest
        month = _month_index(moment)
        if policy.keep_monthly and oldest_month <= month <= _month_index(now) and month not in seen_months:
            seen_months.add(month)
            keep.add(name)

    managed = {n for _, n in dated}
    keep.update(p for p in protect if p in managed)
    return keep


def plan_prune(
    family_name: str,
    names: Iterable[str],
    policy: RetentionPolicy = DEFAULT_POLICY,
    *,
    protect: Iterable[str] = (),
    now: datetime | None = None,
) -> tuple[list[str], list[str]]:
    """Return ``(keep, delete)`` name lists (oldest first) for *family_name*'s folder.

    Files that do not match the family's naming pattern appear in neither list.
    """
    parse = parser_for_family(family_name)
    if parse is None:
        return [], []
    managed = sorted((n for n in names if parse(n) is not None), key=lambda n: (parse(n), n))
    keep = select_to_keep(managed, parse, policy, protect=protect, now=now)
    return [n for n in managed if n in keep], [n for n in managed if n not in keep]
