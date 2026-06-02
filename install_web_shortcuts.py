"""Compatibility shim for the moved shortcut installer."""

try:
    from utilities.install_web_shortcuts import main
except ModuleNotFoundError:
    from purity_app.utilities.install_web_shortcuts import main


if __name__ == "__main__":
    main()
