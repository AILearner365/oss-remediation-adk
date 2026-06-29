from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence


def run_command(command: Sequence[str], cwd: str | Path | None = None, timeout: int = 1800) -> dict:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": list(command),
            "exitCode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except FileNotFoundError as exc:
        return {"command": list(command), "exitCode": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {
            "command": list(command),
            "exitCode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "Command timed out",
        }
