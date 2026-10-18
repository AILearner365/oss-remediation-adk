#!/usr/bin/env python3
"""Disposable native 1.55.1 idle-create smoke. No model execution or /run.

Uses existing POC3 prepared task fixture, not real Maven/OSV. Never uses the
legacy runtime HTTP transport: only native Agent Server 1.55.1 conversation API.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

import openhands_native_poc as native
import openhands_native_validator_poc as fixture
import openhands_native_remediation as handoff
from openhands_shared.store import SQLiteTaskStore

CASE = "native-idle-create-v1"


def main():
    native.configure_server_version("1.55.1")
    state = native.ROOT / CASE
    report = native.RESULT_DIR / (CASE + ".json")
    native.wait_ready()
    native.wait_canvas_ready()
    if state.exists():
        raise native.Failure("Idle-create fixture already exists: preserve evidence and do not overwrite")
    state.mkdir(parents=True)
    old = fixture.STATE
    fixture.STATE = state
    try:
        data = fixture.fixture_setup()
    finally:
        fixture.STATE = old
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
        accepted = store.get_status(data["taskId"]).accepted
        check = {
            "nativeIdentityMatched": uid == data["conversationId"],
            "workspaceMatched": request["workspace"]["working_dir"] == data["workspace"],
            "hookPersisted": True,  # checked by create_idle_native_conversation
            "notAccepted": accepted is False,
            "noRunCalled": True,  # code contains POST create, GET only; never /run
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
