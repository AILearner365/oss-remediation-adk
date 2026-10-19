#!/usr/bin/env python3
"""Single entrypoint for safe OpenHands evidence/recovery lifecycle.

prepare-idle: create new durable recovery task and attach its native context.
preserve: audit accepted task, write private local SQLite backup/evidence.

Neither command dispatches /run or initiates Gemini. Billable execution
requires a separate task-bound dispatcher and separate explicit authorization.
On any partial failure, do not retry blindly: inspect durable state.
"""
from __future__ import annotations
import argparse
import json
import time
import openhands_native_poc as native
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openhands_shared.store import SQLiteTaskStore
from openhands_real_recovery_prepare import DATABASE, HOOK, ORIGINAL, prepare_recovery
from openhands_real_native_idle import attach_idle
from openhands_real_preserve_evidence import TASK, preserve
from openhands_real_finalize import finalize


def monitor_finalize(task_id: str, hook: Path, timeout_seconds: int, poll_seconds: int) -> dict:
    """Observe one existing native conversation; never dispatch or reset claims."""
    if timeout_seconds < 0 or poll_seconds < 1:
        raise ValueError("Invalid monitoring limits")
    from openhands_shared.stop_hook import load_stop_hook_config
    db, _ = load_stop_hook_config(hook.resolve(strict=True))
    with SQLiteTaskStore(db) as store:
        runtime = store.get_openhands_runtime(task_id)
        claim = store.get_execution_claim(task_id)
        if runtime is None or claim is None or claim.conversation_id != runtime.conversation_id:
            raise ValueError("Monitoring requires an existing claimed native execution")
        cid = runtime.conversation_id
    native.configure_server_version("1.55.1")
    deadline = time.monotonic() + timeout_seconds
    while True:
        state = native.http("GET", f"/api/conversations/{cid}").get("execution_status")
        if state == "finished":
            return finalize(task_id, hook)
        if state in {"error", "failed", "cancelled", "stopped"}:
            raise ValueError("Native run terminated without success; preserve evidence and inspect")
        if state not in {"running", "idle", "starting", "pending", "awaiting_input"}:
            raise ValueError("Unknown native execution state; operator inspection required")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"status": "MONITOR_TIMEOUT_NO_DISPATCH", "taskId": task_id,
                    "conversationId": cid, "nativeStatus": state, "nativeRunCalled": False}
        time.sleep(min(poll_seconds, remaining))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare-idle", help="prepare one new recovery task and attach native idle context")
    prepare.add_argument("--database", type=Path, default=DATABASE)
    prepare.add_argument("--hook-config", type=Path, default=HOOK)
    prepare.add_argument("--original-task", default=ORIGINAL)
    finish = commands.add_parser("finalize", help="verify native termination, independent PASS, and reconcile durable acceptance")
    finish.add_argument("--task-id", default=TASK)
    finish.add_argument("--hook-config", type=Path, default=HOOK)
    monitor = commands.add_parser("monitor-finalize", help="wait for existing native run then finalize once; no dispatch")
    monitor.add_argument("--task-id", default=TASK)
    monitor.add_argument("--hook-config", type=Path, default=HOOK)
    monitor.add_argument("--timeout-seconds", type=int, default=300)
    monitor.add_argument("--poll-seconds", type=int, default=10)
    archive = commands.add_parser("preserve", help="verify accepted task and archive evidence locally")
    archive.add_argument("--task-id", default=TASK)
    archive.add_argument("--hook-config", type=Path, default=HOOK)
    archive.add_argument("--destination", type=Path,
                         default=Path.home() / "openhands-native-poc-reports" / ("accepted-evidence-" + TASK))
    args = parser.parse_args()
    try:
        if args.command == "prepare-idle":
            with SQLiteTaskStore(args.database) as store:
                created = prepare_recovery(store, args.original_task, args.hook_config)
                # Failure after this point leaves durable state; never replay.
                idle = attach_idle(store, created["taskId"], args.hook_config)
                result = {"status": "IDLE_ATTACHED_NOT_AUTHORIZED",
                          "taskId": created["taskId"],
                          "conversationId": idle["conversationId"],
                          "baselineEvidenceReused": True, "nativeRunCalled": False}
        elif args.command == "finalize":
            result = finalize(args.task_id, args.hook_config)
        elif args.command == "monitor-finalize":
            result = monitor_finalize(args.task_id, args.hook_config, args.timeout_seconds, args.poll_seconds)
        else:
            result = preserve(args.task_id, args.hook_config, args.destination)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:220],
                  "doNotRetryWithoutInspection": True, "nativeRunCalled": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"IDLE_ATTACHED_NOT_AUTHORIZED", "EVIDENCE_PRESERVED", "FINALIZED_VERIFIED_ACCEPTED", "MONITOR_TIMEOUT_NO_DISPATCH"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
