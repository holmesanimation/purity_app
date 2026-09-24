# Plan: Scheduled Task for Purity Supervisor

## Goal
Start `supervisor.py` at login and auto-restart it within 30 seconds if killed.
Requires elevation to disable or delete — closes the "kill from Task Manager" gap.

---

## Step 1 — Add `install_scheduled_task.py`

Run once as admin. Uses `schtasks` — no external dependencies.

```python
# install_scheduled_task.py
import subprocess, sys
from pathlib import Path

TASK_NAME  = "PuritySupervisor"
PYTHON     = sys.executable                         # pythonw.exe for no console window
SCRIPT     = str(Path(__file__).parent / "supervisor.py")
DATA_ROOT  = str(Path.home() / ".purity")           # or read from settings

XML = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <RestartOnFailure>
      <Interval>PT30S</Interval>
      <Count>99</Count>
    </RestartOnFailure>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions>
    <Exec>
      <Command>{PYTHON.replace("python.exe", "pythonw.exe")}</Command>
      <Arguments>"{SCRIPT}" --data-root "{DATA_ROOT}"</Arguments>
      <WorkingDirectory>{str(Path(__file__).parent)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

xml_path = Path(__file__).parent / "_purity_supervisor_task.xml"
xml_path.write_text(XML, encoding="utf-16")

subprocess.run([
    "schtasks", "/Create", "/F",
    "/TN", TASK_NAME,
    "/XML", str(xml_path),
], check=True)

xml_path.unlink()
print(f"Task '{TASK_NAME}' installed.")
```

---

## Step 2 — Add `uninstall_scheduled_task.py`

```python
# uninstall_scheduled_task.py
import subprocess
subprocess.run(["schtasks", "/Delete", "/F", "/TN", "PuritySupervisor"], check=True)
print("Task removed.")
```

---

## Step 3 — Remove the "Quit Supervisor" tray button

A task that auto-restarts is only useful if there is no easy quit path.
Remove these lines from `supervisor.py`:

```python
# Remove:
quit_action = menu.addAction("Quit Supervisor")
...
quit_action.triggered.connect(_on_quit_action)
```

Optionally replace with a password-gated action later.

---

## Step 4 — Update `_launch_supervisor()` in `app.py`

Once the task is installed the supervisor will already be running at login.
Prefer `schtasks /Run` (gets restart protection) over a raw `Popen`:

```python
def _launch_supervisor(data_root: Path) -> None:
    # Try the scheduled task first (preferred — gets restart protection).
    try:
        subprocess.Popen(
            ["schtasks", "/Run", "/TN", "PuritySupervisor"],
            creationflags=0x08000000,
        )
        return
    except Exception:
        pass
    # Fallback: direct spawn (task not installed).
    ...existing Popen code...
```

---

## Step 5 — Installation flow

```
Run once as admin:
    python install_scheduled_task.py

Thereafter:
    - Task starts supervisor at every login automatically
    - If killed → restarts in 30 s
    - schtasks /Delete requires elevation to undo
```

---

## Protection summary

| Threat | Result |
|---|---|
| Task Manager "End Task" on supervisor | Restarts in 30 s |
| `taskkill /F` on supervisor | Restarts in 30 s |
| Tray "Quit" button (removed) | No longer available |
| `schtasks /Delete` to remove task | Requires elevation |
| Disabling task in Task Scheduler GUI | Requires elevation |
