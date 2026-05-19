# purity_app/tests/test_purity_log_normalizer.py
"""Tests for PurityLogNormalizerSink and the purity kind map."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from purity_app.services.log_kind_map import (
    PURITY_KIND_MAP,
    TYPE_INTERVENTION,
    TYPE_NOTES,
    TYPE_REVIEW,
    TYPE_SYSTEM,
    TYPE_WEB,
    classify_purity_row_type,
    spec_for_purity_kind,
)
from shane_common.ui.log_viewer.base_normalizer_sink import BaseLogNormalizerSink, _parse_ts
from shane_common.ui.log_viewer.log_row_emitter import CallbackLogRowEmitter
from shane_common.ui.log_viewer.kind_spec import _DEFAULT_KIND_SPEC
from shane_common.ui.log_viewer.log_row import LogRow


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_sink():
    captured = []

    class _TestSink(BaseLogNormalizerSink):
        pass

    emitter = CallbackLogRowEmitter(on_row=lambda row: captured.append(row))
    sink = _TestSink(kind_spec_fn=spec_for_purity_kind, emitter=emitter)
    return sink, captured


def _make_envelope(kind: str, payload: dict | None = None, instrument: str | None = None) -> dict:
    env = {
        "v": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": "test-run",
        "kind": kind,
        "source": {"app": "purity_app"},
        "payload": payload or {},
    }
    if instrument is not None:
        env["instrument"] = instrument
    return env


# ------------------------------------------------------------------ #
# Kind-map tests
# ------------------------------------------------------------------ #

class TestPurityKindMap:
    def test_all_expected_kinds_present(self):
        expected = {
            "system.start", "system.stop", "system.alive",
            "chrome.opened", "chrome.allowed", "chrome.blocked",
            "popup.triggered", "note.created", "review.opened",
        }
        assert expected <= set(PURITY_KIND_MAP.keys())

    def test_unknown_kind_returns_default(self):
        result = spec_for_purity_kind("totally.unknown.kind")
        assert result is _DEFAULT_KIND_SPEC

    def test_chrome_blocked_is_warn_and_problem(self):
        spec = spec_for_purity_kind("chrome.blocked")
        assert spec.severity == "WARN"
        assert spec.problem is True

    def test_system_start_is_info_normal(self):
        spec = spec_for_purity_kind("system.start")
        assert spec.severity == "INFO"
        assert spec.importance == "NORMAL"

    def test_row_type_classifier_maps_known_kinds(self):
        row = LogRow(0.0, "system.start", "INFO", "system.start", None, "started")
        assert classify_purity_row_type(row) == TYPE_SYSTEM

        row = LogRow(0.0, "chrome.allowed", "INFO", "chrome.allowed", None, "allowed")
        assert classify_purity_row_type(row) == TYPE_WEB

        row = LogRow(0.0, "popup.triggered", "WARN", "popup.triggered", None, "popup")
        assert classify_purity_row_type(row) == TYPE_INTERVENTION

        row = LogRow(0.0, "note.created", "INFO", "note.created", None, "note")
        assert classify_purity_row_type(row) == TYPE_NOTES

        row = LogRow(0.0, "review.opened", "INFO", "review.opened", None, "review")
        assert classify_purity_row_type(row) == TYPE_REVIEW


# ------------------------------------------------------------------ #
# Normalisation tests
# ------------------------------------------------------------------ #

class TestPurityNormalization:
    def test_chrome_blocked_produces_warn_row(self):
        sink, captured = _make_sink()
        sink.emit(_make_envelope("chrome.blocked", {"url": "https://example.com"}))
        assert len(captured) == 1
        row = captured[0]
        assert row.severity == "WARN"
        assert "https://example.com" in row.message

    def test_system_start_produces_info_row(self):
        sink, captured = _make_sink()
        sink.emit(_make_envelope("system.start"))
        assert len(captured) == 1
        row = captured[0]
        assert row.severity == "INFO"
        assert row.importance == "NORMAL"

    def test_unknown_kind_does_not_raise(self):
        sink, captured = _make_sink()
        sink.emit(_make_envelope("no.such.kind"))
        assert len(captured) == 1
        row = captured[0]
        assert row.kind == "no.such.kind"

    def test_drain_buffer_returns_rows(self):
        sink, captured = _make_sink()
        sink.emit(_make_envelope("system.start"))
        sink.emit(_make_envelope("chrome.opened"))
        buffered = sink.drain_buffer()
        assert len(buffered) == 2
        assert buffered[0].kind == "system.start"
        assert buffered[1].kind == "chrome.opened"

    def test_emit_never_raises_on_malformed_envelope(self):
        sink, captured = _make_sink()
        sink.emit({})           # missing kind
        sink.emit({"kind": "chrome.blocked"})   # missing ts
        sink.emit({"kind": "chrome.blocked", "ts": "not-a-date"})
        # Should not raise; rows with missing/bad ts are dropped
        assert len(captured) == 0
