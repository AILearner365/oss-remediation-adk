#!/usr/bin/env python3
"""Independent deterministic validation for OpenHands Gate 2 run 1.

Consumes the saved pre-agent baseline, evaluates the current target checkout
with the existing deterministic validator, and does not invoke any LLM/agent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from autonomous_oss_remediation_agent.capabilities.execution import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import (
    ConstraintSpec,
    ExecutionBudgetConfig,
    MavenConfig,
    OsvScannerConfig,
    RemediationRequest,
    RuntimePolicy,
    ScannerConfig,
    SpringBootVersionPolicy,
)
from autonomous_oss_remediation_agent.deterministic.constraints import ConstraintEvaluator
from autonomous_oss_remediation_agent.deterministic.scanner import ScannerPreflightError, create_scanner
from autonomous_oss_remediation_agent.deterministic.validation import DeterministicValidator
from autonomous_oss_remediation_agent.models import (
    ConstraintBaseline,
    RepositoryBaseline,
    ScanOutcome,
    ScanReport,
    VulnerabilityFinding,
)
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


DEFAULT_TARGET = Path.home() / "maven-multimodule-app"
DEFAULT_STATE = Path.home() / ".openhands" / "gate2" / "task-01" / "baseline.json"
DEFAULT_SCANNER = Path.home() / "bin" / "osv-scanner"
DEFAULT_OUTPUT = Path.home() / ".openhands" / "gate2" / "task-01" / "validation.json"


def die(message: str, code: int = 1) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def finding_from_dict(data: dict) -> VulnerabilityFinding:
    dep = data.get("dependency") or {}
    return VulnerabilityFinding(
        vulnerability_id=str(data.get("vulnerabilityId") or ""),
        aliases=tuple(str(x) for x in data.get("aliases") or ()),
        severity=str(data.get("severity") or ""),
        group_id=dep.get("groupId"),
        artifact_id=dep.get("artifactId"),
        package_name=str(dep.get("packageName") or ""),
        version=str(dep.get("currentVersion") or ""),
        fixed_versions=tuple(str(x) for x in data.get("fixedVersions") or ()),
        summary=str(data.get("summary") or ""),
        ecosystem=str(dep.get("ecosystem") or "Maven"),
        backend_evidence=dict(data.get("backendEvidence") or {}),
    )


def baseline_from_state(state: dict, target: Path) -> RepositoryBaseline:
    scan_data = state["scan"]
    findings = tuple(finding_from_dict(x) for x in scan_data.get("findings") or ())
    scan = ScanReport(
        succeeded=bool(scan_data.get("succeeded")),
        findings=findings,
        command_result=None,
        raw_report_path=str(scan_data.get("rawReportPath") or ""),
        error=scan_data.get("error"),
        outcome=ScanOutcome(str(scan_data.get("outcome"))),
        attempts=tuple(scan_data.get("attempts") or ()),
        backend=str(scan_data.get("backend") or "osv"),
        evidence=dict(scan_data.get("evidence") or {}),
    )
    constraint_data = state["constraints"]
    constraints = ConstraintBaseline(
        java_versions=tuple(str(x) for x in constraint_data.get("javaVersions") or ()),
        spring_boot_versions=tuple(str(x) for x in constraint_data.get("springBootVersions") or ()),
        suppression_files=dict(constraint_data.get("suppressionFiles") or {}),
    )
    return RepositoryBaseline(
        repository_path=str(target),
        commit=str(state["baselineCommit"]),
        reference=str(state["baseBranch"]),
        remote_url=str(state["origin"]),
        build_results=(),
        scan=scan,
        constraints=constraints,
        target_findings=findings,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate native OpenHands Gate 2 run independently")
    parser.add_argument("--target-repo", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--scanner", type=Path, default=DEFAULT_SCANNER)
    parser.add_argument("--scanner-version", default="2.6.0")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    target = args.target_repo.expanduser().resolve()
    state_file = args.state_file.expanduser().resolve()
    scanner_path = args.scanner.expanduser().resolve()

    if not target.is_dir():
        die(f"Target repository not found at {target}")
    import subprocess
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=target,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        die(f"Target repository is not a Git worktree at {target}")
    if not state_file.is_file():
        die(f"Saved Gate 2 baseline not found at {state_file}")
    if not scanner_path.is_file() or not os.access(scanner_path, os.X_OK):
        die(f"OSV Scanner is not executable: {scanner_path}")

    state = json.loads(state_file.read_text(encoding="utf-8"))
    baseline = baseline_from_state(state, target)

    current_branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=target, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    ).stdout.strip()
    if current_branch != state["taskBranch"]:
        die(f"Expected task branch {state['taskBranch']}, found {current_branch}")

    request = RemediationRequest(
        repository_url=str(state["origin"]),
        reference_branch=str(state["baseBranch"]),
        severity_scope=("CRITICAL", "HIGH"),
        build_commands=("mvn clean verify",),
        test_commands=(),
        startup_commands=(),
        runtime_policy=RuntimePolicy(
            trusted_repository=True,
            dedicated_runner=True,
            enable_autonomous_shell=False,
            allow_network=True,
        ),
        maven=MavenConfig(mode="auto"),
        scanner=ScannerConfig(
            backend="osv",
            osv=OsvScannerConfig(
                mode="configured",
                executable=str(scanner_path),
                version=args.scanner_version,
                timeout_seconds=300,
            ),
        ),
        constraints=ConstraintSpec(
            spring_boot_version_policy=SpringBootVersionPolicy(
                allow_patch=True,
                allow_minor=True,
                allow_major=False,
                allow_downgrade=False,
            ),
            prohibit_suppressions=True,
            prohibited_new_severities=("CRITICAL", "HIGH"),
        ),
    )

    temp = tempfile.TemporaryDirectory(prefix="openhands-gate2-validation-", dir="/tmp")
    try:
        root = Path(temp.name)
        workspace = RunWorkspace(
            root=root,
            repository=target,
            artifacts=root / "artifacts",
            cache=root / "cache",
            temp=root / "temp",
            tools=root / "tools",
        )
        for directory in (workspace.artifacts, workspace.cache, workspace.temp, workspace.tools, workspace.investigation):
            directory.mkdir(parents=True, exist_ok=True)

        trace = TraceStore(workspace)
        budget = ExecutionBudget(
            ExecutionBudgetConfig(
                max_cycles=1,
                max_tool_calls=40,
                command_timeout_seconds=1800,
                overall_timeout_seconds=3600,
                max_returned_output_chars=30000,
            )
        )
        runner = ProcessRunner(workspace, trace, budget, request.runtime_policy)
        scanner = create_scanner(request.scanner, workspace, runner, trace, maven_config=request.maven)

        try:
            scanner.preflight(request.scanner)
        except ScannerPreflightError as exc:
            die(f"OSV Scanner preflight failed: {exc}")

        validator = DeterministicValidator(
            request,
            workspace,
            runner,
            scanner,
            ConstraintEvaluator(),
            trace,
        )

        print("==> Running independent deterministic Gate 2 validation")
        print(f"==> Target: {target}")
        print(f"==> Baseline commit: {baseline.commit}")
        print(f"==> Baseline HIGH/CRITICAL findings: {len(baseline.target_findings)}")

        report = validator.validate(1, baseline)
        payload = report.to_dict()

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        for check in report.checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"[{status}] {check.name}: {check.message}")

        print(f"==> Changed files: {len(report.changed_files)}")
        for path in report.changed_files:
            print(f"    {path}")
        print(f"==> Resolved target findings: {len(report.resolved_target_findings)}")
        print(f"==> Remaining target findings: {len(report.remaining_target_findings)}")
        print(f"==> Validation report: {args.output}")

        if report.passed:
            print("==> Gate 2 independent deterministic validation PASSED")
            return 0

        print("==> Gate 2 independent deterministic validation FAILED")
        return 2
    finally:
        temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
