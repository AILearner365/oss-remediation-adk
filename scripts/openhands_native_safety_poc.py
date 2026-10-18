#!/usr/bin/env python3
"""POC4 native safety: no false acceptance on validator/hook failure.

Four isolated scenarios. Uses real SharedValidationService and its prepared
task fixture, native 1.55.1 HookExecutionEvents, and a local mock model.
No Maven/OSV, paid LLM, real repository delivery, or frozen Gate-2 changes.
"""
from __future__ import annotations
import argparse
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import secrets
import sys
import threading
import time

import openhands_native_poc as native
import openhands_native_hook_poc as mock
import openhands_native_validator_poc as bridge
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.validation import SharedValidationService, ValidationInfrastructureError

CASES = ("infrastructure", "malformed", "exhausted", "hook-crash")
CASE = "infrastructure"
STATE = None
REPORT = None
PORT = 12997
REPO = Path(__file__).resolve().parents[1]


def configure(case):
    global CASE, STATE, REPORT
    if case not in CASES:
        raise ValueError("Unknown test scenario")
    native.configure_server_version("1.55.1")
    CASE = case
    STATE = native.ROOT / ("hook-poc4-v1-" + case)
    REPORT = native.RESULT_DIR / ("native-safety-poc4-v1-" + case + ".json")


class FaultRunner:
    """Test only: inject explicitly classified validation failures."""
    def run(self, repository, request, profile, baseline_document, attempt, runtime_root):
        if CASE == "infrastructure":
            raise ValidationInfrastructureError("POC4 simulated scanner unavailable")
        if CASE == "malformed":
            return {"passed": True, "checks": []}
        if CASE == "exhausted":
            return bridge.report(passed=False, remaining=1)
        raise RuntimeError("FaultRunner should not run in hook-crash case")


def hook():
    sys.stdin.read()
    if CASE == "hook-crash":
        # Real subprocess failure, not a manufactured native event.
        raise SystemExit(37)
    data = bridge.read_json(STATE / "prepared.json", {})
    store = None
    try:
        db, config = load_stop_hook_config(Path(data["hookConfig"]))
        store = SQLiteTaskStore(db)
        response = SharedValidationService(store, config, runner=FaultRunner()).handle_stop(
            data["taskId"], workspace_argument=data["workspace"]
        )
        print(json.dumps(response.to_native_dict()))
        return response.exit_code
    except Exception:
        # Native hooks can fail open; acceptance must still remain false.
        print(json.dumps({"decision": "allow", "reason": "POC4 validator transport failed; NOT ACCEPTED"}))
        return 0
    finally:
        if store is not None:
            store.close()


def hook_command():
    import shlex
    return " ".join(shlex.quote(v) for v in (
        sys.executable, str(Path(__file__).resolve()), "hook", "--case", CASE
    ))


def execute():
    native.wait_ready()
    native.wait_canvas_ready()
    if STATE.exists() and any(STATE.iterdir()):
        raise native.Failure("POC4 fixture exists; previous evidence must not be overwritten")
    STATE.mkdir(parents=True)
    # Shared validation fixture creates a task with the real baseline/identity
    # records. Native conversation uses the exact existing task ID.
    bridge.STATE = STATE
    data = bridge.fixture_setup()
    mock.STATE = STATE
    mock.MARKER = "DETERMINISTIC_VALIDATION_FAILED"
    server = ThreadingHTTPServer(("127.0.0.1", PORT), mock.MockLLM)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    conversation = data["conversationId"]
    try:
        # POC3's request mapping, with the hook command switched to POC4.
        original = bridge.hook_command
        bridge.hook_command = hook_command
        try:
            bridge.native_create(data)
        finally:
            bridge.hook_command = original
        native.http("POST", f"/api/conversations/{conversation}/run", {}, timeout=20)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            status = native.http("GET", f"/api/conversations/{conversation}").get("execution_status")
            if status in ("finished", "error", "stuck", "paused", "waiting_for_confirmation"):
                break
            time.sleep(1)
        status = native.http("GET", f"/api/conversations/{conversation}").get("execution_status")
        events = bridge.collect_events(conversation)
        hook_events = [x for x in events if x.get("kind") == "HookExecutionEvent"
                       and str(x.get("hook_event_type", "")).lower() == "stop"]
        store = SQLiteTaskStore(Path(data["database"]))
        try:
            attempts = store.list_validation_attempts(data["taskId"])
            accepted = store.get_status(data["taskId"]).accepted
            outcomes = [x.outcome.value for x in attempts]
            states = [x.state.value for x in attempts]
        finally:
            store.close()
        calls = bridge.read_json(STATE / "model-requests.json", []) or []
        expected = {
            "infrastructure": "INFRASTRUCTURE_FAILURE",
            "malformed": "VALIDATOR_FAILURE",
            "exhausted": "REMEDIATION_FAILURE",
            "hook-crash": None,
        }[CASE]
        checks = {
            "nativeHookObserved": len(hook_events) >= 1,
            "noAcceptance": accepted is False,
            "noIndependentPass": "PASS" not in outcomes,
            "correctOutcome": (
                not attempts if expected is None
                else bool(attempts) and all(x == expected for x in outcomes)
            ),
            "nativeTerminal": status == "finished",
            "terminalAllowWithoutPass": any(
                x.get("blocked") is False for x in hook_events
            ),
        }
        if CASE == "exhausted":
            checks["denialBeforeTermination"] = (
                len(attempts) >= 2
                and any(x.get("blocked") is True for x in hook_events)
            )
        if CASE == "hook-crash":
            checks["failedNativeHook"] = any(
                x.get("success") is False or x.get("exit_code") not in (0, 2)
                for x in hook_events
            )
        result = {
            "serverVersion": native.SERVER, "canvasVersion": native.CANVAS,
            "case": CASE, "conversationId": conversation, "executionStatus": status,
            "nativeHookEvents": len(hook_events),
            "nativeHookOutcomes": [
                {"blocked": x.get("blocked"), "success": x.get("success"),
                 "exitCode": x.get("exit_code")} for x in hook_events
            ],
            "validationAttempts": len(attempts),
            "validationOutcomes": outcomes, "validationStates": states,
            "modelRequests": len(calls), "accepted": accepted, "checks": checks,
            "notProven": ["Real Maven/OSV infrastructure behavior",
                          "Network/OS-level process kill recovery",
                          "End-to-end restart recovery", "Delivery authorization"],
        }
        result["verdict"] = "PASS" if all(checks.values()) else "NOT_PROVEN"
        bridge.write_json(REPORT, result)
        print(f"[safety-poc] {CASE}: {result['verdict']} report: {REPORT}")
        return result
    finally:
        try:
            if native.http("GET", f"/api/conversations/{conversation}").get("execution_status") == "running":
                native.http("POST", f"/api/conversations/{conversation}/interrupt", {}, timeout=10)
        except Exception:
            pass
        server.shutdown()
        server.server_close()


def publish():
    if not REPORT.is_file():
        raise native.Failure("No result to publish")
    data = bridge.read_json(REPORT, {})
    if data.get("case") != CASE or data.get("serverVersion") != "1.55.1":
        raise native.Failure("Wrong or missing safety POC evidence")
    if native.command(["git", "-C", str(REPO), "branch", "--show-current"]) != "openhands-service-integration":
        raise native.Failure("Wrong Git branch")
    if "AILearner365/oss-remediation-adk" not in native.command(
        ["git", "-C", str(REPO), "remote", "get-url", "origin"]
    ):
        raise native.Failure("Unexpected Git origin")
    if native.command(["git", "-C", str(REPO), "diff", "--cached", "--name-only"]):
        raise native.Failure("Existing staging changes; refusing to publish")
    dest = REPO / "docs/experiments/openhands/evidence" / (
        time.strftime("native-safety-%Y%m%dT%H%M%SZ", time.gmtime())
        + "-" + secrets.token_hex(3) + ".json")
    bridge.write_json(dest, data)
    relative = str(dest.relative_to(REPO))
    native.command(["git", "-C", str(REPO), "add", "--", relative])
    native.command(["git", "-C", str(REPO), "commit", "-m", f"Record native POC4 {CASE} safety evidence", "--", relative])
    native.command(["git", "-C", str(REPO), "push", "origin", "HEAD:openhands-service-integration"])
    print("[safety-poc] Evidence pushed:", relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "hook", "publish"))
    parser.add_argument("--case", required=True, choices=CASES)
    args = parser.parse_args()
    configure(args.case)
    try:
        if args.action == "hook":
            return hook()
        if args.action == "publish":
            publish()
            return 0
        return 0 if execute()["verdict"] == "PASS" else 1
    except Exception as exc:
        print("[safety-poc] ERROR:", type(exc).__name__, str(exc)[:180], file=sys.stderr)
        if args.action == "run":
            bridge.write_json(REPORT, {"case": CASE, "serverVersion": "1.55.1",
                                       "verdict": "ERROR", "errorType": type(exc).__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
