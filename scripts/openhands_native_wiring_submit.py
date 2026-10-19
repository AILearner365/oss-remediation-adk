#!/usr/bin/env python3
"""Prepare one native one-file smoke; --execute explicitly permits one paid run.

Requires an already running, ADC-preflighted native stack and an isolated clean
worktree. A state directory is create-only; never replay after uncertain I/O.
"""
import argparse
import json
from pathlib import Path
import shlex
import sys
import uuid

import openhands_native_poc as native
from openhands_native_wiring_hook import BASE, REPO, URL, SHA, git, save

MODEL = "vertex_ai/gemini-2.5-flash"
TASK = (
    "In the working directory, create exactly one new regular non-executable file named "
    "openhands-native-wiring-test.txt containing exactly: Native OpenHands wiring test passed. "
    "followed by one newline. Use one terminal command to write it, then immediately call FinishTool. "
    "Do not inspect or modify any other files, run tests, commit, or push. A native Stop Hook "
    "independently validates and delivers a draft PR. If the hook blocks, stop making changes "
    "and finish; never retry external actions."
)


def build_request(contract, state):
    command = shlex.join([sys.executable, str(Path(__file__).with_name(
        "openhands_native_wiring_hook.py").resolve()), str(state)])
    return dict(conversation_id=contract["conversationId"],
        workspace=dict(working_dir=contract["workspace"]), worktree=False, autotitle=False,
        max_iterations=3, agent=dict(kind="Agent", llm=dict(model=MODEL,
            usage_id="native-one-file-wiring", stream=False, num_retries=0),
            tools=[dict(name="terminal", params={})], system_prompt_kwargs=dict(cli_mode=True)),
        hook_config=dict(stop=[dict(matcher="*", hooks=[dict(type="command",
            command=command, timeout=120)])]), tags=dict(purpose="native-one-file-wiring"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Authorize one paid native run and automatic draft PR delivery")
    args = parser.parse_args()
    native.configure_server_version("1.55.1")
    workspace = args.workspace.resolve(strict=True)
    state = args.state_dir.resolve()
    if state == workspace or workspace in state.parents:
        raise ValueError("Evidence must be outside the agent worktree")
    if (not SHA.fullmatch(args.expected_base) or git(workspace, "rev-parse", "HEAD") != args.expected_base
            or git(workspace, "remote", "get-url", "origin") != URL
            or git(workspace, "status", "--porcelain", "--untracked-files=all", "--ignored")):
        raise ValueError("Expected clean allowlisted worktree at approved base")
    remote = git(workspace, "ls-remote", URL, "refs/heads/" + BASE).split()
    if not remote or remote[0] != args.expected_base:
        raise ValueError("Approved remote base moved or is absent")
    info = native.http("GET", "/server_info")
    if any(info.get(k) != "1.55.1" for k in ("version", "sdk_version", "tools_version")):
        raise ValueError("Native version mismatch")
    native.wait_canvas_ready()
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    contract = dict(conversationId=str(uuid.uuid4()), workspace=str(workspace),
                    baseCommit=args.expected_base, base=BASE, repository=REPO)
    save(state / "contract.json", contract)
    request = build_request(contract, state)
    save(state / "submission-claim.json", dict(status="CREATE_INTENT", request=request))
    uid = contract["conversationId"]
    native.http("POST", "/api/conversations?include_skills=true", request, timeout=90)
    # 1.55.1 populates effective hook_config lazily on send_message, even run:false.
    native.http("POST", f"/api/conversations/{uid}/events", dict(role="user", run=False,
        content=[dict(type="text", text=TASK)]), timeout=60)
    actual = native.http("GET", f"/api/conversations/{uid}")
    hooks = actual.get("hook_config") or {}
    if (actual["execution_status"] != "idle" or actual["max_iterations"] != 3
            or actual["agent"]["llm"]["model"] != MODEL
            or actual["agent"]["llm"]["num_retries"] != 0
            or [h["command"] for group in hooks.get("stop", []) for h in group["hooks"]]
            != [request["hook_config"]["stop"][0]["hooks"][0]["command"]]):
        raise ValueError("Effective native configuration differs; do not dispatch")
    save(state / "prepared.json", dict(conversationId=uid, effectiveHookVerified=True))
    if args.execute:
        with (state / "run-claim.json").open("x") as claim:
            json.dump(dict(conversationId=uid, status="RUN_INTENT", doNotResubmit=True), claim)
        native.http("POST", f"/api/conversations/{uid}/run", {}, timeout=30)
    print(json.dumps(dict(conversationId=uid, dispatched=args.execute, stateDir=str(state))))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(status="BLOCKED", errorType=type(exc).__name__,
                              inspectBeforeRetry=True)), file=sys.stderr)
        sys.exit(1)
