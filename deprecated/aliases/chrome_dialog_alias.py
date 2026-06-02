"""Compatibility shim for moved chrome dialog module."""

import sys

try:
    from ui.intervention import chrome_dialog as _impl
except ModuleNotFoundError:
    from purity_app.ui.intervention import chrome_dialog as _impl

sys.modules[__name__] = _impl
