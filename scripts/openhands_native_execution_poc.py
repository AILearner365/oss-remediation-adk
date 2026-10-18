#!/usr/bin/env python3
"""Native-first live execution: durable dispatch + native Stop Hook + local mock.

Entirely synthetic validator runner: NO Maven, OSV, remote LLM, or delivery.
Agent uses OpenHands native loop. Test coordinator (NOT agent) applies repair
after verified DENY solely to establish retry feedback.
"""
from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shlex
import sys
import threading
import time

import openhands_native_poc as native
import openhands_native_hook_poc as mock
import openhands_native_idle_create_poc as setup
import openhands_native_remediation as bridge
from openhands_native_validator_poc import ArtifactRunner
from openhands_shared.contracts import OpenHandsEventLink, OpenHandsRuntimeStatus
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.validation import SharedValidationService

CASE = "native-execution-v1"
PORT = 12997
MARKER = "DETERMINISTIC_VALIDATION_FAILED"


def paths():
    native.configure_server_version("1.55.1")
    return native.ROOT / CASE, native.RESULT_DIR / (CASE + ".json")


def hook():
    sys.stdin.read()
    state, _ = paths()
    data = setup.fixture.read_json(state / "prepared.json", {})
    if not data:
        print(json.dumps({"decision": "allow", "reason": "Fixture missing: NOT ACCEPTED"}))
        return 0
    store = None
    try:
        db, config = load_stop_hook_config(Path(data["hookConfig"]))
        store = SQLiteTaskStore(db)
        result = SharedValidationService(store, config, runner=ArtifactRunner()).handle_stop(
            data["taskId"], workspace_argument=data["workspace"])
        answer = result.to_native_dict()
        setup.fixture.write_json(state / "last-hook.json", {
            "decision": answer["decision"], "attempts": len(store.list_validation_attempts(data["taskId"]))
        })
        print(json.dumps(answer))
        return result.exit_code
    except Exception as exc:
        setup.fixture.write_json(state / "hook-error.json", {"type": type(exc).__name__})
        print(json.dumps({"decision": "allow", "reason": "Synthetic validator unavailable: NOT ACCEPTED"}))
        return 0
    finally:
        if store is not None:
            store.close()


def execute():
    state, report = paths()
    native.wait_ready()
    native.wait_canvas_ready()
    if state.exists():
        raise native.Failure("Execution fixture already exists; refusing to overwrite evidence")
    state.mkdir(parents=True)
    data, now = setup.prepare_fixture(state)
    store = SQLiteTaskStore(Path(data["database"]))
    mock.STATE = state
    mock.MARKER = MARKER
    setup.fixture.write_json(state / "model-requests.json", [])
    server = ThreadingHTTPServer(("127.0.0.1", PORT), mock.MockLLM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    uid = data["conversationId"]
    calls_to_run = []
    try:
        request = bridge.build_request(
            store, data["taskId"], hook_config=Path(data["hookConfig"]),
            model="openai/gpt-4o-mini",
            base_url="http://127.0.0.1:12997/v1",
            api_key="synthetic-local-only", max_iterations=6)
        request["agent"]["llm"]["num_retries"] = 0
        request["hook_config"]["stop"][0]["hooks"][0]["command"] = shlex.join([
            sys.executable, str(Path(__file__).resolve()), "hook"])
        request["hook_config"]["stop"][0]["hooks"][0]["timeout"] = 30
        bridge.create_idle_native_conversation(request, native.http)
        page = native.http("GET", f"/api/conversations/{uid}/events/search?limit=100&sort_order=TIMESTAMP")
        messages = [x for x in page.get("items", []) if x.get("kind") == "MessageEvent" and x.get("id")]
        if len(messages) != 1:
            raise bridge.HandoffError("Native initialization must have exactly one initial message")
        store.link_openhands_event(OpenHandsEventLink(
            task_id=data["taskId"], conversation_id=uid,
            native_event_id=str(messages[0]["id"]), native_order=1,
            native_kind="MessageEvent", native_timestamp=None, observed_at=now,
        ), context_attached=True)

        repaired = [False]
        def repair_on_feedback(messages, calls):
            if MARKER not in json.dumps(messages):
                return
            if repaired[0]:
                return
            # The first validator outcome and native DENY must both be proven
            # before this coordinator writes the test-only marker.
            events = native.http("GET", f"/api/conversations/{uid}/events/search?limit=100&sort_order=TIMESTAMP").get("items", [])
            denied = any(x.get("kind") == "HookExecutionEvent" and
                         x.get("blocked") is True and x.get("exit_code") == 2 for x in events)
            attempts = store.list_validation_attempts(data["taskId"])
            if not denied or len(attempts) != 1 or attempts[0].outcome.value != "REMEDIATION_FAILURE":
                raise native.Failure("Coordinator repair attempted without verified failed validation and native DENY")
            (Path(data["workspace"]) / "poc3-repaired.txt").write_bytes(b"POC3-REPAIRED\n")
            repaired[0] = True
        server.on_model_request = repair_on_feedback

        def tracked_http(method, endpoint, payload=None, **kwargs):
            if method == "POST" and endpoint == f"/api/conversations/{uid}/run":
                calls_to_run.append(endpoint)
            if payload is None:
                return native.http(method, endpoint, **kwargs)
            return native.http(method, endpoint, payload, **kwargs)

        dispatch = bridge.dispatch_native_once(
            store, data["taskId"], worker_id="native-poc-worker",
            request=request, http=tracked_http)
        duplicate = bridge.dispatch_native_once(
            store, data["taskId"], worker_id="native-poc-worker",
            request=request, http=tracked_http)
        deadline = time.monotonic() + 125
        status = None
        while time.monotonic() < deadline:
            status = native.http("GET", f"/api/conversations/{uid}").get("execution_status")
            if status in ("finished", "error", "stuck", "paused", "waiting_for_confirmation"):
                break
            time.sleep(1)
        events = native.http("GET", f"/api/conversations/{uid}/events/search?limit=100&sort_order=TIMESTAMP").get("items", [])
        hooks = [x for x in events if x.get("kind") == "HookExecutionEvent" and
                 str(x.get("hook_event_type", "")).lower() == "stop"]
        attempts = store.list_validation_attempts(data["taskId"])
        outcomes = [x.outcome.value for x in attempts]
        calls = setup.fixture.read_json(state / "model-requests.json", []) or []
        accepted = store.get_status(data["taskId"]).accepted
        checks = {
            "firstDispatchRecorded": dispatch in ("DISPATCHED", "RECONCILED_DISPATCHED"),
            "secondDispatchNotRepeated": duplicate == "ALREADY_DISPATCHED" and len(calls_to_run) == 1,
            "nativeFirstDenial": len(hooks) >= 1 and hooks[0].get("blocked") is True,
            "firstDeterministicFailure": len(outcomes) >= 1 and outcomes[0] == "REMEDIATION_FAILURE",
            "feedbackSeenByMockModel": len(calls) >= 2 and any(c.get("feedbackSeen") for c in calls[1:]),
            "coordinatorRepairAfterDenial": repaired[0],
            "subsequentDeterministicPass": len(outcomes) >= 2 and outcomes[-1] == "PASS",
            "nativeFinished": status == "finished",
            "acceptedOnlyByValidator": accepted and outcomes[-1] == "PASS",
            "contextPersisted": store.get_openhands_runtime(data["taskId"]).runtime_status is OpenHandsRuntimeStatus.CONTEXT_ATTACHED,
        }
        result = {
            "case": CASE, "serverVersion": native.SERVER, "conversationId": uid,
            "nativeExecutionStatus": status, "dispatch": dispatch,
            "repeatDispatch": duplicate, "nativeRunPosts": len(calls_to_run),
            "validationOutcomes": outcomes, "nativeHookEvents": len(hooks),
            "mockModelRequests": len(calls), "checks": checks,
            "coordinatorAppliedSyntheticRepair": repaired[0],
            "notProven": ["Agent-made repository edit", "Real Maven/OSV", "Production isolation", "PR delivery"],
            "verdict": "PASS" if all(checks.values()) else "NOT_PROVEN",
        }
        setup.fixture.write_json(report, result)
        print("[native-execution] " + result["verdict"] + "; report: " + str(report))
        return 0 if result["verdict"] == "PASS" else 1
    finally:
        try:
            if native.http("GET", f"/api/conversations/{uid}").get("execution_status") == "running":
                native.http("POST", f"/api/conversations/{uid}/interrupt", {}, timeout=10)
        except Exception:
            pass
        server.shutdown()
        server.server_close()
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "hook"))
    args = parser.parse_args()
    try:
        return hook() if args.action == "hook" else execute()
    except Exception as exc:
        print("[native-execution] ERROR:", type(exc).__name__, str(exc)[:220], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
