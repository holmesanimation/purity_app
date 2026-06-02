"""Compatibility shim for moved log normalizer sink."""

import sys

try:
    from ui.system import log_normalizer_sink as _impl
except ModuleNotFoundError:
    from purity_app.ui.system import log_normalizer_sink as _impl

sys.modules[__name__] = _impl
