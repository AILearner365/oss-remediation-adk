#!/usr/bin/env python3
"""POC3: native 1.55.1 Stop Hook -> existing SharedValidationService.

A disposable test fixture supplies prepared task/baseline/identity records.
The validator runner deterministically inspects a local repair marker (not OSV).
No Maven, scanner, Vertex, delivery, or custom Task API network service.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import secrets
import sys
import time
import uuid

import openhands_native_poc as native
import openhands_native_hook_poc as previous

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.validation import SharedValidationService
from tests.integration.test_openhands_shared_validation import SharedValidationIntegrationTests, report

CASE_ID = "service-v1"
CASE_NAME = "validator-service"
ROOT = native.ROOT
STATE = ROOT / ("hook-poc3-" + CASE_ID)
REPORT = native.RESULT_DIR / ("native-validator-poc-1.55.1-" + CASE_ID + ".json")
MARKER = "DETERMINISTIC_VALIDATION_FAILED"
PORT = 12997


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ArtifactRunner:
    """Offline deterministic runner: strict marker check, no scanner claims.

    Reuses SharedValidationService classification, Git-state binding, attempt
    records, native response, and acceptance policy, but NOT its Maven/OSV runner.
    """

    def run(self, repository, request, profile, baseline_document, attempt, runtime_root):
        marker = Path(repository) / "poc3-repaired.txt"
        passed = marker.is_file() and marker.read_bytes() == b"POC3-REPAIRED\\n"
        result = report(passed=passed, remaining=0 if passed else 1)
        return result


def fixture_setup():
    """Reuse previously tested production service prerequisites, not an API shim."""
    fixture = SharedValidationIntegrationTests(methodName="test_pass_allows_and_accepts_only_independent_report")
    fixture.setUp()
    try:
        task_id, workspace, _adapter = fixture.ready_and_running("poc3-" + secrets.token_hex(4))
        runtime = fixture.fixture.store.get_openhands_runtime(task_id)
        data = {
            "taskId": task_id, "conversationId": runtime.conversation_id,
            "workspace": str(workspace), "database": str(fixture.fixture.database),
            "hookConfig": str(fixture.hook_config),
        }
        write_json(STATE / "prepared.json", data)
        # Keep prepared disposable artifacts available to the native hook
        # subprocess after this setup function exits.
        fixture.fixture.store.close()
        fixture.fixture.temp_dir._finalizer.detach()
        return data
    except Exception:
        fixture.tearDown()
        raise


def native_hook() -> int:
    """Deployment-owned native hook command calling existing shared validation."""
    sys.stdin.read()
    data = read_json(STATE / "prepared.json", {})
    if not data:
        # Native hooks are fall-open on infrastructure failure. Record absence;
        # no acceptance may be inferred from agent completion.
        print(json.dumps({"decision": "allow", "reason": "Validator fixture missing; acceptance NOT proven"}))
        return 0
    store = None
    try:
        db, config = load_stop_hook_config(Path(data["hookConfig"]))
        store = SQLiteTaskStore(db)
        response = SharedValidationService(store, config, runner=ArtifactRunner()).handle_stop(
            data["taskId"], workspace_argument=data["workspace"]
        )
        answer = response.to_native_dict()
        write_json(STATE / "last-hook.json", {"decision": answer["decision"], "reason": answer["reason"][:200]})
        print(json.dumps(answer))
        return response.exit_code
    except Exception as e:
        write_json(STATE / "hook-error.json", {"type": type(e).__name__})
        print(json.dumps({"decision": "allow", "reason": "Validator service unavailable; independent acceptance NOT proven"}))
        return 0
    finally:
        if store is not None:
            store.close()


def hook_command():
    import shlex
    return " ".join(shlex.quote(x) for x in (
        sys.executable, str(Path(__file__).resolve()), "hook"
    ))


def native_create(data):
    # The existing store has already recorded the conversation identity
    # against its preparation; do NOT invent a second identity.
    uid = data["conversationId"]
    req = {
        "conversation_id": uid, "workspace": {"working_dir": data["workspace"]},
        "worktree": False, "autotitle": False, "max_iterations": 6,
        "tags": {"smoke": "validator", "scenario": "remediation"},
        "agent": {"kind": "Agent", "llm": {
            "model": "openai/gpt-4o-mini", "api_key": "poc-local-only",
            "base_url": "http://127.0.0.1:" + str(PORT) + "/v1",
            "usage_id": "openhands-native-validator-poc3", "stream": False,
            "api_mode": "chat", "num_retries": 0}},
        "hook_config": {"stop": [{"matcher": "*", "hooks": [{
            "type": "command", "command": hook_command(), "timeout": 30
        }]}]},
    }
    got = native.http("POST", "/api/conversations?include_skills=true", req, timeout=90)
    if str(got.get("id", got.get("conversation_id"))) != uid:
        raise native.Failure("Native conversation ID diverged from validation store")
    native.http("POST", f"/api/conversations/{uid}/events", {
        "role": "user",
        "content": [{"type": "text", "text": "Use FinishTool to finish the local test task."}],
        "run": False,
    })
    actual = native.http("GET", f"/api/conversations/{uid}?include_skills=true")
    if hook_command() not in json.dumps(actual.get("hook_config")):
        raise native.Failure("Expected native hook was not attached")
    if actual.get("execution_status") != "idle":
        raise native.Failure("Conversation executed unexpectedly")
    return uid


def collect_events(uid):
    return native.http("GET", f"/api/conversations/{uid}/events/search?limit=100&sort_order=TIMESTAMP").get("items", [])


def execute():
    native.configure_server_version("1.55.1")
    native.wait_ready()
    native.wait_canvas_ready()
    if STATE.exists() and any(STATE.iterdir()):
        raise native.Failure("POC3 already attempted; preserve evidence and do not overwrite fixture")
    STATE.mkdir(parents=True)
    # Reuse the proven local OpenAI mock from POC2. It records whether
    # deterministic validation feedback reaches the next model request.
    from http.server import ThreadingHTTPServer
    import threading
    previous.STATE = STATE
    previous.MARKER = MARKER
    server = ThreadingHTTPServer(("127.0.0.1", PORT), previous.MockLLM)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    uid = None
    try:
        data = fixture_setup()
        uid = native_create(data)
        native.http("POST", f"/api/conversations/{uid}/run", {}, timeout=20)
        deadline = time.monotonic() + 120
        mutated = False
        while time.monotonic() < deadline:
            store = SQLiteTaskStore(Path(data["database"]))
            try:
                attempts = store.list_validation_attempts(data["taskId"])
            finally:
                store.close()
            if attempts and not mutated:
                # Controlled external fixture change, NOT an agent-generated
                # fix. Existing service independently checks the next state.
                Path(data["workspace"], "poc3-repaired.txt").write_bytes(b"POC3-REPAIRED\\n")
                mutated = True
            status = native.http("GET", f"/api/conversations/{uid}").get("execution_status")
            if status in ("finished", "error", "stuck", "paused", "waiting_for_confirmation"):
                break
            time.sleep(1)
        status = native.http("GET", f"/api/conversations/{uid}").get("execution_status")
        rows = collect_events(uid)
        hook_events = [x for x in rows if x.get("kind") == "HookExecutionEvent" and
                       str(x.get("hook_event_type", "")).lower() == "stop"]
        calls = read_json(STATE / "model-requests.json", []) or []
        store = SQLiteTaskStore(Path(data["database"]))
        try:
            attempts = store.list_validation_attempts(data["taskId"])
            accepted = store.get_status(data["taskId"]).accepted
            service = SharedValidationService(store, load_stop_hook_config(Path(data["hookConfig"]))[1],
                                              runner=ArtifactRunner())
            verified = service.verify_validated_state(data["taskId"]) if accepted else False
        finally:
            store.close()
        outcomes = [x.outcome.value for x in attempts]
        checks = {
            "existingValidatorCalledFromNativeHook": len(attempts) >= 2 and len(hook_events) >= 2,
            "firstIndependentOutcomeFail": bool(outcomes) and outcomes[0] != "PASS",
            "nativeDenialObserved": any(x.get("blocked") is True and x.get("exit_code") == 2 for x in hook_events),
            "feedbackSeenByModel": any(x.get("feedbackSeen") for x in calls[1:]),
            "laterIndependentOutcomePass": bool(outcomes) and outcomes[-1] == "PASS",
            "nativeAllowObserved": any(x.get("blocked") is False and x.get("exit_code") == 0 for x in hook_events),
            "acceptedByExistingService": accepted and verified,
            "nativeFinished": status == "finished",
        }
        result = {
            "canvasVersion": native.CANVAS, "serverVersion": native.SERVER,
            "conversationId": uid, "executionStatus": status,
            "validationAttemptCount": len(attempts), "validationOutcomes": outcomes,
            "nativeStopHookEvents": len(hook_events),
            "nativeBlockedDecisions": sum(x.get("blocked") is True for x in hook_events),
            "modelRequestCount": len(calls), "fixtureRepairByCoordinator": mutated,
            "checks": checks,
            "notProven": ["Real Maven/OSV scanner execution", "Agent-produced repository fix",
                          "Tamper-resistant production validator isolation", "Final GitHub delivery"],
            "verdict": "PASS" if all(checks.values()) else "NOT_PROVEN",
        }
        write_json(REPORT, result)
        print("[validator-poc] " + result["verdict"] + "; report: " + str(REPORT))
        return result
    finally:
        if uid:
            try:
                if native.http("GET", f"/api/conversations/{uid}").get("execution_status") == "running":
                    native.http("POST", f"/api/conversations/{uid}/interrupt", {}, timeout=10)
            except Exception:
                pass
        server.shutdown()
        server.server_close()


def publish():
    if not REPORT.is_file():
        raise native.Failure("No POC3 report to publish")
    data = read_json(REPORT, {})
    if data.get("serverVersion") != "1.55.1":
        raise native.Failure("POC3 report version is invalid")
    if native.command(["git", "-C", str(REPO), "branch", "--show-current"]) != "openhands-service-integration":
        raise native.Failure("Wrong git branch")
    if "AILearner365/oss-remediation-adk" not in native.command(["git", "-C", str(REPO), "remote", "get-url", "origin"]):
        raise native.Failure("Wrong git origin")
    if native.command(["git", "-C", str(REPO), "diff", "--cached", "--name-only"]):
        raise native.Failure("Existing staging area is not empty")
    destination = REPO / "docs/experiments/openhands/evidence" / (
        time.strftime("native-validator-%Y%m%dT%H%M%SZ", time.gmtime())
        + "-" + secrets.token_hex(3) + ".json")
    keys = ("canvasVersion", "serverVersion", "conversationId", "executionStatus",
            "validationAttemptCount", "validationOutcomes", "nativeStopHookEvents",
            "nativeBlockedDecisions", "modelRequestCount", "fixtureRepairByCoordinator",
            "checks", "notProven", "verdict")
    write_json(destination, {k: data[k] for k in keys if k in data})
    relative = str(destination.relative_to(REPO))
    native.command(["git", "-C", str(REPO), "add", "--", relative])
    native.command(["git", "-C", str(REPO), "commit", "-m", "Record native validator service POC3 evidence", "--", relative])
    native.command(["git", "-C", str(REPO), "push", "origin", "HEAD:openhands-service-integration"])
    print("[validator-poc] Evidence pushed:", relative)


def main():
    global ROOT, STATE, REPORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "hook", "publish"))
    args = parser.parse_args()
    native.configure_server_version("1.55.1")
    ROOT = native.ROOT
    STATE = ROOT / ("hook-poc3-" + CASE_ID)
    REPORT = native.RESULT_DIR / ("native-validator-poc-1.55.1-" + CASE_ID + ".json")
    try:
        if args.action == "hook":
            return native_hook()
        if args.action == "publish":
            publish()
        else:
            if execute().get("verdict") != "PASS":
                return 1
        return 0
    except Exception as e:
        print("[validator-poc] ERROR", type(e).__name__, str(e)[:250], file=sys.stderr)
        if args.action == "run":
            write_json(REPORT, {"verdict": "ERROR", "errorType": type(e).__name__,
                                "serverVersion": "1.55.1"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
