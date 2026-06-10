from __future__ import annotations

import subprocess

TASK_NAME = "PuritySupervisor"


def main() -> int:
    subprocess.run(
        ["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
        check=True,
    )
    print(f"Removed scheduled task: {TASK_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
