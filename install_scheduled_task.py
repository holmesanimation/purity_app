from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from services.settings_schemas import build_purity_settings_manager, resolve_purity_data_root

TASK_NAME = "PuritySupervisor"


def _resolve_pythonw_exe() -> Path:
    # Pinned to the venv that has PySide6 + dropbox installed, rather than
    # whatever interpreter happens to run this installer (which previously
    # baked a broken system Python into the scheduled task).
    required_venv_pythonw = Path(r"D:\code\git\.venv\Scripts\pythonw.exe")
    if required_venv_pythonw.exists():
        return required_venv_pythonw

    python_exe = Path(sys.executable).resolve()
    if python_exe.name.lower() == "pythonw.exe":
        return python_exe
    pythonw_exe = python_exe.with_name("pythonw.exe")
    if pythonw_exe.exists():
        return pythonw_exe
    return python_exe


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _build_task_xml(
    *,
    pythonw_exe: Path,
    supervisor_script: Path,
    app_script: Path,
    data_root: Path,
) -> str:
    computer = os.environ.get("COMPUTERNAME", "localhost")
    user = f"{computer}\\{getpass.getuser()}"

    purity_app_cmd = json.dumps([str(pythonw_exe), str(app_script)])
    args = subprocess.list2cmdline(
        [
            str(supervisor_script),
            "--data-root",
            str(data_root),
            "--purity-app-cmd",
            purity_app_cmd,
        ]
    )

    return f"""<?xml version=\"1.0\" encoding=\"UTF-16\"?>
<Task version=\"1.4\" xmlns=\"http://schemas.microsoft.com/windows/2004/02/mit/task\">
  <RegistrationInfo>
    <Description>Purity Supervisor watchdog process.</Description>
    <URI>\\{TASK_NAME}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{_esc(user)}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id=\"Author\">
      <UserId>{_esc(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>99</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context=\"Author\">
    <Exec>
      <Command>{_esc(str(pythonw_exe))}</Command>
      <Arguments>{_esc(args)}</Arguments>
      <WorkingDirectory>{_esc(str(supervisor_script.parent))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def main() -> int:
    project_root = Path(__file__).resolve().parent
    supervisor_script = project_root / "supervisor.py"
    app_script = project_root / "app.py"

    pythonw_exe = _resolve_pythonw_exe()
    settings_manager = build_purity_settings_manager()
    data_root = resolve_purity_data_root(settings_manager)

    xml = _build_task_xml(
        pythonw_exe=pythonw_exe,
        supervisor_script=supervisor_script,
        app_script=app_script,
        data_root=data_root,
    )

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        tmp_path.write_text(xml, encoding="utf-16")

        subprocess.run(
            ["schtasks", "/Create", "/F", "/TN", TASK_NAME, "/XML", str(tmp_path)],
            check=True,
        )
        print(f"Installed scheduled task: {TASK_NAME}")
        return 0
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
