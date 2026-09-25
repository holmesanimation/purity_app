"""Creates a 'Purity' launcher shortcut in %LOCALAPPDATA%\purity_app\shortcuts.

Run once:
    python utilities/install_app_shortcut.py

The shortcut runs launchers/app_launcher.py with pythonw. If Purity is
already running it asks the instance to raise its main window; otherwise it
starts the app via start_purity_app (honours Debug mode / console).

The icon is built from ui/icons/icon_48x48.png (largest available) and written
to ui/icons/purity.ico, which the shortcut references.
"""
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

_HERE = Path(__file__).parent.resolve()
_APP_DIR = _HERE.parent

_REQUIRED_VENV_PYTHONW = Path(r"D:\code\git\.venv\Scripts\pythonw.exe")
if _REQUIRED_VENV_PYTHONW.exists():
    _PYTHONW = _REQUIRED_VENV_PYTHONW
else:
    _PYTHONW = Path(sys.executable).parent / "pythonw.exe"
    if not _PYTHONW.exists():
        _PYTHONW = Path(sys.executable)

_SHORTCUTS_DIR = Path(os.environ["LOCALAPPDATA"]) / "purity_app" / "shortcuts"
_APP_SCRIPT = _APP_DIR / "launchers" / "app_launcher.py"
_ICON_PNG = _APP_DIR / "ui" / "icons" / "icon_48x48.png"
_ICON_ICO = _APP_DIR / "ui" / "icons" / "purity.ico"


def _build_ico() -> None:
    Image.open(_ICON_PNG).convert("RGBA").save(
        _ICON_ICO, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)]
    )


def main() -> None:
    _build_ico()
    _SHORTCUTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _SHORTCUTS_DIR / "Purity.lnk"
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut('{path}')
$s.TargetPath       = '{_PYTHONW}'
$s.Arguments        = '"{_APP_SCRIPT}"'
$s.WorkingDirectory = '{_APP_DIR}'
$s.IconLocation     = '{_ICON_ICO},0'
$s.Description      = 'Launch Purity, or show its main window if already running'
$s.Save()
"""
    result = subprocess.run(
        ["powershell", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"Created: {path}")


if __name__ == "__main__":
    main()
