from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Outcome(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_MANUAL_REVIEW_REQUIRED = "PARTIAL / MANUAL REVIEW REQUIRED"
    NO_SAFE_REMEDIATION = "NO SAFE REMEDIATION"
    EXECUTION_LIMIT_REACHED = "EXECUTION LIMIT REACHED"
    REQUESTED_VULNERABILITY_NOT_FOUND = "REQUESTED_VULNERABILITY_NOT_FOUND"
    BASELINE_FAILURE = "BASELINE FAILURE"


class ScanOutcome(str, Enum):
    COMPLETED_CLEAN = "COMPLETED_CLEAN"
    COMPLETED_WITH_FINDINGS = "COMPLETED_WITH_FINDINGS"
    INCOMPLETE_RETRYABLE_FAILURE = "INCOMPLETE_RETRYABLE_FAILURE"
    INCOMPLETE_FATAL_FAILURE = "INCOMPLETE_FATAL_FAILURE"


class ScanFailureKind(str, Enum):
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    NETWORK = "NETWORK"
    TIMEOUT = "TIMEOUT"
    DEPENDENCY_RESOLUTION = "DEPENDENCY_RESOLUTION"
    CONFIGURATION = "CONFIGURATION"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    BACKEND = "BACKEND"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False
    blocked: bool = False
    stdout_artifact: str | None = None
    stderr_artifact: str | None = None

    @property
    def succeeded(self) -> bool:
        return not self.blocked and not self.timed_out and self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "exitCode": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "durationSeconds": self.duration_seconds,
            "timedOut": self.timed_out,
            "blocked": self.blocked,
            "stdoutArtifact": self.stdout_artifact,
            "stderrArtifact": self.stderr_artifact,
        }


@dataclass(frozen=True)
class VulnerabilityFinding:
    vulnerability_id: str
    aliases: tuple[str, ...]
    severity: str
    group_id: str | None
    artifact_id: str | None
    package_name: str
    version: str
    fixed_versions: tuple[str, ...] = ()
    summary: str = ""
    ecosystem: str = "Maven"
    backend_evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def coordinate(self) -> str:
        if self.group_id and self.artifact_id:
            return f"{self.group_id}:{self.artifact_id}"
        return self.package_name

    @property
    def identifiers(self) -> frozenset[str]:
        return frozenset(
            value.upper()
            for value in (self.vulnerability_id, *self.aliases)
            if value
        )

    @property
    def identity(self) -> str:
        canonical = sorted(self.identifiers)[0] if self.identifiers else "UNKNOWN"
        return f"{canonical}|{self.coordinate}"

    def matches(self, other: "VulnerabilityFinding") -> bool:
        return self.coordinate == other.coordinate and bool(self.identifiers & other.identifiers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vulnerabilityId": self.vulnerability_id,
            "aliases": list(self.aliases),
            "severity": self.severity,
            "dependency": {
                "groupId": self.group_id,
                "artifactId": self.artifact_id,
                "packageName": self.package_name,
                "ecosystem": self.ecosystem,
                "currentVersion": self.version,
            },
            "fixedVersions": list(self.fixed_versions),
            "summary": self.summary,
            "identity": self.identity,
            "backendEvidence": dict(self.backend_evidence),
        }


@dataclass(frozen=True)
class ScanReport:
    succeeded: bool
    findings: tuple[VulnerabilityFinding, ...]
    command_result: CommandResult | None
    raw_report_path: str
    error: str | None = None
    outcome: ScanOutcome | None = None
    attempts: tuple[dict[str, Any], ...] = ()
    backend: str = "osv"
    failure_kind: ScanFailureKind | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_outcome(self) -> ScanOutcome:
        if self.outcome is not None:
            return self.outcome
        if not self.succeeded:
            return ScanOutcome.INCOMPLETE_FATAL_FAILURE
        if self.findings:
            return ScanOutcome.COMPLETED_WITH_FINDINGS
        return ScanOutcome.COMPLETED_CLEAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "succeeded": self.succeeded,
            "findings": [finding.to_dict() for finding in self.findings],
            "commandResult": self.command_result.to_dict() if self.command_result else None,
            "rawReportPath": self.raw_report_path,
            "error": self.error,
            "outcome": self.effective_outcome.value,
            "attempts": list(self.attempts),
            "backend": self.backend,
            "failureKind": self.failure_kind.value if self.failure_kind else None,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ScannerHandle:
    executable: str
    version: str
    sha256: str
    provisioned: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConstraintBaseline:
    java_versions: tuple[str, ...] = ()
    spring_boot_versions: tuple[str, ...] = ()
    suppression_files: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "javaVersions": list(self.java_versions),
            "springBootVersions": list(self.spring_boot_versions),
            "suppressionFiles": dict(self.suppression_files),
        }


@dataclass(frozen=True)
class RepositoryBaseline:
    repository_path: str
    commit: str
    reference: str
    remote_url: str
    build_results: tuple[CommandResult, ...]
    scan: ScanReport
    constraints: ConstraintBaseline
    target_findings: tuple[VulnerabilityFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "repositoryPath": self.repository_path,
            "commit": self.commit,
            "reference": self.reference,
            "remoteUrl": self.remote_url,
            "buildResults": [result.to_dict() for result in self.build_results],
            "scan": self.scan.to_dict(),
            "constraints": self.constraints.to_dict(),
            "targetFindings": [finding.to_dict() for finding in self.target_findings],
        }


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    passed: bool
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RepositoryCycleEvidence:
    before_state_digest: str
    after_state_digest: str
    before_changed_files: tuple[str, ...]
    after_changed_files: tuple[str, ...]
    paths_added_to_change_set: tuple[str, ...]
    paths_modified_since_cycle_start: tuple[str, ...]
    paths_removed_from_change_set: tuple[str, ...]
    repository_state_changed: bool
    matches_prior_cycle: int | None
    delta_path: str
    before_state_captured: bool = True
    after_state_captured: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "beforeStateDigest": self.before_state_digest,
            "afterStateDigest": self.after_state_digest,
            "beforeChangedFiles": list(self.before_changed_files),
            "afterChangedFiles": list(self.after_changed_files),
            "pathsAddedToChangeSet": list(self.paths_added_to_change_set),
            "pathsModifiedSinceCycleStart": list(self.paths_modified_since_cycle_start),
            "pathsRemovedFromChangeSet": list(self.paths_removed_from_change_set),
            "repositoryStateChanged": self.repository_state_changed,
            "matchesPriorCycle": self.matches_prior_cycle,
            "deltaPath": self.delta_path,
            "beforeStateCaptured": self.before_state_captured,
            "afterStateCaptured": self.after_state_captured,
        }


@dataclass(frozen=True)
class ValidationReport:
    cycle: int
    passed: bool
    checks: tuple[ValidationCheck, ...]
    changed_files: tuple[str, ...]
    diff_path: str
    tree_digest: str
    scan: ScanReport | None = None
    delivery_eligible: bool = True
    warnings: tuple[str, ...] = ()
    cycle_evidence: RepositoryCycleEvidence | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "changedFiles": list(self.changed_files),
            "diffPath": self.diff_path,
            "treeDigest": self.tree_digest,
            "scan": self.scan.to_dict() if self.scan else None,
            "deliveryEligible": self.delivery_eligible,
            "warnings": list(self.warnings),
            "cycleEvidence": self.cycle_evidence.to_dict() if self.cycle_evidence else None,
        }


@dataclass(frozen=True)
class DeliveryPreflight:
    eligible: bool
    adapter: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeliveryResult:
    succeeded: bool
    status: str
    branch: str | None = None
    commit: str | None = None
    pull_request_url: str | None = None
    reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "succeeded": self.succeeded,
            "status": self.status,
            "branch": self.branch,
            "commit": self.commit,
            "pullRequestUrl": self.pull_request_url,
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class AgentTurnResult:
    text: str


@dataclass(frozen=True)
class RunResult:
    outcome: Outcome
    reason: str
    workspace_root: str
    baseline: RepositoryBaseline | None = None
    validation: ValidationReport | None = None
    delivery: DeliveryResult | None = None
    cycles_completed: int = 0
    agent_summaries: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "workspaceRoot": self.workspace_root,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "delivery": self.delivery.to_dict() if self.delivery else None,
            "cyclesCompleted": self.cycles_completed,
            "agentSummaries": list(self.agent_summaries),
        }


def relative_to_string(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/")
