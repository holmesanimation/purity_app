"""Launcher for the Purity desktop shortcut.

If Purity is running, ask it to raise its main window; otherwise start it via
start_purity_app so Debug mode (console attached) and log redirection apply.

Usage (via shortcut):
    pythonw launchers/app_launcher.py
"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
_PROJECT_ROOT = _HERE.parent
_WORKSPACE_ROOT = _PROJECT_ROOT.parent
for _path in (_PROJECT_ROOT, _WORKSPACE_ROOT, _WORKSPACE_ROOT / "shane_common" / "src"):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from services.web_requests import (  # noqa: E402
    is_purity_app_running,
    resolve_data_root,
    start_purity_app,
    submit_show_app_request,
)


def main() -> int:
    data_root = resolve_data_root()
    if is_purity_app_running(data_root):
        submit_show_app_request(data_root, source="app_shortcut")
    else:
        start_purity_app(data_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
