#!/usr/bin/env python3
"""Read-only shared-task to native OpenHands Canvas smoke checker.

This never registers a task, invokes /run, or calls an LLM. A prepared and
provisioned task must already exist in the shared Task API.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


class SmokeFailure(Exception):
    pass


def get_json(base: str, path: str) -> dict:
    url = base.rstrip("/") + path
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            value = json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise SmokeFailure("GET " + path + " failed: " + type(exc).__name__) from exc
    if not isinstance(value, dict):
        raise SmokeFailure("GET " + path + " returned a non-object response")
    return value


def check(task_api: str, agent_server: str, canvas: str, task_id: str) -> dict:
    if not task_id.startswith("task_") or not all(
        c in "0123456789abcdef" for c in task_id[5:]
    ) or len(task_id) != 37:
        raise SmokeFailure("task-id must be task_ followed by 32 lowercase hex digits")

    task = get_json(task_api, "/v1/tasks/" + task_id)
    if task.get("taskId") != task_id:
        raise SmokeFailure("task API returned a mismatched task ID")
    runtime = task.get("openhands")
    if not isinstance(runtime, dict):
        raise SmokeFailure("task status lacks OpenHands mapping")
    conversation_id = runtime.get("conversationId")
    try:
        uuid.UUID(conversation_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise SmokeFailure("task has no valid native conversation ID") from exc
    if runtime.get("executionStatus") != "NOT_STARTED":
        raise SmokeFailure("task execution is not NOT_STARTED; this is an idle-only smoke test")
    if task.get("validation", {}).get("accepted") is not False:
        raise SmokeFailure("task must not be accepted for an idle smoke test")

    conv = get_json(
        agent_server, "/api/conversations/" + urllib.parse.quote(conversation_id) +
        "?include_skills=true"
    )
    native_id = conv.get("conversation_id", conv.get("id"))
    if native_id != conversation_id:
        raise SmokeFailure("native conversation ID does not match task mapping")
    native_status = conv.get("execution_status")
    if native_status != "idle":
        raise SmokeFailure("native conversation must be idle (got " + repr(native_status) + ")")
    hook = conv.get("hook_config")
    if not isinstance(hook, dict) or not isinstance(hook.get("stop"), list) or not hook["stop"]:
        raise SmokeFailure("effective native Stop Hook is absent or invalid; no launch permitted")

    events = get_json(task_api, "/v1/tasks/" + task_id + "/events")
    if events.get("taskId") != task_id or not isinstance(events.get("events"), list):
        raise SmokeFailure("task event API returned an invalid response")
    native_events = get_json(
        agent_server,
        "/api/conversations/" + urllib.parse.quote(conversation_id) +
        "/events/search?limit=100&sort_order=TIMESTAMP",
    )
    # Native server event response varies by transport; confirm only a documented
    # object response here, without assuming fake-server-only field names.
    native_items = native_events.get("items")
    if not isinstance(native_items, list) or not native_items:
        raise SmokeFailure("native event search returned no native events")
    url = canvas.rstrip("/") + "/conversations/" + urllib.parse.quote(conversation_id)
    return {
        "verdict": "API_MAPPING_PASSED__CANVAS_BROWSER_NOT_PROVEN",
        "taskId": task_id,
        "productStatus": task.get("status"),
        "productEventCount": len(events["events"]),
        "nativeEventCount": len(native_items),
        "nativeConversationId": conversation_id,
        "nativeExecutionStatus": native_status,
        "effectiveHookVisible": True,
        "productExecutionStatus": runtime["executionStatus"],
        "accepted": False,
        "canvasUrl": url,
        "nextManualStep": "Open canvasUrl in Canvas connected to this SAME Agent Server; verify initial user context and native events. A URL alone is not browser proof.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-api", default="http://127.0.0.1:8080")
    parser.add_argument("--agent-server", required=True)
    parser.add_argument("--canvas", required=True)
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    for name, address in (
        ("task-api", args.task_api),
        ("agent-server", args.agent_server),
        ("canvas", args.canvas),
    ):
        parsed = urllib.parse.urlsplit(address)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or (
            parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            parser.error(name + " must be a plain HTTP(S) origin without credentials")
    try:
        result = check(args.task_api, args.agent_server, args.canvas, args.task_id)
    except SmokeFailure as exc:
        print(json.dumps({"verdict": "FAILED", "reason": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
