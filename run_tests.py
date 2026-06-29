#!/usr/bin/env python3
"""Run repository verification checks for the OSS Remediation ADK project.

The runner is intentionally simple and CI-friendly:
- compile Python sources
- run unit tests
- run fixture/workflow integration tests
- run end-to-end workflow tests
- return non-zero when any step fails
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Check:
    name: str
    command: Sequence[str]


def run_check(check: Check) -> bool:
    print("\n" + "=" * 80)
    print(f"Running: {check.name}")
    print("Command: " + " ".join(check.command))
    print("=" * 80)
    completed = subprocess.run(check.command, check=False)
    if completed.returncode == 0:
        print(f"PASS: {check.name}")
        return True
    print(f"FAIL: {check.name} (exit code {completed.returncode})")
    return False


def main() -> int:
    checks = [
        Check("Python compilation", [sys.executable, "-m", "compileall", "-q", "oss_remediation_agent"]),
        Check("Unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests/unit", "-p", "test_*.py", "-v"]),
        Check("Integration tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests/integration", "-p", "test_*.py", "-v"]),
        Check("End-to-end tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests/e2e", "-p", "test_*.py", "-v"]),
    ]

    print("OSS Remediation ADK Test Runner")
    print("-" * 80)
    results = [(check.name, run_check(check)) for check in checks]

    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")

    overall_passed = all(passed for _, passed in results)
    print("-" * 80)
    print(f"Overall Result: {'PASS' if overall_passed else 'FAIL'}")
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
