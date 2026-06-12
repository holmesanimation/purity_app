# purity_app/utilities/console_capture.py
# Re-exports from shane_common.  The real implementation lives at:
#   shane_common/src/shane_common/logging/console_capture.py

from shane_common.logging.console_capture import ConsoleCapture  # noqa: F401

__all__ = ["ConsoleCapture"]
