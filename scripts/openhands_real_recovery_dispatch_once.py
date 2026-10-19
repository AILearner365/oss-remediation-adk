#!/usr/bin/env python3
"""One explicitly authorized native 1.55.1 dispatch of recovery attempt 2.

This command incurs potential Vertex AI charges. It never creates a new
conversation, restarts Canvas, or initiates a second /run. It records a durable
dispatch intent before the native POST, and fails closed on uncertainty.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import openhands_native_poc as native
import openhands_native_remediation as handoff
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.contracts import ExecutionStatus, OpenHandsRuntimeStatus, TaskStatus

TASK = "task_65edba181e354c6f85a000b48b879f9c"
CONVERSATION = "0bd0a45c-f8b0-49e1-a502-e413b9b40a03"
MODEL = "vertex_ai/gemini-2.5-flash"
DATABASE = Path("/tmp/openhands-real-durable-task-recovered-v1/state/tasks.sqlite3")
HOOK = Path("/tmp/openhands-real-durable-task-recovered-v1/stop-hook.json")
WORKER = "operator-approved-native-recovery-attempt-2"
ACK = "I_AUTHORIZE_ONE_BILLABLE_VERTEX_RUN"


def run(approval: str) -> dict:
    if approval != ACK:
        raise ValueError("Explicit one-run cost approval token required")
    native.configure_server_version("1.55.1")
    with SQLiteTaskStore(DATABASE) as store:
        task = store.get_request(TASK)
        status = store.get_status(TASK)
        runtime = store.get_openhands_runtime(TASK)
        if (runtime is None or runtime.conversation_id != CONVERSATION
                or runtime.native_model != MODEL
                or runtime.runtime_status is not OpenHandsRuntimeStatus.CONTEXT_ATTACHED
                or runtime.execution_status is not ExecutionStatus.NOT_STARTED
                or status.execution_status is not ExecutionStatus.NOT_STARTED
                or status.status is not TaskStatus.AGENT_RUNNING or status.accepted
                or store.get_execution_claim(TASK) is not None):
            raise ValueError("Approved task/conversation is not idle and unclaimed")
        if task.agent.max_iterations != 12 or task.agent.max_validation_denials != 2:
            raise ValueError("Task's immutable execution/validation limits differ from approval")
        request = handoff.build_request(
            store, TASK, hook_config=HOOK, model=MODEL, max_iterations=12
        )
        info = native.http("GET", "/server_info")
        if any(info.get(key) != "1.55.1" for key in ("version","sdk_version","tools_version")):
            raise ValueError("Native pinned versions have changed")
        persisted = native.http("GET", f"/api/conversations/{CONVERSATION}?include_skills=true")
        handoff.validate_native_response(persisted, request)
        if persisted.get("max_iterations") != 12:
            raise ValueError("Persisted native max_iterations is not 12")
        if persisted.get("agent", {}).get("llm", {}).get("model") != MODEL:
            raise ValueError("Persisted native model differs from authorization")
        # The caller is responsible for checking exact Vertex project/location
        # in the running processes and understanding no hard dollar cap exists.
        result = handoff.dispatch_native_once(
            store, TASK, worker_id=WORKER, request=request, http=native.http
        )
        claim = store.get_execution_claim(TASK)
        return {
            "status": result,
            "taskId": TASK,
            "conversationId": CONVERSATION,
            "nativeRunRequested": result == "DISPATCHED",
            "executionClaim": claim.dispatch_status.value if claim else None,
            "executionIsNotAcceptance": True,
            "independentStopHookRequired": True,
            "autoPR": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-billable-run", required=True)
    args = parser.parse_args()
    try:
        result = run(args.approve_billable_run)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:220],
                  "doNotRetry": True}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] == "DISPATCHED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
