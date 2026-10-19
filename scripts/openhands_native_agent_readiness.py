#!/usr/bin/env python3
"""Nonbillable verification of the native 1.55.1 remediation agent contract.

Run using the pinned Agent Server uvx environment Python. This tool does NOT
invoke /run, obtain ADC credentials, or call an LLM.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import openhands_native_poc as native


def verify_agent() -> dict:
    from openhands.sdk import AgentContext, LLM
    from openhands.sdk.skills import load_skills_from_dir
    from openhands.tools.preset.default import get_default_agent
    from openhands.tools.terminal import TerminalTool
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool

    skills_path = ROOT / "scripts/openhands/skills"
    _, _, available = load_skills_from_dir(skills_path)
    selected = ("dependency-remediation-decision", "maven-dependency-evidence")
    missing = set(selected) - set(available)
    if missing:
        raise ValueError(f"Missing required remediation Skills: {sorted(missing)}")
    general = (ROOT / "scripts/openhands/guidance/general-engineering.md").read_text(encoding="utf-8").strip()
    if not general:
        raise ValueError("General engineering guidance is empty")
    llm = LLM(model="openai/gpt-4o-mini", api_key="poc-local-dummy-not-real",
              base_url="http://127.0.0.1:12999/v1", usage_id="native-readiness")
    agent = get_default_agent(llm, cli_mode=True)
    agent = agent.model_copy(update={"agent_context": AgentContext(
        skills=[available[name] for name in selected],
        system_message_suffix=general,
        load_public_skills=False,
    )})
    data = agent.model_dump(mode="json")
    names = [item["name"] for item in data["tools"]]
    required = {TerminalTool.name, FileEditorTool.name, TaskTrackerTool.name}
    if not required.issubset(names):
        raise ValueError(f"Native CLI preset missing tools: {sorted(required-set(names))}; actual={names}")
    context = data.get("agent_context") or {}
    actual_skills = [item["name"] for item in context.get("skills", [])]
    if actual_skills != list(selected) or context.get("system_message_suffix") != general:
        raise ValueError("Serialized native Skills/guidance differ from approved selection")
    return {"agent": data, "toolNames": names, "skillNames": actual_skills,
            "guidancePresent": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idle-server-check", action="store_true",
                        help="Create and inspect one idle native conversation (never /run)")
    args = parser.parse_args()
    os.environ["OPENHANDS_SUPPRESS_BANNER"] = "1"
    outcome = verify_agent()
    print("Native default coding tools:", outcome["toolNames"])
    print("Remediation Skills:", outcome["skillNames"])
    print("General engineering guidance: PASS")
    print("Repository-specific guidance: NOT INCLUDED (task dependent)")
    if not args.idle_server_check:
        print("SDK schema/serialization: PASS; live server check not requested")
        return 0

    native.configure_server_version("1.55.1")
    native.wait_ready()
    info = native.http("GET", "/server_info")
    if info.get("version") != "1.55.1":
        raise RuntimeError("Unexpected native Agent Server version")
    uid = str(uuid.uuid4())
    workspace = native.create_fixture("normal", uid)
    request = {
        "conversation_id": uid,
        "workspace": {"working_dir": str(workspace)},
        "worktree": False,
        "autotitle": False,
        "max_iterations": 1,
        "tags": {"smoke": "native-agent-readiness"},
        "agent": outcome["agent"],
    }
    created = native.http("POST", "/api/conversations?include_skills=true", request)
    if str(created.get("id", created.get("conversation_id", ""))) != uid:
        raise RuntimeError("Native create response has unexpected identity")
    # No initial user message and NO /run: inspect the persisted configuration.
    persisted = native.http("GET", f"/api/conversations/{uid}?include_skills=true")
    agent = persisted.get("agent") or {}
    actual_tools = [t.get("name") for t in (agent.get("tools") or [])]
    context = agent.get("agent_context") or {}
    actual_skills = [s.get("name") for s in (context.get("skills") or [])]
    if not set(outcome["toolNames"]).issubset(actual_tools):
        raise RuntimeError("Agent Server did not persist native tools")
    if actual_skills != outcome["skillNames"]:
        raise RuntimeError("Agent Server did not persist selected remediation Skills")
    if not context.get("system_message_suffix"):
        raise RuntimeError("Agent Server did not persist engineering guidance")
    if persisted.get("execution_status") != "idle":
        raise RuntimeError("Readiness conversation unexpectedly not idle")
    print("Native idle conversation persisted tools, Skills and guidance: PASS")
    print("Native conversation:", uid)
    print("NO /run; NO model inference; NO ADC check")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BLOCKED: {type(exc).__name__}: {str(exc)[:400]}", file=sys.stderr)
        raise SystemExit(1)
