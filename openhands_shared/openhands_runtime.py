"""Fail-closed adapter for pinned OpenHands Agent Server 1.50.0.

This component provisions a native conversation, attaches task context, and
provides the Change 6 controlled execution-start boundary.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .contracts import (
    BaselineAssessmentStatus,
    ExecutionStatus,
    IntelligenceOutcome,
    OpenHandsEventLink,
    OpenHandsRuntimeRecord,
    OpenHandsRuntimeStatus,
    TaskRequest,
    TaskStatus,
    canonical_json,
    reject_sensitive_input,
    utc_now,
)
from .preparation import GitCommandError, GitRunner
from .store import ExecutionClaimConflictError, InvalidTransitionError, SQLiteTaskStore


PINNED_AGENT_SERVER_VERSION = "1.50.0"
PINNED_SDK_VERSION = "1.50.0"
PINNED_TOOLS_VERSION = "1.50.0"
_CONVERSATION_NAMESPACE = uuid.UUID("a0ae0bb1-e44e-5ce1-b521-f51bfbb1f627")
_CONTEXT_MARKER_PREFIX = "OPENHANDS_SHARED_TASK_CONTEXT"
_CONTINUING_INTELLIGENCE = frozenset(
    {
        IntelligenceOutcome.DISABLED,
        IntelligenceOutcome.NOT_APPLICABLE,
        IntelligenceOutcome.COMPLETE,
        IntelligenceOutcome.PARTIAL,
        IntelligenceOutcome.FAILED,
    }
)
_FORBIDDEN_REQUEST_KEYS = frozenset(
    {"env", "environment", "environment_variables", "secrets", "api_key", "token"}
)


class OpenHandsRuntimeError(RuntimeError):
    pass


class RuntimeConfigurationError(OpenHandsRuntimeError):
    pass


class AgentServerUnavailableError(OpenHandsRuntimeError):
    pass


class AgentServerCompatibilityError(OpenHandsRuntimeError):
    pass


class RuntimeIdentityError(OpenHandsRuntimeError):
    pass


class RuntimeRecoveryRequiredError(OpenHandsRuntimeError):
    pass


class AgentServerTransport(Protocol):
    """The small pinned REST surface used by the shared backend."""

    def server_info(self) -> Mapping[str, Any]: ...

    def get_conversation(self, conversation_id: str) -> Mapping[str, Any] | None: ...

    def create_conversation(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def send_message(
        self, conversation_id: str, request: Mapping[str, Any]
    ) -> None: ...

    def search_events(
        self,
        conversation_id: str,
        *,
        page_id: str | None = None,
        body: str | None = None,
    ) -> Mapping[str, Any]: ...

    def run_conversation(self, conversation_id: str) -> None: ...


class HttpAgentServerTransport:
    """Standard-library client whose auth headers never enter task payloads."""

    def __init__(
        self,
        base_url: str,
        *,
        headers_factory: Callable[[], Mapping[str, str]] | None = None,
        timeout_seconds: float = 15.0,
    ):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeConfigurationError("Agent Server URL must be HTTP(S)")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeConfigurationError(
                "Agent Server URL cannot contain credentials, query, or fragment"
            )
        self.base_url = base_url.rstrip("/")
        self.headers_factory = headers_factory
        self.timeout_seconds = timeout_seconds

    def server_info(self) -> Mapping[str, Any]:
        return self._request("GET", "/server_info")

    def get_conversation(self, conversation_id: str) -> Mapping[str, Any] | None:
        try:
            return self._request(
                "GET", f"/api/conversations/{conversation_id}?include_skills=true"
            )
        except _AgentServerNotFound:
            return None

    def create_conversation(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._request(
            "POST", "/api/conversations?include_skills=true", payload=request
        )

    def send_message(
        self, conversation_id: str, request: Mapping[str, Any]
    ) -> None:
        self._request(
            "POST", f"/api/conversations/{conversation_id}/events", payload=request
        )

    def search_events(
        self,
        conversation_id: str,
        *,
        page_id: str | None = None,
        body: str | None = None,
    ) -> Mapping[str, Any]:
        query: dict[str, str] = {"limit": "100", "sort_order": "TIMESTAMP"}
        if page_id is not None:
            query["page_id"] = page_id
        if body is not None:
            query["body"] = body
        return self._request(
            "GET",
            f"/api/conversations/{conversation_id}/events/search?"
            + urllib.parse.urlencode(query),
        )

    def run_conversation(self, conversation_id: str) -> None:
        self._request("POST", f"/api/conversations/{conversation_id}/run")

    def _request(
        self, method: str, path: str, *, payload: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        headers = {"Accept": "application/json"}
        if self.headers_factory is not None:
            supplied = dict(self.headers_factory())
            if any(not isinstance(key, str) or not isinstance(value, str) for key, value in supplied.items()):
                raise RuntimeConfigurationError("Agent Server headers must be strings")
            headers.update(supplied)
        data = None
        if payload is not None:
            data = canonical_json(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                value = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise _AgentServerNotFound from exc
            raise AgentServerUnavailableError(
                f"Agent Server {method} failed with HTTP {exc.code}"
            ) from exc
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise AgentServerUnavailableError(
                f"Agent Server {method} did not return a valid response"
            ) from exc
        if not isinstance(value, Mapping):
            raise AgentServerCompatibilityError("Agent Server returned a non-object response")
        return value


class _AgentServerNotFound(Exception):
    pass


@dataclass(frozen=True)
class OpenHandsAgentProfile:
    """Deployment-owned mapping to one native, secret-scoped Agent Profile."""

    profile_id: str
    model_profile_id: str
    native_agent_profile_id: str
    native_agent_profile_revision: int
    native_model: str
    required_skills: tuple[str, ...]
    allowed_terminal_environment: tuple[str, ...]
    guidance_files: tuple[Path, ...]
    stop_hook_argv: tuple[str, ...]
    stop_hook_timeout_seconds: int = 1800
    stop_hook_sha256: str | None = None

    def __post_init__(self) -> None:
        try:
            uuid.UUID(self.native_agent_profile_id)
        except (TypeError, ValueError) as exc:
            raise RuntimeConfigurationError("native Agent Profile id must be a UUID") from exc
        if self.native_agent_profile_revision < 0:
            raise RuntimeConfigurationError("native Agent Profile revision cannot be negative")
        if not self.required_skills or len(set(self.required_skills)) != len(self.required_skills):
            raise RuntimeConfigurationError("required Skills must be non-empty and unique")
        if len(set(self.allowed_terminal_environment)) != len(
            self.allowed_terminal_environment
        ):
            raise RuntimeConfigurationError(
                "allowed terminal environment names must be unique"
            )
        for name in self.allowed_terminal_environment:
            normalized = name.lower().replace("-", "_")
            if (
                not name
                or not name.replace("_", "").isalnum()
                or any(
                    part in normalized
                    for part in (
                        "token",
                        "password",
                        "secret",
                        "credential",
                        "github",
                        "gitlab",
                    )
                )
            ):
                raise RuntimeConfigurationError(
                    "terminal environment allowlist contains a sensitive name"
                )
        if not self.guidance_files:
            raise RuntimeConfigurationError("approved guidance files are required")
        if not self.stop_hook_argv:
            raise RuntimeConfigurationError("a native Stop Hook command is required")
        executable = Path(self.stop_hook_argv[0])
        if not executable.is_absolute() or executable.name in {"true", "false", "echo"}:
            raise RuntimeConfigurationError(
                "Stop Hook executable must be an approved absolute non-placeholder path"
            )
        if not 1 <= self.stop_hook_timeout_seconds <= 3600:
            raise RuntimeConfigurationError("Stop Hook timeout is outside the approved bound")
        if self.stop_hook_sha256 is not None and (
            len(self.stop_hook_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.stop_hook_sha256)
        ):
            raise RuntimeConfigurationError("Stop Hook executable SHA-256 is invalid")


@dataclass(frozen=True)
class OpenHandsRuntimeConfig:
    artifact_root: Path
    agent_server_identity: str
    profiles: tuple[OpenHandsAgentProfile, ...]

    def __post_init__(self) -> None:
        root = self.artifact_root.expanduser().resolve()
        object.__setattr__(self, "artifact_root", root)
        if not self.agent_server_identity or any(
            character.isspace() for character in self.agent_server_identity
        ):
            raise RuntimeConfigurationError("Agent Server identity is invalid")
        keys = [(profile.profile_id, profile.model_profile_id) for profile in self.profiles]
        if len(keys) != len(set(keys)):
            raise RuntimeConfigurationError("OpenHands runtime profiles must be unique")

    def profile_for(self, request: TaskRequest) -> OpenHandsAgentProfile:
        matches = [
            profile
            for profile in self.profiles
            if profile.profile_id == request.agent.profile
            and profile.model_profile_id == request.agent.model_profile
        ]
        if len(matches) != 1:
            raise RuntimeConfigurationError(
                "task agent/model profile is not mapped to one approved native profile"
            )
        return matches[0]


class SharedOpenHandsRuntime:
    """Provision native conversations and guard the single native run dispatch."""

    def __init__(
        self,
        store: SQLiteTaskStore,
        config: OpenHandsRuntimeConfig,
        transport: AgentServerTransport,
        *,
        git: GitRunner | None = None,
    ):
        self.store = store
        self.config = config
        self.transport = transport
        self.git = git or GitRunner()
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def provision(self, task_id: str) -> OpenHandsRuntimeRecord:
        """Create/reconcile one IDLE native conversation and attach context."""

        with self._task_lock(task_id):
            status = self.store.get_status(task_id)
            if status.status is not TaskStatus.AGENT_RUNNING:
                raise InvalidTransitionError(
                    "OpenHands provisioning requires task status AGENT_RUNNING"
                )
            if status.execution_status is not ExecutionStatus.NOT_STARTED:
                raise InvalidTransitionError(
                    "OpenHands provisioning requires execution status NOT_STARTED"
                )
            existing = self.store.get_openhands_runtime(task_id)
            if (
                existing is not None
                and existing.runtime_status is OpenHandsRuntimeStatus.RECOVERY_REQUIRED
            ):
                return self._reconcile_recovery(existing)

            request = self.store.get_request(task_id)
            preparation, baseline, intelligence, summary = self._verified_inputs(
                task_id, request
            )
            workspace = self._verify_workspace(
                request, preparation, allow_agent_changes=False
            )
            profile = self.config.profile_for(request)
            guidance, guidance_hashes = self._load_guidance(profile)
            hook_command = self._hook_command(profile, task_id, workspace)
            profile_fingerprint = self._profile_fingerprint(
                profile, guidance_hashes, hook_command, request.agent.max_iterations
            )
            conversation_id = str(
                uuid.uuid5(
                    _CONVERSATION_NAMESPACE,
                    f"{self.config.agent_server_identity}:{task_id}",
                )
            )
            payload = self._conversation_request(
                task_id=task_id,
                conversation_id=conversation_id,
                workspace=workspace,
                request=request,
                profile=profile,
                guidance=guidance,
                hook_command=hook_command,
                profile_fingerprint=profile_fingerprint,
            )
            self._assert_credential_isolation(payload)
            request_fingerprint = _sha256(canonical_json(payload).encode("utf-8"))
            server = self._verified_server()

            conversation = self.transport.get_conversation(conversation_id)
            if conversation is None:
                try:
                    conversation = self.transport.create_conversation(payload)
                except AgentServerUnavailableError:
                    conversation = self.transport.get_conversation(conversation_id)
                    if conversation is None:
                        raise
            try:
                self._verify_conversation(
                    conversation,
                    payload=payload,
                    profile=profile,
                    guidance=guidance,
                    allow_pending_hook=True,
                )
            except RuntimeIdentityError as exc:
                recovery = self._runtime_record(
                    task_id=task_id,
                    conversation_id=conversation_id,
                    server=server,
                    profile=profile,
                    profile_fingerprint=profile_fingerprint,
                    request_fingerprint=request_fingerprint,
                    workspace=workspace,
                    baseline_commit=baseline.baseline_commit,
                    runtime_status=OpenHandsRuntimeStatus.RECOVERY_REQUIRED,
                    failure_code="CONVERSATION_IDENTITY_MISMATCH",
                    failure_detail="Deterministic native conversation identity requires operator review",
                )
                if existing is None:
                    self.store.record_openhands_runtime(recovery)
                else:
                    self.store.mark_openhands_recovery_required(
                        task_id,
                        failure_code=recovery.failure_code or "CONVERSATION_IDENTITY_MISMATCH",
                        failure_detail=recovery.failure_detail or "operator review required",
                    )
                raise RuntimeRecoveryRequiredError(recovery.failure_detail or "recovery required") from exc

            now = utc_now()
            runtime = self._runtime_record(
                task_id=task_id,
                conversation_id=conversation_id,
                server=server,
                profile=profile,
                profile_fingerprint=profile_fingerprint,
                request_fingerprint=request_fingerprint,
                workspace=workspace,
                baseline_commit=baseline.baseline_commit,
                runtime_status=OpenHandsRuntimeStatus.CONVERSATION_READY,
                created_at=(existing.created_at if existing is not None else now),
            )
            runtime = self.store.record_openhands_runtime(runtime)
            instruction = self._agent_instruction(
                task_id, request, preparation, baseline, intelligence, summary,
                request_fingerprint,
            )
            reject_sensitive_input(instruction, "agentInstruction")
            marker = self._context_marker(task_id, request_fingerprint)
            context_event = self._find_context_event(conversation_id, marker)
            if context_event is None:
                try:
                    self.transport.send_message(
                        conversation_id,
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": instruction}],
                            "run": False,
                        },
                    )
                except AgentServerUnavailableError as exc:
                    try:
                        context_event = self._find_context_event(conversation_id, marker)
                    except OpenHandsRuntimeError:
                        context_event = None
                    if context_event is None:
                        self.store.mark_openhands_recovery_required(
                            task_id,
                            failure_code="INITIAL_MESSAGE_UNCERTAIN",
                            failure_detail=(
                                "Native context submission outcome is uncertain; automatic resend is disabled"
                            ),
                        )
                        raise RuntimeRecoveryRequiredError(
                            "native context submission requires operator-safe reconciliation"
                        ) from exc
                if context_event is None:
                    try:
                        context_event = self._find_context_event(conversation_id, marker)
                    except OpenHandsRuntimeError as exc:
                        self.store.mark_openhands_recovery_required(
                            task_id,
                            failure_code="INITIAL_MESSAGE_UNCERTAIN",
                            failure_detail=(
                                "Native context submission outcome is uncertain; automatic resend is disabled"
                            ),
                        )
                        raise RuntimeRecoveryRequiredError(
                            "native context submission requires operator-safe reconciliation"
                        ) from exc
            if context_event is None:
                self.store.mark_openhands_recovery_required(
                    task_id,
                    failure_code="INITIAL_MESSAGE_NOT_OBSERVED",
                    failure_detail=(
                        "Native context event was not observable; automatic resend is disabled"
                    ),
                )
                raise RuntimeRecoveryRequiredError(
                    "native context event requires operator-safe reconciliation"
                )
            try:
                initialized = self.transport.get_conversation(conversation_id)
                if initialized is None:
                    raise RuntimeIdentityError(
                        "native conversation disappeared after context attachment"
                    )
                self._verify_conversation(
                    initialized,
                    payload=payload,
                    profile=profile,
                    guidance=guidance,
                )
            except RuntimeIdentityError as exc:
                self.store.mark_openhands_recovery_required(
                    task_id,
                    failure_code="CONVERSATION_IDENTITY_MISMATCH",
                    failure_detail=(
                        "Initialized native conversation identity requires operator review"
                    ),
                )
                raise RuntimeRecoveryRequiredError(
                    "initialized native conversation identity requires operator review"
                ) from exc
            return self._link_context_event(runtime, context_event)

    def recover_provisioning(self, task_id: str) -> OpenHandsRuntimeRecord:
        """Explicitly recover a pre-execution hook-observation failure.

        This operation never starts execution. It may attach the uniquely
        marked context when it is provably absent, then requires the initialized
        native conversation—including the effective Stop Hook—to match before
        preserving the recovery history and advancing the current state.
        """

        with self._task_lock(task_id):
            runtime = self.store.get_openhands_runtime(task_id)
            if (
                runtime is None
                or runtime.runtime_status is not OpenHandsRuntimeStatus.RECOVERY_REQUIRED
                or runtime.failure_code != "CONVERSATION_IDENTITY_MISMATCH"
                or runtime.execution_status is not ExecutionStatus.NOT_STARTED
            ):
                raise RuntimeRecoveryRequiredError(
                    "task is not eligible for explicit provisioning recovery"
                )
            request = self.store.get_request(task_id)
            preparation, baseline, intelligence, summary = self._verified_inputs(
                task_id, request
            )
            workspace = self._verify_workspace(
                request, preparation, allow_agent_changes=False
            )
            profile = self.config.profile_for(request)
            guidance, guidance_hashes = self._load_guidance(profile)
            hook_command = self._hook_command(profile, task_id, workspace)
            profile_fingerprint = self._profile_fingerprint(
                profile, guidance_hashes, hook_command, request.agent.max_iterations
            )
            payload = self._conversation_request(
                task_id=task_id,
                conversation_id=runtime.conversation_id,
                workspace=workspace,
                request=request,
                profile=profile,
                guidance=guidance,
                hook_command=hook_command,
                profile_fingerprint=profile_fingerprint,
            )
            self._assert_credential_isolation(payload)
            request_fingerprint = _sha256(canonical_json(payload).encode("utf-8"))
            if (
                request_fingerprint != runtime.request_fingerprint
                or profile_fingerprint != runtime.profile_fingerprint
                or baseline.baseline_commit != runtime.baseline_commit
            ):
                raise RuntimeIdentityError(
                    "durable recovery identity differs from the original provisioning request"
                )
            self._verified_server()
            conversation = self.transport.get_conversation(runtime.conversation_id)
            if conversation is None:
                raise RuntimeRecoveryRequiredError(
                    "native recovery conversation is unavailable"
                )
            self._verify_conversation(
                conversation,
                payload=payload,
                profile=profile,
                guidance=guidance,
                allow_pending_hook=True,
            )
            instruction = self._agent_instruction(
                task_id,
                request,
                preparation,
                baseline,
                intelligence,
                summary,
                request_fingerprint,
            )
            reject_sensitive_input(instruction, "agentInstruction")
            marker = self._context_marker(task_id, request_fingerprint)
            context_event = self._find_context_event(runtime.conversation_id, marker)
            if context_event is None:
                try:
                    self.transport.send_message(
                        runtime.conversation_id,
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": instruction}],
                            "run": False,
                        },
                    )
                except AgentServerUnavailableError as exc:
                    context_event = self._find_context_event(
                        runtime.conversation_id, marker
                    )
                    if context_event is None:
                        raise RuntimeRecoveryRequiredError(
                            "explicit context recovery remains uncertain; resend is disabled"
                        ) from exc
                if context_event is None:
                    context_event = self._find_context_event(
                        runtime.conversation_id, marker
                    )
            if context_event is None:
                raise RuntimeRecoveryRequiredError(
                    "explicit recovery could not observe the native context event"
                )
            initialized = self.transport.get_conversation(runtime.conversation_id)
            if initialized is None:
                raise RuntimeRecoveryRequiredError(
                    "native recovery conversation disappeared after initialization"
                )
            self._verify_conversation(
                initialized,
                payload=payload,
                profile=profile,
                guidance=guidance,
            )
            ready = self.store.complete_openhands_recovery(
                task_id, expected_failure_code="CONVERSATION_IDENTITY_MISMATCH"
            )
            return self._link_context_event(ready, context_event)

    def synchronize_event_references(self, task_id: str) -> tuple[OpenHandsEventLink, ...]:
        """Project native identifiers/kinds only; native storage retains payloads."""

        runtime = self.store.get_openhands_runtime(task_id)
        if runtime is None:
            raise InvalidTransitionError("task has no native conversation")
        if runtime.runtime_status is OpenHandsRuntimeStatus.RECOVERY_REQUIRED:
            raise RuntimeRecoveryRequiredError("native conversation requires operator recovery")
        existing = {link.native_event_id for link in self.store.list_openhands_event_links(task_id)}
        order = runtime.last_native_event_order
        for item in self._all_events(runtime.conversation_id):
            event_id = item.get("id")
            if not isinstance(event_id, str) or event_id in existing:
                continue
            order += 1
            link = self._event_link(task_id, runtime.conversation_id, item, order)
            self.store.link_openhands_event(link)
            existing.add(event_id)
        return self.store.list_openhands_event_links(task_id)

    def start_execution(self, task_id: str, *, worker_id: str) -> OpenHandsRuntimeRecord:
        """Claim once, record intent, then invoke native ``/run`` at most once."""

        with self._task_lock(task_id):
            runtime = self.store.get_openhands_runtime(task_id)
            if runtime is None or runtime.runtime_status is not OpenHandsRuntimeStatus.CONTEXT_ATTACHED:
                raise InvalidTransitionError("execution requires a context-attached native conversation")
            existing_claim = self.store.get_execution_claim(task_id)
            if existing_claim is not None:
                if existing_claim.worker_id != worker_id:
                    raise ExecutionClaimConflictError("task is already owned by another worker")
                return self._reconcile_execution_claim(runtime, existing_claim)
            request = self.store.get_request(task_id)
            preparation, baseline, _intelligence, _summary = self._verified_inputs(task_id, request)
            workspace = self._verify_workspace(request, preparation, allow_agent_changes=False)
            profile = self.config.profile_for(request)
            guidance, guidance_hashes = self._load_guidance(profile)
            hook_command = self._hook_command(profile, task_id, workspace)
            executable = Path(profile.stop_hook_argv[0])
            if executable.is_symlink() or not executable.is_file() or not executable.stat().st_mode & 0o111:
                raise RuntimeConfigurationError("configured Stop Hook executable is not installed and executable")
            if profile.stop_hook_sha256 is None or _sha256(executable.read_bytes()) != profile.stop_hook_sha256:
                raise RuntimeConfigurationError("Stop Hook executable differs from its approved SHA-256")
            if task_id not in hook_command or str(workspace) not in hook_command:
                raise RuntimeConfigurationError("Stop Hook command lacks durable task/workspace binding")
            try:
                config_index = profile.stop_hook_argv.index("--config") + 1
                config_path = Path(profile.stop_hook_argv[config_index])
            except (ValueError, IndexError) as exc:
                raise RuntimeConfigurationError("Stop Hook command lacks deployment configuration") from exc
            if not config_path.is_absolute() or config_path.is_symlink() or not config_path.is_file():
                raise RuntimeConfigurationError("Stop Hook deployment configuration is unavailable")
            from .stop_hook import load_stop_hook_config
            try:
                hook_database, validation_config = load_stop_hook_config(config_path)
                validation_profile = validation_config.profile_for(request)
            except Exception as exc:
                raise RuntimeConfigurationError("Stop Hook deployment configuration is invalid") from exc
            if (
                hook_database != self.store.database_path.resolve()
                or validation_config.artifact_root != self.config.artifact_root
                or validation_profile.build_commands != request.acceptance.build_commands
            ):
                raise RuntimeConfigurationError("Stop Hook configuration differs from durable task service")
            profile_fingerprint = self._profile_fingerprint(
                profile, guidance_hashes, hook_command, request.agent.max_iterations
            )
            payload = self._conversation_request(
                task_id=task_id,
                conversation_id=runtime.conversation_id,
                workspace=workspace,
                request=request,
                profile=profile,
                guidance=guidance,
                hook_command=hook_command,
                profile_fingerprint=profile_fingerprint,
            )
            if _sha256(canonical_json(payload).encode("utf-8")) != runtime.request_fingerprint:
                raise RuntimeIdentityError("native execution request differs from the provisioned identity")
            conversation = self.transport.get_conversation(runtime.conversation_id)
            if conversation is None:
                raise RuntimeRecoveryRequiredError("native conversation is unavailable")
            self._verify_conversation(
                conversation,
                payload=payload,
                profile=profile,
                guidance=guidance,
                require_idle=True,
            )
            marker = self._context_marker(task_id, runtime.request_fingerprint)
            if self._find_context_event(runtime.conversation_id, marker) is None:
                raise RuntimeRecoveryRequiredError("expected task context event is missing")

            claim = self.store.claim_execution(task_id, worker_id)
            try:
                self.transport.run_conversation(runtime.conversation_id)
            except AgentServerUnavailableError as exc:
                try:
                    conversation = self.transport.get_conversation(runtime.conversation_id)
                except AgentServerUnavailableError:
                    conversation = None
                native_status = None if conversation is None else conversation.get("execution_status")
                if native_status in {"running", "finished"}:
                    self.store.update_execution_dispatch(task_id, dispatched=True)
                    return self.store.get_openhands_runtime(task_id) or runtime
                self.store.update_execution_dispatch(
                    task_id, dispatched=False, recovery_code="RUN_RESPONSE_UNCERTAIN"
                )
                raise RuntimeRecoveryRequiredError(
                    "native /run outcome is uncertain; automatic redispatch is disabled"
                ) from exc
            self.store.update_execution_dispatch(task_id, dispatched=True)
            return self.store.get_openhands_runtime(task_id) or runtime

    def _reconcile_execution_claim(self, runtime: OpenHandsRuntimeRecord, claim: Any) -> OpenHandsRuntimeRecord:
        if claim.dispatch_status.value == "DISPATCHED":
            return runtime
        if claim.dispatch_status.value == "RECOVERY_REQUIRED":
            raise RuntimeRecoveryRequiredError("native execution dispatch requires operator recovery")
        try:
            conversation = self.transport.get_conversation(runtime.conversation_id)
        except AgentServerUnavailableError:
            conversation = None
        native_status = None if conversation is None else conversation.get("execution_status")
        if native_status in {"running", "finished"}:
            self.store.update_execution_dispatch(runtime.task_id, dispatched=True)
            return self.store.get_openhands_runtime(runtime.task_id) or runtime
        self.store.update_execution_dispatch(
            runtime.task_id, dispatched=False, recovery_code="RUN_INTENT_UNCERTAIN"
        )
        raise RuntimeRecoveryRequiredError(
            "execution intent exists without observable dispatch; automatic /run is disabled"
        )

    def reconcile_execution(self, task_id: str) -> Any:
        """Project native terminal state while preserving independent acceptance."""

        runtime = self.store.get_openhands_runtime(task_id)
        claim = self.store.get_execution_claim(task_id)
        if runtime is None or claim is None:
            raise InvalidTransitionError("task has no claimed native execution")
        conversation = self.transport.get_conversation(runtime.conversation_id)
        if conversation is None:
            raise RuntimeRecoveryRequiredError("native conversation is unavailable")
        status = conversation.get("execution_status")
        if status == "finished":
            return self.store.record_native_execution_terminal(task_id, completed=True)
        if status in {"error", "failed"}:
            return self.store.record_native_execution_terminal(task_id, completed=False)
        if status in {"running", "paused", "idle"}:
            return self.store.get_status(task_id)
        raise AgentServerCompatibilityError("native execution status is unsupported")

    def _reconcile_recovery(self, runtime: OpenHandsRuntimeRecord) -> OpenHandsRuntimeRecord:
        if runtime.failure_code not in {
            "INITIAL_MESSAGE_UNCERTAIN",
            "INITIAL_MESSAGE_NOT_OBSERVED",
        }:
            raise RuntimeRecoveryRequiredError(
                "native conversation identity requires operator review"
            )
        marker = self._context_marker(runtime.task_id, runtime.request_fingerprint)
        context_event = self._find_context_event(runtime.conversation_id, marker)
        if context_event is None:
            raise RuntimeRecoveryRequiredError(
                "native context remains uncertain; automatic resend is disabled"
            )
        # Recovery rows are intentionally not cleared automatically. Change 6
        # will add a claimed worker/operator recovery transition.
        raise RuntimeRecoveryRequiredError(
            "native context exists but operator acknowledgement is required"
        )

    def _verified_inputs(self, task_id: str, request: TaskRequest):
        preparation = self.store.get_preparation(task_id)
        baseline = self.store.get_baseline(task_id)
        intelligence = self.store.get_intelligence(task_id)
        if preparation is None or baseline is None or intelligence is None:
            raise RuntimeIdentityError("durable preparation, baseline, and intelligence are required")
        if (
            preparation.repository_url != request.repository.url
            or preparation.base_ref != request.repository.base_ref
            or preparation.expected_commit != request.repository.expected_commit
            or preparation.baseline_commit != request.repository.expected_commit
        ):
            raise RuntimeIdentityError("preparation identity differs from registered task")
        if (
            baseline.assessment_status is not BaselineAssessmentStatus.COMPLETED
            or baseline.baseline_commit != preparation.baseline_commit
        ):
            raise RuntimeIdentityError("successful matching baseline is required")
        if (
            intelligence.outcome not in _CONTINUING_INTELLIGENCE
            or intelligence.baseline_commit != baseline.baseline_commit
        ):
            raise RuntimeIdentityError("continuing matching intelligence is required")
        artifacts = {item.artifact_id: item for item in self.store.list_artifacts(task_id)}
        required = {
            baseline.report_artifact_id: baseline.report_sha256,
            intelligence.record_artifact_id: intelligence.record_sha256,
            intelligence.summary_artifact_id: None,
        }
        stage_artifacts = [
            artifact
            for artifact in artifacts.values()
            if artifact.kind.startswith("baseline-")
            or artifact.kind.startswith("intelligence-")
        ]
        if not stage_artifacts:
            raise RuntimeIdentityError("baseline/intelligence artifact manifest is empty")
        for artifact in stage_artifacts:
            self._verify_artifact(
                artifact.relative_path, artifact.sha256, artifact.size_bytes
            )
        for artifact_id, expected_hash in required.items():
            artifact = artifacts.get(artifact_id)
            if artifact is None or (expected_hash is not None and artifact.sha256 != expected_hash):
                raise RuntimeIdentityError("required baseline/intelligence artifact metadata is inconsistent")
        baseline_document = self._artifact_json(artifacts[baseline.report_artifact_id])
        if (
            baseline_document.get("taskId") != task_id
            or baseline_document.get("baselineCommit") != baseline.baseline_commit
            or baseline_document.get("assessmentStatus")
            != baseline.assessment_status.value
        ):
            raise RuntimeIdentityError("baseline report identity is inconsistent")
        intelligence_document = self._artifact_json(
            artifacts[intelligence.record_artifact_id]
        )
        if (
            intelligence_document.get("taskId") != task_id
            or intelligence_document.get("baselineCommit")
            != intelligence.baseline_commit
            or intelligence_document.get("outcome") != intelligence.outcome.value
        ):
            raise RuntimeIdentityError("intelligence record identity is inconsistent")
        summary_artifact = artifacts[intelligence.summary_artifact_id]
        try:
            summary = (self.config.artifact_root / summary_artifact.relative_path).read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeDecodeError) as exc:
            raise RuntimeIdentityError("SBRI summary artifact is unreadable") from exc
        if not summary.strip():
            raise RuntimeIdentityError("SBRI summary artifact is empty")
        if intelligence.outcome not in {
            IntelligenceOutcome.DISABLED,
            IntelligenceOutcome.NOT_APPLICABLE,
        } and (
            "<SBRI_PRE_EDIT_EVIDENCE>" not in summary
            or "</SBRI_PRE_EDIT_EVIDENCE>" not in summary
        ):
            raise RuntimeIdentityError("SBRI summary lost its bounded evidence markers")
        return preparation, baseline, intelligence, summary.strip()

    def _artifact_json(self, artifact: Any) -> Mapping[str, Any]:
        try:
            value = json.loads(
                (self.config.artifact_root / artifact.relative_path).read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeIdentityError("required stage record is invalid JSON") from exc
        if not isinstance(value, Mapping):
            raise RuntimeIdentityError("required stage record must be a JSON object")
        return value

    def _verify_artifact(self, relative_path: str, digest: str, size_bytes: int) -> None:
        root = self.config.artifact_root
        if root.is_symlink():
            raise RuntimeIdentityError("artifact root cannot be a symbolic link")
        path = root / relative_path
        current = root
        for part in Path(relative_path).parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeIdentityError("artifact path cannot traverse a symbolic link")
        if not path.is_file():
            raise RuntimeIdentityError("required artifact is unavailable")
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise RuntimeIdentityError("artifact escaped the configured root")
        payload = path.read_bytes()
        if len(payload) != size_bytes or _sha256(payload) != digest:
            raise RuntimeIdentityError("required artifact failed checksum verification")

    def _verify_workspace(
        self,
        request: TaskRequest,
        preparation: Any,
        *,
        allow_agent_changes: bool,
    ) -> Path:
        workspace = Path(preparation.workspace_path)
        source = Path(preparation.source_path)
        if (
            not workspace.is_dir()
            or workspace.is_symlink()
            or not source.is_dir()
            or source.is_symlink()
        ):
            raise RuntimeIdentityError("prepared task workspace is unavailable")
        try:
            _, workspace_common = self.git.run(
                workspace, ["rev-parse", "--git-common-dir"], operation="agent_workspace_identity"
            )
            _, source_common = self.git.run(
                source, ["rev-parse", "--git-common-dir"], operation="agent_source_identity"
            )
            if _common_path(workspace, workspace_common) != _common_path(source, source_common):
                raise RuntimeIdentityError("task workspace belongs to a foreign repository")
            branch_code, branch = self.git.run(
                workspace,
                ["symbolic-ref", "--quiet", "HEAD"],
                operation="agent_workspace_branch",
                allowed_return_codes=frozenset({0, 1}),
            )
            if branch_code != 0 or branch != f"refs/heads/{preparation.local_branch}":
                raise RuntimeIdentityError("task workspace is on a foreign branch")
            _, head = self.git.run(
                workspace,
                ["rev-parse", "--verify", "HEAD^{commit}"],
                operation="agent_workspace_head",
            )
            code, _ = self.git.run(
                workspace,
                ["merge-base", "--is-ancestor", preparation.baseline_commit, "HEAD"],
                operation="agent_baseline_ancestor",
                allowed_return_codes=frozenset({0, 1}),
            )
            if code != 0:
                raise RuntimeIdentityError("immutable baseline is not an ancestor of workspace HEAD")
            if not allow_agent_changes:
                if head != preparation.baseline_commit:
                    raise RuntimeIdentityError(
                        "pre-execution workspace HEAD differs from immutable baseline"
                    )
                _, dirty = self.git.run(
                    workspace,
                    ["status", "--porcelain=v1", "--untracked-files=all"],
                    operation="agent_pre_execution_cleanliness",
                )
                if dirty:
                    raise RuntimeIdentityError(
                        "pre-execution workspace contains unapproved changes"
                    )
        except GitCommandError as exc:
            raise RuntimeIdentityError("task workspace identity could not be verified") from exc
        return workspace.resolve()

    def _load_guidance(
        self, profile: OpenHandsAgentProfile
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        sections: list[str] = []
        hashes: list[tuple[str, str]] = []
        for path_value in profile.guidance_files:
            path = path_value.expanduser().resolve()
            if not path.is_file() or path.is_symlink():
                raise RuntimeConfigurationError("approved guidance file is unavailable")
            payload = path.read_bytes()
            try:
                text = payload.decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                raise RuntimeConfigurationError("approved guidance must be UTF-8") from exc
            if not text:
                raise RuntimeConfigurationError("approved guidance cannot be empty")
            sections.append(text)
            hashes.append((path.name, _sha256(payload)))
        guidance = "\n\n".join(sections)
        if len(guidance) > 32768:
            raise RuntimeConfigurationError("approved guidance exceeds native launch bound")
        return guidance, tuple(hashes)

    @staticmethod
    def _hook_command(
        profile: OpenHandsAgentProfile, task_id: str, workspace: Path
    ) -> str:
        substitutions = {"task_id": task_id, "workspace": str(workspace)}
        arguments: list[str] = []
        for value in profile.stop_hook_argv:
            try:
                expanded = value.format_map(substitutions)
            except (KeyError, ValueError) as exc:
                raise RuntimeConfigurationError("Stop Hook command has an invalid placeholder") from exc
            if "\x00" in expanded:
                raise RuntimeConfigurationError("Stop Hook command contains a NUL character")
            arguments.append(expanded)
        return shlex.join(arguments)

    def _profile_fingerprint(
        self,
        profile: OpenHandsAgentProfile,
        guidance_hashes: tuple[tuple[str, str], ...],
        hook_command: str,
        max_iterations: int,
    ) -> str:
        return _sha256(
            canonical_json(
                {
                    "agentServerVersion": PINNED_AGENT_SERVER_VERSION,
                    "sdkVersion": PINNED_SDK_VERSION,
                    "toolsVersion": PINNED_TOOLS_VERSION,
                    "agentProfileId": profile.profile_id,
                    "modelProfileId": profile.model_profile_id,
                    "nativeAgentProfileId": profile.native_agent_profile_id,
                    "nativeAgentProfileRevision": profile.native_agent_profile_revision,
                    "nativeModel": profile.native_model,
                    "requiredSkills": list(profile.required_skills),
                    "allowedTerminalEnvironment": list(
                        profile.allowed_terminal_environment
                    ),
                    "guidanceHashes": [list(item) for item in guidance_hashes],
                    "stopHookCommandSha256": _sha256(hook_command.encode("utf-8")),
                    "stopHookTimeout": profile.stop_hook_timeout_seconds,
                    "maxIterations": max_iterations,
                    "stopHookExecutableSha256": profile.stop_hook_sha256,
                    "validatorParity": profile.stop_hook_sha256 is not None,
                    "executionEnabled": profile.stop_hook_sha256 is not None,
                }
            ).encode("utf-8")
        )

    @staticmethod
    def _conversation_request(
        *,
        task_id: str,
        conversation_id: str,
        workspace: Path,
        request: TaskRequest,
        profile: OpenHandsAgentProfile,
        guidance: str,
        hook_command: str,
        profile_fingerprint: str,
    ) -> dict[str, Any]:
        return {
            "workspace": {"working_dir": str(workspace), "kind": "LocalWorkspace"},
            "worktree": False,
            "conversation_id": conversation_id,
            "agent_profile_id": profile.native_agent_profile_id,
            "max_iterations": request.agent.max_iterations,
            "stuck_detection": True,
            "agent_launch_additions": {
                "system_message_suffix_append": guidance,
            },
            "hook_config": {
                "pre_tool_use": [],
                "post_tool_use": [],
                "user_prompt_submit": [],
                "session_start": [],
                "session_end": [],
                "stop": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "name": "openhands-shared-independent-validation",
                                "command": hook_command,
                                "prompt": None,
                                "system_prompt": None,
                                "tools": [],
                                "timeout": profile.stop_hook_timeout_seconds,
                                "max_iterations": 3,
                                "async": False,
                            }
                        ],
                    }
                ],
            },
            "tags": {
                "sharedtaskid": task_id,
                "sharedprofile": profile.profile_id,
                "sharedfingerprint": profile_fingerprint,
            },
            "observability_metadata": {
                "shared_task_id": task_id,
                "shared_profile_fingerprint": profile_fingerprint,
            },
            "observability_tags": ["openhands-shared"],
            "autotitle": False,
        }

    @staticmethod
    def _assert_credential_isolation(value: Any, path: str = "request") -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized = str(key).lower().replace("-", "_")
                if normalized in _FORBIDDEN_REQUEST_KEYS:
                    raise RuntimeConfigurationError(
                        f"native request contains prohibited credential/environment field at {path}"
                    )
                SharedOpenHandsRuntime._assert_credential_isolation(
                    nested, f"{path}.{key}"
                )
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                SharedOpenHandsRuntime._assert_credential_isolation(
                    nested, f"{path}[{index}]"
                )

    def _verified_server(self) -> Mapping[str, Any]:
        info = self.transport.server_info()
        expected = {
            "version": PINNED_AGENT_SERVER_VERSION,
            "sdk_version": PINNED_SDK_VERSION,
            "tools_version": PINNED_TOOLS_VERSION,
        }
        for key, value in expected.items():
            if info.get(key) != value:
                raise AgentServerCompatibilityError(
                    f"Agent Server {key} is incompatible with pinned Change 5 contract"
                )
        return info

    @staticmethod
    def _verify_conversation(
        conversation: Mapping[str, Any],
        *,
        payload: Mapping[str, Any],
        profile: OpenHandsAgentProfile,
        guidance: str,
        require_idle: bool = True,
        allow_pending_hook: bool = False,
    ) -> None:
        if conversation.get("id") != payload["conversation_id"]:
            raise RuntimeIdentityError("native conversation id differs from deterministic id")
        if require_idle and conversation.get("execution_status") != "idle":
            raise RuntimeIdentityError("native conversation is not idle/non-running")
        if not require_idle and conversation.get("execution_status") not in {
            "idle", "running", "paused", "finished", "error", "failed"
        }:
            raise RuntimeIdentityError("native conversation execution status is unsupported")
        workspace = conversation.get("workspace")
        if not isinstance(workspace, Mapping) or (
            workspace.get("working_dir") != payload["workspace"]["working_dir"]
            or workspace.get("kind") != "LocalWorkspace"
        ):
            raise RuntimeIdentityError("native conversation workspace differs from task workspace")
        for key in ("max_iterations", "stuck_detection", "tags"):
            if conversation.get(key) != payload[key]:
                raise RuntimeIdentityError(f"native conversation {key} differs from approved request")
        observed_hook = conversation.get("hook_config")
        if observed_hook != payload["hook_config"] and not (
            allow_pending_hook and observed_hook is None
        ):
            raise RuntimeIdentityError(
                "native conversation hook_config differs from approved request"
            )
        launched = conversation.get("launched_agent_profile")
        if not isinstance(launched, Mapping) or (
            launched.get("agent_profile_id") != profile.native_agent_profile_id
            or launched.get("revision") != profile.native_agent_profile_revision
            or launched.get("secret_refs") != []
        ):
            raise RuntimeIdentityError(
                "native Agent Profile provenance or secret scope differs from approval"
            )
        agent = conversation.get("agent")
        if not isinstance(agent, Mapping):
            raise RuntimeIdentityError("native conversation did not expose resolved agent")
        llm = agent.get("llm")
        if not isinstance(llm, Mapping) or llm.get("model") != profile.native_model:
            raise RuntimeIdentityError("native model differs from approved model profile")
        context = agent.get("agent_context")
        if not isinstance(context, Mapping):
            raise RuntimeIdentityError("native agent context is missing")
        suffix = context.get("system_message_suffix")
        if not isinstance(suffix, str) or not suffix.endswith(guidance):
            raise RuntimeIdentityError("approved engineering guidance was not attached")
        skills = context.get("skills")
        if not isinstance(skills, list):
            raise RuntimeIdentityError("native Skill catalog was not returned for verification")
        names = {
            item.get("name") for item in skills if isinstance(item, Mapping)
        }
        if not set(profile.required_skills).issubset(names):
            raise RuntimeIdentityError("approved Skills are missing from native agent profile")
        tools = agent.get("tools")
        if not isinstance(tools, list):
            raise RuntimeIdentityError("native agent tools were not returned for verification")
        terminals = [
            item
            for item in tools
            if isinstance(item, Mapping) and item.get("name") == "terminal"
        ]
        if len(terminals) != 1:
            raise RuntimeIdentityError("native agent must expose exactly one terminal tool")
        params = terminals[0].get("params")
        if not isinstance(params, Mapping):
            raise RuntimeIdentityError("native terminal configuration is missing")
        environment = params.get("env", {})
        if not isinstance(environment, Mapping) or any(
            key not in profile.allowed_terminal_environment for key in environment
        ):
            raise RuntimeIdentityError(
                "native terminal environment exceeds the deployment allowlist"
            )
        reject_sensitive_input(dict(environment), "nativeTerminalEnvironment")

    def _runtime_record(
        self,
        *,
        task_id: str,
        conversation_id: str,
        server: Mapping[str, Any],
        profile: OpenHandsAgentProfile,
        profile_fingerprint: str,
        request_fingerprint: str,
        workspace: Path,
        baseline_commit: str,
        runtime_status: OpenHandsRuntimeStatus,
        failure_code: str | None = None,
        failure_detail: str | None = None,
        created_at: str | None = None,
    ) -> OpenHandsRuntimeRecord:
        now = utc_now()
        return OpenHandsRuntimeRecord(
            task_id=task_id,
            conversation_id=conversation_id,
            agent_server_identity=self.config.agent_server_identity,
            agent_server_version=str(server["version"]),
            sdk_version=str(server["sdk_version"]),
            tools_version=str(server["tools_version"]),
            agent_profile_id=profile.profile_id,
            native_agent_profile_id=profile.native_agent_profile_id,
            native_agent_profile_revision=profile.native_agent_profile_revision,
            model_profile_id=profile.model_profile_id,
            native_model=profile.native_model,
            profile_fingerprint=profile_fingerprint,
            request_fingerprint=request_fingerprint,
            workspace_path=str(workspace),
            baseline_commit=baseline_commit,
            runtime_status=runtime_status,
            execution_status=ExecutionStatus.NOT_STARTED,
            last_native_event_id=None,
            last_native_event_order=0,
            failure_code=failure_code,
            failure_detail=failure_detail,
            created_at=created_at or now,
            updated_at=now,
        )

    def _agent_instruction(
        self,
        task_id: str,
        request: TaskRequest,
        preparation: Any,
        baseline: Any,
        intelligence: Any,
        summary: str,
        request_fingerprint: str,
    ) -> str:
        marker = self._context_marker(task_id, request_fingerprint)
        lines = [
            f"<{_CONTEXT_MARKER_PREFIX} id=\"{marker}\">",
            "Use the registered task contract below as authoritative. Do not deliver or push changes.",
            f"Objective: {request.objective}",
            "Constraints: " + canonical_json(request.constraints.to_dict()),
            "Acceptance requirements: " + canonical_json(request.acceptance.to_dict()),
            "Repository: "
            + canonical_json(
                {
                    "url": request.repository.url,
                    "baseRef": request.repository.base_ref,
                    "baselineCommit": preparation.baseline_commit,
                    "workspace": preparation.workspace_path,
                    "taskBranch": preparation.local_branch,
                }
            ),
            "Baseline evidence: "
            + canonical_json(
                {
                    "reportArtifactId": baseline.report_artifact_id,
                    "reportSha256": baseline.report_sha256,
                    "findingCount": baseline.finding_count,
                }
            ),
        ]
        if intelligence.outcome not in {
            IntelligenceOutcome.DISABLED,
            IntelligenceOutcome.NOT_APPLICABLE,
        }:
            lines.extend(["", summary])
        else:
            lines.append(
                "SBRI status: "
                + intelligence.outcome.value
                + "; no SBRI candidate evidence is asserted for this task."
            )
        lines.extend(
            [
                "",
                "SBRI candidate selection limits collected evidence, not available strategies.",
                "SBRI ranking is not an implementation decision.",
                "Residual SBRI candidate findings are not acceptable final remediation results.",
                "Independent deterministic validation remains authoritative; agent completion is not acceptance.",
                f"</{_CONTEXT_MARKER_PREFIX}>",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _context_marker(task_id: str, request_fingerprint: str) -> str:
        return f"{task_id}:{request_fingerprint}"

    def _find_context_event(
        self, conversation_id: str, marker: str
    ) -> Mapping[str, Any] | None:
        for item in self._all_events(conversation_id, body=marker):
            if _contains_string(item, marker):
                return item
        return None

    def _all_events(
        self, conversation_id: str, *, body: str | None = None
    ) -> list[Mapping[str, Any]]:
        output: list[Mapping[str, Any]] = []
        page_id: str | None = None
        seen_pages: set[str] = set()
        while True:
            page = self.transport.search_events(
                conversation_id, page_id=page_id, body=body
            )
            items = page.get("items")
            if not isinstance(items, list) or any(not isinstance(item, Mapping) for item in items):
                raise AgentServerCompatibilityError("native event search response is invalid")
            output.extend(items)
            next_page = page.get("next_page_id")
            if next_page is None:
                return output
            if not isinstance(next_page, str) or not next_page or next_page in seen_pages:
                raise AgentServerCompatibilityError("native event pagination cursor is invalid")
            seen_pages.add(next_page)
            page_id = next_page

    def _link_context_event(
        self, runtime: OpenHandsRuntimeRecord, event: Mapping[str, Any]
    ) -> OpenHandsRuntimeRecord:
        for existing in self.store.list_openhands_event_links(runtime.task_id):
            if existing.native_event_id == event.get("id"):
                return self.store.get_openhands_runtime(runtime.task_id) or runtime
        link = self._event_link(
            runtime.task_id,
            runtime.conversation_id,
            event,
            runtime.last_native_event_order + 1,
        )
        return self.store.link_openhands_event(link, context_attached=True)

    @staticmethod
    def _event_link(
        task_id: str,
        conversation_id: str,
        event: Mapping[str, Any],
        order: int,
    ) -> OpenHandsEventLink:
        event_id = event.get("id")
        kind = event.get("kind")
        if not isinstance(event_id, str) or not isinstance(kind, str):
            raise AgentServerCompatibilityError("native event lacks id or kind")
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
            timestamp = None
        return OpenHandsEventLink(
            task_id=task_id,
            conversation_id=conversation_id,
            native_event_id=event_id,
            native_order=order,
            native_kind=kind,
            native_timestamp=timestamp,
            observed_at=utc_now(),
        )

    def _task_lock(self, task_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(task_id, threading.Lock())


def _contains_string(value: Any, expected: str) -> bool:
    if isinstance(value, str):
        return expected in value
    if isinstance(value, Mapping):
        return any(_contains_string(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_contains_string(item, expected) for item in value)
    return False


def _common_path(repository: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repository / path
    return path.resolve()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
