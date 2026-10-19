"""Independent validation and native Stop Hook policy for M2 Change 6.

The adapter reuses :class:`DeterministicValidator`; it does not implement an
agent loop, scanner, Maven runner, or substitute acceptance engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from autonomous_oss_remediation_agent.capabilities.execution import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import (
    ConstraintSpec,
    ExecutionBudgetConfig,
    MavenConfig,
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

from .contracts import (
    ArtifactMetadata,
    ContractValidationError,
    StopHookDecision,
    TaskRequest,
    ValidationAttemptRecord,
    ValidationAttemptState,
    ValidationOutcome,
    canonical_json,
    reject_sensitive_input,
    safe_artifact_path,
    utc_now,
)
from .preparation import GitCommandError, GitRunner
from .store import SQLiteTaskStore
from .tool_environment import tool_environment


class SharedValidationError(RuntimeError):
    pass


class ValidationConfigurationError(SharedValidationError):
    pass


class ValidationIdentityError(SharedValidationError):
    pass


class ValidationInfrastructureError(SharedValidationError):
    """Known Maven/scanner/runner infrastructure failure."""


class ValidationRecoveryRequiredError(SharedValidationError):
    pass


@dataclass(frozen=True)
class ValidationProfile:
    profile_id: str
    build_commands: tuple[str, ...]
    maven: MavenConfig
    scanner: ScannerConfig
    budget: ExecutionBudgetConfig = field(
        default_factory=lambda: ExecutionBudgetConfig(
            max_cycles=1,
            max_tool_calls=40,
            command_timeout_seconds=1800,
            overall_timeout_seconds=3600,
            max_returned_output_chars=30_000,
        )
    )

    def __post_init__(self) -> None:
        if not self.profile_id or not self.build_commands:
            raise ValidationConfigurationError("validation profile and build commands are required")
        if self.scanner.backend != "osv":
            raise ValidationConfigurationError("shared validation requires the approved OSV backend")


@dataclass(frozen=True)
class ValidationConfig:
    artifact_root: Path
    profiles: tuple[ValidationProfile, ...]
    max_feedback_characters: int = 4000

    def __post_init__(self) -> None:
        root = self.artifact_root.expanduser().resolve(strict=False)
        if root.exists() and root.is_symlink():
            raise ValidationConfigurationError("artifact root cannot be a symbolic link")
        object.__setattr__(self, "artifact_root", root)
        if not 256 <= self.max_feedback_characters <= 4000:
            raise ValidationConfigurationError("validation feedback bound is invalid")
        names = [item.profile_id for item in self.profiles]
        if len(names) != len(set(names)):
            raise ValidationConfigurationError("validation profiles must be unique")

    def profile_for(self, request: TaskRequest) -> ValidationProfile:
        matches = [item for item in self.profiles if item.profile_id == request.agent.profile]
        if len(matches) != 1:
            raise ValidationConfigurationError("task does not select one approved validation profile")
        profile = matches[0]
        if profile.build_commands != request.acceptance.build_commands:
            raise ValidationConfigurationError("validation build commands differ from the task contract")
        return profile


class ValidationRunner(Protocol):
    def run(
        self,
        repository: Path,
        request: TaskRequest,
        profile: ValidationProfile,
        baseline_document: Mapping[str, Any],
        attempt: int,
        runtime_root: Path,
    ) -> Mapping[str, Any]: ...


class ExistingDeterministicValidationRunner:
    """Run the repository's existing independent deterministic validator."""

    def run(
        self,
        repository: Path,
        request: TaskRequest,
        profile: ValidationProfile,
        baseline_document: Mapping[str, Any],
        attempt: int,
        runtime_root: Path,
    ) -> Mapping[str, Any]:
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
            workspace.artifacts, workspace.cache, workspace.temp,
            workspace.tools, workspace.investigation,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        trace = TraceStore(workspace)
        execution_home = runtime_root / "execution-home"
        execution_home.mkdir(exist_ok=True)
        runner = _ValidationProcessRunner(
            workspace,
            trace,
            ExecutionBudget(profile.budget),
            RuntimePolicy(
                trusted_repository=True,
                dedicated_runner=True,
                enable_autonomous_shell=False,
                allow_network=True,
            ),
            environment=tool_environment(execution_home),
        )
        scanner = create_scanner(
            profile.scanner, workspace, runner, trace, maven_config=profile.maven
        )
        try:
            scanner.preflight(profile.scanner)
        except ScannerPreflightError as exc:
            raise ValidationInfrastructureError("approved scanner preflight failed") from exc
        remediation = _remediation_request(request, profile)
        baseline = _baseline_from_document(baseline_document, repository)
        report = DeterministicValidator(
            remediation, workspace, runner, scanner, ConstraintEvaluator(), trace
        ).validate(attempt, baseline)
        return report.to_dict()


@dataclass(frozen=True)
class StopHookResponse:
    decision: StopHookDecision
    reason: str
    additional_context: str | None = None

    @property
    def exit_code(self) -> int:
        return 2 if self.decision is StopHookDecision.DENY else 0

    def to_native_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "decision": self.decision.value.lower(),
            "reason": self.reason,
        }
        if self.additional_context:
            value["additionalContext"] = self.additional_context
        return value


class SharedValidationService:
    """Trusted internal Stop Hook target with durable bounded attempts."""

    def __init__(
        self,
        store: SQLiteTaskStore,
        config: ValidationConfig,
        *,
        runner: ValidationRunner | None = None,
        git: GitRunner | None = None,
    ):
        self.store = store
        self.config = config
        self.runner = runner or ExistingDeterministicValidationRunner()
        self.git = git or GitRunner()
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def handle_stop(self, task_id: str, *, workspace_argument: str | None = None) -> StopHookResponse:
        with self._task_lock(task_id):
            request = self.store.get_request(task_id)
            profile = self.config.profile_for(request)
            preparation, baseline_document, workspace = self._verified_inputs(task_id, request)
            if workspace_argument is not None and Path(workspace_argument).resolve() != workspace:
                raise ValidationIdentityError("Stop Hook workspace argument differs from durable preparation")
            prior_running = next(
                (
                    item for item in self.store.list_validation_attempts(task_id)
                    if item.state is ValidationAttemptState.RUNNING
                ),
                None,
            )
            attempt = self.store.begin_validation(task_id)
            report_path = self._report_path(task_id, attempt.attempt)
            if report_path.exists():
                return self._reconcile_existing(task_id, request, attempt, report_path, workspace)
            if prior_running is not None:
                validator_report = _failure_report(
                    "VALIDATOR_FAILURE",
                    "Interrupted validation has no complete immutable report; it will not be rerun automatically.",
                )
                outcome = ValidationOutcome.VALIDATOR_FAILURE
                classification_detail = "Interrupted validator state requires a fresh task/operator decision."
            else:
                try:
                    raw_report = self.runner.run(
                        workspace, request, profile, baseline_document, attempt.attempt,
                        self._runtime_root(task_id, attempt.attempt),
                    )
                    validator_report = _validated_report(raw_report)
                    outcome = _validation_outcome(validator_report)
                    classification_detail = None
                except ValidationInfrastructureError as exc:
                    validator_report = _failure_report("INFRASTRUCTURE_FAILURE", str(exc))
                    outcome = ValidationOutcome.INFRASTRUCTURE_FAILURE
                    classification_detail = "Validator infrastructure was unavailable."
                except Exception as exc:
                    validator_report = _failure_report("VALIDATOR_FAILURE", type(exc).__name__)
                    outcome = ValidationOutcome.VALIDATOR_FAILURE
                    classification_detail = "Validator result was missing, corrupt, or internally invalid."

            state = self._capture_repository_state(workspace, preparation.baseline_commit)
            decision = self._decision(request, attempt.attempt, outcome)
            feedback = self._feedback(validator_report, attempt.attempt, classification_detail)
            envelope = {
                "contractVersion": "1",
                "kind": "openhands-shared-validation",
                "taskId": task_id,
                "attempt": attempt.attempt,
                "conversationId": attempt.conversation_id,
                "baselineCommit": preparation.baseline_commit,
                "outcome": outcome.value,
                "hookDecision": decision.value,
                "validatedRepository": state,
                "validatorReport": validator_report,
                "completedAt": utc_now(),
            }
            try:
                reject_sensitive_input(envelope, "validationReport")
            except ContractValidationError:
                validator_report = _failure_report(
                    "VALIDATOR_FAILURE",
                    "Validation evidence failed the credential-safety policy.",
                )
                outcome = ValidationOutcome.VALIDATOR_FAILURE
                decision = StopHookDecision.ALLOW
                feedback = self._feedback(
                    validator_report,
                    attempt.attempt,
                    "Unsafe validator evidence was rejected and was not persisted.",
                )
                envelope.update(
                    {
                        "outcome": outcome.value,
                        "hookDecision": decision.value,
                        "validatorReport": validator_report,
                    }
                )
            reject_sensitive_input(feedback, "validationFeedback")
            payload = (canonical_json(envelope) + "\n").encode("utf-8")
            self._write_immutable(report_path, payload)
            record, artifact = self._record_and_artifact(
                task_id, attempt, envelope, payload, feedback
            )
            self.store.complete_validation(record, artifact)
            return self._response(record)

    def verify_validated_state(self, task_id: str, attempt_number: int | None = None) -> bool:
        attempts = self.store.list_validation_attempts(task_id)
        candidates = [item for item in attempts if item.state is ValidationAttemptState.COMPLETED]
        if attempt_number is not None:
            candidates = [item for item in candidates if item.attempt == attempt_number]
        if not candidates:
            raise ValidationIdentityError("no completed validation attempt exists")
        record = candidates[-1]
        preparation = self.store.get_preparation(task_id)
        if preparation is None:
            raise ValidationIdentityError("durable preparation is missing")
        state = self._capture_repository_state(Path(preparation.workspace_path), preparation.baseline_commit)
        return (
            state["head"] == record.validated_head
            and state["tree"] == record.validated_tree
            and state["stateSha256"] == record.repository_state_sha256
        )

    def associate_native_hook_event(
        self, task_id: str, attempt_number: int, event: Mapping[str, Any]
    ) -> None:
        """Link the bounded verdict to its native 1.50.0 HookExecutionEvent."""

        event_id = event.get("id")
        kind = event.get("kind") or event.get("event_type")
        hook_type = event.get("hook_event_type") or event.get("hookEventType")
        if (
            not isinstance(event_id, str)
            or kind != "HookExecutionEvent"
            or hook_type != "Stop"
        ):
            raise ValidationIdentityError("native event is not a pinned Stop Hook execution event")
        attempts = {
            item.attempt: item for item in self.store.list_validation_attempts(task_id)
        }
        record = attempts.get(attempt_number)
        if record is None or record.state is not ValidationAttemptState.COMPLETED:
            raise ValidationIdentityError("native hook event has no completed validation attempt")
        blocked = event.get("blocked")
        if not isinstance(blocked, bool) or blocked != (
            record.hook_decision is StopHookDecision.DENY
        ):
            raise ValidationIdentityError("native hook event decision differs from durable validation")
        self.store.link_validation_hook_event(task_id, attempt_number, event_id)

    def _verified_inputs(self, task_id: str, request: TaskRequest):
        preparation = self.store.get_preparation(task_id)
        baseline = self.store.get_baseline(task_id)
        intelligence = self.store.get_intelligence(task_id)
        runtime = self.store.get_openhands_runtime(task_id)
        claim = self.store.get_execution_claim(task_id)
        if None in (preparation, baseline, intelligence, runtime, claim):
            raise ValidationIdentityError("validation requires all prior durable stage records")
        if preparation.repository_url != request.repository.url or preparation.baseline_commit != request.repository.expected_commit:
            raise ValidationIdentityError("registered repository identity differs from preparation")
        if runtime.workspace_path != preparation.workspace_path or runtime.baseline_commit != preparation.baseline_commit:
            raise ValidationIdentityError("native runtime identity differs from preparation")
        if claim.conversation_id != runtime.conversation_id:
            raise ValidationIdentityError("execution claim belongs to another conversation")
        workspace = self._verify_workspace(request, preparation)
        artifacts = {item.artifact_id: item for item in self.store.list_artifacts(task_id)}
        required_ids = {
            baseline.report_artifact_id, intelligence.record_artifact_id,
            intelligence.summary_artifact_id,
        }
        if not required_ids.issubset(artifacts):
            raise ValidationIdentityError("baseline/intelligence artifact metadata is incomplete")
        for artifact_id in required_ids:
            self._verify_artifact(artifacts[artifact_id])
        baseline_artifact = artifacts[baseline.report_artifact_id]
        if baseline_artifact.sha256 != baseline.report_sha256:
            raise ValidationIdentityError("baseline report hash differs from durable metadata")
        try:
            document = json.loads((self.config.artifact_root / baseline_artifact.relative_path).read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationIdentityError("baseline report is unreadable") from exc
        if (
            not isinstance(document, Mapping)
            or document.get("baselineCommit") != preparation.baseline_commit
            or not isinstance(document.get("originalVulnerabilityFindings"), list)
            or len(document.get("originalVulnerabilityFindings")) != baseline.finding_count
        ):
            raise ValidationIdentityError("baseline report identity or finding inventory is invalid")
        if document.get("taskId") != task_id:
            # A recovered task inherits the original immutable baseline report.
            # Its correlation is a provenance reference, not a trust exemption.
            original_id = request.correlation_id
            if not original_id or document.get("taskId") != original_id or original_id == task_id:
                raise ValidationIdentityError("baseline report belongs to another task without recovery provenance")
            old_request = self.store.get_request(original_id)
            old_preparation = self.store.get_preparation(original_id)
            old_baseline = self.store.get_baseline(original_id)
            old_artifacts = {item.artifact_id: item for item in self.store.list_artifacts(original_id)}
            original_artifact = old_artifacts.get(baseline.report_artifact_id)
            if (
                old_preparation is None or old_baseline is None or original_artifact is None
                or old_baseline.report_sha256 != baseline.report_sha256
                or original_artifact.sha256 != baseline_artifact.sha256
                or original_artifact.relative_path != baseline_artifact.relative_path
                or old_preparation.baseline_commit != preparation.baseline_commit
                or old_request.repository != request.repository
                or old_request.objective != request.objective
                or old_request.constraints != request.constraints
                or old_request.acceptance != request.acceptance
                or old_request.agent != request.agent
                or old_request.sbri_mode != request.sbri_mode
                or old_request.delivery_mode != request.delivery_mode
            ):
                raise ValidationIdentityError("reused baseline provenance or contract mismatch")
            self._verify_artifact(original_artifact)
        return preparation, document, workspace

    def _verify_workspace(self, request: TaskRequest, preparation: Any) -> Path:
        workspace = Path(preparation.workspace_path)
        source = Path(preparation.source_path)
        if not workspace.is_dir() or workspace.is_symlink() or not source.is_dir() or source.is_symlink():
            raise ValidationIdentityError("task workspace identity is unavailable")
        try:
            _, workspace_common = self.git.run(workspace, ["rev-parse", "--git-common-dir"], operation="validation_workspace_identity")
            _, source_common = self.git.run(source, ["rev-parse", "--git-common-dir"], operation="validation_source_identity")
            if _common_path(workspace, workspace_common) != _common_path(source, source_common):
                # Recovery uses a separate git clone rather than a linked worktree.
                # Require an explicit, content-verified lineage to the trusted source.
                if not request.correlation_id:
                    raise ValidationIdentityError("task workspace belongs to another repository")
                old_prep = self.store.get_preparation(request.correlation_id)
                if old_prep is None or Path(old_prep.source_path).resolve() != source.resolve():
                    raise ValidationIdentityError("recovery workspace source does not match provenance")
                _, origin = self.git.run(workspace, ["remote", "get-url", "origin"], operation="validation_recovery_origin")
                if Path(origin.strip()).resolve() != source.resolve():
                    raise ValidationIdentityError("recovery clone origin differs from trusted source")
                _, source_head = self.git.run(source, ["rev-parse", "HEAD"], operation="validation_recovery_source_commit")
                if source_head.strip() != preparation.baseline_commit:
                    raise ValidationIdentityError("recovery trusted source commit has changed")
            code, branch = self.git.run(workspace, ["symbolic-ref", "--quiet", "HEAD"], operation="validation_branch", allowed_return_codes=frozenset({0, 1}))
            if code != 0 or branch != f"refs/heads/{preparation.local_branch}":
                raise ValidationIdentityError("task workspace is on another branch")
            code, _ = self.git.run(workspace, ["merge-base", "--is-ancestor", preparation.baseline_commit, "HEAD"], operation="validation_ancestry", allowed_return_codes=frozenset({0, 1}))
            if code != 0:
                raise ValidationIdentityError("immutable baseline is not an ancestor of task HEAD")
        except GitCommandError as exc:
            raise ValidationIdentityError("task Git identity could not be verified") from exc
        return workspace.resolve()

    def _capture_repository_state(self, workspace: Path, baseline_commit: str) -> dict[str, str]:
        self._verify_workspace(self.store.get_request(self._task_id_for_workspace(workspace)), self.store.get_preparation(self._task_id_for_workspace(workspace)))
        runtime = workspace.parent / ".validation-index"
        runtime.mkdir(exist_ok=True)
        index = runtime / f"index-{uuid.uuid4().hex}"
        env = {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C", "GIT_INDEX_FILE": str(index)}
        try:
            _run_git(workspace, ["read-tree", "HEAD"], env=env)
            _run_git(workspace, ["add", "-A"], env=env)
            tree = _run_git(workspace, ["write-tree"], env=env)
        finally:
            if index.exists():
                index.unlink()
        head = _run_git(workspace, ["rev-parse", "HEAD"])
        status = _run_git_bytes(workspace, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        state_hash = hashlib.sha256(
            baseline_commit.encode() + b"\0" + head.encode() + b"\0" + tree.encode() + b"\0" + status
        ).hexdigest()
        return {"head": head, "tree": tree, "stateSha256": state_hash}

    def _task_id_for_workspace(self, workspace: Path) -> str:
        # Runtime records provide the authoritative reverse association; this
        # private lookup is deliberately narrow and read-only.
        connection = self.store._connect()
        try:
            row = connection.execute(
                "SELECT task_id FROM openhands_runtimes WHERE workspace_path = ?", (str(workspace.resolve()),)
            ).fetchone()
            if row is None:
                raise ValidationIdentityError("workspace is not associated with a task")
            return str(row["task_id"])
        finally:
            connection.close()

    def _decision(self, request: TaskRequest, attempt: int, outcome: ValidationOutcome) -> StopHookDecision:
        if outcome is ValidationOutcome.PASS:
            return StopHookDecision.ALLOW
        if outcome is ValidationOutcome.REMEDIATION_FAILURE and attempt <= request.agent.max_validation_denials:
            return StopHookDecision.DENY
        return StopHookDecision.ALLOW

    def _feedback(self, report: Mapping[str, Any], attempt: int, detail: str | None) -> str:
        parts = [detail] if detail else []
        checks = report.get("checks")
        if isinstance(checks, list):
            failed = [
                f"{item.get('name', 'check')}: {str(item.get('message', '')).strip()}"
                for item in checks if isinstance(item, Mapping) and not item.get("passed", False)
            ]
            if failed:
                parts.append("Failed deterministic checks: " + " | ".join(failed[:8]))
        for key, label in (
            ("remainingTargetFindings", "remaining original findings"),
            ("unknownTargetFindings", "unknown original findings"),
        ):
            value = report.get(key)
            if isinstance(value, list):
                parts.append(f"{label}: {len(value)}")
                if value:
                    parts.append(label + " identities: " + " | ".join(
                        _finding_summary(item) for item in value[:12]
                    ))
        resolved = report.get("resolvedTargetFindings")
        if isinstance(resolved, list):
            parts.append(f"current validated progress: {len(resolved)} original findings resolved")
        new_findings: list[Any] = []
        for check in report.get("checks") or ():
            if isinstance(check, Mapping) and check.get("name") == "no_new_prohibited_findings":
                candidate = (check.get("evidence") or {}).get("newFindings")
                if isinstance(candidate, list):
                    new_findings = candidate
        parts.append(f"new prohibited findings: {len(new_findings)}")
        if new_findings:
            parts.append("new prohibited finding identities: " + " | ".join(
                _finding_summary(item) for item in new_findings[:12]
            ))
        if not parts:
            parts.append("Independent deterministic validation did not pass.")
        text = (
            f"DETERMINISTIC_VALIDATION_FAILED attempt {attempt}: "
            + " ".join(parts)
            + " Reassess using this evidence; choose and validate the next engineering action independently."
        )
        return text[: self.config.max_feedback_characters]

    def _record_and_artifact(self, task_id: str, running: ValidationAttemptRecord, envelope: Mapping[str, Any], payload: bytes, feedback: str):
        report = envelope["validatorReport"]
        outcome = ValidationOutcome(envelope["outcome"])
        decision = StopHookDecision(envelope["hookDecision"])
        coverage = _coverage(report)
        completed = str(envelope["completedAt"])
        artifact_id = f"validation-attempt-{running.attempt}"
        relative = safe_artifact_path(f"{task_id}/validation/attempt-{running.attempt}/report.json")
        artifact = ArtifactMetadata(
            artifact_id=artifact_id, task_id=task_id, kind="validation-report",
            relative_path=relative, media_type="application/json",
            sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload), created_at=completed,
        )
        state = envelope["validatedRepository"]
        record = ValidationAttemptRecord(
            task_id=task_id, attempt=running.attempt, state=ValidationAttemptState.COMPLETED,
            outcome=outcome, hook_decision=decision,
            report_artifact_id=artifact_id, report_sha256=artifact.sha256,
            validated_head=state["head"], validated_tree=state["tree"],
            repository_state_sha256=state["stateSha256"],
            original_finding_count=coverage["original"], resolved_finding_count=coverage["resolved"],
            remaining_finding_count=coverage["remaining"], unknown_finding_count=coverage["unknown"],
            new_prohibited_finding_count=coverage["new"], constraints_passed=coverage["constraintsPassed"],
            bounded_feedback=(feedback if decision is StopHookDecision.DENY else None),
            conversation_id=running.conversation_id, native_hook_event_id=None,
            started_at=running.started_at, completed_at=completed,
        )
        return record, artifact

    def _response(self, record: ValidationAttemptRecord) -> StopHookResponse:
        if record.outcome is ValidationOutcome.PASS:
            reason = f"Independent deterministic validation passed on stop attempt {record.attempt}."
            return StopHookResponse(StopHookDecision.ALLOW, reason)
        if record.hook_decision is StopHookDecision.DENY:
            return StopHookResponse(
                StopHookDecision.DENY,
                f"Independent deterministic validation failed on stop attempt {record.attempt}.",
                record.bounded_feedback,
            )
        reason = (
            f"Validation could not accept stop attempt {record.attempt}; native termination is allowed "
            f"only because the denial bound or an infrastructure boundary was reached. "
            "Deterministic acceptance has NOT passed."
        )
        return StopHookResponse(StopHookDecision.ALLOW, reason)

    def _reconcile_existing(self, task_id: str, request: TaskRequest, running: ValidationAttemptRecord, path: Path, workspace: Path) -> StopHookResponse:
        try:
            payload = path.read_bytes()
            envelope = json.loads(payload)
            if (
                not isinstance(envelope, Mapping)
                or set(envelope) != {
                    "contractVersion", "kind", "taskId", "attempt", "conversationId",
                    "baselineCommit", "outcome", "hookDecision", "validatedRepository",
                    "validatorReport", "completedAt",
                }
                or envelope.get("contractVersion") != "1"
                or envelope.get("kind") != "openhands-shared-validation"
                or envelope.get("taskId") != task_id
                or envelope.get("attempt") != running.attempt
                or envelope.get("conversationId") != running.conversation_id
            ):
                raise ValueError("foreign validation report")
            reject_sensitive_input(envelope, "validationReport")
            preparation = self.store.get_preparation(task_id)
            if preparation is None or envelope.get("baselineCommit") != preparation.baseline_commit:
                raise ValueError("validation report baseline differs from durable preparation")
            report = _validated_report(envelope.get("validatorReport"))
            classification = report.get("failureClassification")
            if classification == ValidationOutcome.VALIDATOR_FAILURE.value:
                outcome = ValidationOutcome.VALIDATOR_FAILURE
            elif classification == ValidationOutcome.INFRASTRUCTURE_FAILURE.value:
                outcome = ValidationOutcome.INFRASTRUCTURE_FAILURE
            else:
                outcome = _validation_outcome(report)
            if envelope.get("outcome") != outcome.value:
                raise ValueError("validation report outcome is inconsistent")
            if envelope.get("hookDecision") != self._decision(
                request, running.attempt, outcome
            ).value:
                raise ValueError("validation report Stop Hook decision is inconsistent")
            state = envelope.get("validatedRepository")
            if not isinstance(state, Mapping) or dict(state) != self._capture_repository_state(
                workspace, preparation.baseline_commit
            ):
                raise ValueError("validation report repository state is stale or invalid")
            record, artifact = self._record_and_artifact(
                task_id, running, envelope, payload,
                self._feedback(report, running.attempt, None),
            )
            self.store.complete_validation(record, artifact)
            return self._response(record)
        except Exception as exc:
            raise ValidationRecoveryRequiredError("existing validation report cannot be reconciled safely") from exc

    def _verify_artifact(self, artifact: ArtifactMetadata) -> None:
        path = self.config.artifact_root / artifact.relative_path
        if not path.is_file() or path.is_symlink():
            raise ValidationIdentityError("required stage artifact is unavailable")
        payload = path.read_bytes()
        if len(payload) != artifact.size_bytes or hashlib.sha256(payload).hexdigest() != artifact.sha256:
            raise ValidationIdentityError("required stage artifact failed integrity verification")

    def _write_immutable(self, path: Path, payload: bytes) -> None:
        self.config.artifact_root.mkdir(parents=True, exist_ok=True)
        try:
            relative = path.relative_to(self.config.artifact_root)
        except ValueError as exc:
            raise ValidationIdentityError("validation artifact escaped its configured root") from exc
        if self.config.artifact_root.is_symlink():
            raise ValidationIdentityError("validation artifact path cannot traverse symbolic links")
        current = self.config.artifact_root
        for part in relative.parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise ValidationIdentityError("validation artifact path cannot traverse symbolic links")
            current.mkdir(exist_ok=True)
        if path.exists():
            if path.is_file() and not path.is_symlink() and path.read_bytes() == payload:
                return
            raise ValidationRecoveryRequiredError("refusing to overwrite validation evidence")
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _report_path(self, task_id: str, attempt: int) -> Path:
        return self.config.artifact_root / safe_artifact_path(
            f"{task_id}/validation/attempt-{attempt}/report.json"
        )

    def _runtime_root(self, task_id: str, attempt: int) -> Path:
        return self.config.artifact_root / safe_artifact_path(
            f"{task_id}/validation/attempt-{attempt}/runtime"
        )

    def _task_lock(self, task_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(task_id, threading.Lock())


class _ValidationProcessRunner(ProcessRunner):
    def __init__(self, *args: Any, environment: Mapping[str, str], **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._validation_environment = dict(environment)

    def run_deterministic_shell(self, command: str, cwd: str | Path, timeout_seconds: int | None = None, environment: Mapping[str, str] | None = None, source: str = "deterministic"):
        return super().run_deterministic_shell(command, cwd, timeout_seconds, environment=self._validation_environment, source=source)

    def run_argv(self, command: Sequence[str], cwd: str | Path | None = None, timeout_seconds: int | None = None, environment: Mapping[str, str] | None = None, source: str = "deterministic", redact_values: Sequence[str] = (), display_command: Sequence[str] | None = None):
        return super().run_argv(command, cwd, timeout_seconds, environment=self._validation_environment, source=source, redact_values=redact_values, display_command=display_command)


def _remediation_request(request: TaskRequest, profile: ValidationProfile) -> RemediationRequest:
    constraints = request.constraints
    return RemediationRequest(
        repository_url=request.repository.url,
        reference_branch=request.repository.base_ref,
        severity_scope=request.acceptance.severity_scope,
        build_commands=request.acceptance.build_commands,
        runtime_policy=RuntimePolicy(trusted_repository=True, dedicated_runner=True, enable_autonomous_shell=False, allow_network=True),
        maven=profile.maven,
        scanner=profile.scanner,
        constraints=ConstraintSpec(
            spring_boot_version_policy=SpringBootVersionPolicy(
                allow_patch=constraints.allow_spring_patch,
                allow_minor=constraints.allow_spring_minor,
                allow_major=constraints.allow_spring_major,
                allow_downgrade=constraints.allow_spring_downgrade,
            ),
            prohibit_suppressions=constraints.prohibit_suppressions,
            prohibited_new_severities=constraints.prohibited_new_severities,
        ),
    )


def _finding(data: Mapping[str, Any]) -> VulnerabilityFinding:
    dependency = data.get("dependency") or {}
    return VulnerabilityFinding(
        vulnerability_id=str(data.get("vulnerabilityId") or ""),
        aliases=tuple(str(value) for value in data.get("aliases") or ()),
        severity=str(data.get("severity") or ""),
        group_id=dependency.get("groupId"), artifact_id=dependency.get("artifactId"),
        package_name=str(dependency.get("packageName") or ""),
        version=str(dependency.get("currentVersion") or ""),
        fixed_versions=tuple(str(value) for value in data.get("fixedVersions") or ()),
        summary=str(data.get("summary") or ""), ecosystem=str(dependency.get("ecosystem") or "Maven"),
        backend_evidence=dict(data.get("backendEvidence") or {}),
    )


def _baseline_from_document(document: Mapping[str, Any], repository: Path) -> RepositoryBaseline:
    scan_data = document.get("scan")
    constraints = document.get("constraints")
    if not isinstance(scan_data, Mapping) or not isinstance(constraints, Mapping):
        raise ValidationIdentityError("successful baseline lacks scan or constraint evidence")
    findings = tuple(_finding(value) for value in scan_data.get("findings") or ())
    scan = ScanReport(
        succeeded=bool(scan_data.get("succeeded")), findings=findings, command_result=None,
        raw_report_path=str(scan_data.get("rawReportPath") or ""), error=scan_data.get("error"),
        outcome=ScanOutcome(str(scan_data.get("outcome"))), attempts=tuple(scan_data.get("attempts") or ()),
        backend=str(scan_data.get("backend") or "osv"), evidence=dict(scan_data.get("evidence") or {}),
    )
    baseline_constraints = ConstraintBaseline(
        java_versions=tuple(str(value) for value in constraints.get("javaVersions") or ()),
        spring_boot_versions=tuple(str(value) for value in constraints.get("springBootVersions") or ()),
        suppression_files=dict(constraints.get("suppressionFiles") or {}),
    )
    repository_data = document.get("repository") or {}
    return RepositoryBaseline(
        repository_path=str(repository), commit=str(document["baselineCommit"]),
        reference=str(repository_data.get("baseRef") or ""), remote_url=str(repository_data.get("url") or ""),
        build_results=(), scan=scan, constraints=baseline_constraints,
        target_findings=tuple(_finding(value) for value in document.get("originalVulnerabilityFindings") or ()),
    )


def _validated_report(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("passed"), bool):
        raise ValueError("validator report lacks an explicit passed boolean")
    checks = value.get("checks")
    if not isinstance(checks, list) or not checks or any(not isinstance(item, Mapping) or not isinstance(item.get("passed"), bool) for item in checks):
        raise ValueError("validator report lacks complete checks")
    if value["passed"] != all(bool(item["passed"]) for item in checks):
        raise ValueError("validator PASS conflicts with check results")
    for key in ("resolvedTargetFindings", "remainingTargetFindings", "unknownTargetFindings"):
        if not isinstance(value.get(key), list):
            raise ValueError("validator report lacks original-finding coverage")
    scan = value.get("scan")
    if value["passed"] and (not isinstance(scan, Mapping) or not scan.get("succeeded")):
        raise ValueError("validator PASS requires a complete fresh scan")
    return dict(value)


def _failure_report(classification: str, detail: str) -> dict[str, Any]:
    return {
        "passed": False,
        "checks": [{"name": "validator_availability", "passed": False, "message": detail}],
        "scan": None,
        "resolvedTargetFindings": [], "remainingTargetFindings": [],
        "unknownTargetFindings": [], "newProhibitedFindings": [],
        "failureClassification": classification,
    }


def _validation_outcome(report: Mapping[str, Any]) -> ValidationOutcome:
    if report.get("passed") is True:
        return ValidationOutcome.PASS
    scan = report.get("scan")
    if not isinstance(scan, Mapping) or scan.get("succeeded") is not True:
        return ValidationOutcome.INFRASTRUCTURE_FAILURE
    for check in report.get("checks") or ():
        if (
            isinstance(check, Mapping)
            and check.get("name") == "git_change_evidence"
            and check.get("passed") is False
        ):
            return ValidationOutcome.VALIDATOR_FAILURE
    return ValidationOutcome.REMEDIATION_FAILURE


def _coverage(report: Mapping[str, Any]) -> dict[str, Any]:
    resolved = report.get("resolvedTargetFindings") or []
    remaining = report.get("remainingTargetFindings") or []
    unknown = report.get("unknownTargetFindings") or []
    new = report.get("newProhibitedFindings")
    if not isinstance(new, list):
        new = []
        for check in report.get("checks") or []:
            if isinstance(check, Mapping) and check.get("name") == "no_new_prohibited_findings":
                candidate = (check.get("evidence") or {}).get("newFindings")
                if isinstance(candidate, list):
                    new = candidate
    core = {"baseline_ancestry", "git_change_evidence", "build_test_startup", "fresh_vulnerability_scan", "target_findings_improved", "target_findings_resolved", "no_new_prohibited_findings"}
    constraint_checks = [item for item in report.get("checks") or [] if isinstance(item, Mapping) and item.get("name") not in core]
    return {
        "original": len(resolved) + len(remaining) + len(unknown),
        "resolved": len(resolved), "remaining": len(remaining), "unknown": len(unknown),
        "new": len(new),
        "constraintsPassed": bool(constraint_checks) and all(bool(item.get("passed")) for item in constraint_checks),
    }


def _finding_summary(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "UNKNOWN"
    dependency = value.get("dependency") or {}
    identity = str(value.get("identity") or value.get("vulnerabilityId") or "UNKNOWN")
    group = dependency.get("groupId")
    artifact = dependency.get("artifactId")
    package = f"{group}:{artifact}" if group and artifact else dependency.get("packageName") or "unknown-package"
    version = dependency.get("currentVersion") or "unknown-version"
    severity = value.get("severity") or "UNKNOWN"
    return f"identity={identity}; severity={severity}; package={package}@{version}"


def _common_path(repository: Path, value: str) -> Path:
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else repository / candidate).resolve()


def _run_git(repository: Path, arguments: Sequence[str], *, env: Mapping[str, str] | None = None) -> str:
    result = subprocess.run(["git", *arguments], cwd=repository, env=dict(env) if env else {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"}, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise ValidationIdentityError("Git repository state capture failed")
    return result.stdout.strip()


def _run_git_bytes(repository: Path, arguments: Sequence[str]) -> bytes:
    result = subprocess.run(["git", *arguments], cwd=repository, env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise ValidationIdentityError("Git repository status capture failed")
    return result.stdout
