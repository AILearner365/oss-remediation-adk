#!/usr/bin/env python3
"""Prepare a credential-free, nonexecuting Vertex Gemini remediation run plan.

Checks the existing real OSV baseline and fixed comparison (the known fixed
version is NEVER included in the agent objective). Reads files only. Does NOT
call Vertex, Agent Server, Maven, OSV, or change any repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

MODEL = "vertex_ai/gemini-2.5-flash"
TARGET = "GHSA-mjmj-j48q-9wg2"
PACKAGE = "org.yaml:snakeyaml"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def findings(path: Path) -> list[tuple[str, str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return sorted(
        (str(pkg.get("package", {}).get("name")), str(vuln.get("id")))
        for result in document.get("results", [])
        for pkg in result.get("packages", [])
        for vuln in pkg.get("vulnerabilities", [])
    )


def run_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        text=True, capture_output=True, timeout=15, check=True
    )
    return result.stdout.strip()


def prepare(base: Path, fixed: Path, baseline_report: Path, fixed_report: Path, scanner: Path) -> dict:
    # No model or scanner invocation, including --version.
    for path in (base, fixed):
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Both baseline and fixed comparison directories must exist without symlinks")
    for path in (baseline_report, fixed_report, scanner):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Required evidence or scanner binary is missing or symlinked")
    base, fixed = base.resolve(), fixed.resolve()
    if base == fixed:
        raise ValueError("Baseline and fixed comparison must be separate directories")
    pom = base / "pom.xml"
    fixed_pom = fixed / "pom.xml"
    if not pom.is_file() or pom.is_symlink() or not fixed_pom.is_file() or fixed_pom.is_symlink():
        raise ValueError("Both directories require regular pom.xml files")
    baseline_content = pom.read_text(encoding="utf-8")
    fixed_content = fixed_pom.read_text(encoding="utf-8")
    if "<artifactId>snakeyaml</artifactId>" not in baseline_content:
        raise ValueError("Unexpected baseline POM: target artifact missing")
    if baseline_content == fixed_content:
        raise ValueError("Comparison POM was not modified")
    head = run_git(base, "rev-parse", "--verify", "HEAD")
    if len(head) != 40 or not re.fullmatch("[0-9a-f]{40}", head):
        raise ValueError("Full baseline Git identity not available")
    status = run_git(base, "status", "--porcelain=v1", "--untracked-files=all")
    # Maven target/ from previously observed baseline build is allowed only
    # as untracked generated output, not source-code changes.
    if any(line not in ("?? target/",) and not line.startswith("?? target/") for line in status.splitlines()):
        raise ValueError("Baseline contains source modifications or unexpected untracked files")
    tracked_pom = subprocess.run(
        ["git", "-C", str(base), "show", f"{head}:pom.xml"],
        capture_output=True, timeout=15, check=True,
    ).stdout
    if tracked_pom != pom.read_bytes():
        raise ValueError("Baseline pom.xml differs from its immutable Git commit")
    original = findings(baseline_report)
    repaired = findings(fixed_report)
    if original != [(PACKAGE, TARGET)]:
        raise ValueError("Baseline findings differ from the agreed single advisory")
    if repaired:
        raise ValueError("Fixed comparison still has OSV findings")
    # The plan intentionally contains no fixed POM path/version: agent
    # must investigate and select a remediation candidate independently.
    return {
        "kind": "native-autonomous-remediation-plan-v1",
        "status": "PREPARED_NOT_AUTHORIZED",
        "model": MODEL,
        "modelExecutionAuthorized": False,
        "modelInvocationAllowed": False,
        "sourceRepository": str(base),
        "baselineCommit": head,
        "baselinePomSha256": digest(pom),
        "approvedScannerCandidate": str(scanner.resolve()),
        "scannerSha256": digest(scanner),
        "baselineReportSha256": digest(baseline_report),
        "fixedComparisonReportSha256": digest(fixed_report),
        "verifiedBaselineFindings": [{"package": PACKAGE, "advisory": TARGET}],
        "fixedComparisonFindingCount": 0,
        "agentObjective": (
            "Investigate the vulnerable Maven project in the prepared disposable worktree. "
            "Resolve the identified dependency security vulnerability while keeping the Maven "
            "build passing. Independently assess credible remediation strategies and compatibility "
            "trade-offs before editing. Do not suppress findings, change Java version, or "
            "claim completion without independent deterministic validation."
        ),
        "executionBoundary": {
            "requiresExplicitSeparateApproval": True,
            "requiresDisposableTaskWorktree": True,
            "requiresIndependentRealMavenOsvStopHook": True,
            "requiresVertexAuthenticationOutsideAgentContext": True,
            "requiresConfiguredIterationAndCostCaps": True,
            "nativeFinishIsNotAcceptance": True,
        },
        "notYetVerified": [
            "Configured Vertex Gemini runtime and ADC",
            "Actual selected scanner backend configuration and permission",
            "Real baseline assessed through shared deterministic service",
            "Native agent-produced modification and independent acceptance",
            "Runtime token/cost cap enforcement",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-repository", type=Path, default=Path("/tmp/openhands-real-remediation-snakeyaml-v1"))
    parser.add_argument("--fixed-repository", type=Path, default=Path("/tmp/openhands-real-remediation-snakeyaml-fixed-v1"))
    parser.add_argument("--baseline-osv", type=Path, default=Path("/tmp/openhands-real-remediation-baseline-v1/osv-baseline.json"))
    parser.add_argument("--fixed-osv", type=Path, default=Path("/tmp/openhands-real-remediation-fixed-v1/osv-fixed.json"))
    parser.add_argument("--scanner", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = prepare(args.baseline_repository, args.fixed_repository,
                       args.baseline_osv, args.fixed_osv, args.scanner)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(json.dumps({"status":"BLOCKED", "errorType":type(exc).__name__,
                          "modelExecutionAuthorized":False,
                          "modelInvocationAllowed":False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
