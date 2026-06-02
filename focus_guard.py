"""Compatibility shim for legacy standalone entrypoint."""

# Importing this module preserves legacy side effects from the original file.
try:
	from legacy.focus_guard import *  # noqa: F401,F403
except ModuleNotFoundError:
	from purity_app.legacy.focus_guard import *  # noqa: F401,F403
