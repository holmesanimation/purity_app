from __future__ import annotations

import json
import time
from pathlib import Path

from purity_app.services.browser_session import (
    BrowserSessionManager,
    ExtensionHeartbeatMonitor,
    active_session_path,
    extract_allowed_domains,
    parse_allowed_urls,
)


def test_parse_allowed_urls_requires_http_or_https() -> None:
    assert parse_allowed_urls("https://example.com\nhttp://example.org/docs") == [
        "https://example.com",
        "http://example.org/docs",
    ]


def test_parse_allowed_urls_infers_https_for_bare_domains() -> None:
    assert parse_allowed_urls("chatgpt.com\ndocs.python.org/3/") == [
        "https://chatgpt.com",
        "https://docs.python.org/3/",
    ]


def test_parse_allowed_urls_rejects_invalid_entries() -> None:
    try:
        parse_allowed_urls("not a url")
    except ValueError as exc:
        assert "Invalid URL" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid URL")


def test_extract_allowed_domains_deduplicates_hosts() -> None:
    domains = extract_allowed_domains([
        "https://example.com",
        "https://example.com/path",
        "https://docs.python.org/3/",
    ])

    assert domains == ["example.com", "docs.python.org"]


def test_browser_session_manager_writes_active_session(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path)

    payload = manager.start_session(
        purpose="Work",
        allowed_urls=["https://example.com", "https://docs.python.org/3/"],
        duration_seconds=300,
    )

    assert payload["is_active"] is True
    assert payload["purpose"] == "Work"
    assert payload["allowed_urls"] == ["https://example.com", "https://docs.python.org/3/"]
    assert payload["allowed_domains"] == ["example.com", "docs.python.org"]
    written = json.loads(active_session_path(tmp_path).read_text(encoding="utf-8"))
    assert written["allowed_urls"] == payload["allowed_urls"]


def test_browser_session_manager_allow_url_appends_to_whitelist(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path)
    manager.start_session(
        purpose="Research",
        allowed_urls=["https://example.com"],
        duration_seconds=300,
    )

    payload = manager.allow_url("https://new.example.org/path")

    assert payload["allowed_urls"] == ["https://example.com", "https://new.example.org/path"]
    assert payload["allowed_domains"] == ["example.com", "new.example.org"]


def test_browser_session_manager_expires_session(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path)
    manager.start_session(
        purpose="Work",
        allowed_urls=["https://example.com"],
        duration_seconds=1,
    )

    time.sleep(1.1)

    assert manager.get_session_payload() == {"is_active": False}


def test_extension_heartbeat_monitor_records_healthy_status(tmp_path: Path) -> None:
    monitor = ExtensionHeartbeatMonitor(tmp_path, stale_after_seconds=5.0)

    status = monitor.record_heartbeat(
        extension_version="0.1.0",
        instance_id="abc123",
    )

    assert status["healthy"] is True
    assert status["extension_version"] == "0.1.0"
    assert status["instance_id"] == "abc123"


def test_extension_heartbeat_monitor_becomes_stale(tmp_path: Path) -> None:
    monitor = ExtensionHeartbeatMonitor(tmp_path, stale_after_seconds=0.2)
    monitor.record_heartbeat()

    time.sleep(0.25)

    assert monitor.get_status()["healthy"] is False


# ---------------------------------------------------------------------------
# Override counter tests
# ---------------------------------------------------------------------------

def test_allow_url_increments_override_count_from_zero(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path)
    manager.start_session(
        purpose="Research",
        allowed_urls=["https://example.com"],
        duration_seconds=300,
    )

    payload = manager.allow_url("https://new.example.org")
    assert payload["override_count"] == 1


def test_allow_url_increments_override_count_on_each_call(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path)
    manager.start_session(
        purpose="Research",
        allowed_urls=["https://example.com"],
        duration_seconds=300,
    )

    manager.allow_url("https://a.example.org")
    manager.allow_url("https://b.example.org")
    payload = manager.allow_url("https://c.example.org")
    assert payload["override_count"] == 3


def test_allow_url_records_last_override_url(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path)
    manager.start_session(
        purpose="Research",
        allowed_urls=["https://example.com"],
        duration_seconds=300,
    )

    payload = manager.allow_url("https://special.example.org/page")
    assert payload["last_override_url"] == "https://special.example.org/page"


def test_allow_url_records_last_override_ts(tmp_path: Path) -> None:
    before = time.time()
    manager = BrowserSessionManager(tmp_path)
    manager.start_session(
        purpose="Research",
        allowed_urls=["https://example.com"],
        duration_seconds=300,
    )
    payload = manager.allow_url("https://new.example.org")
    after = time.time()

    assert "last_override_ts" in payload
    assert before <= payload["last_override_ts"] <= after


def test_clear_session_removes_override_count(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path)
    manager.start_session(
        purpose="Research",
        allowed_urls=["https://example.com"],
        duration_seconds=300,
    )
    manager.allow_url("https://new.example.org")

    cleared = manager.clear_session()
    assert "override_count" not in cleared
    assert not cleared.get("is_active", True)


def test_get_session_payload_reflects_override_count(tmp_path: Path) -> None:
    manager = BrowserSessionManager(tmp_path)
    manager.start_session(
        purpose="Research",
        allowed_urls=["https://example.com"],
        duration_seconds=300,
    )
    manager.allow_url("https://new.example.org")

    payload = manager.get_session_payload()
    assert payload["override_count"] == 1
    assert payload["last_override_url"] == "https://new.example.org"
