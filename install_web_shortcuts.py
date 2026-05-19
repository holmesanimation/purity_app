"""Creates guarded browser shortcuts in %LOCALAPPDATA%\\purity_app\\shortcuts.

Run once:
    python install_chrome_shortcut.py

Creates:
  - Chrome (Guarded).lnk  — routes Chrome through chrome_launcher.py
  - Internet Explorer (Guarded).lnk  — will route IE through explorer_launcher.py
    (placeholder; explorer_launcher.py is not yet implemented)

Add the shortcuts folder to your taskbar / Start menu instead of the default
browser shortcuts so every browser open goes through the Purity guard.
"""
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
_PYTHONW = Path(sys.executable).parent / "pythonw.exe"
if not _PYTHONW.exists():
    _PYTHONW = Path(sys.executable)  # fall back to python.exe

# Shortcut destination: %LOCALAPPDATA%\purity_app\shortcuts
_SHORTCUTS_DIR = Path(os.environ["LOCALAPPDATA"]) / "purity_app" / "shortcuts"

_WEB_LAUNCHER     = _HERE / "web_launcher.py"
_EXPLORE_LAUNCHER = _HERE / "explorer_launcher.py"  # created later

_CHROME_ICO = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
_IE_ICO     = r"C:\Program Files\Internet Explorer\iexplore.exe"

_SHORTCUTS = [
    {
        "name":        "Chrome (Guarded).lnk",
        "launcher":    _WEB_LAUNCHER,
        "icon":        _CHROME_ICO,
        "description": "Open Chrome via Purity guard",
    },
    {
        "name":        "Internet Explorer (Guarded).lnk",
        "launcher":    _EXPLORE_LAUNCHER,
        "icon":        _IE_ICO,
        "description": "Open Internet Explorer via Purity guard",
    },
]


def _ps_create_shortcut(shortcut_path: Path, launcher: Path, icon: str, description: str) -> str:
    return f"""
$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut('{shortcut_path}')
$s.TargetPath       = '{_PYTHONW}'
$s.Arguments        = '"{launcher}"'
$s.WorkingDirectory = '{_HERE}'
$s.IconLocation     = '{icon},0'
$s.Description      = '{description}'
$s.Save()
Write-Host 'Created: {shortcut_path}'
"""


def main() -> None:
    _SHORTCUTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Shortcuts folder: {_SHORTCUTS_DIR}")

    errors = []
    for spec in _SHORTCUTS:
        path = _SHORTCUTS_DIR / spec["name"]
        ps = _ps_create_shortcut(path, spec["launcher"], spec["icon"], spec["description"])
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            errors.append(f"  {spec['name']}: {result.stderr.strip()}")

    if errors:
        print("\nErrors:", *errors, sep="\n", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nDone. Pin shortcuts from:\n  {_SHORTCUTS_DIR}")


if __name__ == "__main__":
    main()
