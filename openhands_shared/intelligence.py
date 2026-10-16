"""Optional durable SBRI stage for the shared OpenHands lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from scripts.openhands.sbri_integration import (
    agent_message,
    project_fingerprint,
    retain_review_bundle,
    run_pre_edit_intelligence,
)
from spring_boot_release_intelligence.release_selection import (
    ReleaseSelectionError,
    validate_resolved_selection,
)
from spring_boot_release_intelligence.standalone import validate_result

from .contracts import (
    ArtifactMetadata,
    BaselineAssessmentStatus,
    IntelligenceOutcome,
    IntelligenceRecord,
    PreparationRecord,
    TaskRequest,
    TaskStatus,
    canonical_json,
    safe_artifact_path,
    utc_now,
)
from .preparation import GitCommandError, GitRunner
from .store import InvalidTransitionError, SQLiteTaskStore


RECORD_ARTIFACT_ID = "intelligence-record"
SUMMARY_ARTIFACT_ID = "intelligence-summary"


class IntelligenceError(RuntimeError):
    pass


class IntelligenceConfigurationError(IntelligenceError):
    pass


class IntelligenceEvidenceError(IntelligenceError):
    pass


class IntelligenceWorkspaceError(IntelligenceError):
    pass


@dataclass(frozen=True)
class IntelligenceProfile:
    """Deployment-owned SBRI invocation and candidate-selection settings."""

    profile_id: str
    task_agent_profile: str
    control_repo: Path
    scanner: Path | None = None
    config: Path | None = None
    release_versions: str | None = None
    release_ranges: str | None = None
    max_candidates: int | None = None
    timeout_seconds: int = 2400

    def __post_init__(self) -> None:
        if not self.profile_id or not self.task_agent_profile:
            raise IntelligenceConfigurationError("intelligence profile identifiers are required")
        control_repo = self.control_repo.expanduser().resolve(strict=False)
        object.__setattr__(self, "control_repo", control_repo)
        if not control_repo.is_dir():
            raise IntelligenceConfigurationError("control_repo must be an existing directory")
        for name in ("scanner", "config"):
            value = getattr(self, name)
            if value is not None:
                resolved = value.expanduser().resolve(strict=False)
                object.__setattr__(self, name, resolved)
                if not resolved.is_file() or resolved.is_symlink():
                    raise IntelligenceConfigurationError(
                        f"{name} must be an existing regular deployment-owned file"
                    )
        if self.release_versions is not None and self.release_ranges is not None:
            raise IntelligenceConfigurationError(
                "approved intelligence profile cannot combine versions and ranges"
            )
        if self.max_candidates is not None and self.max_candidates < 1:
            raise IntelligenceConfigurationError("max_candidates must be positive")
        if self.timeout_seconds < 1:
            raise IntelligenceConfigurationError("timeout_seconds must be positive")


@dataclass(frozen=True)
class IntelligenceConfig:
    artifact_root: Path
    profiles: tuple[IntelligenceProfile, ...]

    def __post_init__(self) -> None:
        configured = self.artifact_root.expanduser()
        if configured.exists() and configured.is_symlink():
            raise IntelligenceConfigurationError("artifact root must not be a symbolic link")
        object.__setattr__(self, "artifact_root", configured.resolve(strict=False))
        names = [profile.profile_id for profile in self.profiles]
        task_profiles = [profile.task_agent_profile for profile in self.profiles]
        if len(names) != len(set(names)) or len(task_profiles) != len(set(task_profiles)):
            raise IntelligenceConfigurationError("intelligence profile mappings must be unique")

    def profile_for(self, request: TaskRequest) -> IntelligenceProfile:
        for profile in self.profiles:
            if profile.task_agent_profile == request.agent.profile:
                return profile
        raise IntelligenceConfigurationError(
            "task does not map to an approved intelligence profile"
        )


class SbriRunner(Protocol):
    def run(
        self,
        *,
        profile: IntelligenceProfile,
        project: Path,
        objective: str,
        state_dir: Path,
    ) -> dict[str, Any]:
        ...


class ExistingSbriRunner:
    """Thin call-through to the frozen experiment's reusable SBRI functions."""

    def run(
        self,
        *,
        profile: IntelligenceProfile,
        project: Path,
        objective: str,
        state_dir: Path,
    ) -> dict[str, Any]:
        return run_pre_edit_intelligence(
            control_repo=profile.control_repo,
            project=project,
            task=objective,
            state_dir=state_dir,
            scanner=profile.scanner,
            config=profile.config,
            release_versions=profile.release_versions,
            release_ranges=profile.release_ranges,
            max_candidates=profile.max_candidates,
            enabled=True,
            timeout=profile.timeout_seconds,
        )


class SharedIntelligenceAssessor:
    """Trusted internal operation for M2 Change 4; it never starts an agent."""

    def __init__(
        self,
        store: SQLiteTaskStore,
        config: IntelligenceConfig,
        *,
        runner: SbriRunner | None = None,
        git: GitRunner | None = None,
    ):
        self.store = store
        self.config = config
        self.runner = runner or ExistingSbriRunner()
        self.git = git or GitRunner()
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def assess(self, task_id: str) -> IntelligenceRecord:
        with self._task_lock(task_id):
            existing = self.store.get_intelligence(task_id)
            if existing is not None:
                self._verify_committed_artifacts(existing)
                self._verified_baseline(task_id)
                return existing

            request = self.store.get_request(task_id)
            try:
                baseline, _baseline_report = self._verified_baseline(task_id)
            except IntelligenceEvidenceError:
                baseline = self.store.get_baseline(task_id)
                if (
                    baseline is None
                    or baseline.assessment_status is not BaselineAssessmentStatus.COMPLETED
                    or self.store.get_status(task_id).status is not TaskStatus.INTELLIGENCE
                ):
                    raise
                self._ensure_artifact_boundary(task_id)
                return self._finalize(
                    task_id,
                    baseline.baseline_commit,
                    IntelligenceOutcome.CORRUPT_EVIDENCE,
                    profile_id="baseline-integrity",
                    collector={"status": "CORRUPT_EVIDENCE", "invoked": False},
                    explanation="durable baseline evidence failed integrity verification",
                )
            if self.store.get_status(task_id).status is not TaskStatus.INTELLIGENCE:
                raise InvalidTransitionError(
                    "intelligence can start only while the task is INTELLIGENCE"
                )
            preparation = self.store.get_preparation(task_id)
            if preparation is None:
                raise InvalidTransitionError("intelligence requires immutable preparation metadata")
            self._ensure_artifact_boundary(task_id)

            recovered = self._reconcile_record(task_id, baseline.baseline_commit)
            if recovered is not None:
                self.store.complete_intelligence(recovered[0], recovered[1])
                return recovered[0]

            try:
                workspace = self._verify_workspace(request, preparation)
            except IntelligenceWorkspaceError:
                return self._finalize(
                    task_id,
                    baseline.baseline_commit,
                    IntelligenceOutcome.REPOSITORY_MUTATION,
                    profile_id="workspace-check",
                    collector={"status": "REPOSITORY_MUTATION", "invoked": False},
                    explanation="prepared repository identity or cleanliness check failed",
                )

            if request.sbri_mode == "disabled":
                return self._finalize(
                    task_id,
                    baseline.baseline_commit,
                    IntelligenceOutcome.DISABLED,
                    profile_id="disabled",
                    collector={
                        "status": "DISABLED",
                        "applicability": {
                            "applicable": None,
                            "reason": "disabled by registered task contract",
                        },
                        "invoked": False,
                        "reused": False,
                    },
                    explanation="SBRI disabled by registered task contract",
                )

            try:
                profile = self.config.profile_for(request)
            except IntelligenceConfigurationError:
                return self._finalize(
                    task_id,
                    baseline.baseline_commit,
                    IntelligenceOutcome.INVALID_SELECTION,
                    profile_id="unresolved",
                    collector={"status": "INVALID_RELEASE_SELECTION", "invoked": False},
                    explanation="no approved intelligence profile resolved for this task",
                )

            try:
                collector = self.runner.run(
                    profile=profile,
                    project=workspace,
                    objective=request.objective,
                    state_dir=self._runtime_root(task_id),
                )
            except Exception:
                collector = {
                    "status": "FAILED",
                    "applicability": {"applicable": True, "reason": "operational failure"},
                    "invoked": True,
                    "reused": False,
                    "deliveredBeforeAgentRun": False,
                }

            outcome, explanation, selection, versions, fingerprint = self._classify_collector(
                collector,
                workspace,
            )
            try:
                self._verify_workspace(request, preparation)
            except IntelligenceWorkspaceError:
                outcome = IntelligenceOutcome.REPOSITORY_MUTATION
                explanation = "SBRI evaluation modified or displaced the prepared repository"
            if collector.get("sourceUnchanged") is False:
                outcome = IntelligenceOutcome.REPOSITORY_MUTATION
                explanation = "SBRI fingerprint evidence reports repository mutation"

            return self._finalize(
                task_id,
                baseline.baseline_commit,
                outcome,
                profile_id=profile.profile_id,
                collector=collector,
                explanation=explanation,
                selection=selection,
                versions=versions,
                fingerprint=fingerprint,
            )

    def _classify_collector(
        self,
        collector: Mapping[str, Any],
        workspace: Path,
    ) -> tuple[IntelligenceOutcome, str, dict[str, Any], tuple[str, ...], str | None]:
        status = collector.get("status")
        applicability = collector.get("applicability")
        if not isinstance(applicability, Mapping):
            return self._corrupt("collector applicability is missing")
        applicable = applicability.get("applicable")
        if status == "NOT_APPLICABLE" and applicable is False and not collector.get("invoked"):
            return (
                IntelligenceOutcome.NOT_APPLICABLE,
                str(applicability.get("reason") or "SBRI is not applicable"),
                {},
                (),
                None,
            )
        if status == "INVALID_RELEASE_SELECTION" and not collector.get("invoked"):
            return (
                IntelligenceOutcome.INVALID_SELECTION,
                "approved SBRI candidate selection was rejected",
                dict(collector.get("releaseSelection") or {}),
                (),
                None,
            )
        if status not in {"COMPLETE", "PARTIAL", "FAILED"} or applicable is not True:
            return self._corrupt("collector returned an unknown or inconsistent status")

        invoked = collector.get("invoked")
        if invoked is not True:
            return self._corrupt("applicable collector result does not record invocation")
        fingerprint = collector.get("fingerprint")
        request = collector.get("request")
        if not isinstance(fingerprint, str) or not isinstance(request, dict):
            if status == "FAILED":
                return IntelligenceOutcome.FAILED, "SBRI failed before complete evidence", {}, (), None
            return self._corrupt("collector fingerprint or request is missing")
        recalculated, _ = project_fingerprint(workspace, request)
        if recalculated != fingerprint:
            return self._corrupt("collector fingerprint does not match the prepared repository")

        selection = collector.get("releaseSelection")
        baseline_version = applicability.get("baseline")
        if not isinstance(selection, dict) or not isinstance(baseline_version, str):
            return self._corrupt("collector release selection is missing")
        try:
            candidates, selection = validate_resolved_selection(selection, baseline_version)
        except ReleaseSelectionError:
            return self._corrupt("collector release selection failed validation")

        versions: tuple[str, ...] = ()
        if status in {"COMPLETE", "PARTIAL"}:
            result_path = collector.get("resultPath")
            if not isinstance(result_path, str) or not Path(result_path).is_file():
                return self._corrupt("collector result artifact is missing")
            try:
                result = json.loads(Path(result_path).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return self._corrupt("collector result artifact is invalid")
            if validate_result(result):
                return self._corrupt("collector result schema or arithmetic is invalid")
            expected_result_status = "SUCCESS" if status == "COMPLETE" else "PARTIAL"
            if result.get("status") != expected_result_status:
                return self._corrupt("collector stage status and result status disagree")
            execution = result.get("execution", {})
            evaluated = execution.get("evaluated_releases")
            if execution.get("release_selection") != selection or not isinstance(evaluated, list):
                return self._corrupt("collector result and selection manifest disagree")
            expected = [baseline_version, *candidates]
            if evaluated != expected:
                return self._corrupt("collector evaluated versions differ from resolved selection")
            versions = tuple(evaluated)
            outcome = (
                IntelligenceOutcome.COMPLETE
                if status == "COMPLETE"
                else IntelligenceOutcome.PARTIAL
            )
            explanation = (
                "complete bounded SBRI evidence is available"
                if outcome is IntelligenceOutcome.COMPLETE
                else "partial SBRI evidence is available with explicit uncertainty"
            )
            return outcome, explanation, selection, versions, fingerprint

        return (
            IntelligenceOutcome.FAILED,
            "SBRI operational failure produced no usable recommendation",
            selection,
            tuple([baseline_version, *candidates]),
            fingerprint,
        )

    @staticmethod
    def _corrupt(
        explanation: str,
    ) -> tuple[IntelligenceOutcome, str, dict[str, Any], tuple[str, ...], None]:
        return IntelligenceOutcome.CORRUPT_EVIDENCE, explanation, {}, (), None

    def _finalize(
        self,
        task_id: str,
        baseline_commit: str,
        outcome: IntelligenceOutcome,
        *,
        profile_id: str,
        collector: Mapping[str, Any],
        explanation: str,
        selection: Mapping[str, Any] | None = None,
        versions: tuple[str, ...] = (),
        fingerprint: str | None = None,
    ) -> IntelligenceRecord:
        completed_at = utc_now()
        summary = self._summary_text(collector, outcome, explanation)
        evidence_artifacts = self._retain_evidence(task_id, collector, completed_at)
        summary_artifact = self._publish_bytes(
            task_id,
            SUMMARY_ARTIFACT_ID,
            "intelligence-summary",
            "summary.txt",
            (summary.rstrip() + "\n").encode("utf-8"),
            "text/plain",
            completed_at,
        )
        applicable_value = self._applicable_value(outcome, collector)
        invoked = bool(collector.get("invoked", False))
        reused = bool(collector.get("reused", False))
        document = {
            "contractVersion": "1",
            "kind": "openhands-shared-intelligence",
            "taskId": task_id,
            "baselineCommit": baseline_commit,
            "outcome": outcome.value,
            "applicable": applicable_value,
            "invoked": invoked,
            "reused": reused,
            "profileId": profile_id,
            "fingerprint": fingerprint,
            "selectionManifest": dict(selection or {}),
            "evaluatedVersions": list(versions),
            "explanation": explanation,
            "collectorRecord": dict(collector),
            "preEditEvidence": summary,
            "rankIsSecurityEvidenceOnly": True,
            "independentValidationRemainsAuthoritative": True,
            "evidenceArtifacts": [
                artifact.to_dict() for artifact in (*evidence_artifacts, summary_artifact)
            ],
            "completedAt": completed_at,
        }
        record_payload = (canonical_json(document) + "\n").encode("utf-8")
        record_artifact = self._publish_bytes(
            task_id,
            RECORD_ARTIFACT_ID,
            "intelligence-record",
            "record.json",
            record_payload,
            "application/json",
            completed_at,
        )
        record = IntelligenceRecord(
            task_id=task_id,
            baseline_commit=baseline_commit,
            outcome=outcome,
            applicable=applicable_value,
            invoked=invoked,
            reused=reused,
            profile_id=profile_id,
            fingerprint=fingerprint,
            selection_manifest=dict(selection or {}),
            evaluated_versions=versions,
            record_artifact_id=record_artifact.artifact_id,
            record_sha256=record_artifact.sha256,
            summary_artifact_id=summary_artifact.artifact_id,
            explanation=explanation,
            completed_at=completed_at,
        )
        self.store.complete_intelligence(
            record,
            (record_artifact, summary_artifact, *evidence_artifacts),
        )
        return record

    def _summary_text(
        self,
        collector: Mapping[str, Any],
        outcome: IntelligenceOutcome,
        explanation: str,
    ) -> str:
        try:
            body = agent_message(dict(collector))
        except (KeyError, OSError, UnicodeError):
            body = (
                "SBRI pre-edit intelligence is unavailable or incomplete: "
                f"{explanation}. This is not evidence that Spring Boot upgrades are impossible; "
                "continue with other task-permitted investigation methods."
            )
        return (
            "<SBRI_PRE_EDIT_EVIDENCE>\n"
            + body
            + "\nCandidate selection bounds only the evaluated evidence, not the agent's available "
            "strategies. A candidate rank is not implementation approval, and residual findings are "
            "not acceptable final-state exceptions. Independent validation remains authoritative.\n"
            "</SBRI_PRE_EDIT_EVIDENCE>"
        )

    @staticmethod
    def _applicable_value(
        outcome: IntelligenceOutcome,
        collector: Mapping[str, Any],
    ) -> bool | None:
        if outcome is IntelligenceOutcome.DISABLED:
            return None
        applicability = collector.get("applicability")
        if isinstance(applicability, Mapping) and isinstance(applicability.get("applicable"), bool):
            return applicability["applicable"]
        if outcome in {
            IntelligenceOutcome.COMPLETE,
            IntelligenceOutcome.PARTIAL,
            IntelligenceOutcome.FAILED,
        }:
            return True
        if outcome is IntelligenceOutcome.NOT_APPLICABLE:
            return False
        return None

    def _retain_evidence(
        self,
        task_id: str,
        collector: Mapping[str, Any],
        created_at: str,
    ) -> tuple[ArtifactMetadata, ...]:
        latest = self._runtime_root(task_id) / "sbri" / "latest.json"
        if not latest.is_file():
            return ()
        with tempfile.TemporaryDirectory(prefix="shared-sbri-review-") as value:
            temporary = Path(value)
            retain_review_bundle(latest, temporary)
            artifacts: list[ArtifactMetadata] = []
            for source in sorted(temporary.rglob("*")):
                if source.is_symlink():
                    raise IntelligenceEvidenceError("retained SBRI evidence contains a symbolic link")
                if not source.is_file():
                    continue
                relative = source.relative_to(temporary).as_posix()
                artifact_id = (
                    "intelligence-evidence-"
                    + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
                )
                media_type = (
                    "application/json"
                    if source.suffix == ".json"
                    else "text/html" if source.suffix == ".html" else "text/plain"
                )
                artifacts.append(
                    self._publish_bytes(
                        task_id,
                        artifact_id,
                        "intelligence-evidence",
                        f"evidence/{relative}",
                        source.read_bytes(),
                        media_type,
                        created_at,
                    )
                )
            return tuple(artifacts)

    def _publish_bytes(
        self,
        task_id: str,
        artifact_id: str,
        kind: str,
        suffix: str,
        payload: bytes,
        media_type: str,
        created_at: str,
    ) -> ArtifactMetadata:
        relative = safe_artifact_path(f"{task_id}/intelligence/{suffix}")
        target = self.config.artifact_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        self._reject_symlink_path(target.parent)
        if target.exists():
            if not target.is_file() or target.is_symlink() or _sha256_file(target) != _sha256(payload):
                raise IntelligenceEvidenceError("refusing to overwrite conflicting intelligence evidence")
        else:
            temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
            try:
                with temporary.open("xb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    if not target.is_file() or _sha256_file(target) != _sha256(payload):
                        raise IntelligenceEvidenceError(
                            "concurrent intelligence evidence conflicts with this task"
                        )
            finally:
                if temporary.exists():
                    temporary.unlink()
        return ArtifactMetadata(
            artifact_id=artifact_id,
            task_id=task_id,
            kind=kind,
            relative_path=relative,
            media_type=media_type,
            sha256=_sha256(payload),
            size_bytes=len(payload),
            created_at=created_at,
        )

    def _reconcile_record(
        self,
        task_id: str,
        baseline_commit: str,
    ) -> tuple[IntelligenceRecord, tuple[ArtifactMetadata, ...]] | None:
        relative = safe_artifact_path(f"{task_id}/intelligence/record.json")
        path = self.config.artifact_root / relative
        if not path.exists():
            return None
        if not path.is_file() or path.is_symlink():
            raise IntelligenceEvidenceError("intelligence record path is not a regular file")
        payload = path.read_bytes()
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntelligenceEvidenceError("intelligence record is invalid") from exc
        if document.get("taskId") != task_id or document.get("baselineCommit") != baseline_commit:
            raise IntelligenceEvidenceError("intelligence record has foreign identity")
        artifacts = self._artifacts_from_document(document)
        for artifact in artifacts:
            self._verify_artifact(artifact)
        record_artifact = ArtifactMetadata(
            artifact_id=RECORD_ARTIFACT_ID,
            task_id=task_id,
            kind="intelligence-record",
            relative_path=relative,
            media_type="application/json",
            sha256=_sha256(payload),
            size_bytes=len(payload),
            created_at=document["completedAt"],
        )
        record = self._record_from_document(document, record_artifact)
        return record, (record_artifact, *artifacts)

    def _record_from_document(
        self,
        document: Mapping[str, Any],
        artifact: ArtifactMetadata,
    ) -> IntelligenceRecord:
        try:
            return IntelligenceRecord(
                task_id=document["taskId"],
                baseline_commit=document["baselineCommit"],
                outcome=IntelligenceOutcome(document["outcome"]),
                applicable=document["applicable"],
                invoked=document["invoked"],
                reused=document["reused"],
                profile_id=document["profileId"],
                fingerprint=document["fingerprint"],
                selection_manifest=document["selectionManifest"],
                evaluated_versions=tuple(document["evaluatedVersions"]),
                record_artifact_id=artifact.artifact_id,
                record_sha256=artifact.sha256,
                summary_artifact_id=SUMMARY_ARTIFACT_ID,
                explanation=document["explanation"],
                completed_at=document["completedAt"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise IntelligenceEvidenceError("intelligence record metadata is invalid") from exc

    def _artifacts_from_document(
        self,
        document: Mapping[str, Any],
    ) -> tuple[ArtifactMetadata, ...]:
        values = document.get("evidenceArtifacts")
        if not isinstance(values, list):
            raise IntelligenceEvidenceError("intelligence artifact manifest is invalid")
        artifacts: list[ArtifactMetadata] = []
        try:
            for value in values:
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
            raise IntelligenceEvidenceError("intelligence artifact manifest is invalid") from exc
        if not any(item.artifact_id == SUMMARY_ARTIFACT_ID for item in artifacts):
            raise IntelligenceEvidenceError("intelligence summary artifact is missing")
        return tuple(artifacts)

    def _verify_committed_artifacts(self, record: IntelligenceRecord) -> None:
        artifacts = {
            item.artifact_id: item
            for item in self.store.list_artifacts(record.task_id)
            if item.kind.startswith("intelligence-")
        }
        record_artifact = artifacts.get(record.record_artifact_id)
        if record_artifact is None or record_artifact.sha256 != record.record_sha256:
            raise IntelligenceEvidenceError("committed intelligence record metadata is inconsistent")
        for artifact in artifacts.values():
            self._verify_artifact(artifact)

    def _verify_artifact(self, artifact: ArtifactMetadata) -> None:
        path = self.config.artifact_root / artifact.relative_path
        self._reject_symlink_path(path.parent)
        if not path.is_file() or path.is_symlink():
            raise IntelligenceEvidenceError("intelligence artifact is unavailable")
        if path.stat().st_size != artifact.size_bytes or _sha256_file(path) != artifact.sha256:
            raise IntelligenceEvidenceError("intelligence artifact failed checksum verification")

    def _verified_baseline(self, task_id: str):
        baseline = self.store.get_baseline(task_id)
        if baseline is None or baseline.assessment_status is not BaselineAssessmentStatus.COMPLETED:
            raise InvalidTransitionError("intelligence requires a successful durable baseline")
        artifacts = {
            item.artifact_id: item
            for item in self.store.list_artifacts(task_id)
            if item.kind.startswith("baseline-")
        }
        report_artifact = artifacts.get(baseline.report_artifact_id)
        if report_artifact is None or report_artifact.sha256 != baseline.report_sha256:
            raise IntelligenceEvidenceError("baseline report metadata is inconsistent")
        for artifact in artifacts.values():
            path = self.config.artifact_root / artifact.relative_path
            self._reject_symlink_path(path.parent)
            if (
                not path.is_file()
                or path.is_symlink()
                or path.stat().st_size != artifact.size_bytes
                or _sha256_file(path) != artifact.sha256
            ):
                raise IntelligenceEvidenceError("baseline artifact failed integrity verification")
        report_path = self.config.artifact_root / report_artifact.relative_path
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntelligenceEvidenceError("baseline report is invalid") from exc
        if (
            report.get("taskId") != task_id
            or report.get("baselineCommit") != baseline.baseline_commit
            or report.get("assessmentStatus") != BaselineAssessmentStatus.COMPLETED.value
        ):
            raise IntelligenceEvidenceError("baseline report identity or outcome is inconsistent")
        return baseline, report

    def _verify_workspace(self, request: TaskRequest, preparation: PreparationRecord) -> Path:
        if (
            preparation.repository_url != request.repository.url
            or preparation.base_ref != request.repository.base_ref
            or preparation.baseline_commit != request.repository.expected_commit
        ):
            raise IntelligenceWorkspaceError("preparation identity differs from task contract")
        workspace = Path(preparation.workspace_path)
        source = Path(preparation.source_path)
        if not workspace.is_dir() or workspace.is_symlink() or not source.is_dir():
            raise IntelligenceWorkspaceError("prepared workspace is unavailable")
        try:
            _, workspace_common = self.git.run(
                workspace, ["rev-parse", "--git-common-dir"], operation="intelligence_workspace_identity"
            )
            _, source_common = self.git.run(
                source, ["rev-parse", "--git-common-dir"], operation="intelligence_source_identity"
            )
            if _common_path(workspace, workspace_common) != _common_path(source, source_common):
                raise IntelligenceWorkspaceError("prepared workspace belongs to a foreign repository")
            _, head = self.git.run(
                workspace, ["rev-parse", "--verify", "HEAD^{commit}"], operation="intelligence_head"
            )
            if head != preparation.baseline_commit:
                raise IntelligenceWorkspaceError("prepared workspace HEAD differs from baseline")
            _, branch = self.git.run(
                workspace, ["symbolic-ref", "--quiet", "HEAD"], operation="intelligence_branch"
            )
            if branch != f"refs/heads/{preparation.local_branch}":
                raise IntelligenceWorkspaceError("prepared workspace is on a foreign branch")
            _, dirty = self.git.run(
                workspace,
                ["status", "--porcelain=v1", "--untracked-files=all"],
                operation="intelligence_cleanliness",
            )
            if dirty:
                raise IntelligenceWorkspaceError("prepared workspace is dirty")
        except GitCommandError as exc:
            raise IntelligenceWorkspaceError("prepared workspace could not be verified") from exc
        return workspace.resolve()

    def _ensure_artifact_boundary(self, task_id: str) -> None:
        root = self.config.artifact_root
        root.mkdir(parents=True, exist_ok=True)
        self._reject_symlink_path(root)
        current = root
        for part in (safe_artifact_path(task_id), "intelligence"):
            current = current / part
            if current.exists() and current.is_symlink():
                raise IntelligenceEvidenceError("intelligence artifact path traverses a symbolic link")
            current.mkdir(exist_ok=True)

    def _reject_symlink_path(self, path: Path) -> None:
        root = self.config.artifact_root
        if root.is_symlink():
            raise IntelligenceEvidenceError("artifact root must not be a symbolic link")
        relative = path.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise IntelligenceEvidenceError("intelligence artifact path traverses a symbolic link")

    def _runtime_root(self, task_id: str) -> Path:
        return self.config.artifact_root / safe_artifact_path(
            f"{task_id}/intelligence/runtime"
        )

    def _task_lock(self, task_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(task_id, threading.Lock())


def _common_path(repository: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repository / candidate
    return candidate.resolve()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
