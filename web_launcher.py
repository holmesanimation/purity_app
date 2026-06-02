"""Compatibility shim — delegates to web_viewer.py (canonical entry point)."""

try:
    from web_viewer import main
except ModuleNotFoundError:
    from purity_app.web_viewer import main  # type: ignore[no-redef]


if __name__ == "__main__":
    main()
