#!/usr/bin/env python3
"""Read-only prerequisites for the first *real* Maven/OSV native remediation.

Does not run any LLM, edit the repository, download artifacts, run Maven goals
or launch a vulnerability scan. PASS means prerequisites only, not remediation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def command(args: list[str], cwd: Path, *, timeout: int = 15) -> dict:
    try:
        p = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "errorType": type(exc).__name__}
    # Do not include arbitrary command output: proxies, home paths and tokens
    # may be printed in environment-specific Maven / Java diagnostics.
    return {"ok": p.returncode == 0, "exitCode": p.returncode}


def preflight(repository: Path, scanner_executable: Path) -> dict:
    repository = repository.expanduser()
    scanner_executable = scanner_executable.expanduser()
    if repository.is_symlink() or scanner_executable.is_symlink():
        raise ValueError("Repository and scanner cannot be symbolic links")
    repository = repository.resolve(strict=True)
    scanner_executable = scanner_executable.resolve(strict=True)
    if not repository.is_dir():
        raise ValueError("Repository must be an existing directory")
    if scanner_executable.is_symlink() or not scanner_executable.is_file():
        raise ValueError("Scanner must be an installed, non-symlink file")
    pom = repository / "pom.xml"
    if not pom.is_file() or pom.is_symlink():
        raise ValueError("Repository root must contain a regular pom.xml")
    head = command(["git", "rev-parse", "--verify", "HEAD"], repository)
    inside = command(["git", "rev-parse", "--is-inside-work-tree"], repository)
    # Require a clean working tree so a later disposable worktree starts from
    # a reproducible commit, not untracked/modified local changes.
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repository, text=True, capture_output=True,
            timeout=15, check=False,
        )
        clean = status.returncode == 0 and not status.stdout
    except (OSError, subprocess.TimeoutExpired):
        clean = False
    maven = command(["mvn", "-version"], repository)
    scanner = command([str(scanner_executable), "--version"], repository)
    checks = {
        "gitRepository": inside["ok"] and head["ok"],
        "cleanGitWorktree": clean,
        "pomPresent": True,
        "mavenAvailable": maven["ok"],
        "approvedScannerBinaryInvocable": scanner["ok"],
    }
    return {
        "kind": "real-remediation-prerequisite-check",
        "verdict": "READY_FOR_BASELINE_SETUP" if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "notProven": [
            "Scanner approval and exact configured profile",
            "Actual Maven build and dependency resolution",
            "OSV vulnerability baseline and target findings",
            "Fixed-version Maven build and OSV comparison",
            "Autonomous agent remediation", "Independent acceptance",
        ],
        "noScannerExecuted": True,
        "noModelExecuted": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--scanner", type=Path, required=True,
                        help="Existing approved OSV scanner binary (absolute or relative path)")
    args = parser.parse_args()
    try:
        report = preflight(args.repository, args.scanner)
    except (OSError, ValueError) as exc:
        report = {
            "kind": "real-remediation-prerequisite-check", "verdict": "BLOCKED",
            "errorType": type(exc).__name__,
            "noScannerExecuted": True, "noModelExecuted": True,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "READY_FOR_BASELINE_SETUP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
