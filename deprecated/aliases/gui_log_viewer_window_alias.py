"""Compatibility shim for moved log viewer window."""

import sys

try:
    from ui.system import log_viewer_window as _impl
except ModuleNotFoundError:
    from purity_app.ui.system import log_viewer_window as _impl

sys.modules[__name__] = _impl
