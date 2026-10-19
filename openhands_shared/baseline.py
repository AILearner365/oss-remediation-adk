"""Deterministic baseline assessment and durable evidence for prepared tasks.

This is a narrow adapter over the repository's existing Maven, scanner and
constraint components.  It does not invoke SBRI, OpenHands, models or delivery.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from autonomous_oss_remediation_agent.capabilities.execution import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import (
    ExecutionBudgetConfig,
    MavenConfig,
    RuntimePolicy,
    ScannerConfig,
)
from autonomous_oss_remediation_agent.deterministic.constraints import ConstraintEvaluator
from autonomous_oss_remediation_agent.deterministic.maven import MavenService
from autonomous_oss_remediation_agent.deterministic.scanner import ScannerPreflightError, create_scanner
from autonomous_oss_remediation_agent.models import CommandResult, ConstraintBaseline, ScanReport
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore

from .contracts import (
    ArtifactMetadata,
    BaselineAssessmentStatus,
    BaselineRecord,
    PreparationRecord,
    TaskRequest,
    TaskStatus,
    canonical_json,
    safe_artifact_path,
    utc_now,
)
from .preparation import GitCommandError, GitRunner
from .store import InvalidTransitionError, SQLiteTaskStore
from .tool_environment import tool_environment


REPORT_ARTIFACT_ID = "baseline-report"
REPORT_RELATIVE_SUFFIX = "baseline/report.json"


class BaselineError(RuntimeError):
    pass


class BaselineConfigurationError(BaselineError):
    pass


class BaselineWorkspaceError(BaselineError):
    pass


class BaselineArtifactError(BaselineError):
    pass


class BaselineScannerError(BaselineError):
    """Known scanner setup failure safe to persist without leaking details."""


@dataclass(frozen=True)
class BaselineProfile:
    """Deployment-owned commands and deterministic tool configuration."""

    profile: str
    build_commands: tuple[str, ...]
    maven: MavenConfig
    scanner: ScannerConfig
    budget: ExecutionBudgetConfig = field(
        default_factory=lambda: ExecutionBudgetConfig(
            max_cycles=1,
            max_tool_calls=30,
            command_timeout_seconds=1800,
            overall_timeout_seconds=3600,
            max_returned_output_chars=30_000,
        )
    )

    def __post_init__(self) -> None:
        if not self.profile or not self.build_commands:
            raise BaselineConfigurationError("baseline profile and build commands are required")
        if self.scanner.backend != "osv":
            raise BaselineConfigurationError("shared baseline profiles must use the approved OSV scanner")
        if any(
            not command
            or command != command.strip()
            or "\n" in command
            or "\r" in command
            for command in self.build_commands
        ):
            raise BaselineConfigurationError("baseline profile contains an invalid build command")


@dataclass(frozen=True)
class BaselineConfig:
    artifact_root: Path
    profiles: tuple[BaselineProfile, ...]

    def __post_init__(self) -> None:
        configured_root = self.artifact_root.expanduser()
        if configured_root.exists() and configured_root.is_symlink():
            raise BaselineConfigurationError("artifact root must not be a symbolic link")
        root = configured_root.resolve(strict=False)
        object.__setattr__(self, "artifact_root", root)
        if not root.is_absolute():
            raise BaselineConfigurationError("artifact root must be absolute")
        names = [profile.profile for profile in self.profiles]
        if len(names) != len(set(names)):
            raise BaselineConfigurationError("baseline profile names must be unique")

    def profile_for(self, request: TaskRequest) -> BaselineProfile:
        for profile in self.profiles:
            if profile.profile == request.agent.profile:
                if request.acceptance.build_commands != profile.build_commands:
                    raise BaselineConfigurationError(
                        "task build commands do not exactly match the approved baseline profile"
                    )
                return profile
        raise BaselineConfigurationError("task does not select an approved baseline profile")


@dataclass(frozen=True)
class BaselineRunEvidence:
    build_results: tuple[CommandResult, ...]
    scan: ScanReport | None
    constraints: ConstraintBaseline | None
    scanner_handle: Mapping[str, Any]
    tool_versions: Mapping[str, Any]


class BaselineRunner(Protocol):
    def run(
        self,
        repository: Path,
        request: TaskRequest,
        profile: BaselineProfile,
        runtime_root: Path,
    ) -> BaselineRunEvidence:
        ...


class ExistingDeterministicBaselineRunner:
    """Runs the same deterministic services used by the Gate-2 baseline."""

    def run(
        self,
        repository: Path,
        request: TaskRequest,
        profile: BaselineProfile,
        runtime_root: Path,
    ) -> BaselineRunEvidence:
        runtime_root.mkdir(parents=True, exist_ok=True)
        workspace = RunWorkspace(
            root=runtime_root,
            repository=repository,
            artifacts=runtime_root / "artifacts",
            cache=runtime_root / "cache",
            temp=runtime_root / "temp",
            tools=runtime_root / "tools",
        )
        for directory in (
            workspace.artifacts,
            workspace.cache,
            workspace.temp,
            workspace.tools,
            workspace.investigation,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        trace = TraceStore(workspace)
        runtime_home = runtime_root.parent / "execution-home"
        runtime_home.mkdir(parents=True, exist_ok=True)
        runner = _BaselineProcessRunner(
            workspace,
            trace,
            ExecutionBudget(profile.budget),
            RuntimePolicy(
                trusted_repository=True,
                dedicated_runner=True,
                enable_autonomous_shell=False,
                allow_network=True,
            ),
            environment=tool_environment(runtime_home),
        )
        scanner = create_scanner(
            profile.scanner,
            workspace,
            runner,
            trace,
            maven_config=profile.maven,
        )
        try:
            scanner_handle = scanner.preflight(profile.scanner)
        except ScannerPreflightError as exc:
            raise BaselineScannerError("approved scanner preflight failed") from exc

        maven = MavenService(repository, runner, profile.maven)
        build_results = maven.run_baseline(profile.build_commands, (), ())
        tools = {
            "maven": {"mode": profile.maven.mode, "executable": maven.maven_executable()},
            "scanner": scanner_handle.to_dict(),
        }
        if not build_results or not all(result.succeeded for result in build_results):
            return BaselineRunEvidence(build_results, None, None, scanner_handle.to_dict(), tools)
        scan = scanner.scan(repository, request.acceptance.severity_scope, "shared-baseline")
        constraints = ConstraintEvaluator().capture(repository) if scan.succeeded else None
        return BaselineRunEvidence(build_results, scan, constraints, scanner_handle.to_dict(), tools)


class DeterministicBaselineAssessor:
    """Trusted internal baseline operation; task registration never calls it."""

    def __init__(
        self,
        store: SQLiteTaskStore,
        config: BaselineConfig,
        *,
        runner: BaselineRunner | None = None,
        git: GitRunner | None = None,
    ):
        self.store = store
        self.config = config
        self.runner = runner or ExistingDeterministicBaselineRunner()
        self.git = git or GitRunner()
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def assess(self, task_id: str) -> BaselineRecord:
        with self._task_lock(task_id):
            recorded = self.store.get_baseline(task_id)
            if recorded is not None:
                self._verify_recorded_artifact(recorded)
                return recorded

            request = self.store.get_request(task_id)
            preparation = self.store.get_preparation(task_id)
            if preparation is None:
                raise InvalidTransitionError("baseline requires a prepared task")
            if self.store.get_status(task_id).status is not TaskStatus.BASELINING:
                raise InvalidTransitionError("baseline can start only while the task is BASELINING")
            profile = self.config.profile_for(request)
            workspace = self._verify_workspace(request, preparation)
            self._ensure_artifact_boundary(task_id)

            reconciled = self._reconcile_report(task_id, request, preparation)
            if reconciled is not None:
                self.store.complete_baseline(reconciled[0], reconciled[1])
                return reconciled[0]

            try:
                evidence = self.runner.run(
                    workspace,
                    request,
                    profile,
                    self._runtime_root(task_id),
                )
                self._verify_workspace(request, preparation)
                report = self._report_for_evidence(request, preparation, evidence)
            except BaselineScannerError:
                report = self._scanner_failure_report(request, preparation)

            evidence_artifacts = self._runtime_artifacts(task_id, report["completedAt"])
            report["evidenceArtifacts"] = [artifact.to_dict() for artifact in evidence_artifacts]
            payload = (canonical_json(report) + "\n").encode("utf-8")
            relative_path = self._report_relative_path(task_id)
            report_path = self._write_immutable(relative_path, payload)
            artifact = ArtifactMetadata(
                artifact_id=REPORT_ARTIFACT_ID,
                task_id=task_id,
                kind="baseline-report",
                relative_path=relative_path,
                media_type="application/json",
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                created_at=report["completedAt"],
            )
            record = self._record_from_report(report, artifact)
            self.store.complete_baseline(record, (artifact, *evidence_artifacts))
            if not report_path.is_file():  # defensive assertion after durable metadata commit
                raise BaselineArtifactError("durable baseline artifact disappeared")
            return record

    def _verify_workspace(self, request: TaskRequest, preparation: PreparationRecord) -> Path:
        if (
            preparation.repository_url != request.repository.url
            or preparation.base_ref != request.repository.base_ref
            or preparation.expected_commit != request.repository.expected_commit
            or preparation.baseline_commit != request.repository.expected_commit
        ):
            raise BaselineWorkspaceError("preparation identity differs from the registered task")
        workspace = Path(preparation.workspace_path)
        source = Path(preparation.source_path)
        if not workspace.is_dir() or workspace.is_symlink() or not source.is_dir():
            raise BaselineWorkspaceError("prepared workspace identity is unavailable")
        try:
            _, workspace_common = self.git.run(
                workspace, ["rev-parse", "--git-common-dir"], operation="baseline_workspace_identity"
            )
            _, source_common = self.git.run(
                source, ["rev-parse", "--git-common-dir"], operation="baseline_source_identity"
            )
            if self._common_path(workspace, workspace_common) != self._common_path(source, source_common):
                raise BaselineWorkspaceError("prepared workspace belongs to a foreign repository")
            _, head = self.git.run(workspace, ["rev-parse", "--verify", "HEAD^{commit}"], operation="baseline_head")
            if head.lower() != preparation.baseline_commit:
                raise BaselineWorkspaceError("prepared workspace HEAD differs from the baseline commit")
            _, branch = self.git.run(workspace, ["symbolic-ref", "--quiet", "HEAD"], operation="baseline_branch")
            if branch != f"refs/heads/{preparation.local_branch}":
                raise BaselineWorkspaceError("prepared workspace is on a foreign branch")
            _, dirty = self.git.run(
                workspace,
                ["status", "--porcelain=v1", "--untracked-files=all"],
                operation="baseline_cleanliness",
            )
            if dirty:
                raise BaselineWorkspaceError("prepared workspace is dirty")
        except GitCommandError as exc:
            raise BaselineWorkspaceError("prepared workspace could not be verified") from exc
        return workspace.resolve()

    @staticmethod
    def _common_path(repository: Path, value: str) -> Path:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = repository / candidate
        return candidate.resolve()

    def _report_for_evidence(
        self,
        request: TaskRequest,
        preparation: PreparationRecord,
        evidence: BaselineRunEvidence,
    ) -> dict[str, Any]:
        build_succeeded = bool(evidence.build_results) and all(item.succeeded for item in evidence.build_results)
        if not build_succeeded:
            assessment = BaselineAssessmentStatus.FAILED_BUILD
            scanner_outcome = "NOT_RUN"
            scan_data = None
            finding_count = 0
        elif evidence.scan is None or not evidence.scan.succeeded:
            assessment = BaselineAssessmentStatus.FAILED_SCANNER
            scanner_outcome = (
                evidence.scan.effective_outcome.value if evidence.scan is not None else "INCOMPLETE_FATAL_FAILURE"
            )
            scan_data = evidence.scan.to_dict() if evidence.scan is not None else None
            finding_count = 0
        else:
            finding_count = len(evidence.scan.findings)
            assessment = (
                BaselineAssessmentStatus.COMPLETED
                if finding_count
                else BaselineAssessmentStatus.NO_TARGET_FINDINGS
            )
            scanner_outcome = evidence.scan.effective_outcome.value
            scan_data = evidence.scan.to_dict()
        return {
            "contractVersion": "1",
            "kind": "openhands-shared-baseline",
            "taskId": preparation.task_id,
            "repository": {
                "url": preparation.repository_url,
                "baseRef": preparation.base_ref,
                "localBranch": preparation.local_branch,
            },
            "baselineCommit": preparation.baseline_commit,
            "severityScope": list(request.acceptance.severity_scope),
            "assessmentStatus": assessment.value,
            "buildSucceeded": build_succeeded,
            "buildResults": [item.to_dict() for item in evidence.build_results],
            "scannerOutcome": scanner_outcome,
            "scan": scan_data,
            "originalVulnerabilityFindings": scan_data["findings"] if scan_data is not None else [],
            "constraints": evidence.constraints.to_dict() if evidence.constraints is not None else None,
            "scanner": dict(evidence.scanner_handle),
            "toolVersions": dict(evidence.tool_versions),
            "completedAt": utc_now(),
        }

    @staticmethod
    def _scanner_failure_report(request: TaskRequest, preparation: PreparationRecord) -> dict[str, Any]:
        return {
            "contractVersion": "1",
            "kind": "openhands-shared-baseline",
            "taskId": preparation.task_id,
            "repository": {
                "url": preparation.repository_url,
                "baseRef": preparation.base_ref,
                "localBranch": preparation.local_branch,
            },
            "baselineCommit": preparation.baseline_commit,
            "severityScope": list(request.acceptance.severity_scope),
            "assessmentStatus": BaselineAssessmentStatus.FAILED_SCANNER.value,
            "buildSucceeded": False,
            "buildResults": [],
            "scannerOutcome": "PREFLIGHT_FAILED",
            "scan": None,
            "originalVulnerabilityFindings": [],
            "constraints": None,
            "scanner": {},
            "toolVersions": {},
            "completedAt": utc_now(),
        }

    def _record_from_report(self, report: Mapping[str, Any], artifact: ArtifactMetadata) -> BaselineRecord:
        findings = report.get("originalVulnerabilityFindings")
        if not isinstance(findings, list):
            raise BaselineArtifactError("baseline report has an invalid findings inventory")
        scan = report.get("scan")
        if scan is not None and (
            not isinstance(scan, dict)
            or scan.get("outcome") != report.get("scannerOutcome")
            or scan.get("findings") != findings
        ):
            raise BaselineArtifactError("baseline report scanner result and findings disagree")
        try:
            return BaselineRecord(
                task_id=report["taskId"],
                baseline_commit=report["baselineCommit"],
                assessment_status=BaselineAssessmentStatus(report["assessmentStatus"]),
                build_succeeded=report["buildSucceeded"],
                scanner_outcome=report["scannerOutcome"],
                finding_count=len(findings),
                report_artifact_id=artifact.artifact_id,
                report_sha256=artifact.sha256,
                tool_versions=report.get("toolVersions", {}),
                completed_at=report["completedAt"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BaselineArtifactError("baseline report has invalid assessment metadata") from exc

    def _reconcile_report(
        self,
        task_id: str,
        request: TaskRequest,
        preparation: PreparationRecord,
    ) -> tuple[BaselineRecord, tuple[ArtifactMetadata, ...]] | None:
        relative = self._report_relative_path(task_id)
        path = self.config.artifact_root / relative
        if not path.exists():
            return None
        if not path.is_file() or path.is_symlink():
            raise BaselineArtifactError("baseline report path is not a regular file")
        payload = path.read_bytes()
        try:
            report = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BaselineArtifactError("existing baseline report is invalid") from exc
        if (
            report.get("taskId") != task_id
            or report.get("baselineCommit") != preparation.baseline_commit
            or report.get("repository", {}).get("url") != request.repository.url
            or report.get("repository", {}).get("baseRef") != request.repository.base_ref
        ):
            raise BaselineArtifactError("existing baseline report has foreign identity")
        artifact = ArtifactMetadata(
            artifact_id=REPORT_ARTIFACT_ID,
            task_id=task_id,
            kind="baseline-report",
            relative_path=relative,
            media_type="application/json",
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            created_at=str(report.get("completedAt")),
        )
        evidence_artifacts = self._artifacts_from_report(report)
        for evidence in evidence_artifacts:
            self._verify_artifact_content(evidence)
        return self._record_from_report(report, artifact), (artifact, *evidence_artifacts)

    def _verify_recorded_artifact(self, record: BaselineRecord) -> None:
        artifacts = {item.artifact_id: item for item in self.store.list_artifacts(record.task_id)}
        artifact = artifacts.get(record.report_artifact_id)
        if artifact is None or artifact.sha256 != record.report_sha256:
            raise BaselineArtifactError("recorded baseline artifact metadata is missing or inconsistent")
        for item in artifacts.values():
            if item.kind.startswith("baseline-"):
                self._verify_artifact_content(item)

    def _runtime_artifacts(self, task_id: str, created_at: str) -> tuple[ArtifactMetadata, ...]:
        runtime_root = self._runtime_root(task_id)
        if not runtime_root.exists():
            return ()
        artifacts: list[ArtifactMetadata] = []
        for path in sorted(runtime_root.rglob("*")):
            if path.is_symlink():
                raise BaselineArtifactError("runtime evidence must not contain symbolic links")
            if not path.is_file():
                continue
            relative = path.relative_to(self.config.artifact_root).as_posix()
            digest = _sha256_file(path)
            identifier = f"baseline-evidence-{hashlib.sha256(relative.encode('utf-8')).hexdigest()[:24]}"
            artifacts.append(
                ArtifactMetadata(
                    artifact_id=identifier,
                    task_id=task_id,
                    kind="baseline-evidence",
                    relative_path=relative,
                    media_type="application/json" if path.suffix == ".json" else "text/plain",
                    sha256=digest,
                    size_bytes=path.stat().st_size,
                    created_at=created_at,
                )
            )
        return tuple(artifacts)

    def _artifacts_from_report(self, report: Mapping[str, Any]) -> tuple[ArtifactMetadata, ...]:
        values = report.get("evidenceArtifacts", [])
        if not isinstance(values, list):
            raise BaselineArtifactError("baseline report has an invalid evidence artifact manifest")
        artifacts: list[ArtifactMetadata] = []
        for value in values:
            if not isinstance(value, dict):
                raise BaselineArtifactError("baseline report has invalid artifact metadata")
            try:
                artifacts.append(
                    ArtifactMetadata(
                        artifact_id=value["artifactId"],
                        task_id=value["taskId"],
                        kind=value["kind"],
                        relative_path=value["relativePath"],
                        media_type=value["mediaType"],
                        sha256=value["sha256"],
                        size_bytes=value["sizeBytes"],
                        created_at=value["createdAt"],
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise BaselineArtifactError("baseline report has invalid artifact metadata") from exc
        return tuple(artifacts)

    def _verify_artifact_content(self, artifact: ArtifactMetadata) -> None:
        path = self.config.artifact_root / artifact.relative_path
        if not path.is_file() or path.is_symlink():
            raise BaselineArtifactError("recorded baseline artifact is unavailable")
        digest = _sha256_file(path)
        if digest != artifact.sha256 or path.stat().st_size != artifact.size_bytes:
            raise BaselineArtifactError("recorded baseline artifact failed integrity verification")

    def _write_immutable(self, relative_path: str, payload: bytes) -> Path:
        relative = safe_artifact_path(relative_path)
        target = self.config.artifact_root / relative
        root = self.config.artifact_root
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise BaselineArtifactError("artifact root must not be a symbolic link")
        target.parent.mkdir(parents=True, exist_ok=True)
        current = root
        for part in Path(relative).parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise BaselineArtifactError("artifact path must not traverse symbolic links")
        if target.exists():
            if target.is_file() and not target.is_symlink() and target.read_bytes() == payload:
                return target
            raise BaselineArtifactError("refusing to overwrite an existing baseline artifact")
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if not target.is_file() or target.is_symlink() or target.read_bytes() != payload:
                    raise BaselineArtifactError("concurrent baseline artifact conflicts with evidence")
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def _ensure_artifact_boundary(self, task_id: str) -> None:
        root = self.config.artifact_root
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise BaselineArtifactError("artifact root must not be a symbolic link")
        current = root
        for part in (safe_artifact_path(task_id), "baseline"):
            current = current / part
            if current.exists() and current.is_symlink():
                raise BaselineArtifactError("task artifact path must not traverse symbolic links")
            current.mkdir(exist_ok=True)

    def _report_relative_path(self, task_id: str) -> str:
        return safe_artifact_path(f"{task_id}/{REPORT_RELATIVE_SUFFIX}")

    def _runtime_root(self, task_id: str) -> Path:
        return self.config.artifact_root / safe_artifact_path(f"{task_id}/baseline/runtime")

    def _task_lock(self, task_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(task_id, threading.Lock())


class _BaselineProcessRunner(ProcessRunner):
    """ProcessRunner variant with a constructed credential-free environment."""

    def __init__(self, *args: Any, environment: Mapping[str, str], **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._baseline_environment = dict(environment)

    def run_deterministic_shell(
        self,
        command: str,
        cwd: str | Path,
        timeout_seconds: int | None = None,
        environment: Mapping[str, str] | None = None,
        source: str = "deterministic",
    ) -> CommandResult:
        return super().run_deterministic_shell(
            command,
            cwd,
            timeout_seconds,
            environment=self._baseline_environment,
            source=source,
        )

    def run_argv(
        self,
        command: Sequence[str],
        cwd: str | Path | None = None,
        timeout_seconds: int | None = None,
        environment: Mapping[str, str] | None = None,
        source: str = "deterministic",
        redact_values: Sequence[str] = (),
        display_command: Sequence[str] | None = None,
    ) -> CommandResult:
        return super().run_argv(
            command,
            cwd,
            timeout_seconds,
            environment=self._baseline_environment,
            source=source,
            redact_values=redact_values,
            display_command=display_command,
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
