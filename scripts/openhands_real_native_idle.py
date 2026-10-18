#!/usr/bin/env python3
"""Inspect a durable real task, or attach one OpenHands 1.55.1 idle conversation.

Never calls native /run. Never performs model inference. Native creation may
initialize a model client; run only against the existing authorized local
Canvas test server, with no unrelated conversation cleanup or restart.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import openhands_native_poc as native
import openhands_native_remediation as handoff
from openhands_shared.contracts import (
    BaselineAssessmentStatus, ExecutionStatus, OpenHandsEventLink,
    OpenHandsRuntimeRecord, OpenHandsRuntimeStatus, TaskStatus, utc_now
)
from openhands_shared.store import SQLiteTaskStore

EXPECTED_COMMIT = "f44f94c2b2ec553fc3276e36e6a99a0dcc4cd13a"
MODEL = "vertex_ai/gemini-2.5-flash"


def verify_stored(store: SQLiteTaskStore, task_id: str, hook_config: Path) -> dict:
    status = store.get_status(task_id)
    prep = store.get_preparation(task_id)
    baseline = store.get_baseline(task_id)
    intel = store.get_intelligence(task_id)
    request = store.get_request(task_id)
    if (status.status is not TaskStatus.AGENT_RUNNING
        or status.accepted or status.execution_status is not ExecutionStatus.NOT_STARTED):
        raise ValueError("Task must be AGENT_RUNNING / NOT_STARTED / unaccepted")
    if prep is None or baseline is None or intel is None:
        raise ValueError("Durable task preparation, baseline or intelligence missing")
    if (prep.baseline_commit != EXPECTED_COMMIT
        or baseline.baseline_commit != EXPECTED_COMMIT
        or baseline.assessment_status is not BaselineAssessmentStatus.COMPLETED
        or baseline.finding_count != 1):
        raise ValueError("Controlled immutable baseline does not match approved one-finding case")
    if request.repository.expected_commit != EXPECTED_COMMIT:
        raise ValueError("Task repository commit differs from durable baseline")
    if not Path(prep.workspace_path).is_dir():
        raise ValueError("Prepared workspace unavailable")
    db, config = handoff.load_stop_hook_config(hook_config.resolve(strict=True))
    if db != store.database_path.resolve():
        raise ValueError("Stop Hook database is not authoritative task store")
    config.profile_for(request)
    report = next((a for a in store.list_artifacts(task_id) if a.artifact_id == baseline.report_artifact_id), None)
    if report is None:
        raise ValueError("Durable baseline report artifact missing")
    report_file = config.artifact_root / report.relative_path
    body = report_file.read_bytes()
    if hashlib.sha256(body).hexdigest() != baseline.report_sha256:
        raise ValueError("Durable baseline report failed checksum verification")
    value = json.loads(body)
    findings = value.get("originalVulnerabilityFindings", [])
    if len(findings) != 1:
        raise ValueError("Original baseline finding inventory differs")
    f = findings[0]
    identifiers = {f.get("vulnerabilityId"), *f.get("aliases", [])}
    if "GHSA-mjmj-j48q-9wg2" not in identifiers:
        raise ValueError("Target advisory not present in immutable baseline evidence")
    return {"baselineAdvisoryVerified": True, "taskUnstarted": True,
            "hookConfigValidated": True, "baselineArtifactVerified": True,
            "workspace": prep.workspace_path, "findingCount": baseline.finding_count}


def inspect(store: SQLiteTaskStore, task_id: str, config: Path) -> dict:
    result = verify_stored(store, task_id, config)
    runtime = store.get_openhands_runtime(task_id)
    result.update({"taskId": task_id, "runtimeAssociationExists": runtime is not None,
                   "nativeRunCalled": False, "modelExecutionAuthorized": False,
                   "status": "VERIFIED_DURABLE_TASK_NOT_AUTHORIZED"})
    return result


def attach_idle(store: SQLiteTaskStore, task_id: str, config: Path) -> dict:
    checks = verify_stored(store, task_id, config)
    if store.get_openhands_runtime(task_id) is not None:
        raise ValueError("Runtime already associated; do not create duplicate conversation")
    if store.get_execution_claim(task_id) is not None:
        raise ValueError("Execution claim already exists")
    native.configure_server_version("1.55.1")
    # Do NOT start the Canvas/Server here; only use already-running POC stack.
    native.wait_ready()
    # refuse mismatched pinned server before registering or issuing HTTP POST
    info = native.http("GET", "/server_info")
    server_version = str(info.get("version", ""))
    if server_version != "1.55.1":
        raise ValueError("Running Agent Server version is not exactly 1.55.1")
    conversation_id = str(uuid4())
    now = utc_now()
    prep = store.get_preparation(task_id)
    request = store.get_request(task_id)
    fingerprint = hashlib.sha256((task_id + conversation_id + request.objective).encode()).hexdigest()
    runtime = OpenHandsRuntimeRecord(
        task_id=task_id, conversation_id=conversation_id,
        agent_server_identity="native-local-1551",
        agent_server_version="1.55.1", sdk_version="1.55.1",
        tools_version="1.55.1",
        agent_profile_id=request.agent.profile,
        native_agent_profile_id=str(uuid4()), native_agent_profile_revision=0,
        model_profile_id=request.agent.model_profile, native_model=MODEL,
        profile_fingerprint=fingerprint, request_fingerprint=fingerprint,
        workspace_path=str(Path(prep.workspace_path).resolve()),
        baseline_commit=prep.baseline_commit,
        runtime_status=OpenHandsRuntimeStatus.CONVERSATION_READY,
        execution_status=ExecutionStatus.NOT_STARTED,
        last_native_event_id=None, last_native_event_order=0,
        failure_code=None, failure_detail=None,
        created_at=now, updated_at=now,
    )
    store.record_openhands_runtime(runtime)
    payload = handoff.build_request(
        store, task_id, hook_config=config, model=MODEL,
        max_iterations=min(request.agent.max_iterations, 12)
    )
    initial = handoff.render_task_objective(store, task_id)
    handoff.create_idle_native_conversation(payload, native.http, initial_message=initial)
    event_page = native.http(
        "GET", f"/api/conversations/{conversation_id}/events/search?limit=100&sort_order=TIMESTAMP"
    )
    events = event_page.get("items", [])
    messages = [e for e in events if e.get("kind") == "MessageEvent" and e.get("id")]
    if len(messages) != 1:
        raise ValueError("Expected exactly one native initial MessageEvent; manual recovery required")
    store.link_openhands_event(OpenHandsEventLink(
        task_id=task_id, conversation_id=conversation_id,
        native_event_id=str(messages[0]["id"]), native_order=1,
        native_kind="MessageEvent", native_timestamp=None, observed_at=utc_now()
    ), context_attached=True)
    persisted = native.http("GET", f"/api/conversations/{conversation_id}?include_skills=true")
    handoff.validate_native_response(persisted, payload)
    if store.get_execution_claim(task_id) is not None:
        raise ValueError("Unexpected native execution claim")
    checks.update({"nativeServerVersionVerified": True, "nativeIdleHookPersisted": True,
                   "nativeMessageLinked": True, "nativeRunCalled": False,
                   "modelExecutionAuthorized": False,
                   "conversationId": conversation_id,
                   "status": "NATIVE_IDLE_ATTACHED_NOT_AUTHORIZED"})
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--hook-config", required=True, type=Path)
    parser.add_argument("--mode", choices=["inspect", "attach-idle"], default="inspect")
    args = parser.parse_args()
    try:
        with SQLiteTaskStore(args.database) as store:
            outcome = (inspect(store, args.task_id, args.hook_config)
                       if args.mode == "inspect"
                       else attach_idle(store, args.task_id, args.hook_config))
    except Exception as exc:
        outcome = {"status": "BLOCKED", "errorType": type(exc).__name__,
                   "errorDetail": str(exc)[:240], "nativeRunCalled": False,
                   "modelExecutionAuthorized": False}
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 0 if outcome["status"] != "BLOCKED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
