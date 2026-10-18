#!/usr/bin/env python3
"""POC 2: exercise native Agent Server 1.55.1 Stop Hook with local mock LLM.

Run only after 'openhands_native_poc.py run --server-version 1.55.1'.
No Vertex/Maven/OSV calls. A dedicated conversation, not the idle smoke ones.
Synthetic validation is for integration testing only, NEVER security acceptance.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import uuid

import openhands_native_poc as native

MARKER = "POC2_VALIDATION_FAILED__RETRY_REQUIRED"
PORT = 12997
STATE = native.ROOT / "hook-poc2"
REPORT = native.RESULT_DIR / "native-hook-poc-1.55.1.json"


def json_file(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def hook_cli() -> int:
    """Real command executed by native Stop Hook. Validates fixture state only."""
    import sys as _sys
    _sys.stdin.read()  # native hook supplies JSON event on stdin
    verdict = json_file(STATE / "verdict.json", {})
    entries = json_file(STATE / "hooks.json", [])
    passed = verdict.get("accepted") is True
    entries.append({"accepted": passed, "index": len(entries) + 1})
    save(STATE / "hooks.json", entries)
    if passed:
        print(json.dumps({"decision": "allow", "reason": "Synthetic fixture passed"}))
        return 0
    print(json.dumps({"decision": "deny", "reason": MARKER,
                      "additionalContext": MARKER + ": fixture has not passed; retry finishing after fixture changes"}))
    return 2


class MockLLM(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 2_000_000:
                self.send_error(400)
                return
            incoming = json.loads(self.rfile.read(size))
            calls = json_file(STATE / "model-requests.json", [])
            messages = incoming.get("messages", [])
            reflected = MARKER in json.dumps(messages, ensure_ascii=True)
            tools = incoming.get("tools", [])
            tool_names = [t.get("function", {}).get("name") for t in tools if isinstance(t, dict)]
            finish = next((x for x in tool_names if x and "finish" in x.lower()), None)
            calls.append({"index": len(calls) + 1, "feedbackSeen": reflected,
                          "finishToolAdvertised": bool(finish)})
            save(STATE / "model-requests.json", calls)
            if not finish:
                # Do not pretend that arbitrary text is an SDK FinishTool call.
                self.send_error(422, "Native FinishTool not advertised")
                return
            reply = {
                "id": "chatcmpl-poc2-" + str(len(calls)),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": incoming.get("model", "gpt-4o-mini"),
                "choices": [{"index": 0, "finish_reason": "tool_calls",
                             "message": {"role": "assistant", "content": None,
                                         "tool_calls": [{"id": "call_" + str(len(calls)),
                                                         "type": "function",
                                                         "function": {"name": finish, "arguments":
                                                                      json.dumps({"message": "Fixture finish attempt " + str(len(calls))})}}]}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            }
            payload = json.dumps(reply).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            self.send_error(500)


def hook_command() -> str:
    import shlex
    return " ".join(shlex.quote(x) for x in
        [sys.executable, str(Path(__file__).resolve()), "hook",
         "--server-version", "1.55.1"])


def create() -> str:
    conv = str(uuid.uuid4())
    workspace = STATE / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Only synthetic integration fixture.\n", encoding="utf-8")
    # Distinct mock endpoint, no external LLM credentials.
    req = {
        "conversation_id": conv,
        "workspace": {"working_dir": str(workspace)},
        "worktree": False, "autotitle": False, "max_iterations": 6,
        "tags": {"smoke": "hook", "scenario": "remediation"},
        "agent": {"kind": "Agent", "llm": {
            "model": "openai/gpt-4o-mini", "api_key": "only-local-poc",
            "base_url": "http://127.0.0.1:" + str(PORT) + "/v1",
            "usage_id": "openhands-native-hook-poc2", "stream": False,
            "num_retries": 0}},
        "hook_config": {"stop": [{"matcher": "*", "hooks": [
            {"type": "command", "command": hook_command(), "timeout": 15}
        ]}]},
    }
    info = native.http("POST", "/api/conversations?include_skills=true", req, timeout=90)
    if str(info.get("id", info.get("conversation_id"))) != conv:
        raise native.Failure("Native conversation ID mismatch")
    native.http("POST", f"/api/conversations/{conv}/events", {
        "role": "user",
        "content": [{"type": "text", "text": "Use FinishTool to finish this synthetic integration task."}],
        "run": False})
    actual = native.http("GET", f"/api/conversations/{conv}?include_skills=true")
    hooks = actual.get("hook_config") or {}
    if hook_command() not in json.dumps(hooks):
        raise native.Failure("Effective native Stop Hook missing")
    if actual.get("execution_status") != "idle":
        raise native.Failure("Conversation unexpectedly ran")
    return conv


def event_rows(conv: str):
    payload = native.http("GET", f"/api/conversations/{conv}/events/search?limit=100&sort_order=TIMESTAMP")
    return payload.get("items", [])


def execute() -> dict:
    native.configure_server_version("1.55.1")
    global STATE, REPORT
    STATE = native.ROOT / "hook-poc2"
    REPORT = native.RESULT_DIR / "native-hook-poc-1.55.1.json"
    native.wait_ready()
    native.wait_canvas_ready()
    if STATE.exists() and any(STATE.iterdir()):
        raise native.Failure("POC2 fixture already exists; refusing to overwrite evidence; use a fresh OH_POC_TMP")
    STATE.mkdir(parents=True)
    save(STATE / "verdict.json", {"accepted": False})
    save(STATE / "hooks.json", [])
    save(STATE / "model-requests.json", [])
    server = ThreadingHTTPServer(("127.0.0.1", PORT), MockLLM)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    conv = None
    try:
        conv = create()
        native.http("POST", f"/api/conversations/{conv}/run", {}, timeout=30)
        deadline = time.monotonic() + 100
        transitioned = False
        while time.monotonic() < deadline:
            rows = event_rows(conv)
            hooks = json_file(STATE / "hooks.json", [])
            if len(hooks) >= 1 and hooks[0].get("accepted") is False and not transitioned:
                save(STATE / "verdict.json", {"accepted": True})
                transitioned = True
            status = native.http("GET", f"/api/conversations/{conv}").get("execution_status")
            if status != "running" and transitioned:
                break
            time.sleep(1)
        rows = event_rows(conv)
        calls = json_file(STATE / "model-requests.json", [])
        hooks = json_file(STATE / "hooks.json", [])
        status = native.http("GET", f"/api/conversations/{conv}").get("execution_status")
        hook_events = [e for e in rows if "HookExecutionEvent" in json.dumps(e) or
                       (str(e.get("hook_event_type", "")).lower() == "stop")]
        # A standalone hook CLI invocation never meets this criterion.
        actual_native = len(hook_events) >= 2
        result = {
            "serverVersion": "1.55.1", "canvasVersion": native.CANVAS,
            "conversationId": conv, "executionStatus": status,
            "hookInvocations": len(hooks),
            "nativeHookEvents": len(hook_events),
            "mockModelRequests": len(calls),
            "feedbackSeenInLaterModelRequest": any(x.get("feedbackSeen") for x in calls[1:]),
            "fixtureDecisions": [x.get("accepted") for x in hooks],
            "nativeHookEventObserved": actual_native,
            "checks": {
                "nativeStopHookInvokedTwice": len(hooks) >= 2 and actual_native,
                "firstCompletionDenied": bool(hooks) and hooks[0].get("accepted") is False,
                "sameConversationRetriedWithFeedback": len(calls) >= 2 and any(x.get("feedbackSeen") for x in calls[1:]),
                "subsequentHookAllowed": any(x.get("accepted") is True for x in hooks[1:]),
                "finishReturned": status == "finished",
            },
            "notProven": ["Real independent Maven/OSV validation", "Vertex ADC", "GitHub delivery"],
        }
        result["verdict"] = ("PASS" if all(result["checks"].values()) else "NOT_PROVEN")
        save(REPORT, result)
        print("[hook-poc] " + result["verdict"] + "; report: " + str(REPORT))
        return result
    finally:
        server.shutdown()
        server.server_close()


def publish() -> None:
    if not REPORT.exists():
        raise native.Failure("No POC2 report")
    # Reuse native runner's allowlisted, branch-gated publish mechanism by adding
    # a separate allowlist, never uploading raw mock requests, hook inputs or logs.
    data = json_file(REPORT, {})
    if data.get("serverVersion") != "1.55.1":
        raise native.Failure("Wrong report version")
    repo = Path(__file__).resolve().parent.parent
    if native.command(["git", "-C", str(repo), "branch", "--show-current"]) != "openhands-service-integration":
        raise native.Failure("Wrong branch")
    if "AILearner365/oss-remediation-adk" not in native.command(["git", "-C", str(repo), "remote", "get-url", "origin"]):
        raise native.Failure("Wrong origin")
    if native.command(["git", "-C", str(repo), "diff", "--cached", "--name-only"]):
        raise native.Failure("Already staged changes; refusing publication")
    destination = repo / "docs/experiments/openhands/evidence" / (
        time.strftime("native-hook-%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3) + ".json")
    keys = ("serverVersion", "canvasVersion", "conversationId", "executionStatus",
            "hookInvocations", "nativeHookEvents", "mockModelRequests", "feedbackSeenInLaterModelRequest",
            "fixtureDecisions", "nativeHookEventObserved", "checks", "notProven", "verdict")
    save(destination, {k: data[k] for k in keys if k in data})
    rel = str(destination.relative_to(repo))
    native.command(["git", "-C", str(repo), "add", "--", rel])
    native.command(["git", "-C", str(repo), "commit", "-m", "Record native 1.55.1 Stop Hook POC evidence", "--", rel])
    native.command(["git", "-C", str(repo), "push", "origin", "HEAD:openhands-service-integration"])
    print("[hook-poc] Evidence pushed: " + rel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "hook", "publish"))
    parser.add_argument("--server-version", default="1.55.1", choices=("1.55.1",))
    args = parser.parse_args()
    native.configure_server_version("1.55.1")
    global STATE, REPORT
    STATE = native.ROOT / "hook-poc2"
    REPORT = native.RESULT_DIR / "native-hook-poc-1.55.1.json"
    try:
        if args.action == "hook":
            return hook_cli()
        if args.action == "publish":
            publish()
        else:
            execute()
            # NOT_PROVEN is a test failure, even if script reached a terminal state.
            if json_file(REPORT, {}).get("verdict") != "PASS":
                return 1
        return 0
    except Exception as exc:
        msg = str(exc)
        save(REPORT, {"verdict": "ERROR", "reason": type(exc).__name__, "detail": msg[:240],
                      "serverVersion": "1.55.1"})
        print("[hook-poc] ERROR:", type(exc).__name__, msg[:200], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
