#!/usr/bin/env python3
"""Run only the corrected OSV source scan; retain original Maven baseline evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from openhands_real_app_prepare import REPOSITORY, REFERENCE, SHA, MODULES, run_git

def retry(project: Path, original: Path, output: Path, expected: str, scanner: str) -> dict:
    if not SHA.fullmatch(expected):
        raise ValueError("Exact baseline commit required")
    if output.exists() or output.is_symlink():
        raise ValueError("Retry evidence directory already exists")
    project = project.resolve(strict=True)
    original = original.resolve(strict=True)
    previous = json.loads((original / "summary.json").read_text(encoding="utf-8"))
    prior = previous.get("runs", {}).get("maven", {})
    if (previous.get("repository") != REPOSITORY or previous.get("reference") != REFERENCE
            or previous.get("commit") != expected or prior.get("status") != "BUILD_PASSED"
            or prior.get("exitCode") != 0):
        raise ValueError("Original successful pinned Maven baseline unavailable")
    for key, filename in (("stdoutSha256", "maven.stdout"), ("stderrSha256", "maven.stderr")):
        if hashlib.sha256((original / filename).read_bytes()).hexdigest() != prior.get(key):
            raise ValueError("Original Maven evidence checksum mismatch")
    if run_git("-C", str(project), "rev-parse", "HEAD") != expected or run_git("-C", str(project), "status", "--porcelain"):
        raise ValueError("Baseline repository is not clean at expected commit")
    if run_git("-C", str(project), "remote", "get-url", "origin") != REPOSITORY:
        raise ValueError("Repository origin mismatch")
    if run_git("ls-remote", "--exit-code", REPOSITORY, "refs/heads/" + REFERENCE).split()[0] != expected:
        raise ValueError("Remote reference changed")
    for path in ("pom.xml", *(m + "/pom.xml" for m in MODULES)):
        if not (project / path).is_file():
            raise ValueError("Expected Maven POM missing")
    output.mkdir(parents=True, mode=0o700)
    stdout_path, stderr_path = output / "osv.stdout", output / "osv.stderr"
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            proc = subprocess.run([scanner, "scan", "source", "-r", str(project), "--format", "json",
                                   "--data-source=native"], cwd=project, stdout=stdout, stderr=stderr,
                                  timeout=600, check=False)
        result_code = proc.returncode
        try:
            report = json.loads(stdout_path.read_text(encoding="utf-8"))
            valid = isinstance(report, dict) and bool(report)
        except (UnicodeError, ValueError):
            valid = False
        status = "REPORT_RECORDED_REQUIRES_FINDING_REVIEW" if valid else "INVALID_SCANNER_REPORT"
    except (OSError, subprocess.TimeoutExpired) as exc:
        result_code, status = None, "EXECUTION_ERROR_" + type(exc).__name__
    output_summary = {
        "status": "OSV_EVIDENCE_RECORDED" if status == "REPORT_RECORDED_REQUIRES_FINDING_REVIEW" else "OSV_INCOMPLETE",
        "repository": REPOSITORY, "reference": REFERENCE, "commit": expected,
        "priorMavenBuild": "VERIFIED_REUSED_NO_RERUN",
        "priorMavenSummary": str(original / "summary.json"), "osvExitCode": result_code,
        "osvStatus": status, "evidence": str(output),
        "osvStdoutSha256": hashlib.sha256(stdout_path.read_bytes()).hexdigest(),
        "osvStderrSha256": hashlib.sha256(stderr_path.read_bytes()).hexdigest(),
        "findingClassificationVerified": False, "noModelRun": True, "noPush": True,
    }
    (output / "summary.json").write_text(json.dumps(output_summary, indent=2, sort_keys=True) + "\n")
    return output_summary

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--original-evidence", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--scanner", default="osv-scanner")
    args = parser.parse_args()
    try:
        result = retry(args.project, args.original_evidence, args.evidence, args.expected_commit, args.scanner)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__, "errorDetail": str(exc)[:180],
                  "noModelRun": True}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] == "OSV_EVIDENCE_RECORDED" else 1

if __name__ == "__main__":
    sys.exit(main())
