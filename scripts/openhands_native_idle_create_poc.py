#!/usr/bin/env python3
"""Disposable native 1.55.1 idle-create smoke. No model execution or /run.

Uses existing POC3 prepared task fixture, not real Maven/OSV. Never uses the
legacy runtime HTTP transport: only native Agent Server 1.55.1 conversation API.
"""
from __future__ import annotations
import json
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys

import openhands_native_poc as native
import openhands_native_validator_poc as fixture
import openhands_native_remediation as handoff
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.contracts import (OpenHandsRuntimeRecord, OpenHandsRuntimeStatus, ExecutionStatus, OpenHandsEventLink)

CASE = "native-idle-create-v4"


def main():
    native.configure_server_version("1.55.1")
    state = native.ROOT / CASE
    report = native.RESULT_DIR / (CASE + ".json")
    native.wait_ready()
    native.wait_canvas_ready()
    if state.exists():
        raise native.Failure("Idle-create fixture already exists: preserve evidence and do not overwrite")
    state.mkdir(parents=True)
    # Prepare the deterministic task directly; do not invoke the legacy
    # runtime adapter's provision() or start_execution().
    test = fixture.SharedValidationIntegrationTests(
        methodName="test_pass_allows_and_accepts_only_independent_report"
    )
    test.setUp()
    try:
        task_id, workspace = test.fixture._ready("native-direct-" + uuid.uuid4().hex[:8])
        conversation_id = str(uuid.uuid4())
        prep = test.fixture.store.get_preparation(task_id)
        profile = test.fixture.profile
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        digest = hashlib.sha256((task_id + conversation_id).encode()).hexdigest()
        runtime = OpenHandsRuntimeRecord(
            task_id=task_id, conversation_id=conversation_id,
            agent_server_identity="native-local-1551",
            agent_server_version="1.55.1", sdk_version="1.55.1",
            tools_version="1.55.1",
            agent_profile_id=profile.profile_id,
            native_agent_profile_id=profile.native_agent_profile_id,
            native_agent_profile_revision=profile.native_agent_profile_revision,
            model_profile_id=profile.model_profile_id, native_model="openai/gpt-4o-mini",
            profile_fingerprint=digest, request_fingerprint=digest,
            workspace_path=str(workspace.resolve()),
            baseline_commit=prep.baseline_commit,
            runtime_status=OpenHandsRuntimeStatus.CONVERSATION_READY,
            execution_status=ExecutionStatus.NOT_STARTED,
            last_native_event_id=None, last_native_event_order=0,
            failure_code=None, failure_detail=None,
            created_at=now, updated_at=now,
        )
        test.fixture.store.record_openhands_runtime(runtime)
        data = {
            "taskId": task_id, "conversationId": conversation_id,
            "workspace": str(workspace), "database": str(test.fixture.database),
            "hookConfig": str(test.hook_config),
        }
        fixture.write_json(state / "prepared.json", data)
        test.fixture.store.close()
        test.fixture.temp_dir._finalizer.detach()
    except Exception:
        test.tearDown()
        raise
    store = SQLiteTaskStore(Path(data["database"]))
    try:
        request = handoff.build_request(
            store, data["taskId"], hook_config=Path(data["hookConfig"]),
            model="openai/gpt-4o-mini",
            base_url="http://127.0.0.1:12997/v1",
            api_key="poc-no-paid-llm",
            max_iterations=6,
        )
        uid = handoff.create_idle_native_conversation(request, native.http)
        # Bind the initialized native user event to the existing durable
        # event index. No execution claim is made before /run.
        event_page = native.http("GET", f"/api/conversations/{uid}/events/search?limit=100&sort_order=TIMESTAMP")
        events = event_page.get("items", [])
        messages = [e for e in events if e.get("kind") == "MessageEvent" and e.get("id")]
        if len(messages) != 1:
            raise handoff.HandoffError("Expected one uniquely observed native initial message")
        event = messages[0]
        store.link_openhands_event(OpenHandsEventLink(
            task_id=data["taskId"], conversation_id=uid,
            native_event_id=str(event["id"]), native_order=1,
            native_kind="MessageEvent", native_timestamp=None,
            observed_at=now,
        ), context_attached=True)
        accepted = store.get_status(data["taskId"]).accepted
        check = {
            "nativeIdentityMatched": uid == data["conversationId"],
            "workspaceMatched": request["workspace"]["working_dir"] == data["workspace"],
            "hookPersisted": True,  # checked by create_idle_native_conversation
            "notAccepted": accepted is False,
            "noRunCalled": store.get_execution_claim(data["taskId"]) is None,
            "contextLinked": store.get_openhands_runtime(data["taskId"]).runtime_status is OpenHandsRuntimeStatus.CONTEXT_ATTACHED,
        }
        result = {
            "case": CASE, "serverVersion": native.SERVER,
            "conversationId": uid, "checks": check,
            "verdict": "PASS" if all(check.values()) else "NOT_PROVEN",
            "notProven": ["Real agent action", "Maven/OSV scan", "Native retry", "PR delivery"],
        }
        fixture.write_json(report, result)
        print("[idle-create] " + result["verdict"] + "; report: " + str(report))
        return 0 if result["verdict"] == "PASS" else 1
    finally:
        store.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("[idle-create] ERROR:", type(exc).__name__, str(exc)[:220], file=sys.stderr)
        raise SystemExit(1)
