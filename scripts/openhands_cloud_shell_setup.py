#!/usr/bin/env python3
"""Bounded Cloud Shell startup wrapper: no task dispatch or model execution.

Running with --start-native invokes the pinned existing launcher, which may
download/install packages and create disposable idle smoke conversations.
It never restores archived credentials or assumes /tmp task state survived.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
import openhands_cloud_shell_doctor as readiness


def start_native() -> dict:
    command = [sys.executable, str(ROOT / "scripts" / "openhands_native_poc.py"),
               "run", "--server-version", "1.55.1"]
    subprocess.run(command, check=True, timeout=1200)
    return {"status": "NATIVE_START_ATTEMPT_COMPLETED",
            "nativeVersion": "1.55.1", "noModelRun": True,
            "taskRestored": False, "oldConversationReused": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-native", action="store_true",
                        help="Explicitly start/install pinned native smoke stack; no model")
    args = parser.parse_args()
    try:
        if args.start_native:
            result = start_native()
        else:
            result = readiness.doctor()
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "noModelRun": True, "doNotRetryWithoutInspection": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
