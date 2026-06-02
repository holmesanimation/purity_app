from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

from purity_app.services.browser_session import BrowserSessionManager, ExtensionHeartbeatMonitor
from purity_app.services.browser_session_api_server import BrowserSessionApiServer


def test_extension_heartbeat_endpoint_records_status(tmp_path: Path) -> None:
    session_manager = BrowserSessionManager(tmp_path)
    heartbeat_monitor = ExtensionHeartbeatMonitor(tmp_path)
    server = BrowserSessionApiServer(session_manager, heartbeat_monitor, host="127.0.0.1", port=0)
    server.start()

    try:
        request = Request(
            f"http://127.0.0.1:{server.port}/extension-heartbeat",
            data=json.dumps(
                {
                    "extension_version": "0.1.0",
                    "instance_id": "test-instance",
                    "source": "test",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.stop()

    assert payload["healthy"] is True
    assert payload["extension_version"] == "0.1.0"
    assert payload["instance_id"] == "test-instance"