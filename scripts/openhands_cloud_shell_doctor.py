#!/usr/bin/env python3
"""Read-only Cloud Shell continuity diagnostics. Never starts services or models."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

TASK = "task_65edba181e354c6f85a000b48b879f9c"
ARCHIVE = Path.home() / "openhands-native-poc-reports" / ("accepted-evidence-" + TASK)
RUN_ROOT = Path("/tmp/openhands-real-durable-task-recovered-v1")
NATIVE_ROOT = Path(os.environ.get("OH_POC_TMP", "/tmp/openhands-native-poc-1271-server-1551"))


def check_archive(directory: Path) -> dict:
    manifest_path = directory / "shareable" / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return {"status": "MISSING"}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative, expected in manifest["files"].items():
            path = directory / relative
            if (not path.is_file() or path.is_symlink()
                    or not path.resolve().is_relative_to(directory.resolve())):
                raise ValueError("Archive component missing or unsafe")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Archived file checksum mismatch")
        return {"status": "VERIFIED", "fileCount": len(manifest["files"])}
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return {"status": "INVALID"}


def doctor() -> dict:
    tools = {k: shutil.which(k) is not None for k in
             ("python3", "node", "npm", "uvx", "java", "mvn", "git", "osv-scanner")}
    archive = check_archive(ARCHIVE)
    runtime = {
        "durableDatabase": (RUN_ROOT / "state" / "tasks.sqlite3").is_file(),
        "hookConfig": (RUN_ROOT / "stop-hook.json").is_file(),
        "nativeLauncher": (NATIVE_ROOT / "launcher.pid").is_file(),
        "nativeSessionKey": (NATIVE_ROOT / "session-key.txt").is_file(),
    }
    required = ("python3", "node", "npm", "uvx", "java", "mvn", "git", "osv-scanner")
    ready = all(tools[x] for x in required) and all(runtime.values())
    return {
        "status": "LOCAL_PREREQUISITES_PRESENT" if ready else "RECOVERY_OR_SETUP_REQUIRED",
        "archive": archive, "tools": tools, "runtimeFiles": runtime,
        "credentialsVerified": False, "nativeServerHealthVerified": False,
        "scannerApprovalVerified": False, "modelRunAuthorized": False,
        "actions": ["Inspect missing prerequisites; use pinned native launcher only after review",
                    "Never reuse an expired conversation or replay dispatch claims",
                    "Check archived evidence checksums before attempting any restore"],
        "noChanges": True, "noModelRun": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(doctor(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
