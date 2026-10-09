#!/usr/bin/env python3
"""Run Gate 2 with native OpenHands Stop-hook deterministic validation.

This experiment changes one variable from the native Gate 2 run:
OpenHands completion is intercepted by a native Stop hook that invokes the
existing independent deterministic validator. Validator failures are returned
to the same conversation as evidence. No remediation strategy is prescribed.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path

from openhands.sdk import AgentContext, Conversation, LLM
from openhands.sdk.event import HookExecutionEvent
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
from openhands.tools.preset.default import get_default_agent


CONTROL_REPO = Path(__file__).resolve().parents[2]
DEFAULT_TARGET = Path.home() / "maven-multimodule-app-stop-hook"
DEFAULT_STATE_DIR = Path.home() / ".openhands" / "gate2" / "task-02-stop-hook"
DEFAULT_TASK_DOC = CONTROL_REPO / "docs" / "experiments" / "openhands" / "GATE2-TASK.md"
DEFAULT_HOOK = CONTROL_REPO / "scripts" / "openhands" / "openhands-gate2-stop-hook.sh"
DEFAULT_ENGINEERING_GUIDANCE = (
    CONTROL_REPO
    / "scripts"
    / "openhands"
    / "guidance"
    / "engineering-judgment.md"
)
ENGINEERING_GUIDANCE_ENV = "OPENHANDS_ENGINEERING_JUDGMENT_GUIDANCE"


def environment_flag(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise SystemExit(
        f"{name} must be one of 1/0, true/false, yes/no, or on/off"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run controlled Gate 2 with native Stop-hook validation."
    )
    parser.add_argument("--target-repo", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--task-doc", type=Path, default=DEFAULT_TASK_DOC)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--model", default="vertex_ai/gemini-2.5-flash")
    parser.add_argument("--max-denials", type=int, default=3)
    parser.add_argument("--max-iterations", type=int, default=250)
    parser.add_argument(
        "--engineering-judgment-guidance",
        action=argparse.BooleanOptionalAction,
        default=environment_flag(ENGINEERING_GUIDANCE_ENV),
        help=(
            "inject the opt-in engineering-judgment guidance through native "
            "AgentContext.system_message_suffix"
        ),
    )
    return parser.parse_args()


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def extract_task_prompt(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    marker = "## Prompt to give OpenHands"
    section = text.split(marker, 1)
    if len(section) != 2:
        raise SystemExit(f"Task prompt section not found in {path}")
    after = section[1]
    start = after.find("```text")
    if start < 0:
        raise SystemExit(f"Task prompt opening fence not found in {path}")
    start += len("```text")
    end = after.find("```", start)
    if end < 0:
        raise SystemExit(f"Task prompt closing fence not found in {path}")
    return after[start:end].strip()


def report_passed(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if isinstance(data.get("passed"), bool):
        return data["passed"]
    checks = data.get("checks")
    return bool(checks) and all(bool(c.get("passed")) for c in checks)


def load_engineering_guidance(path: Path = DEFAULT_ENGINEERING_GUIDANCE) -> str:
    try:
        guidance = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SystemExit(
            f"Unable to load engineering judgment guidance from {path}: {exc}"
        ) from exc
    if not guidance:
        raise SystemExit(f"Engineering judgment guidance is empty: {path}")
    return guidance


def build_agent(llm: LLM, *, engineering_guidance: bool):
    agent = get_default_agent(llm=llm, cli_mode=True)
    if not engineering_guidance:
        return agent
    context = AgentContext(
        system_message_suffix=load_engineering_guidance(),
    )
    return agent.model_copy(update={"agent_context": context})


def build_hook_config(
    *,
    target: Path,
    baseline: Path,
    validation: Path,
    hook_state: Path,
    max_denials: int,
) -> HookConfig:
    env_prefix = {
        "CONTROL_REPO": str(CONTROL_REPO),
        "GATE2_STATE_FILE": str(baseline),
        "GATE2_VALIDATION_OUTPUT": str(validation),
        "GATE2_HOOK_STATE_DIR": str(hook_state),
        "GATE2_TARGET_REPO": str(target),
        "GATE2_MAX_DENIALS": str(max_denials),
    }
    command = " ".join(
        [f"{key}={shlex.quote(value)}" for key, value in env_prefix.items()]
        + ["bash", shlex.quote(str(DEFAULT_HOOK))]
    )
    return HookConfig(
        stop=[
            HookMatcher(
                matcher="*",
                hooks=[HookDefinition(command=command, timeout=1800)],
            )
        ]
    )


def main() -> int:
    args = parse_args()
    target = args.target_repo.expanduser().resolve()
    state_dir = args.state_dir.expanduser().resolve()
    baseline = state_dir / "baseline.json"
    validation = state_dir / "validation.json"
    hook_state = state_dir / "hook"
    infrastructure_failure = hook_state / "infrastructure-failure"
    persistence = state_dir / "conversation"

    if args.max_denials < 1:
        raise SystemExit("--max-denials must be at least 1")
    if not target.is_dir():
        raise SystemExit(f"Target repository not found: {target}")
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=target,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        raise SystemExit(f"Target repository is not a Git worktree: {target}")
    if not baseline.is_file():
        raise SystemExit(
            f"Baseline state not found: {baseline}. Run the task-02 baseline first."
        )

    state = json.loads(baseline.read_text(encoding="utf-8"))
    expected_branch = state["taskBranch"]
    current_branch = run_git(target, "branch", "--show-current")
    if current_branch != expected_branch:
        raise SystemExit(
            f"Expected target branch {expected_branch}, found {current_branch}"
        )
    if run_git(target, "status", "--porcelain"):
        raise SystemExit("Target repo must be clean before starting the experiment.")
    expected_head = state["baselineCommit"]
    actual_head = run_git(target, "rev-parse", "HEAD")
    if actual_head != expected_head:
        raise SystemExit(
            f"Target HEAD {actual_head} does not equal recorded baseline {expected_head}"
        )

    if args.model.startswith("vertex_ai/"):
        missing = [
            name
            for name in ("VERTEXAI_PROJECT", "VERTEXAI_LOCATION")
            if not os.environ.get(name)
        ]
        if missing:
            raise SystemExit(
                "Missing required Vertex environment variable(s): "
                + ", ".join(missing)
            )

    state_dir.mkdir(parents=True, exist_ok=True)
    hook_state.mkdir(parents=True, exist_ok=True)
    for path in (
        hook_state / "attempt-count",
        hook_state / "last-validator.log",
        infrastructure_failure,
        validation,
    ):
        if path.exists():
            path.unlink()

    hook_config = build_hook_config(
        target=target,
        baseline=baseline,
        validation=validation,
        hook_state=hook_state,
        max_denials=args.max_denials,
    )

    llm = LLM(
        usage_id="openhands-gate2-stop-hook",
        model=args.model,
        api_key=None,
    )
    agent = build_agent(
        llm,
        engineering_guidance=args.engineering_judgment_guidance,
    )
    if args.engineering_judgment_guidance:
        print(f"ENGINEERING_JUDGMENT_GUIDANCE={DEFAULT_ENGINEERING_GUIDANCE}")
    conversation = Conversation(
        agent=agent,
        workspace=str(target),
        hook_config=hook_config,
        persistence_dir=persistence,
        delete_on_close=False,
        max_iteration_per_run=args.max_iterations,
        stuck_detection=True,
    )

    task = extract_task_prompt(args.task_doc)
    try:
        conversation.send_message(task)
        conversation.run()

        status = conversation.state.execution_status
        status_value = getattr(status, "value", str(status))
        stop_events = [
            event
            for event in conversation.state.events
            if isinstance(event, HookExecutionEvent)
            and event.hook_event_type == "Stop"
        ]
        denied = [event for event in stop_events if event.blocked]

        count_file = hook_state / "attempt-count"
        attempts = int(count_file.read_text().strip()) if count_file.exists() else 0
        accepted = report_passed(validation)

        print(f"MODEL={args.model}")
        print(f"CONVERSATION_ID={conversation.state.id}")
        print(f"FINAL_STATUS={status_value}")
        print(f"STOP_HOOK_INVOCATIONS={attempts}")
        print(f"STOP_HOOK_EVENTS={len(stop_events)}")
        print(f"DENIED_COMPLETIONS={len(denied)}")
        print(f"DETERMINISTIC_VALIDATION_PASSED={accepted}")
        print(f"VALIDATION_REPORT={validation}")
        print(f"CONVERSATION_PERSISTENCE={persistence}")

        if infrastructure_failure.is_file():
            detail = infrastructure_failure.read_text(encoding="utf-8").strip()
            print(f"VALIDATOR_INFRASTRUCTURE_FAILURE={detail or 'true'}")
            print("GATE2_STOP_HOOK_RESULT=INFRASTRUCTURE_FAIL")
            return 3

        if status_value == "finished" and accepted:
            print("GATE2_STOP_HOOK_RESULT=PASS")
            return 0

        if attempts > args.max_denials and not accepted:
            print("GATE2_STOP_HOOK_RESULT=BOUNDED_FAIL")
            return 2

        print("GATE2_STOP_HOOK_RESULT=FAIL")
        return 1
    finally:
        conversation.close()


if __name__ == "__main__":
    raise SystemExit(main())
