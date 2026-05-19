"""Standalone Chrome guard launcher.

Point your Chrome desktop shortcut here so every Chrome open goes through
the Purity guard popup first.  If approved, the real Chrome is launched.
If rejected, Chrome never starts.

Usage (via shortcut):
    pythonw chrome_launcher.py [chrome-args-or-url ...]
"""
import sys
from pathlib import Path

# Allow running as a standalone script from any working directory.
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from services.web_requests import (  # noqa: E402
    append_web_request_log,
    is_purity_app_running,
    resolve_data_root,
    start_purity_app,
    submit_web_launch_request,
)


def main() -> None:
    data_root = resolve_data_root()
    try:
        submit_web_launch_request(data_root, sys.argv[1:])

        if not is_purity_app_running(data_root):
            start_purity_app(data_root)
    except Exception as exc:
        append_web_request_log(
            data_root,
            "launcher.failed",
            "Standalone web launcher failed before handing off to Purity.",
            level="ERROR",
            details={"argv": list(sys.argv)},
            exc=exc,
        )
        raise

    sys.exit(0)


if __name__ == "__main__":
    main()
