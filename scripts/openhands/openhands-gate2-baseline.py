#!/usr/bin/env python3
"""Deterministic Gate 2 baseline for the native OpenHands experiment.

This script intentionally reuses the existing Maven/OSV deterministic components
without creating an ADK agent session or invoking remediation orchestration.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from autonomous_oss_remediation_agent.capabilities.execution import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import (
    ExecutionBudgetConfig,
    MavenConfig,
    OsvScannerConfig,
    RuntimePolicy,
    ScannerConfig,
)
from autonomous_oss_remediation_agent.deterministic.constraints import ConstraintEvaluator
from autonomous_oss_remediation_agent.deterministic.maven import MavenService
from autonomous_oss_remediation_agent.deterministic.scanner import ScannerPreflightError, create_scanner
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


DEFAULT_TARGET = Path.home() / "maven-multimodule-app"
DEFAULT_BASE = "main-runrunning"
DEFAULT_TASK = "openhands-poc-task-01"
DEFAULT_SCANNER = Path.home() / "bin" / "osv-scanner"
DEFAULT_STATE = Path.home() / ".openhands" / "gate2" / "task-01" / "baseline.json"


def die(message: str, code: int = 1) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        die(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def verify_target(repo: Path, base_branch: str, task_branch: str) -> tuple[str, str]:
    if not repo.is_dir():
        die(f"Target repository not found at {repo}")
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        die(f"Target repository is not a Git worktree at {repo}")

    origin = run_git(repo, "remote", "get-url", "origin")
    if "AILearner365/maven-multimodule-app" not in origin:
        die(f"Unexpected target origin: {origin}")

    if run_git(repo, "status", "--porcelain"):
        die("Target working tree is not clean")

    current_branch = run_git(repo, "branch", "--show-current")
    if current_branch != task_branch:
        die(f"Expected branch {task_branch}, found {current_branch}")

    head = run_git(repo, "rev-parse", "HEAD")
    base = run_git(repo, "rev-parse", f"origin/{base_branch}")

    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head],
        cwd=repo,
        check=False,
    )
    if ancestry.returncode != 0:
        die(f"{task_branch} is not based on origin/{base_branch}")

    if head != base:
        die(
            f"Gate 2 baseline must start exactly at origin/{base_branch}. "
            f"HEAD={head}, baseline={base}"
        )

    return origin, head


def make_workspace(target: Path) -> tuple[RunWorkspace, tempfile.TemporaryDirectory[str]]:
    temp = tempfile.TemporaryDirectory(prefix="openhands-gate2-baseline-", dir="/tmp")
    root = Path(temp.name)
    workspace = RunWorkspace(
        root=root,
        repository=target.resolve(),
        artifacts=root / "artifacts",
        cache=root / "cache",
        temp=root / "temp",
        tools=root / "tools",
    )
    for directory in (workspace.artifacts, workspace.cache, workspace.temp, workspace.tools, workspace.investigation):
        directory.mkdir(parents=True, exist_ok=True)
    return workspace, temp


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic Gate 2 OpenHands baseline")
    parser.add_argument("--target-repo", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--base-branch", default=DEFAULT_BASE)
    parser.add_argument("--task-branch", default=DEFAULT_TASK)
    parser.add_argument("--scanner", type=Path, default=DEFAULT_SCANNER)
    parser.add_argument("--scanner-version", default="2.6.0")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()

    target = args.target_repo.expanduser().resolve()
    scanner_path = args.scanner.expanduser().resolve()

    print(f"==> Target repository: {target}")
    origin, baseline_commit = verify_target(target, args.base_branch, args.task_branch)
    print(f"==> Branch: {args.task_branch}")
    print(f"==> Baseline commit: {baseline_commit}")

    if not scanner_path.is_file() or not os.access(scanner_path, os.X_OK):
        die(f"OSV Scanner is not executable: {scanner_path}")

    workspace, temp_workspace = make_workspace(target)
    try:
        trace = TraceStore(workspace)
        budget = ExecutionBudget(
            ExecutionBudgetConfig(
                max_cycles=1,
                max_tool_calls=30,
                command_timeout_seconds=1800,
                overall_timeout_seconds=3600,
                max_returned_output_chars=30000,
            )
        )
        runner = ProcessRunner(
            workspace,
            trace,
            budget,
            RuntimePolicy(
                trusted_repository=True,
                dedicated_runner=True,
                enable_autonomous_shell=False,
                allow_network=True,
            ),
        )

        maven_config = MavenConfig(mode="auto")
        scanner_config = ScannerConfig(
            backend="osv",
            osv=OsvScannerConfig(
                mode="configured",
                executable=str(scanner_path),
                version=args.scanner_version,
                timeout_seconds=300,
            ),
        )

        scanner = create_scanner(
            scanner_config,
            workspace,
            runner,
            trace,
            maven_config=maven_config,
        )

        try:
            scanner_handle = scanner.preflight(scanner_config)
        except ScannerPreflightError as exc:
            die(f"OSV Scanner preflight failed: {exc}")

        print(f"==> Scanner: {scanner_handle.version}")
        print("==> Running deterministic Maven baseline: clean verify")
        build_results = MavenService(target, runner, maven_config).run_baseline(
            ("mvn clean verify",),
            (),
            (),
        )
        if not build_results or not all(result.succeeded for result in build_results):
            for result in build_results:
                print(f"    exit={result.exit_code} command={' '.join(result.command)}")
                if result.stderr:
                    print(result.stderr[-4000:], file=sys.stderr)
            die("Baseline Maven build failed")

        print("==> Maven baseline PASSED")
        print("==> Running deterministic OSV scan with local Maven repository support")
        scan = scanner.scan(target, ("CRITICAL", "HIGH"), "gate2-baseline")
        if not scan.succeeded:
            die(
                "Baseline vulnerability scan was incomplete: "
                f"{scan.effective_outcome.value}: {scan.error}"
            )

        findings = list(scan.findings)
        constraints = ConstraintEvaluator().capture(target)

        state = {
            "experiment": "openhands-gate2-task-01",
            "targetRepository": str(target),
            "origin": origin,
            "baseBranch": args.base_branch,
            "taskBranch": args.task_branch,
            "baselineCommit": baseline_commit,
            "severityScope": ["CRITICAL", "HIGH"],
            "buildResults": [result.to_dict() for result in build_results],
            "scan": scan.to_dict(),
            "constraints": constraints.to_dict(),
            "scanner": scanner_handle.to_dict(),
        }

        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        args.state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        print(f"==> Completed scan outcome: {scan.effective_outcome.value}")
        print(f"==> HIGH/CRITICAL findings: {len(findings)}")
        for finding in findings:
            print(
                f"    {finding.severity} {finding.vulnerability_id} "
                f"{finding.coordinate}@{finding.version}"
            )
        print(f"==> Baseline state: {args.state_file}")

        if not findings:
            die(
                "No HIGH/CRITICAL findings were present. "
                "Do not start the OpenHands Gate 2 remediation run.",
                code=2,
            )

        print("==> Gate 2 deterministic baseline PASSED")
        return 0
    finally:
        temp_workspace.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
