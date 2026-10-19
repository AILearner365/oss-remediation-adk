#!/usr/bin/env python3
"""Prepare an isolated, commit-pinned copy of the real Maven POC repository.

No Maven, scanner, OpenHands, model, remote push, PR or task registration.
A unique local destination is required; never modifies the source GitHub branch.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = "https://github.com/AILearner365/maven-multimodule-app.git"
REFERENCE = "main-runrunning"
SHA = re.compile(r"^[0-9a-f]{40}$")
MODULES = ("task-common", "task-domain", "task-service", "task-web")


def run_git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                            text=True, check=False, timeout=120)
    if result.returncode:
        raise ValueError("Git checkout verification failed")
    return result.stdout.strip()


def prepare(destination: Path, expected: str) -> dict:
    if not SHA.fullmatch(expected):
        raise ValueError("An exact 40-character expected branch commit is required")
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new one, never overwrite")
    # Check remote ref before cloning; refuse if it moved.
    remote = run_git("ls-remote", "--exit-code", REPOSITORY,
                     "refs/heads/" + REFERENCE)
    actual = remote.split()[0]
    if actual != expected:
        raise ValueError("Reference branch moved from approved commit; review before proceeding")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_git("clone", "--single-branch", "--branch", REFERENCE,
            "--no-tags", REPOSITORY, str(destination))
    if run_git("-C", str(destination), "rev-parse", "HEAD") != expected:
        raise ValueError("Checkout does not match approved commit; retain for inspection")
    if run_git("-C", str(destination), "status", "--porcelain"):
        raise ValueError("Cloned repository is not clean")
    if run_git("-C", str(destination), "remote", "get-url", "origin") != REPOSITORY:
        raise ValueError("Unexpected clone origin")
    for path in ("pom.xml", *(m + "/pom.xml" for m in MODULES)):
        if not (destination / path).is_file():
            raise ValueError("Expected Maven module POM missing: " + path)
    return {"status": "ISOLATED_REPOSITORY_PREPARED", "repository": REPOSITORY,
            "reference": REFERENCE, "commit": expected, "workspace": str(destination),
            "modules": list(MODULES), "baselineExecuted": False,
            "noModelRun": True, "noPush": True, "noPR": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.destination, args.expected_commit)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:150], "doNotRetryWithoutInspection": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ISOLATED_REPOSITORY_PREPARED" else 1


if __name__ == "__main__":
    sys.exit(main())
