#!/usr/bin/env python3
"""Run Maven and OSV baseline on an isolated, pinned real-app checkout.

Creates unique local evidence directory. Does not edit Git-tracked files,
open a PR, create a durable remediation task, or execute a model.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from openhands_real_app_prepare import REPOSITORY, REFERENCE, SHA, MODULES, run_git


def baseline(project: Path, expected: str, output: Path, scanner: str) -> dict:
    if not SHA.fullmatch(expected):
        raise ValueError("Expected base commit must be a 40-character SHA")
    if output.exists() or output.is_symlink():
        raise ValueError("Evidence destination already exists")
    project = project.resolve(strict=True)
    if run_git("-C", str(project), "rev-parse", "HEAD") != expected:
        raise ValueError("Repository commit differs from expected")
    if run_git("-C", str(project), "status", "--porcelain"):
        raise ValueError("Repository must be clean before baseline")
    if run_git("-C", str(project), "remote", "get-url", "origin") != REPOSITORY:
        raise ValueError("Unexpected repository origin")
    remote = run_git("ls-remote", "--exit-code", REPOSITORY, "refs/heads/" + REFERENCE)
    if remote.split()[0] != expected:
        raise ValueError("Remote reference moved since checkout")
    for rel in ("pom.xml", *(module + "/pom.xml" for module in MODULES)):
        if not (project / rel).is_file():
            raise ValueError("Missing expected Maven module POM")
    output.mkdir(parents=True, mode=0o700)
    checks = [
        ("maven", ["mvn", "-B", "-ntp", "clean", "verify"], 1800),
        ("osv", [scanner, "scan", "source", "-r", str(project), "--format", "json", "--data-source=osv"], 600),
    ]
    runs = {}
    for name, command, timeout in checks:
        target = output / (name + ".stdout")
        errors = output / (name + ".stderr")
        try:
            with target.open("wb") as stdout, errors.open("wb") as stderr:
                result = subprocess.run(command, cwd=project, stdout=stdout,
                                        stderr=stderr, timeout=timeout, check=False)
            code = result.returncode
            if name == "maven" and code != 0:
                runs[name] = {"exitCode": code, "status": "BUILD_FAILED"}
                break
            if name == "osv":
                try:
                    json.loads(target.read_text(encoding="utf-8"))
                    outcome = "REPORT_RECORDED_REQUIRES_FINDING_REVIEW"
                except (ValueError, UnicodeError):
                    outcome = "INVALID_SCANNER_REPORT"
                runs[name] = {"exitCode": code, "status": outcome}
            else:
                runs[name] = {"exitCode": code, "status": "BUILD_PASSED"}
        except (OSError, subprocess.TimeoutExpired) as exc:
            runs[name] = {"status": "EXECUTION_ERROR", "errorType": type(exc).__name__}
            break
        runs[name]["stdoutSha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        runs[name]["stderrSha256"] = hashlib.sha256(errors.read_bytes()).hexdigest()
    result = {"status": "BASELINE_EVIDENCE_RECORDED" if
              runs.get("maven", {}).get("status") == "BUILD_PASSED" and
              runs.get("osv", {}).get("status") == "REPORT_RECORDED_REQUIRES_FINDING_REVIEW"
              else "BASELINE_INCOMPLETE",
              "repository": REPOSITORY, "reference": REFERENCE, "commit": expected,
              "runs": runs, "evidence": str(output), "noModelRun": True, "noPush": True,
              "notProven": ["OSV findings classified and accepted",
                            "SBRI release candidates", "durable task registration",
                            "independent post-remediation validation"]}
    (output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--expected-commit", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--scanner", default="osv-scanner")
    a = p.parse_args()
    try:
        result = baseline(a.project, a.expected_commit, a.evidence, a.scanner)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:180], "noModelRun": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "BASELINE_EVIDENCE_RECORDED" else 1


if __name__ == "__main__":
    sys.exit(main())
