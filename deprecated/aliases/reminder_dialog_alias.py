"""Compatibility shim for moved reminder dialog module."""

import sys

try:
    from ui.intervention import reminder_dialog as _impl
except ModuleNotFoundError:
    from purity_app.ui.intervention import reminder_dialog as _impl

sys.modules[__name__] = _impl
