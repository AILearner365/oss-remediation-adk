#!/usr/bin/env python3
"""POC4 restart recovery: real native hooks, one interrupted durable attempt.

Start: native Stop Hook reserves validation attempt then exits 37 without report.
After caller restarts the Agent Server, recover SAME conversation/task via a
second native completion. Existing service reconciles without running validator.
All artifacts are disposable. No Maven/OSV/Vertex/delivery.
"""
from __future__ import annotations
import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import threading
import time
import uuid

import openhands_native_poc as native
import openhands_native_hook_poc as mock
import openhands_native_validator_poc as bridge
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.validation import SharedValidationService

CASE = "restart-v1"
STATE = None
REPORT = None
REPO = Path(__file__).resolve().parents[1]
PORT = 12997


def configure():
    global STATE, REPORT
    native.configure_server_version("1.55.1")
    STATE = native.ROOT / ("hook-poc4-recovery-" + CASE)
    REPORT = native.RESULT_DIR / ("native-recovery-poc4-" + CASE + ".json")


class NeverRunValidator:
    def run(self, repository, request, profile, baseline_document, attempt, runtime_root):
        marker = STATE / "validator-invoked.json"
        bridge.write_json(marker, {"unexpected": True})
        raise AssertionError("Interrupted attempt MUST NOT rerun validation")


def hook():
    sys.stdin.read()
    data = bridge.read_json(STATE / "prepared.json", {})
    if not data:
        print(json.dumps({"decision": "allow", "reason": "No prepared task; NOT ACCEPTED"}))
        return 0
    store = SQLiteTaskStore(Path(data["database"]))
    try:
        attempts = store.list_validation_attempts(data["taskId"])
        if not attempts:
            # Durably begin validation, then simulate hook worker crash before
            # writing any report. This is NOT an actual OS-level kill.
            record = store.begin_validation(data["taskId"])
            bridge.write_json(STATE / "interrupted.json",
                              {"attempt": record.attempt, "conversationId": record.conversation_id})
            raise SystemExit(37)
        db, config = load_stop_hook_config(Path(data["hookConfig"]))
        response = SharedValidationService(
            store, config, runner=NeverRunValidator()
        ).handle_stop(data["taskId"], workspace_argument=data["workspace"])
        print(json.dumps(response.to_native_dict()))
        return response.exit_code
    except SystemExit:
        raise
    except Exception as exc:
        bridge.write_json(STATE / "hook-error.json", {"errorType": type(exc).__name__})
        print(json.dumps({"decision": "allow", "reason": "Recovery not accepted"}))
        return 0
    finally:
        store.close()


def command():
    import shlex
    return " ".join(shlex.quote(x) for x in (
        sys.executable, str(Path(__file__).resolve()), "hook"
    ))


def start_mock():
    mock.STATE = STATE
    mock.MARKER = "DETERMINISTIC_VALIDATION_FAILED"
    server = ThreadingHTTPServer(("127.0.0.1", PORT), mock.MockLLM)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def status_snapshot(data):
    store = SQLiteTaskStore(Path(data["database"]))
    try:
        attempts = store.list_validation_attempts(data["taskId"])
        snapshot = store.get_status(data["taskId"])
        return {
            "accepted": snapshot.accepted,
            "taskStatus": snapshot.status.value,
            "attempts": [{"number": x.attempt, "state": x.state.value,
                          "outcome": x.outcome.value if x.outcome else None,
                          "conversationId": x.conversation_id} for x in attempts],
        }
    finally:
        store.close()


def wait_end(uid):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        value = native.http("GET", f"/api/conversations/{uid}")
        status = value.get("execution_status")
        if status in ("finished", "error", "stuck", "paused", "waiting_for_confirmation"):
            return status
        time.sleep(1)
    raise native.Failure("Native conversation did not reach terminal status in 120s")


def start():
    native.wait_ready()
    native.wait_canvas_ready()
    if STATE.exists() and any(STATE.iterdir()):
        raise native.Failure("Existing recovery fixture; refusing to overwrite")
    STATE.mkdir(parents=True)
    bridge.STATE = STATE
    data = bridge.fixture_setup()
    server = start_mock()
    try:
        original = bridge.hook_command
        bridge.hook_command = command
        try:
            uid = bridge.native_create(data)
        finally:
            bridge.hook_command = original
        native.http("POST", f"/api/conversations/{uid}/run", {}, timeout=20)
        execution = wait_end(uid)
        rows = bridge.collect_events(uid)
        hooks = [e for e in rows if e.get("kind") == "HookExecutionEvent"
                 and str(e.get("hook_event_type", "")).lower() == "stop"]
        snapshot = status_snapshot(data)
        checks = {
            "interruptedAttemptRecorded": len(snapshot["attempts"]) == 1
            and snapshot["attempts"][0]["state"] == "RUNNING",
            "notAccepted": snapshot["accepted"] is False,
            "noImmutableReport": not (
                Path(data["database"]).parents[1] / "artifacts" / data["taskId"]
                / "validation" / "attempt-1" / "report.json"
            ).exists(),
            "nativeHookCrashed": any(e.get("exit_code") == 37 for e in hooks),
            "nativeFinished": execution == "finished",
        }
        result = {
            "case": CASE, "stage": "interrupted", "serverVersion": native.SERVER,
            "conversationId": uid, "executionStatus": execution,
            "snapshot": snapshot, "nativeStopEvents": len(hooks),
            "checks": checks, "verdict": "PASS" if all(checks.values()) else "NOT_PROVEN",
        }
        bridge.write_json(STATE / "start-report.json", result)
        print("[recovery-poc] start:", result["verdict"], "snapshot:", STATE / "start-report.json")
        return result
    finally:
        server.shutdown()
        server.server_close()


def recover():
    native.wait_ready()
    native.wait_canvas_ready()
    data = bridge.read_json(STATE / "prepared.json", {})
    before = bridge.read_json(STATE / "start-report.json", {})
    if not data or before.get("verdict") != "PASS":
        raise native.Failure("Start stage not proven; do not attempt recovery")
    if (STATE / "recovery-attempted.json").exists():
        raise native.Failure("Recovery already attempted; preserve evidence")
    uid = data["conversationId"]
    if before.get("conversationId") != uid:
        raise native.Failure("Conversation identity changed")
    bridge.write_json(STATE / "recovery-attempted.json", {"conversationId": uid})
    server = start_mock()
    try:
        # Native conversation is persisted across server restart. Reuse it:
        # submit a second explicit user message and run, without new workspace
        # or an invented second conversation.
        native.http("POST", f"/api/conversations/{uid}/events", {
            "role": "user", "content": [{
                "type": "text", "text": "Retry finishing the interrupted validation task."
            }], "run": False
        })
        native.http("POST", f"/api/conversations/{uid}/run", {}, timeout=20)
        execution = wait_end(uid)
        rows = bridge.collect_events(uid)
        hooks = [e for e in rows if e.get("kind") == "HookExecutionEvent"
                 and str(e.get("hook_event_type", "")).lower() == "stop"]
        snapshot = status_snapshot(data)
        attempts = snapshot["attempts"]
        checks = {
            "sameNativeConversation": before["conversationId"] == uid,
            "interruptedAttemptPreserved": len(attempts) >= 2 and
                attempts[0]["state"] == "RUNNING",
            "secondAttemptValidatorFailure": len(attempts) >= 2 and
                attempts[1]["outcome"] == "VALIDATOR_FAILURE",
            "validatorNotRerun": not (STATE / "validator-invoked.json").exists(),
            "neverAccepted": snapshot["accepted"] is False,
            "noPass": not any(x["outcome"] == "PASS" for x in attempts),
            "nativeRecoveryHookObserved": len(hooks) >= 2,
            "nativeFinished": execution == "finished",
        }
        result = {
            "case": CASE, "stage": "recovered",
            "serverVersion": native.SERVER, "conversationId": uid,
            "executionStatus": execution, "snapshot": snapshot,
            "nativeStopEvents": len(hooks),
            "checks": checks, "verdict": "PASS" if all(checks.values()) else "NOT_PROVEN",
            "notProven": ["Real OS kill", "Real Maven/OSV", "Delivery authorization"],
        }
        bridge.write_json(REPORT, result)
        print("[recovery-poc] recover:", result["verdict"], "report:", REPORT)
        return result
    finally:
        server.shutdown()
        server.server_close()


def publish():
    doc = bridge.read_json(REPORT, {})
    if doc.get("case") != CASE or doc.get("serverVersion") != "1.55.1":
        raise native.Failure("No verified recovery stage report")
    if native.command(["git", "-C", str(REPO), "branch", "--show-current"]) != "openhands-service-integration":
        raise native.Failure("Unexpected branch")
    if "AILearner365/oss-remediation-adk" not in native.command(
        ["git", "-C", str(REPO), "remote", "get-url", "origin"]
    ):
        raise native.Failure("Unexpected origin")
    if native.command(["git", "-C", str(REPO), "diff", "--cached", "--name-only"]):
        raise native.Failure("Index not empty")
    file = REPO / "docs/experiments/openhands/evidence" / (
        time.strftime("native-recovery-%Y%m%dT%H%M%SZ", time.gmtime())
        + "-" + secrets.token_hex(3) + ".json"
    )
    bridge.write_json(file, doc)
    relative = str(file.relative_to(REPO))
    native.command(["git", "-C", str(REPO), "add", "--", relative])
    native.command(["git", "-C", str(REPO), "commit", "-m", "Record native POC4 restart recovery evidence", "--", relative])
    native.command(["git", "-C", str(REPO), "push", "origin", "HEAD:openhands-service-integration"])
    print("[recovery-poc] Evidence pushed:", relative)


def main():
    configure()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "recover", "publish"))
    args = parser.parse_args()
    try:
        if args.action == "start":
            return 0 if start()["verdict"] == "PASS" else 1
        if args.action == "recover":
            return 0 if recover()["verdict"] == "PASS" else 1
        publish()
        return 0
    except Exception as exc:
        print("[recovery-poc] ERROR", type(exc).__name__, str(exc)[:220], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
