#!/usr/bin/env python3
"""Run Gate 2 with native OpenHands Stop-hook deterministic validation.

This experiment changes one variable from the native Gate 2 run:
OpenHands completion is intercepted by a native Stop hook that invokes the
existing independent deterministic validator. Validator failures are returned
to the same conversation as evidence. No remediation strategy is prescribed.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
import shlex
import subprocess
import shutil
import sys
from pathlib import Path
from typing import Any

CONTROL_REPO = Path(__file__).resolve().parents[2]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

from maven_repository_server import serve_maven_repository
from scripts.openhands.sbri_integration import (
    agent_message,
    require_valid_selection,
    run_pre_edit_intelligence,
)

from openhands.sdk import AgentContext, Conversation, LLM
from openhands.sdk.event import HookExecutionEvent
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
from openhands.sdk.llm import Message, TextContent
from openhands.tools.preset.default import get_default_agent


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
TASK_SKILL_ENV = "OPENHANDS_TASK_SKILL"
STRUCTURED_ENV = "OPENHANDS_STRUCTURED_GUIDANCE"
DECISION_ENV = "OPENHANDS_DECISION_GUIDANCE"
SBRI_ENV = "OPENHANDS_SBRI"
GENERAL_GUIDANCE = CONTROL_REPO / "scripts/openhands/guidance/general-engineering.md"
PROJECT_GUIDANCE = CONTROL_REPO / "scripts/openhands/project-context/AGENTS.md"
MAVEN_SKILL_NAME = "maven-dependency-evidence"
DECISION_SKILL_NAME = "dependency-remediation-decision"
TASK_SKILL_DIR = CONTROL_REPO / "scripts" / "openhands" / "skills"
TASK_SKILL_NAME = "evidence-driven-dependency-remediation"


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
    parser.add_argument(
        "--task-skill",
        action=argparse.BooleanOptionalAction,
        default=environment_flag(TASK_SKILL_ENV),
        help="opt in to the pinned local Agent Skill instead of the legacy guidance suffix",
    )
    parser.add_argument("--structured-guidance", action=argparse.BooleanOptionalAction,
                        default=environment_flag(STRUCTURED_ENV),
                        help="opt-in general engineering guidance, repository context and Maven evidence Skill")
    parser.add_argument("--decision-guidance", action=argparse.BooleanOptionalAction,
                        default=environment_flag(DECISION_ENV),
                        help="opt-in candidate decision Skill and Maven evidence Skill")
    parser.add_argument("--sbri", action=argparse.BooleanOptionalAction,
                        default=(environment_flag(SBRI_ENV) if SBRI_ENV in os.environ else True),
                        help="provide applicable Spring Boot security tasks with pre-edit SBRI evidence")
    parser.add_argument("--sbri-config", type=Path,
                        help="optional SBRI JSON configuration for Maven/scanner settings")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--sbri-versions",
                           help="comma-separated published stable Spring Boot versions")
    selection.add_argument("--sbri-range",
                           help="comma-separated major.minor.x release ranges")
    parser.add_argument("--sbri-max-candidates", type=int,
                        help="reject selection exceeding this candidate count (default: 12)")
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


def build_agent(llm: LLM, *, engineering_guidance: bool, task_skill: bool = False, structured_guidance: bool = False, decision_guidance: bool = False):
    agent = get_default_agent(llm=llm, cli_mode=True)
    if sum((engineering_guidance, task_skill, structured_guidance, decision_guidance)) > 1:
        raise SystemExit("Choose only one guidance experiment")
    if structured_guidance or decision_guidance:
        from openhands.sdk.skills import load_skills_from_dir
        _repo, _knowledge, skills = load_skills_from_dir(TASK_SKILL_DIR)
        if MAVEN_SKILL_NAME not in skills:
            raise SystemExit(f"Missing Maven evidence Skill: {MAVEN_SKILL_NAME}")
        if decision_guidance and DECISION_SKILL_NAME not in skills:
            raise SystemExit(f"Missing decision Skill: {DECISION_SKILL_NAME}")
        guidance = load_engineering_guidance(GENERAL_GUIDANCE)
        project = load_engineering_guidance(PROJECT_GUIDANCE)
        selected_skills = ([skills[DECISION_SKILL_NAME], skills[MAVEN_SKILL_NAME]]
                           if decision_guidance else [skills[MAVEN_SKILL_NAME]])
        context = AgentContext(skills=selected_skills,
            system_message_suffix=guidance + "\n\n<REPOSITORY_GUIDANCE>\n" + project + "\n</REPOSITORY_GUIDANCE>",
            load_public_skills=False)
        return agent.model_copy(update={"agent_context": context})
    if engineering_guidance and task_skill:
        raise SystemExit("Select one guidance mechanism: --task-skill or --engineering-judgment-guidance")
    if task_skill:
        from openhands.sdk.skills import load_skills_from_dir

        _repo, _knowledge, skills = load_skills_from_dir(TASK_SKILL_DIR)
        if TASK_SKILL_NAME not in skills:
            raise SystemExit(f"Expected Agent Skill not found: {TASK_SKILL_NAME} in {TASK_SKILL_DIR}")
        context = AgentContext(skills=[skills[TASK_SKILL_NAME]], load_public_skills=False)
        return agent.model_copy(update={"agent_context": context})
    if engineering_guidance:
        context = AgentContext(system_message_suffix=load_engineering_guidance())
        return agent.model_copy(update={"agent_context": context})
    return agent


def guidance_delivery_evidence(
    agent: Any,
    task: str,
    *,
    engineering_guidance: bool,
    task_skill: bool,
    structured_guidance: bool,
    decision_guidance: bool = False,
) -> dict[str, Any]:
    """Describe prompt/Skill delivery without claiming observable agent use."""
    context = agent.agent_context
    available_skills = sorted(skill.name for skill in context.skills) if context else []
    triggered_skills: list[str] = []
    if context:
        activated = context.get_user_message_suffix(
            Message(role="user", content=[TextContent(text=task)]),
            skip_skill_names=[],
        )
        if activated is not None:
            _injected, triggered = activated
            triggered_skills = sorted(str(name) for name in triggered)

    engineering_text = load_engineering_guidance() if engineering_guidance else ""
    engineering_delivered = bool(
        context
        and engineering_text
        and context.system_message_suffix == engineering_text
    )
    maven_path = TASK_SKILL_DIR / MAVEN_SKILL_NAME / "SKILL.md"
    task_skill_path = TASK_SKILL_DIR / TASK_SKILL_NAME / "SKILL.md"
    decision_path = TASK_SKILL_DIR / DECISION_SKILL_NAME / "SKILL.md"
    return {
        "engineeringJudgment": {
            "configured": engineering_guidance,
            "available": engineering_delivered,
            "delivered": engineering_delivered,
            "observedUsed": "NOT_PROVEN",
            "sha256": (
                hashlib.sha256(DEFAULT_ENGINEERING_GUIDANCE.read_bytes()).hexdigest()
                if engineering_delivered
                else None
            ),
        },
        "mavenSkill": {
            "configured": structured_guidance or decision_guidance,
            "available": MAVEN_SKILL_NAME in available_skills,
            "delivered": MAVEN_SKILL_NAME in triggered_skills,
            "observedUsed": "NOT_PROVEN",
            "sha256": (
                hashlib.sha256(maven_path.read_bytes()).hexdigest()
                if MAVEN_SKILL_NAME in available_skills
                else None
            ),
        },
        "taskSkill": {
            "configured": task_skill,
            "available": TASK_SKILL_NAME in available_skills,
            "delivered": TASK_SKILL_NAME in triggered_skills,
            "observedUsed": "NOT_PROVEN",
            "sha256": (
                hashlib.sha256(task_skill_path.read_bytes()).hexdigest()
                if TASK_SKILL_NAME in available_skills
                else None
            ),
        },
        "decisionSkill": {"configured": decision_guidance,
                          "available": DECISION_SKILL_NAME in available_skills,
                          "delivered": DECISION_SKILL_NAME in triggered_skills,
                          "observedUsed": "NOT_PROVEN",
                          "sha256": (hashlib.sha256(decision_path.read_bytes()).hexdigest()
                                     if DECISION_SKILL_NAME in available_skills else None)},
        "availableSkills": available_skills,
        "triggeredSkills": triggered_skills,
    }


def configure_scanner_terminal(
    agent: Any,
    *,
    launcher_dir: Path,
    scanner_binary: Path | None = None,
    registry_url: str | None = None,
    validation_env: dict[str, str] | None = None,
) -> Any:
    """Give OpenHands the harness-owned launchers and fixed validation context."""
    shell = launcher_dir / "openhands-shell"
    shell.write_text("#!/bin/sh\nexec /bin/bash --norc \"$@\"\n", encoding="utf-8")
    shell.chmod(0o700)
    terminal_env = dict(validation_env or {})
    terminal_env["PATH"] = str(launcher_dir) + os.pathsep + os.environ.get("PATH", "")
    if scanner_binary is not None:
        terminal_env["OPENHANDS_OSV_EXECUTABLE"] = str(scanner_binary)
    if registry_url is not None:
        terminal_env["OPENHANDS_OSV_MAVEN_REGISTRY"] = registry_url
    configured_tools = []
    terminal_found = False
    for tool in agent.tools:
        if tool.name == "terminal":
            terminal_found = True
            params = dict(tool.params)
            params.update(
                {
                    "env": terminal_env,
                    "shell_path": str(shell),
                    "terminal_type": "subprocess",
                }
            )
            tool = tool.model_copy(update={"params": params})
        configured_tools.append(tool)
    if not terminal_found:
        raise SystemExit("OpenHands default agent does not expose the terminal tool")
    return agent.model_copy(update={"tools": configured_tools})


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
        task_skill=args.task_skill,
        structured_guidance=args.structured_guidance,
        decision_guidance=args.decision_guidance,
    )
    if args.engineering_judgment_guidance:
        print(f"ENGINEERING_JUDGMENT_GUIDANCE={DEFAULT_ENGINEERING_GUIDANCE}")
    if args.structured_guidance or args.decision_guidance:
        print(f"GENERAL_GUIDANCE={GENERAL_GUIDANCE}")
        print(f"REPOSITORY_GUIDANCE={PROJECT_GUIDANCE}")
        print(f"MAVEN_SKILL={TASK_SKILL_DIR / MAVEN_SKILL_NAME / 'SKILL.md'}")
    if args.decision_guidance:
        print(f"DECISION_SKILL={TASK_SKILL_DIR / DECISION_SKILL_NAME / 'SKILL.md'}")
    if args.task_skill:
        print(f"TASK_SKILL={TASK_SKILL_DIR / TASK_SKILL_NAME / 'SKILL.md'}")
    conversation = None
    resources = ExitStack()
    try:
        launcher_dir = state_dir / "scanner-bin"
        launcher_dir.mkdir(parents=True, exist_ok=True)
        validation_launcher = launcher_dir / "validate-remediation"
        shutil.copyfile(CONTROL_REPO / "scripts/openhands/validate-remediation", validation_launcher)
        validation_launcher.chmod(0o700)
        sbri_launcher = launcher_dir / "sbri"
        sbri_launcher.write_text(
            "#!/bin/sh\n"
            f"export PYTHONPATH={shlex.quote(str(CONTROL_REPO))}${{PYTHONPATH:+:$PYTHONPATH}}\n"
            f"exec {shlex.quote(sys.executable)} {shlex.quote(str(CONTROL_REPO / 'sbri'))} \"$@\"\n",
            encoding="utf-8",
        )
        sbri_launcher.chmod(0o700)
        terminal_validation_env = {
            "CONTROL_REPO": str(CONTROL_REPO),
            "GATE2_TARGET_REPO": str(target),
            "GATE2_STATE_FILE": str(baseline),
            "GATE2_SCANNER_EXECUTABLE": str(Path.home() / "bin" / "osv-scanner"),
            "GATE2_SELF_VALIDATION_ROOT": str(state_dir / "self-validation"),
        }
        if args.structured_guidance:
            local_repository = Path.home() / ".m2" / "repository"
            scanner_binary = Path.home() / "bin" / "osv-scanner"
            if (
                not local_repository.is_dir()
                or not scanner_binary.is_file()
                or not os.access(scanner_binary, os.X_OK)
            ):
                raise SystemExit(
                    "Maven-aware OSV launcher requires ~/.m2/repository and an executable "
                    "~/bin/osv-scanner"
                )
            registry_url, _registry_requests = resources.enter_context(
                serve_maven_repository((local_repository,))
            )
            launcher = launcher_dir / "osv-scanner"
            shutil.copyfile(CONTROL_REPO / "scripts/openhands/openhands-osv-scanner.sh", launcher)
            launcher.chmod(0o700)
            agent = configure_scanner_terminal(
                agent,
                launcher_dir=launcher_dir,
                scanner_binary=scanner_binary,
                registry_url=registry_url,
                validation_env=terminal_validation_env,
            )
            print(f"OPENHANDS_OSV_LAUNCHER={launcher}")
            print("OPENHANDS_OSV_REPOSITORY=local-maven")
        else:
            agent = configure_scanner_terminal(
                agent,
                launcher_dir=launcher_dir,
                validation_env=terminal_validation_env,
            )
        print(f"OPENHANDS_VALIDATION_LAUNCHER={validation_launcher}")
        print(f"OPENHANDS_SELF_VALIDATION_EVIDENCE={state_dir / 'self-validation'}")

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
        if args.structured_guidance:
            task += ("\n\nUse the available maven-dependency-evidence Skill when Maven dependency "
                     "or published-version facts materially affect your engineering decision. "
                     "Run `validate-remediation` for complete-project build, test, vulnerability, "
                     "and constraint validation, with detailed retained evidence paths.")
        if args.decision_guidance:
            task += ("\n\nBefore consequential remediation edits, use the "
                     "dependency-remediation-decision Skill to establish ownership, "
                     "investigate credible candidate effects, and predict original-finding "
                     "coverage and compatibility. Use the maven-dependency-evidence Skill "
                     "for current Maven release and resolution facts rather than remembered "
                     "versions. Choose the solution autonomously; use `validate-remediation` "
                     "for full-project self-validation.")
        if args.task_skill:
            task += (
                "\n\nBefore making consequential dependency-remediation changes, "
                "read and apply the available evidence-driven-dependency-remediation "
                "Agent Skill. It does not supersede the task constraints."
            )
        sbri_record = run_pre_edit_intelligence(
            control_repo=CONTROL_REPO,
            project=target,
            task=task,
            state_dir=state_dir,
            scanner=None if args.sbri_config else Path.home() / "bin" / "osv-scanner",
            config=args.sbri_config.expanduser().resolve() if args.sbri_config else None,
            release_versions=args.sbri_versions,
            release_ranges=args.sbri_range,
            max_candidates=args.sbri_max_candidates,
            enabled=args.sbri,
        )
        if sbri_record["status"] not in {"DISABLED", "NOT_APPLICABLE"}:
            task += "\n\n<SBRI_PRE_EDIT_EVIDENCE>\n" + agent_message(sbri_record) + \
                    "\n</SBRI_PRE_EDIT_EVIDENCE>"
        print("SBRI_INTEGRATION_EVIDENCE=" + json.dumps({
            key: sbri_record.get(key) for key in (
                "status", "invoked", "reused", "duplicateExecutionAvoided", "exitCode",
                "sourceUnchanged", "summaryPath", "resultPath", "reportPath", "evidencePath",
                "agentContextCharacters", "agentContextApproxTokens", "deliveredBeforeAgentRun",
                "rankForcedAsStrategy", "measurement", "outputBytes", "mavenCacheJarCount",
                "mavenCacheJarBytes", "releaseSelection", "request")
        }, sort_keys=True))
        require_valid_selection(sbri_record)
        print(f"OPENHANDS_SBRI_LAUNCHER={sbri_launcher}")
        print(
            "GUIDANCE_DELIVERY_EVIDENCE="
            + json.dumps(
                guidance_delivery_evidence(
                    agent,
                    task,
                    engineering_guidance=args.engineering_judgment_guidance,
                    task_skill=args.task_skill,
                    structured_guidance=args.structured_guidance,
                    decision_guidance=args.decision_guidance,
                ),
                sort_keys=True,
            )
        )
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
        try:
            if conversation is not None:
                conversation.close()
        finally:
            resources.close()


if __name__ == "__main__":
    raise SystemExit(main())
