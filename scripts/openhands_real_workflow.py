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
        else:
            result = preserve(args.task_id, args.hook_config, args.destination)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:220],
                  "doNotRetryWithoutInspection": True, "nativeRunCalled": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"IDLE_ATTACHED_NOT_AUTHORIZED", "EVIDENCE_PRESERVED", "FINALIZED_VERIFIED_ACCEPTED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
