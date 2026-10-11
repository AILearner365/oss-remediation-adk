"""Offline coverage and agent-visible validation launcher regressions."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from autonomous_oss_remediation_agent.capabilities.execution import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig, RemediationRequest, RuntimePolicy
from autonomous_oss_remediation_agent.deterministic.osv import _maven_scan_coverage
from autonomous_oss_remediation_agent.deterministic.constraints import ConstraintEvaluator
from autonomous_oss_remediation_agent.deterministic.validation import DeterministicValidator
from autonomous_oss_remediation_agent.models import (
    CommandResult,
    ConstraintBaseline,
    RepositoryBaseline,
    ScanOutcome,
    ScanReport,
)
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_DIR = ROOT / "scripts" / "openhands"


def _repository(root: Path, pom_count: int = 5) -> Path:
    repository = root / "target"
    repository.mkdir()
    modules = [f"module-{number}" for number in range(1, pom_count)]
    (repository / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion>"
        "<groupId>example</groupId><artifactId>root</artifactId><version>1</version>"
        "<packaging>pom</packaging><modules>"
        + "".join(f"<module>{module}</module>" for module in modules)
        + "</modules></project>\n",
        encoding="utf-8",
    )
    for module in modules:
        directory = repository / module
        directory.mkdir()
        (directory / "pom.xml").write_text(
            "<project><modelVersion>4.0.0</modelVersion>"
            f"<groupId>example</groupId><artifactId>{module}</artifactId><version>1</version>"
            "</project>\n",
            encoding="utf-8",
        )
    subprocess.run(["git", "init", "-b", "task"], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "baseline"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    return repository


def _stderr(repository: Path, included: list[str]) -> str:
    return "\n".join(
        f"Scanned {repository / relative} file and found 3 packages" for relative in included
    )


def test_maven_coverage_accepts_all_repository_derived_poms() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repository = _repository(Path(tmp))
        expected = ["pom.xml", "module-1/pom.xml", "module-2/pom.xml", "module-3/pom.xml", "module-4/pom.xml"]
        result = CommandResult(["osv-scanner"], str(repository), 0)

        coverage = _maven_scan_coverage(repository, result, _stderr(repository, expected))

        assert coverage["complete"] is True
        assert coverage["expectedPomCount"] == coverage["scannedPomCount"] == 5
        assert coverage["missingPoms"] == []


def test_root_only_zero_finding_scope_is_incomplete() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repository = _repository(Path(tmp))
        result = CommandResult(["osv-scanner"], str(repository), 0)

        coverage = _maven_scan_coverage(repository, result, _stderr(repository, ["pom.xml"]))

        assert coverage["complete"] is False
        assert coverage["scannedPoms"] == ["pom.xml"]
        assert len(coverage["missingPoms"]) == 4


def test_omitted_recursive_module_is_incomplete() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repository = _repository(Path(tmp))
        included = ["pom.xml", "module-1/pom.xml", "module-2/pom.xml", "module-3/pom.xml"]
        result = CommandResult(["osv-scanner"], str(repository), 0)

        coverage = _maven_scan_coverage(repository, result, _stderr(repository, included))

        assert coverage["complete"] is False
        assert coverage["missingPoms"] == ["module-4/pom.xml"]


def test_agent_visible_launcher_runs_real_validator_and_retains_isolated_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repository = _repository(root)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository, check=True, text=True, capture_output=True
        ).stdout.strip()
        baseline = root / "baseline.json"
        baseline.write_text(json.dumps({
            "origin": "https://example.test/multimodule.git",
            "baseBranch": "main",
            "taskBranch": "task",
            "baselineCommit": head,
            "scan": {
                "succeeded": True, "findings": [], "rawReportPath": "/retained/baseline.json",
                "outcome": "COMPLETED_CLEAN", "attempts": [], "backend": "osv", "evidence": {},
            },
            "constraints": {"javaVersions": [], "springBootVersions": [], "suppressionFiles": {}},
        }), encoding="utf-8")
        tool_dir = root / "bin"
        tool_dir.mkdir()
        scanner = tool_dir / "osv-scanner"
        scanner.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, sys\n"
            "if '--version' in sys.argv:\n print('osv-scanner version 2.6.0'); raise SystemExit(0)\n"
            "scan_root = pathlib.Path(sys.argv[sys.argv.index('-r') + 1])\n"
            "for pom in sorted(scan_root.rglob('pom.xml')):\n print(f'Scanned {pom} file and found 3 packages', file=sys.stderr)\n"
            "print(json.dumps({'results': []}))\n",
            encoding="utf-8",
        )
        scanner.chmod(0o755)
        maven = tool_dir / "mvn"
        maven.write_text("#!/bin/sh\necho 'BUILD SUCCESS'\n", encoding="utf-8")
        maven.chmod(0o755)
        evidence_root = root / "harness-evidence"
        attempt_file = root / "attempt-count"
        attempt_file.write_text("7\n", encoding="utf-8")
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=repository, check=True, text=True, capture_output=True
        ).stdout.splitlines()
        before = {
            relative: hashlib.sha256((repository / relative).read_bytes()).hexdigest()
            for relative in tracked
        }
        env = dict(
            os.environ,
            CONTROL_REPO=str(ROOT),
            GATE2_TARGET_REPO=str(repository),
            GATE2_STATE_FILE=str(baseline),
            GATE2_SCANNER_EXECUTABLE=str(scanner),
            GATE2_SELF_VALIDATION_ROOT=str(evidence_root),
            GATE2_VALIDATOR_PYTHON=sys.executable,
            PATH=str(LAUNCHER_DIR) + os.pathsep + str(tool_dir) + os.pathsep + os.environ.get("PATH", ""),
        )

        first = subprocess.run(["validate-remediation"], env=env, text=True, capture_output=True)
        second = subprocess.run(["validate-remediation"], env=env, text=True, capture_output=True)

        assert first.returncode == second.returncode == 0, first.stdout + first.stderr
        invocations = sorted(evidence_root.glob("validation-*"))
        assert len(invocations) == 2
        for invocation in invocations:
            report_path = invocation / "validation.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            coverage = report["scan"]["evidence"]["mavenCoverage"]
            assert coverage["expectedPomCount"] == coverage["scannedPomCount"] == 5
            assert Path(report["scan"]["rawReportPath"]).is_file()
            assert (invocation / "validator.log").is_file()
            assert (invocation / "execution.json").is_file()
            assert (invocation / "workspace/artifacts/scans/validation-cycle-1-coverage.json").is_file()
        after = {
            relative: hashlib.sha256((repository / relative).read_bytes()).hexdigest()
            for relative in tracked
        }
        assert before == after
        assert attempt_file.read_text(encoding="utf-8") == "7\n"
        assert "Maven POM coverage: expected 5, scanned 5" in first.stdout
        assert "did not request final acceptance" in first.stdout


def test_agent_visible_launcher_retains_missing_baseline_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repository = _repository(root, pom_count=1)
        evidence_root = root / "harness-evidence"
        env = dict(
            os.environ,
            CONTROL_REPO=str(ROOT),
            GATE2_TARGET_REPO=str(repository),
            GATE2_STATE_FILE=str(root / "missing-baseline.json"),
            GATE2_SCANNER_EXECUTABLE=str(root / "missing-scanner"),
            GATE2_SELF_VALIDATION_ROOT=str(evidence_root),
            GATE2_VALIDATOR_PYTHON=sys.executable,
            PATH=str(LAUNCHER_DIR) + os.pathsep + os.environ.get("PATH", ""),
        )

        result = subprocess.run(["validate-remediation"], env=env, text=True, capture_output=True)

        assert result.returncode != 0
        invocation = next(evidence_root.glob("validation-*"))
        assert "Saved Gate 2 baseline not found" in (invocation / "validator.log").read_text()
        execution = json.loads((invocation / "execution.json").read_text())
        assert execution["status"] == "infrastructure_failed"
        assert not (invocation / "validation.json").exists()

        invalid = root / "invalid-baseline.json"
        invalid.write_text("not json\n", encoding="utf-8")
        env["GATE2_STATE_FILE"] = str(invalid)
        env["GATE2_SCANNER_EXECUTABLE"] = sys.executable
        before_invalid = set(evidence_root.glob("validation-*"))
        invalid_result = subprocess.run(
            ["validate-remediation"], env=env, text=True, capture_output=True
        )
        assert invalid_result.returncode != 0
        invalid_invocation = (set(evidence_root.glob("validation-*")) - before_invalid).pop()
        assert "baseline is invalid or unreadable" in (invalid_invocation / "validator.log").read_text()
        assert json.loads((invalid_invocation / "execution.json").read_text())["status"] == "infrastructure_failed"


def test_validator_build_failure_retains_readable_maven_error() -> None:
    class CleanScanner:
        def scan(self, repository, severity_scope, label):
            return ScanReport(
                succeeded=True,
                findings=(),
                command_result=CommandResult(["scanner"], str(repository), 0),
                raw_report_path="/tmp/scan.json",
                outcome=ScanOutcome.COMPLETED_CLEAN,
                backend="fixture",
            )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repository = _repository(root, pom_count=1)
        workspace = RunWorkspace.create(root / "workspaces", "validation")
        object.__setattr__(workspace, "repository", repository)
        trace = TraceStore(workspace)
        runner = ProcessRunner(
            workspace,
            trace,
            ExecutionBudget(ExecutionBudgetConfig(max_tool_calls=20)),
            RuntimePolicy(trusted_repository=True, dedicated_runner=True),
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository, check=True, text=True, capture_output=True
        ).stdout.strip()
        baseline_scan = ScanReport(
            succeeded=True, findings=(), command_result=None, raw_report_path="/baseline.json",
            outcome=ScanOutcome.COMPLETED_CLEAN, backend="fixture",
        )
        baseline = RepositoryBaseline(
            str(repository), head, "main", "https://example.test/repo.git", (), baseline_scan,
            ConstraintBaseline(), (),
        )
        failed_build = CommandResult(
            ["mvn clean verify"], str(repository), 1,
            stdout="[INFO] BUILD FAILURE", stderr="Compilation failed in module-1",
        )
        validator = DeterministicValidator(
            RemediationRequest.from_dict({"repositoryUrl": "https://example.test/repo.git"}),
            workspace, runner, CleanScanner(), ConstraintEvaluator(), trace,
        )

        with patch(
            "autonomous_oss_remediation_agent.deterministic.validation.MavenService.run_validation",
            return_value=(failed_build,),
        ):
            report = validator.validate(1, baseline)

        check = next(item for item in report.checks if item.name == "build_test_startup")
        assert report.passed is False
        assert check.passed is False
        assert check.message == "A required build/test/startup command failed"
        assert check.evidence["results"][0]["stderr"] == "Compilation failed in module-1"


def test_launcher_detects_missing_referenced_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        control = root / "control"
        scripts = control / "scripts/openhands"
        scripts.mkdir(parents=True)
        fake_validator = scripts / "openhands-gate2-validate.sh"
        fake_validator.write_text(
            "#!/bin/bash\n"
            "while [ $# -gt 0 ]; do\n"
            "  if [ \"$1\" = --output ]; then output=$2; shift 2; else shift; fi\n"
            "done\n"
            "printf '%s\\n' '{\"scan\":{\"rawReportPath\":\"/missing/raw-osv.json\",\"attempts\":[]},\"checks\":[]}' > \"$output\"\n"
            "exit 2\n",
            encoding="utf-8",
        )
        fake_validator.chmod(0o755)
        evidence_root = root / "evidence"
        env = dict(
            os.environ,
            CONTROL_REPO=str(control),
            GATE2_TARGET_REPO=str(root),
            GATE2_STATE_FILE=str(root / "baseline.json"),
            GATE2_SELF_VALIDATION_ROOT=str(evidence_root),
            GATE2_VALIDATOR_PYTHON=sys.executable,
        )

        result = subprocess.run(
            [str(LAUNCHER_DIR / "validate-remediation")], env=env, text=True, capture_output=True
        )

        assert result.returncode == 70
        invocation = next(evidence_root.glob("validation-*"))
        integrity = json.loads((invocation / "evidence-integrity.json").read_text())
        assert integrity["complete"] is False
        assert "/missing/raw-osv.json" in integrity["missingOrInaccessible"]
        assert json.loads((invocation / "execution.json").read_text())["status"] == "infrastructure_failed"
