#!/usr/bin/env python3
"""Finalize an already dispatched native task without another model invocation.

Native must be terminal first. Reuse any durable PASS. If no validation attempt
exists, invoke independent deterministic validation once. Reconcile terminal
status only after a completed PASS; otherwise stop for operator review.
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
from openhands_real_run_audit import TASK, HOOK, audit
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.validation import SharedValidationService
from openhands_shared.contracts import ValidationAttemptState, ValidationOutcome


def finalize(task_id: str, hook: Path) -> dict:
    db, config = load_stop_hook_config(hook.resolve(strict=True))
    native.configure_server_version("1.55.1")
    with SQLiteTaskStore(db) as store:
        runtime = store.get_openhands_runtime(task_id)
        claim = store.get_execution_claim(task_id)
        if runtime is None or claim is None or runtime.conversation_id != claim.conversation_id:
            raise ValueError("Task is not bound to a dispatched native conversation")
        native_state = native.http("GET", f"/api/conversations/{runtime.conversation_id}").get("execution_status")
        if native_state != "finished":
            raise ValueError("Native execution is not finished; do not finalize or retry")
        attempts = store.list_validation_attempts(task_id)
        if any(a.state is ValidationAttemptState.RUNNING for a in attempts):
            raise ValueError("Interrupted validation attempt requires operator inspection")
        completed = [a for a in attempts if a.state is ValidationAttemptState.COMPLETED]
        if completed:
            latest = completed[-1]
            if latest.outcome is not ValidationOutcome.PASS:
                raise ValueError("Existing validation is not PASS; refuse replay")
        else:
            prep = store.get_preparation(task_id)
            if prep is None:
                raise ValueError("Task has no prepared workspace")
            # Deliberately one call, never retry after uncertainty.
            SharedValidationService(store, config).handle_stop(
                task_id, workspace_argument=prep.workspace_path
            )
            completed = [a for a in store.list_validation_attempts(task_id)
                         if a.state is ValidationAttemptState.COMPLETED]
            if len(completed) != 1 or completed[0].outcome is not ValidationOutcome.PASS:
                raise ValueError("Independent validation did not establish PASS; inspect evidence")
        validator = SharedValidationService(store, config)
        if not validator.verify_validated_state(task_id, completed[-1].attempt):
            raise ValueError("Repository no longer matches validated tree")
        store.record_native_execution_terminal(task_id, completed=True)
    result = audit(task_id, hook, check_native=True)
    result["status"] = "FINALIZED_VERIFIED_ACCEPTED"
    result["noModelRun"] = True
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task-id", default=TASK)
    p.add_argument("--hook-config", type=Path, default=HOOK)
    args = p.parse_args()
    try:
        result = finalize(args.task_id, args.hook_config)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:220], "doNotRetryWithoutInspection": True,
                  "noModelRun": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "FINALIZED_VERIFIED_ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
