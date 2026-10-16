"""Version 1 contracts for the shared OpenHands task foundation.

The contracts intentionally model execution, validation acceptance, and
delivery as independent facts.  Conversation completion is never interpreted
as validation acceptance or delivery success.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit


CONTRACT_VERSION = "1"
MAX_OBJECTIVE_LENGTH = 10_000
MAX_METADATA_VALUE_LENGTH = 1_000
FULL_GIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
PROFILE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
GIT_REF = re.compile(r"^refs/(heads|tags)/[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MEDIA_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}$")

SUPPORTED_AGENT_PROFILES = frozenset({"gate2-dependency-remediation-v1"})
SUPPORTED_MODEL_PROFILES = frozenset({"vertex-gemini-2-5-flash"})
SUPPORTED_SBRI_MODES = frozenset({"auto", "disabled"})
SUPPORTED_SOURCES = frozenset({"rest", "test", "ui", "experiment-client"})

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "privatekey",
    "apikey",
    "accesskey",
    "clientsecret",
    "serviceaccount",
)
_ENVIRONMENT_KEYS = frozenset({"env", "environment", "environmentvariables", "envvars"})
_RAW_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*[:=]\s*\S+"),
)


class ContractValidationError(ValueError):
    """Raised when a public contract is structurally or semantically invalid."""


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    BASELINING = "BASELINING"
    INTELLIGENCE = "INTELLIGENCE"
    AGENT_RUNNING = "AGENT_RUNNING"
    VALIDATING = "VALIDATING"
    ACCEPTED = "ACCEPTED"
    DELIVERING = "DELIVERING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_INFRASTRUCTURE = "FAILED_INFRASTRUCTURE"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    CANCELLED = "CANCELLED"


class ExecutionStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ValidationStatus(str, Enum):
    NOT_VALIDATED = "NOT_VALIDATED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"


class DeliveryStatus(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ResultOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED_INFRASTRUCTURE = "FAILED_INFRASTRUCTURE"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    CANCELLED = "CANCELLED"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _normal_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def reject_sensitive_input(value: Any, path: str = "request") -> None:
    """Reject secret-shaped fields and arbitrary environment injection recursively."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ContractValidationError(f"{path} contains a non-string key")
            normalized = _normal_key(key)
            if normalized in _ENVIRONMENT_KEYS or any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                raise ContractValidationError(f"{path}.{key} is a prohibited secret or environment field")
            reject_sensitive_input(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            reject_sensitive_input(nested, f"{path}[{index}]")
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in _RAW_SECRET_PATTERNS):
            raise ContractValidationError(f"{path} contains raw credential material")


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{path} must be an object")
    return value


def _strict_keys(value: Mapping[str, Any], required: set[str], optional: set[str], path: str) -> None:
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise ContractValidationError(f"{path} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ContractValidationError(f"{path} contains unknown fields: {', '.join(sorted(unknown))}")


def _string(value: Any, path: str, *, maximum: int = 512, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ContractValidationError(f"{path} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise ContractValidationError(f"{path} exceeds {maximum} characters")
    if "\x00" in value:
        raise ContractValidationError(f"{path} contains a NUL character")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ContractValidationError(f"{path} has an invalid format")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{path} must be a boolean")
    return value


def _integer(value: Any, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ContractValidationError(f"{path} must be an integer from {minimum} through {maximum}")
    return value


def _timestamp(value: Any, path: str) -> str:
    text = _string(value, path, maximum=32)
    if not text.endswith("Z"):
        raise ContractValidationError(f"{path} must be a UTC RFC 3339 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractValidationError(f"{path} must be a valid RFC 3339 timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractValidationError(f"{path} must be UTC")
    return text


def _string_list(value: Any, path: str, *, allowed: frozenset[str] | None = None) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ContractValidationError(f"{path} must be a non-empty array")
    output: list[str] = []
    for index, item in enumerate(value):
        text = _string(item, f"{path}[{index}]", maximum=256)
        if "\n" in text or "\r" in text:
            raise ContractValidationError(f"{path}[{index}] must be one line")
        if allowed is not None and text not in allowed:
            raise ContractValidationError(f"{path}[{index}] is unsupported")
        output.append(text)
    if len(set(output)) != len(output):
        raise ContractValidationError(f"{path} contains duplicates")
    return tuple(output)


def _json_data(value: Any, path: str) -> dict[str, Any]:
    obj = dict(_object(value, path))
    reject_sensitive_input(obj, path)
    try:
        encoded = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(f"{path} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > 64 * 1024:
        raise ContractValidationError(f"{path} exceeds 65536 encoded bytes")
    return obj


@dataclass(frozen=True)
class RepositoryRequest:
    url: str
    base_ref: str
    expected_commit: str

    @classmethod
    def from_dict(cls, value: Any) -> "RepositoryRequest":
        obj = _object(value, "request.repository")
        _strict_keys(obj, {"url", "baseRef", "expectedCommit"}, set(), "request.repository")
        url = _string(obj["url"], "request.repository.url", maximum=2048)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ContractValidationError("request.repository.url must be an HTTPS URL without credentials, query, or fragment")
        return cls(
            url=url,
            base_ref=_string(obj["baseRef"], "request.repository.baseRef", maximum=260, pattern=GIT_REF),
            expected_commit=_string(obj["expectedCommit"], "request.repository.expectedCommit", maximum=40, pattern=FULL_GIT_SHA).lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "baseRef": self.base_ref, "expectedCommit": self.expected_commit}


@dataclass(frozen=True)
class TaskConstraints:
    java_version_unchanged: bool
    allow_spring_patch: bool
    allow_spring_minor: bool
    allow_spring_major: bool
    allow_spring_downgrade: bool
    prohibit_suppressions: bool
    prohibited_new_severities: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "TaskConstraints":
        obj = _object(value, "request.constraints")
        _strict_keys(
            obj,
            {"javaVersionUnchanged", "springBoot", "prohibitSuppressions", "prohibitedNewSeverities"},
            set(),
            "request.constraints",
        )
        spring = _object(obj["springBoot"], "request.constraints.springBoot")
        _strict_keys(spring, {"allowPatch", "allowMinor", "allowMajor", "allowDowngrade"}, set(), "request.constraints.springBoot")
        return cls(
            java_version_unchanged=_bool(obj["javaVersionUnchanged"], "request.constraints.javaVersionUnchanged"),
            allow_spring_patch=_bool(spring["allowPatch"], "request.constraints.springBoot.allowPatch"),
            allow_spring_minor=_bool(spring["allowMinor"], "request.constraints.springBoot.allowMinor"),
            allow_spring_major=_bool(spring["allowMajor"], "request.constraints.springBoot.allowMajor"),
            allow_spring_downgrade=_bool(spring["allowDowngrade"], "request.constraints.springBoot.allowDowngrade"),
            prohibit_suppressions=_bool(obj["prohibitSuppressions"], "request.constraints.prohibitSuppressions"),
            prohibited_new_severities=_string_list(
                obj["prohibitedNewSeverities"],
                "request.constraints.prohibitedNewSeverities",
                allowed=frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"}),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "javaVersionUnchanged": self.java_version_unchanged,
            "springBoot": {
                "allowPatch": self.allow_spring_patch,
                "allowMinor": self.allow_spring_minor,
                "allowMajor": self.allow_spring_major,
                "allowDowngrade": self.allow_spring_downgrade,
            },
            "prohibitSuppressions": self.prohibit_suppressions,
            "prohibitedNewSeverities": list(self.prohibited_new_severities),
        }


@dataclass(frozen=True)
class AcceptanceCriteria:
    build_commands: tuple[str, ...]
    severity_scope: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "AcceptanceCriteria":
        obj = _object(value, "request.acceptance")
        _strict_keys(obj, {"buildCommands", "severityScope"}, set(), "request.acceptance")
        return cls(
            build_commands=_string_list(obj["buildCommands"], "request.acceptance.buildCommands"),
            severity_scope=_string_list(
                obj["severityScope"],
                "request.acceptance.severityScope",
                allowed=frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"}),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"buildCommands": list(self.build_commands), "severityScope": list(self.severity_scope)}


@dataclass(frozen=True)
class AgentProfile:
    profile: str
    model_profile: str
    max_iterations: int
    max_validation_denials: int

    @classmethod
    def from_dict(cls, value: Any) -> "AgentProfile":
        obj = _object(value, "request.agent")
        _strict_keys(obj, {"profile", "modelProfile", "maxIterations", "maxValidationDenials"}, set(), "request.agent")
        profile = _string(obj["profile"], "request.agent.profile", maximum=64, pattern=PROFILE)
        model = _string(obj["modelProfile"], "request.agent.modelProfile", maximum=64, pattern=PROFILE)
        if profile not in SUPPORTED_AGENT_PROFILES:
            raise ContractValidationError("request.agent.profile is not an approved profile")
        if model not in SUPPORTED_MODEL_PROFILES:
            raise ContractValidationError("request.agent.modelProfile is not an approved profile")
        return cls(
            profile=profile,
            model_profile=model,
            max_iterations=_integer(obj["maxIterations"], "request.agent.maxIterations", 1, 1000),
            max_validation_denials=_integer(obj["maxValidationDenials"], "request.agent.maxValidationDenials", 0, 20),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "modelProfile": self.model_profile,
            "maxIterations": self.max_iterations,
            "maxValidationDenials": self.max_validation_denials,
        }


@dataclass(frozen=True)
class TaskRequest:
    idempotency_key: str
    repository: RepositoryRequest
    objective: str
    constraints: TaskConstraints
    acceptance: AcceptanceCriteria
    agent: AgentProfile
    sbri_mode: str
    delivery_mode: str
    source: str
    correlation_id: str | None = None
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def from_dict(cls, value: Any) -> "TaskRequest":
        obj = _object(value, "request")
        reject_sensitive_input(obj)
        _strict_keys(
            obj,
            {"contractVersion", "idempotencyKey", "repository", "objective", "constraints", "acceptance", "agent", "intelligence", "delivery", "metadata"},
            set(),
            "request",
        )
        if obj["contractVersion"] != CONTRACT_VERSION:
            raise ContractValidationError(f"request.contractVersion must be {CONTRACT_VERSION!r}")
        intelligence = _object(obj["intelligence"], "request.intelligence")
        _strict_keys(intelligence, {"sbri"}, set(), "request.intelligence")
        sbri = _object(intelligence["sbri"], "request.intelligence.sbri")
        _strict_keys(sbri, {"mode"}, set(), "request.intelligence.sbri")
        sbri_mode = _string(sbri["mode"], "request.intelligence.sbri.mode", maximum=16)
        if sbri_mode not in SUPPORTED_SBRI_MODES:
            raise ContractValidationError("request.intelligence.sbri.mode is unsupported")
        delivery = _object(obj["delivery"], "request.delivery")
        _strict_keys(delivery, {"mode"}, set(), "request.delivery")
        if delivery["mode"] != "none":
            raise ContractValidationError("request.delivery.mode must be 'none' in M2 Change 1")
        metadata = _object(obj["metadata"], "request.metadata")
        _strict_keys(metadata, {"source"}, {"correlationId"}, "request.metadata")
        source = _string(metadata["source"], "request.metadata.source", maximum=32)
        if source not in SUPPORTED_SOURCES:
            raise ContractValidationError("request.metadata.source is unsupported")
        correlation = metadata.get("correlationId")
        if correlation is not None:
            correlation = _string(correlation, "request.metadata.correlationId", maximum=128, pattern=IDENTIFIER)
        objective = _string(obj["objective"], "request.objective", maximum=MAX_OBJECTIVE_LENGTH)
        return cls(
            contract_version=CONTRACT_VERSION,
            idempotency_key=_string(obj["idempotencyKey"], "request.idempotencyKey", maximum=128, pattern=IDENTIFIER),
            repository=RepositoryRequest.from_dict(obj["repository"]),
            objective=objective,
            constraints=TaskConstraints.from_dict(obj["constraints"]),
            acceptance=AcceptanceCriteria.from_dict(obj["acceptance"]),
            agent=AgentProfile.from_dict(obj["agent"]),
            sbri_mode=sbri_mode,
            delivery_mode="none",
            source=source,
            correlation_id=correlation,
        )

    def to_dict(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {"source": self.source}
        if self.correlation_id is not None:
            metadata["correlationId"] = self.correlation_id
        return {
            "contractVersion": self.contract_version,
            "idempotencyKey": self.idempotency_key,
            "repository": self.repository.to_dict(),
            "objective": self.objective,
            "constraints": self.constraints.to_dict(),
            "acceptance": self.acceptance.to_dict(),
            "agent": self.agent.to_dict(),
            "intelligence": {"sbri": {"mode": self.sbri_mode}},
            "delivery": {"mode": self.delivery_mode},
            "metadata": metadata,
        }


@dataclass(frozen=True)
class PreparationRecord:
    """Immutable identity of a successfully prepared task worktree."""

    task_id: str
    repository_url: str
    base_ref: str
    expected_commit: str
    baseline_commit: str
    source_path: str
    workspace_path: str
    local_branch: str
    prepared_at: str
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _string(self.task_id, "preparation.taskId", maximum=128, pattern=IDENTIFIER)
        repository = RepositoryRequest.from_dict(
            {
                "url": self.repository_url,
                "baseRef": self.base_ref,
                "expectedCommit": self.expected_commit,
            }
        )
        object.__setattr__(self, "repository_url", repository.url)
        object.__setattr__(self, "base_ref", repository.base_ref)
        object.__setattr__(self, "expected_commit", repository.expected_commit)
        baseline = _string(
            self.baseline_commit,
            "preparation.baselineCommit",
            maximum=40,
            pattern=FULL_GIT_SHA,
        ).lower()
        if baseline != repository.expected_commit:
            raise ContractValidationError(
                "preparation baseline commit must equal the registered expected commit"
            )
        object.__setattr__(self, "baseline_commit", baseline)
        for value, path in (
            (self.source_path, "preparation.sourcePath"),
            (self.workspace_path, "preparation.workspacePath"),
        ):
            parsed = Path(_string(value, path, maximum=4096))
            if not parsed.is_absolute() or str(parsed.resolve(strict=False)) != value:
                raise ContractValidationError(f"{path} must be an absolute normalized path")
        branch = _string(self.local_branch, "preparation.localBranch", maximum=240)
        if any(character.isspace() for character in branch) or ".." in branch:
            raise ContractValidationError("preparation.localBranch has an invalid format")
        _timestamp(self.prepared_at, "preparation.preparedAt")
        if self.contract_version != CONTRACT_VERSION:
            raise ContractValidationError("preparation.contractVersion is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractVersion": self.contract_version,
            "taskId": self.task_id,
            "repositoryUrl": self.repository_url,
            "baseRef": self.base_ref,
            "expectedCommit": self.expected_commit,
            "baselineCommit": self.baseline_commit,
            "sourcePath": self.source_path,
            "workspacePath": self.workspace_path,
            "localBranch": self.local_branch,
            "preparedAt": self.prepared_at,
        }


@dataclass(frozen=True)
class TaskStatusSnapshot:
    task_id: str
    status: TaskStatus
    stage: str
    created_at: str
    updated_at: str
    execution_status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    conversation_id: str | None = None
    validation_status: ValidationStatus = ValidationStatus.NOT_VALIDATED
    validation_attempts: int = 0
    accepted: bool = False
    delivery_status: DeliveryStatus = DeliveryStatus.NOT_REQUESTED
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _string(self.task_id, "status.taskId", maximum=128, pattern=IDENTIFIER)
        _string(self.stage, "status.stage", maximum=64, pattern=PROFILE)
        _timestamp(self.created_at, "status.createdAt")
        _timestamp(self.updated_at, "status.updatedAt")
        if isinstance(self.validation_attempts, bool) or not isinstance(self.validation_attempts, int) or self.validation_attempts < 0:
            raise ContractValidationError("status.validation.attempts cannot be negative")
        if not isinstance(self.accepted, bool):
            raise ContractValidationError("status.validation.accepted must be a boolean")
        if self.conversation_id is not None:
            _string(self.conversation_id, "status.openhands.conversationId", maximum=128)
        if self.accepted != (self.validation_status is ValidationStatus.PASSED):
            raise ContractValidationError("status acceptance must exactly reflect independent validation PASS")
        if self.status in {TaskStatus.ACCEPTED, TaskStatus.DELIVERING, TaskStatus.SUCCEEDED} and not self.accepted:
            raise ContractValidationError("accepted/delivery/success status requires independent validation PASS")
        if self.status is TaskStatus.SUCCEEDED and self.delivery_status is not DeliveryStatus.COMPLETED:
            raise ContractValidationError("SUCCEEDED requires completed delivery")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractVersion": self.contract_version,
            "taskId": self.task_id,
            "status": self.status.value,
            "stage": self.stage,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "openhands": {"executionStatus": self.execution_status.value, "conversationId": self.conversation_id},
            "validation": {"status": self.validation_status.value, "attempts": self.validation_attempts, "accepted": self.accepted},
            "delivery": {"status": self.delivery_status.value},
            "links": {
                "self": f"/v1/tasks/{self.task_id}",
                "events": f"/v1/tasks/{self.task_id}/events",
                "artifacts": f"/v1/tasks/{self.task_id}/artifacts",
                "result": f"/v1/tasks/{self.task_id}/result",
            },
        }


@dataclass(frozen=True)
class TaskEvent:
    event_id: str
    task_id: str
    sequence: int
    timestamp: str
    type: str
    stage: str
    data: Mapping[str, Any] = field(default_factory=dict)
    openhands_event_id: str | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _string(self.event_id, "event.eventId", maximum=128, pattern=IDENTIFIER)
        _string(self.task_id, "event.taskId", maximum=128, pattern=IDENTIFIER)
        _timestamp(self.timestamp, "event.timestamp")
        if self.sequence < 1:
            raise ContractValidationError("event.sequence must be positive")
        _string(self.type, "event.type", maximum=128, pattern=IDENTIFIER)
        _string(self.stage, "event.stage", maximum=64, pattern=PROFILE)
        if self.openhands_event_id is not None:
            _string(self.openhands_event_id, "event.openhandsEventId", maximum=128)
        object.__setattr__(self, "data", MappingProxyType(_json_data(self.data, "event.data")))

    def to_dict(self) -> dict[str, Any]:
        output = {
            "contractVersion": self.contract_version,
            "eventId": self.event_id,
            "taskId": self.task_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "type": self.type,
            "stage": self.stage,
            "data": dict(self.data),
        }
        if self.openhands_event_id is not None:
            output["openhandsEventId"] = self.openhands_event_id
        return output


def safe_artifact_path(value: str) -> str:
    path = _string(value, "artifact.relativePath", maximum=1024)
    if "\\" in path:
        raise ContractValidationError("artifact.relativePath must use POSIX separators")
    parsed = PurePosixPath(path)
    if (
        path in {".", ".."}
        or not parsed.parts
        or parsed.is_absolute()
        or path.startswith("/")
        or parsed.as_posix() != path
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise ContractValidationError("artifact.relativePath must be a normalized safe relative path")
    return parsed.as_posix()


@dataclass(frozen=True)
class ArtifactMetadata:
    artifact_id: str
    task_id: str
    kind: str
    relative_path: str
    media_type: str
    sha256: str
    size_bytes: int
    created_at: str
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _string(self.artifact_id, "artifact.artifactId", maximum=128, pattern=IDENTIFIER)
        _string(self.task_id, "artifact.taskId", maximum=128, pattern=IDENTIFIER)
        _string(self.kind, "artifact.kind", maximum=64, pattern=PROFILE)
        object.__setattr__(self, "relative_path", safe_artifact_path(self.relative_path))
        _string(self.media_type, "artifact.mediaType", maximum=128, pattern=MEDIA_TYPE)
        _string(self.sha256, "artifact.sha256", maximum=64, pattern=SHA256)
        _timestamp(self.created_at, "artifact.createdAt")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ContractValidationError("artifact.sizeBytes must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractVersion": self.contract_version,
            "artifactId": self.artifact_id,
            "taskId": self.task_id,
            "kind": self.kind,
            "relativePath": self.relative_path,
            "mediaType": self.media_type,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "createdAt": self.created_at,
        }


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    outcome: ResultOutcome
    execution_status: ExecutionStatus
    validation_status: ValidationStatus
    delivery_status: DeliveryStatus
    baseline_commit: str | None = None
    validated_tree: str | None = None
    validation_attempt: int | None = None
    validation_report_artifact_id: str | None = None
    conversation_id: str | None = None
    pull_request_url: str | None = None
    artifact_ids: tuple[str, ...] = ()
    completed_at: str = field(default_factory=utc_now)
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _string(self.task_id, "result.taskId", maximum=128, pattern=IDENTIFIER)
        _timestamp(self.completed_at, "result.completedAt")
        if self.outcome in {ResultOutcome.ACCEPTED, ResultOutcome.SUCCEEDED}:
            if self.execution_status is not ExecutionStatus.COMPLETED:
                raise ContractValidationError("accepted result requires completed OpenHands execution")
            if self.validation_status is not ValidationStatus.PASSED:
                raise ContractValidationError("accepted result requires independent validation PASS")
            if not isinstance(self.validated_tree, str) or not FULL_GIT_SHA.fullmatch(self.validated_tree):
                raise ContractValidationError("accepted result requires a full validated tree SHA")
            if not self.validation_report_artifact_id:
                raise ContractValidationError("accepted result requires a validation report artifact")
        if self.outcome is ResultOutcome.SUCCEEDED and self.delivery_status is not DeliveryStatus.COMPLETED:
            raise ContractValidationError("successful result requires completed delivery")
        if self.outcome is ResultOutcome.ACCEPTED and self.delivery_status not in {DeliveryStatus.NOT_REQUESTED, DeliveryStatus.PENDING}:
            raise ContractValidationError("accepted result has an inconsistent delivery state")
        if self.baseline_commit is not None and (
            not isinstance(self.baseline_commit, str) or FULL_GIT_SHA.fullmatch(self.baseline_commit) is None
        ):
            raise ContractValidationError("result.baselineCommit must be a full Git SHA")
        if self.validation_attempt is not None and (
            isinstance(self.validation_attempt, bool)
            or not isinstance(self.validation_attempt, int)
            or self.validation_attempt < 1
        ):
            raise ContractValidationError("result.validation.attempt must be positive")
        if self.validation_report_artifact_id is not None:
            _string(
                self.validation_report_artifact_id,
                "result.validation.reportArtifactId",
                maximum=128,
                pattern=IDENTIFIER,
            )
        if self.conversation_id is not None:
            _string(self.conversation_id, "result.openhands.conversationId", maximum=128)
        if self.pull_request_url is not None:
            pull_request = urlsplit(_string(self.pull_request_url, "result.delivery.pullRequestUrl", maximum=2048))
            if pull_request.scheme != "https" or not pull_request.hostname or pull_request.username or pull_request.password:
                raise ContractValidationError("result.delivery.pullRequestUrl must be an HTTPS URL without credentials")
        for artifact_id in self.artifact_ids:
            _string(artifact_id, "result.artifacts[]", maximum=128, pattern=IDENTIFIER)
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ContractValidationError("result.artifacts contains duplicate artifact ids")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractVersion": self.contract_version,
            "taskId": self.task_id,
            "outcome": self.outcome.value,
            "completedAt": self.completed_at,
            "baselineCommit": self.baseline_commit,
            "validatedTree": self.validated_tree,
            "openhands": {"executionStatus": self.execution_status.value, "conversationId": self.conversation_id},
            "validation": {
                "status": self.validation_status.value,
                "attempt": self.validation_attempt,
                "reportArtifactId": self.validation_report_artifact_id,
            },
            "delivery": {"status": self.delivery_status.value, "pullRequestUrl": self.pull_request_url},
            "artifacts": [{"artifactId": artifact_id} for artifact_id in self.artifact_ids],
        }

    @classmethod
    def from_dict(cls, value: Any) -> "TaskResult":
        obj = _object(value, "result")
        reject_sensitive_input(obj, "result")
        _strict_keys(
            obj,
            {"contractVersion", "taskId", "outcome", "completedAt", "baselineCommit", "validatedTree", "openhands", "validation", "delivery", "artifacts"},
            set(),
            "result",
        )
        if obj["contractVersion"] != CONTRACT_VERSION:
            raise ContractValidationError("result.contractVersion is unsupported")
        openhands = _object(obj["openhands"], "result.openhands")
        validation = _object(obj["validation"], "result.validation")
        delivery = _object(obj["delivery"], "result.delivery")
        _strict_keys(openhands, {"executionStatus", "conversationId"}, set(), "result.openhands")
        _strict_keys(validation, {"status", "attempt", "reportArtifactId"}, set(), "result.validation")
        _strict_keys(delivery, {"status", "pullRequestUrl"}, set(), "result.delivery")
        artifacts = obj["artifacts"]
        if not isinstance(artifacts, list):
            raise ContractValidationError("result.artifacts must be an array")
        artifact_ids: list[str] = []
        for index, item in enumerate(artifacts):
            artifact = _object(item, f"result.artifacts[{index}]")
            _strict_keys(artifact, {"artifactId"}, set(), f"result.artifacts[{index}]")
            artifact_ids.append(_string(artifact["artifactId"], f"result.artifacts[{index}].artifactId", maximum=128, pattern=IDENTIFIER))
        try:
            return cls(
                task_id=_string(obj["taskId"], "result.taskId", maximum=128, pattern=IDENTIFIER),
                outcome=ResultOutcome(obj["outcome"]),
                completed_at=_string(obj["completedAt"], "result.completedAt", maximum=64),
                baseline_commit=obj["baselineCommit"],
                validated_tree=obj["validatedTree"],
                execution_status=ExecutionStatus(openhands["executionStatus"]),
                conversation_id=openhands["conversationId"],
                validation_status=ValidationStatus(validation["status"]),
                validation_attempt=validation["attempt"],
                validation_report_artifact_id=validation["reportArtifactId"],
                delivery_status=DeliveryStatus(delivery["status"]),
                pull_request_url=delivery["pullRequestUrl"],
                artifact_ids=tuple(artifact_ids),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ContractValidationError):
                raise
            raise ContractValidationError("result contains an invalid enum value") from exc


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
