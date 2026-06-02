from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from services.browser_session import BrowserSessionManager, ExtensionHeartbeatMonitor


class _BrowserSessionRequestHandler(BaseHTTPRequestHandler):
    session_manager: BrowserSessionManager | None = None
    heartbeat_monitor: ExtensionHeartbeatMonitor | None = None

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/browser-session":
            self._write_json(404, {"error": "not_found"})
            return

        manager = self.session_manager
        if manager is None:
            self._write_json(503, {"error": "session_manager_unavailable"})
            return

        self._write_json(200, manager.get_session_payload())

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json_body()
        if self.path == "/browser-session/allow":
            manager = self.session_manager
            if manager is None:
                self._write_json(503, {"error": "session_manager_unavailable"})
                return

            url = str(body.get("url") or "").strip() if isinstance(body, dict) else ""
            if not url:
                self._write_json(400, {"error": "url_required"})
                return

            try:
                payload = manager.allow_url(url)
            except ValueError as exc:
                self._write_json(400, {"error": "invalid_url", "message": str(exc)})
                return

            self._write_json(200, payload)
            return

        if self.path == "/extension-heartbeat":
            monitor = self.heartbeat_monitor
            if monitor is None:
                self._write_json(503, {"error": "heartbeat_monitor_unavailable"})
                return

            payload = body if isinstance(body, dict) else {}
            status = monitor.record_heartbeat(
                extension_version=str(payload.get("extension_version") or ""),
                instance_id=str(payload.get("instance_id") or ""),
                source=str(payload.get("source") or "chrome_extension"),
            )
            self._write_json(200, status)
            return

        self._write_json(404, {"error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BrowserSessionApiServer:
    def __init__(
        self,
        session_manager: BrowserSessionManager,
        heartbeat_monitor: ExtensionHeartbeatMonitor | None = None,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        self._session_manager = session_manager
        self._heartbeat_monitor = heartbeat_monitor
        self._host = host
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        if self._server is not None:
            return
        _BrowserSessionRequestHandler.session_manager = self._session_manager
        _BrowserSessionRequestHandler.heartbeat_monitor = self._heartbeat_monitor
        self._server = ThreadingHTTPServer((self._host, self._port), _BrowserSessionRequestHandler)
        self._port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None