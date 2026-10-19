#!/usr/bin/env python3
"""Native-first task-to-conversation bridge (no custom API or agent loop).

Existing deterministic preparation/baseline/validation own remediation facts.
OpenHands Agent Server owns conversation creation, execution, and event history.
This module constructs/verifies the handoff; it does not start a paid model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys
from typing import Any, Callable, Mapping
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openhands_shared.contracts import TaskStatus
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.stop_hook import load_stop_hook_config


class HandoffError(ValueError):
    """Unverified native conversation configuration; do not execute."""


def _nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"{name} is required")
    return value


def build_request(
    store: SQLiteTaskStore,
    task_id: str,
    *,
    hook_config: Path,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    max_iterations: int = 20,
) -> dict[str, Any]:
    """Prepare the official 1.55.1 Agent Server API payload, without sending it.

    The native server owns execution. Validation uses the existing durable
    mapping, not native 'finished' as acceptance. No model secrets are saved.
    """
    if not 1 <= max_iterations <= 100:
        raise HandoffError("max_iterations must be between 1 and 100")
    model = _nonempty(model, "model")
    if api_key is not None and not api_key.strip():
        raise HandoffError("api_key cannot be empty")
    status = store.get_status(task_id)
    if status.status is not TaskStatus.AGENT_RUNNING or status.accepted:
        raise HandoffError("Task must be prepared and AGENT_RUNNING, not accepted")
    preparation = store.get_preparation(task_id)
    baseline = store.get_baseline(task_id)
    runtime = store.get_openhands_runtime(task_id)
    claim = store.get_execution_claim(task_id)
    if preparation is None or baseline is None or runtime is None:
        raise HandoffError("Missing durable preparation, baseline or runtime identity")
    if claim is not None and claim.conversation_id != runtime.conversation_id:
        raise HandoffError("Dispatch and runtime conversation identities differ")
    try:
        UUID(runtime.conversation_id)
    except (ValueError, TypeError) as exc:
        raise HandoffError("Native conversation ID must be a UUID") from exc
    workspace = Path(preparation.workspace_path).resolve(strict=True)
    if not workspace.is_dir():
        raise HandoffError("Prepared repository workspace is missing")
    from openhands_shared.contracts import OpenHandsRuntimeStatus, ExecutionDispatchStatus
    # Provisioning occurs before any /run or execution claim. Previously the
    # legacy adapter had to fabricate a dispatched task merely to create the
    # native conversation. Never allow claim-without-context or recovery here.
    from openhands_shared.contracts import ExecutionStatus
    if claim is None:
        if (runtime.runtime_status not in (
                OpenHandsRuntimeStatus.CONVERSATION_READY,
                OpenHandsRuntimeStatus.CONTEXT_ATTACHED,
            )
                or runtime.execution_status is not ExecutionStatus.NOT_STARTED
                or status.execution_status is not ExecutionStatus.NOT_STARTED):
            raise HandoffError("Pre-execution provisioning requires an unstarted conversation")
        # Re-reading a real, already-attached idle conversation is legitimate.
        # However, do not accept a synthetic CONTEXT_ATTACHED state with no
        # durable native message evidence. No execution claim is created here.
        if runtime.runtime_status is OpenHandsRuntimeStatus.CONTEXT_ATTACHED and (
                runtime.last_native_event_order < 1
                or not runtime.last_native_event_id):
            raise HandoffError("Attached native context lacks durable event evidence")
    elif (runtime.runtime_status is not OpenHandsRuntimeStatus.CONTEXT_ATTACHED
          or claim.dispatch_status not in (
              ExecutionDispatchStatus.DISPATCHED, ExecutionDispatchStatus.RECOVERY_REQUIRED
          )):
        raise HandoffError("Existing execution claim is not consistent with native context")
    db, config = load_stop_hook_config(hook_config.resolve(strict=True))
    if db != store.database_path.resolve():
        raise HandoffError("Stop Hook database differs from authoritative task store")
    request = store.get_request(task_id)
    config.profile_for(request)
    # Native hook subprocess may start inside the disposable task worktree,
    # not the control repository. Set the import root explicitly.
    bootstrap = "import sys,runpy;sys.path.insert(0," + repr(str(ROOT)) + ");runpy.run_module('openhands_shared.stop_hook',run_name='__main__')"
    executable = [sys.executable, "-c", bootstrap,
                  "--config", str(hook_config.resolve()),
                  "--task-id", task_id, "--workspace", str(workspace)]
    llm: dict[str, Any] = {"model": model, "usage_id": "native-remediation", "stream": False}
    if base_url is not None:
        if not base_url.startswith("http://127.0.0.1:") and not base_url.startswith("http://localhost:"):
            raise HandoffError("Custom base_url must be a local test endpoint")
        llm["base_url"] = base_url
        llm["api_mode"] = "chat"
    if api_key is not None:
        llm["api_key"] = api_key
    # OpenHands 1.55.1 AgentBase defaults tools to an empty list.
    # Use the native CLI default coding-tool names, not a second tool harness.
    # The upstream 1.55.1 preset selects Terminal, FileEditor, TaskTracker
    # (browser disabled in CLI mode); built-in Finish/Think remain SDK defaults.
    coding_tools = [
        {"name": "terminal", "params": {}},
        {"name": "file_editor", "params": {}},
        {"name": "task_tracker", "params": {}},
    ]
    return {
        "conversation_id": runtime.conversation_id,
        "workspace": {"working_dir": str(workspace)},
        "worktree": False,
        "autotitle": False,
        "max_iterations": max_iterations,
        "agent": {"kind": "Agent", "llm": llm, "tools": coding_tools,
                  "system_prompt_kwargs": {"cli_mode": True}},
        "hook_config": {"stop": [{
            "matcher": "*", "hooks": [{
                "type": "command", "command": shlex.join(executable), "timeout": 3600
            }]
        }]},
        "tags": {"taskid": task_id, "purpose": "independent-remediation"},
    }


def validate_native_response(payload: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    """Verify native persistence before any conversation is executed."""
    uid = str(payload.get("id", payload.get("conversation_id", "")))
    if uid != request["conversation_id"]:
        raise HandoffError("Native conversation ID differs from durable task identity")
    if payload.get("execution_status") != "idle":
        raise HandoffError("Native conversation is not idle; refusing automatic execution")
    # Compare parsed fields, not serialized JSON: command quoting is escaped
    # by json.dumps(), so substring searching rejects valid native responses.
    expected_hook = request["hook_config"]["stop"][0]["hooks"][0]
    config = payload.get("hook_config")
    try:
        entries = config["stop"]
        actual_hooks = [hook for group in entries for hook in group["hooks"]]
    except (TypeError, KeyError):
        raise HandoffError("Native response omitted the configured independent Stop Hook") from None
    if not any(
        isinstance(hook, Mapping)
        and hook.get("type") == expected_hook["type"]
        and hook.get("command") == expected_hook["command"]
        and hook.get("timeout") == expected_hook["timeout"]
        for hook in actual_hooks
    ):
        raise HandoffError("Native response omitted the configured independent Stop Hook")
    workspace = payload.get("workspace")
    if not isinstance(workspace, Mapping) or workspace.get("working_dir") != request["workspace"]["working_dir"]:
        raise HandoffError("Native workspace differs from validated task workspace")
    return uid



def render_task_objective(store: SQLiteTaskStore, task_id: str) -> str:
    """Ground real native initial message in the registered immutable task.

    Do not include the preverified fixed candidate or host/model credentials.
    """
    task = store.get_request(task_id)
    if not task.objective.strip():
        raise HandoffError("Registered remediation objective is empty")
    checks = ", ".join(task.acceptance.build_commands)
    severities = ", ".join(task.acceptance.severity_scope)
    return (
        "Remediation objective: " + task.objective + "\n"
        "Mandatory build commands: " + checks + "\n"
        "Scanner severity scope: " + severities + "\n"
        "Constraints: keep Java version unchanged; no finding suppressions; "
        "respect task policy and independent deterministic validation.\n"
        "Investigate credible strategies before editing. Do not assume any "
        "candidate version is safe without evidence."
    )


def create_idle_native_conversation(
    request: Mapping[str, Any],
    http: Callable[..., Mapping[str, Any]],
    *,
    initial_message: str | None = None,
) -> str:
    """Create native conversation and verify persisted config; NEVER call /run.

    The native API is authoritative for conversation state. Reject any server
    response that differs from the task's workspace, identity or stop hook.
    A failed post-creation check is a blocker, not authorization to execute.
    """
    # Real remediation must provide the durable task's objective. Legacy POC
    # callers may omit it for synthetic lifecycle tests; no model runs here.
    if str(request.get("agent", {}).get("llm", {}).get("model", "")).startswith("vertex_ai/") and initial_message is None:
        raise HandoffError("Real Vertex task requires explicit registered objective before native creation")
    if initial_message is not None:
        if not isinstance(initial_message, str) or not initial_message.strip():
            raise HandoffError("Initial task objective must be nonempty")
        if len(initial_message) > 20000:
            raise HandoffError("Initial task objective exceeds bound")
    uid = str(request["conversation_id"])
    created = http("POST", "/api/conversations?include_skills=true", dict(request), timeout=90)
    if str(created.get("id", created.get("conversation_id", ""))) != uid:
        raise HandoffError("Created native conversation does not match task identity")
    # Server 1.55.1 exposes the effective hook_config after an initial user
    # event is attached. run=False is essential: never start the model here.
    http("POST", f"/api/conversations/{uid}/events", {
        "role": "user",
        "content": [{"type": "text", "text": initial_message if initial_message is not None else (
            "Review this task in the prepared workspace. Independent Stop Hook "
            "validation is mandatory before completion."
        )}],
        "run": False,
    })
    persisted = http("GET", f"/api/conversations/{uid}?include_skills=true")
    return validate_native_response(persisted, request)



def dispatch_native_once(
    store: SQLiteTaskStore,
    task_id: str,
    *,
    worker_id: str,
    request: Mapping[str, Any],
    http: Callable[..., Mapping[str, Any]],
) -> str:
    """Guard native /run with one durable claim and fail-closed reconciliation.

    Before first dispatch, verify the native idle conversation, exact workspace
    and actual Stop Hook. On ambiguous transport failure, /run is NEVER retried.
    A persisted dispatch claim means native execution, not security acceptance.
    """
    from openhands_shared.contracts import ExecutionDispatchStatus, OpenHandsRuntimeStatus
    runtime = store.get_openhands_runtime(task_id)
    if (runtime is None or runtime.runtime_status is not OpenHandsRuntimeStatus.CONTEXT_ATTACHED
            or runtime.conversation_id != request["conversation_id"]):
        raise HandoffError("Native dispatch requires bound context-attached task identity")
    claim = store.get_execution_claim(task_id)
    if claim is not None:
        if claim.worker_id != worker_id or claim.conversation_id != runtime.conversation_id:
            raise HandoffError("Native dispatch already belongs to another identity")
        if claim.dispatch_status is ExecutionDispatchStatus.DISPATCHED:
            return "ALREADY_DISPATCHED"
        if claim.dispatch_status is ExecutionDispatchStatus.RECOVERY_REQUIRED:
            raise HandoffError("Native dispatch requires explicit recovery; automatic retry disabled")
        # An intent may have reached the server even if its response was lost.
        # Never send /run again, regardless of what GET currently reports.
        try:
            status = http("GET", f"/api/conversations/{runtime.conversation_id}").get("execution_status")
        except Exception:
            status = None
        if status in {"running", "finished"}:
            store.update_execution_dispatch(task_id, dispatched=True)
            return "RECONCILED_DISPATCHED"
        store.update_execution_dispatch(
            task_id, dispatched=False, recovery_code="NATIVE_INTENT_UNCERTAIN"
        )
        raise HandoffError("Native dispatch intent cannot safely be replayed")

    persisted = http("GET", f"/api/conversations/{runtime.conversation_id}?include_skills=true")
    validate_native_response(persisted, request)
    if store.get_status(task_id).accepted:
        raise HandoffError("Accepted task must not be re-executed")
    store.claim_execution(task_id, worker_id)
    try:
        http("POST", f"/api/conversations/{runtime.conversation_id}/run", {}, timeout=20)
    except Exception as exc:
        try:
            observed = http("GET", f"/api/conversations/{runtime.conversation_id}")
            status = observed.get("execution_status")
        except Exception:
            status = None
        if status in {"running", "finished"}:
            store.update_execution_dispatch(task_id, dispatched=True)
            return "RECONCILED_DISPATCHED"
        store.update_execution_dispatch(
            task_id, dispatched=False, recovery_code="NATIVE_RUN_RESPONSE_UNCERTAIN"
        )
        raise HandoffError("Native /run response uncertain; automatic redispatch disabled") from exc
    store.update_execution_dispatch(task_id, dispatched=True)
    return "DISPATCHED"


def show_safe_summary(request: Mapping[str, Any]) -> dict[str, Any]:
    """Never print/store LLM credentials from the full native request."""
    return {
        "conversationId": request["conversation_id"],
        "workspace": request["workspace"]["working_dir"],
        "stopHookConfigured": True,
        "model": request["agent"]["llm"]["model"],
        "maxIterations": request["max_iterations"],
        "nativeOwnsExecution": True,
        "independentValidationRequired": True,
        "llmExecutionStarted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--hook-config", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-iterations", type=int, default=20)
    args = parser.parse_args()
    store = SQLiteTaskStore(args.database.resolve())
    try:
        req = build_request(
            store, args.task_id, hook_config=args.hook_config,
            model=args.model, max_iterations=args.max_iterations
        )
        print(json.dumps(show_safe_summary(req), indent=2, sort_keys=True))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
