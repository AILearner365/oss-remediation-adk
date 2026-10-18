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
    if preparation is None or baseline is None or runtime is None or claim is None:
        raise HandoffError("Missing durable preparation, baseline, runtime identity or dispatch claim")
    if claim.conversation_id != runtime.conversation_id:
        raise HandoffError("Dispatch and runtime conversation identities differ")
    try:
        UUID(runtime.conversation_id)
    except (ValueError, TypeError) as exc:
        raise HandoffError("Native conversation ID must be a UUID") from exc
    workspace = Path(preparation.workspace_path).resolve(strict=True)
    if not workspace.is_dir():
        raise HandoffError("Prepared repository workspace is missing")
    from openhands_shared.contracts import OpenHandsRuntimeStatus, ExecutionDispatchStatus
    if runtime.runtime_status is not OpenHandsRuntimeStatus.CONTEXT_ATTACHED:
        raise HandoffError("Native task context has not been attached")
    if claim.dispatch_status not in (
        ExecutionDispatchStatus.DISPATCHED, ExecutionDispatchStatus.RECOVERY_REQUIRED
    ):
        raise HandoffError("Native execution dispatch is not established")
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
    return {
        "conversation_id": runtime.conversation_id,
        "workspace": {"working_dir": str(workspace)},
        "worktree": False,
        "autotitle": False,
        "max_iterations": max_iterations,
        "agent": {"kind": "Agent", "llm": llm},
        "hook_config": {"stop": [{
            "matcher": "*", "hooks": [{
                "type": "command", "command": shlex.join(executable), "timeout": 3600
            }]
        }]},
        "tags": {"taskId": task_id, "purpose": "independent-remediation"},
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
