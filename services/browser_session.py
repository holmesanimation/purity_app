from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from shane_common.io.atomic import write_json_atomic


def browser_sessions_dir(data_root: Path) -> Path:
    return Path(data_root) / "data" / "browser_sessions"


def active_session_path(data_root: Path) -> Path:
    return browser_sessions_dir(data_root) / "active_session.json"


def extension_heartbeat_path(data_root: Path) -> Path:
    return browser_sessions_dir(data_root) / "extension_heartbeat.json"


def _is_valid_hostname(hostname: str) -> bool:
    host = str(hostname or "").strip().lower()
    if not host or any(char.isspace() for char in host):
        return False
    if host == "localhost":
        return True
    try:
        ip_address(host)
        return True
    except ValueError:
        pass
    return "." in host


def parse_allowed_urls(raw_text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for line in str(raw_text).splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid URL: {candidate}")
        if not _is_valid_hostname(parsed.hostname or ""):
            raise ValueError(f"Invalid URL: {candidate}")
        normalized = parsed.geturl()
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def extract_allowed_domains(urls: list[str]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for url in urls:
        parsed = urlparse(str(url).strip())
        host = (parsed.hostname or "").strip().lower()
        if not host or host in seen:
            continue
        seen.add(host)
        domains.append(host)
    return domains


@dataclass(slots=True)
class BrowsingSession:
    is_active: bool
    expires_ts: int
    allowed_domains: list[str]
    allowed_urls: list[str]
    purpose: str

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class BrowserSessionManager:
    def __init__(self, data_root: Path):
        self._data_root = Path(data_root)
        self._lock = threading.Lock()
        self._path = active_session_path(self._data_root)

    @property
    def session_path(self) -> Path:
        return self._path

    def start_session(self, *, purpose: str, allowed_urls: list[str], duration_seconds: int) -> dict[str, Any]:
        now = int(time.time())
        session = BrowsingSession(
            is_active=True,
            expires_ts=now + max(1, int(duration_seconds)),
            allowed_domains=extract_allowed_domains(allowed_urls),
            allowed_urls=list(allowed_urls),
            purpose=str(purpose),
        )
        return self._write_payload(session.to_payload())

    def clear_session(self) -> dict[str, Any]:
        return self._write_payload({"is_active": False})

    def get_session_payload(self) -> dict[str, Any]:
        with self._lock:
            payload = self._read_payload_unlocked()
            if payload.get("is_active") and self._is_expired(payload):
                payload = {"is_active": False}
                self._write_payload_unlocked(payload)
            return payload

    def allow_url(self, url: str) -> dict[str, Any]:
        parsed_urls = parse_allowed_urls(str(url))
        if not parsed_urls:
            raise ValueError("URL is required.")

        with self._lock:
            payload = self._read_payload_unlocked()
            if not payload.get("is_active") or self._is_expired(payload):
                payload = {"is_active": False}
                self._write_payload_unlocked(payload)
                return payload

            allowed_urls = list(payload.get("allowed_urls") or [])
            candidate = parsed_urls[0]
            if candidate not in allowed_urls:
                allowed_urls.append(candidate)
            payload["allowed_urls"] = allowed_urls
            payload["allowed_domains"] = extract_allowed_domains(allowed_urls)
            payload["override_count"] = int(payload.get("override_count") or 0) + 1
            payload["last_override_ts"] = time.time()
            payload["last_override_url"] = candidate
            self._write_payload_unlocked(payload)
            return payload

    def _write_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._write_payload_unlocked(payload)
            return dict(payload)

    def _read_payload_unlocked(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"is_active": False}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"is_active": False}
        if isinstance(payload, dict):
            return payload
        return {"is_active": False}

    def _write_payload_unlocked(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self._path, payload, sort_keys=False)

    @staticmethod
    def _is_expired(payload: dict[str, Any]) -> bool:
        try:
            expires_ts = int(payload.get("expires_ts") or 0)
        except (TypeError, ValueError):
            return True
        return expires_ts <= int(time.time())


class ExtensionHeartbeatMonitor:
    def __init__(self, data_root: Path, *, stale_after_seconds: float = 75.0):
        self._data_root = Path(data_root)
        self._lock = threading.Lock()
        self._path = extension_heartbeat_path(self._data_root)
        self._stale_after_seconds = float(stale_after_seconds)

    @property
    def heartbeat_path(self) -> Path:
        return self._path

    @property
    def stale_after_seconds(self) -> float:
        return self._stale_after_seconds

    def clear(self) -> dict[str, Any]:
        payload = {
            "is_alive": False,
            "healthy": False,
            "stale_after_seconds": self._stale_after_seconds,
        }
        return self._write_payload(payload)

    def record_heartbeat(
        self,
        *,
        extension_version: str = "",
        instance_id: str = "",
        source: str = "chrome_extension",
    ) -> dict[str, Any]:
        now = time.time()
        payload = {
            "is_alive": True,
            "healthy": True,
            "last_seen_ts": now,
            "age_seconds": 0.0,
            "stale_after_seconds": self._stale_after_seconds,
            "extension_version": str(extension_version),
            "instance_id": str(instance_id),
            "source": str(source),
        }
        return self._write_payload(payload)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            payload = self._read_payload_unlocked()
            return self._decorate_status(payload)

    def is_healthy(self) -> bool:
        return bool(self.get_status().get("healthy"))

    def _write_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._write_payload_unlocked(payload)
            return self._decorate_status(payload)

    def _read_payload_unlocked(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"is_alive": False, "stale_after_seconds": self._stale_after_seconds}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"is_alive": False, "stale_after_seconds": self._stale_after_seconds}
        if isinstance(payload, dict):
            payload.setdefault("stale_after_seconds", self._stale_after_seconds)
            return payload
        return {"is_alive": False, "stale_after_seconds": self._stale_after_seconds}

    def _write_payload_unlocked(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self._path, payload, sort_keys=False)

    def _decorate_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        status = dict(payload)
        status["stale_after_seconds"] = self._stale_after_seconds
        last_seen_ts = status.get("last_seen_ts")
        if not status.get("is_alive") or last_seen_ts is None:
            status["healthy"] = False
            status["age_seconds"] = None
            return status
        try:
            age_seconds = max(0.0, time.time() - float(last_seen_ts))
        except (TypeError, ValueError):
            status["healthy"] = False
            status["age_seconds"] = None
            return status
        status["age_seconds"] = age_seconds
        status["healthy"] = age_seconds < self._stale_after_seconds
        return status