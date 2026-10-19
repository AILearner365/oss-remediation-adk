#!/usr/bin/env python3
"""Read-only authoritative audit of a completed OpenHands remediation attempt.

Checks durable PASS, immutable report checksum, validated repository tree and
native final state. Writes a small sanitized JSON summary atomically to a
distinct local file; never executes Maven, OSV, /run or a model.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import openhands_native_poc as native
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.validation import SharedValidationService
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.contracts import ValidationAttemptState, ValidationOutcome

TASK = "task_65edba181e354c6f85a000b48b879f9c"
HOOK = Path("/tmp/openhands-real-durable-task-recovered-v1/stop-hook.json")


def audit(task_id: str, hook: Path, *, check_native: bool = True) -> dict:
    db, config = load_stop_hook_config(hook.resolve(strict=True))
    with SQLiteTaskStore(db) as store:
        status = store.get_status(task_id)
        runtime = store.get_openhands_runtime(task_id)
        claim = store.get_execution_claim(task_id)
        attempts = store.list_validation_attempts(task_id)
        completed = [a for a in attempts if a.state is ValidationAttemptState.COMPLETED]
        if not completed:
            raise ValueError("No completed independent validation attempt")
        attempt = completed[-1]
        artifacts = {a.artifact_id: a for a in store.list_artifacts(task_id)}
        report = artifacts.get(attempt.report_artifact_id)
        if report is None or report.sha256 != attempt.report_sha256:
            raise ValueError("Validation report metadata mismatch")
        target = config.artifact_root / report.relative_path
        if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(config.artifact_root.resolve()):
            raise ValueError("Validation report path is unsafe or unavailable")
        data = target.read_bytes()
        if len(data) != report.size_bytes or hashlib.sha256(data).hexdigest() != report.sha256:
            raise ValueError("Validation report checksum mismatch")
        envelope = json.loads(data)
        if envelope.get("taskId") != task_id or envelope.get("attempt") != attempt.attempt:
            raise ValueError("Validation report identity mismatch")
        if envelope.get("outcome") != attempt.outcome.value:
            raise ValueError("Validation report verdict mismatch")
        if runtime is None or claim is None or runtime.conversation_id != claim.conversation_id:
            raise ValueError("Native execution association is incomplete")
        validated = SharedValidationService(store, config).verify_validated_state(task_id, attempt.attempt)
        passed = (attempt.outcome is ValidationOutcome.PASS and
                  status.validation_status.value == "PASSED" and
                  status.status.value == "ACCEPTED" and status.accepted and validated)
        if not passed:
            raise ValueError("Independent PASS, durable acceptance or validated tree not established")
        summary = {
            "status": "VERIFIED_ACCEPTED",
            "taskId": task_id,
            "conversationId": runtime.conversation_id,
            "validationAttempt": attempt.attempt,
            "validationOutcome": attempt.outcome.value,
            "durableTaskStatus": status.status.value,
            "validatedTree": attempt.validated_tree,
            "validationReportSha256": attempt.report_sha256,
            "validationReportPath": str(target),
            "repositoryTreeMatches": validated,
            "originalFindingCount": attempt.original_finding_count,
            "resolvedFindingCount": attempt.resolved_finding_count,
            "remainingFindingCount": attempt.remaining_finding_count,
            "unknownFindingCount": attempt.unknown_finding_count,
            "newProhibitedFindingCount": attempt.new_prohibited_finding_count,
            "nativeStatus": "NOT_CHECKED",
        }
    if check_native:
        native.configure_server_version("1.55.1")
        actual = native.http("GET", f"/api/conversations/{summary['conversationId']}")
        summary["nativeStatus"] = actual.get("execution_status", "UNKNOWN")
        if summary["nativeStatus"] != "finished":
            raise ValueError("Native execution is not finished")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", default=TASK)
    parser.add_argument("--hook-config", type=Path, default=HOOK)
    parser.add_argument("--output", type=Path, default=Path.home() / "openhands-native-poc-reports" / "recovery-accepted-audit.json")
    parser.add_argument("--skip-native-check", action="store_true")
    args = parser.parse_args()
    try:
        result = audit(args.task_id, args.hook_config, check_native=not args.skip_native_check)
        destination = args.output.expanduser().resolve()
        if destination.exists():
            raise ValueError("Audit output already exists; refusing overwrite")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
        result["auditSummary"] = str(destination)
    except Exception as exc:
        result = {"status": "NOT_VERIFIED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:200], "noModelRun": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "VERIFIED_ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
