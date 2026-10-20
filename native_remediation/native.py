"""Standalone native SDK 1.55.1 configuration. No HTTP transport or model loop."""
import json
from pathlib import Path
import shlex
import sys

from .files import Blocked

VERSION = "1.55.1"
ENTRY = Path(__file__).with_name("__main__.py").resolve()
INSTRUCTIONS = """You are the single autonomous engineering agent for this contract.
Discover read-only before changing code. Separate facts, assumptions and uncertainty.
Use actual dependency ownership: direct, managed, imported BOM, override, transitive,
relocated or unmanaged. Investigate decision-critical unknowns with repository,
execution and current authoritative research when available. A failed tool call
does not prove absence. Consider credible whole-goal solutions, select a strategy
on evidence, then implement and reassess it; never force a Spring Boot upgrade.
Before each cycle's first material edit, record intent through the cycle_evidence
tool. Record an honest outcome and self-checks before FinishTool. Record concise
evidence and rationale, not private chain of thought. On validation feedback,
reconsider candidates and goal, carry forward evidence, and record a new bounded
cycle if a different approach is needed. Agent self-checks never authorize delivery.
After any Stop denial the old container shell has been stopped. Use terminal
reset=true on your next terminal call to start a fresh isolated shell.
Do not change the trusted task, validator, baseline, claims or evidence; do not
commit, push, create PRs or handle credentials. Trusted Stop validation captures
and tests your exact candidate tree and delivers only independent PASS. Respect
limits. If unable to satisfy the goal, report an evidence-backed bounded failure.
"""


def hook_config(state, task):
    from openhands.sdk.hooks import HookConfig
    hook = shlex.join([sys.executable, str(ENTRY), "hook", "--state", str(state)])
    return HookConfig(stop=[dict(matcher="*", hooks=[dict(type="command", command=hook,
        timeout=task["limits"]["validation_seconds"] + 300)])])


def open_conversation(state, bound, task):
    """Official local SDK factory: initialization/resume never calls run()."""
    from importlib.metadata import version
    from uuid import UUID
    from openhands.sdk import Agent, AgentContext, Conversation, LLM, Tool
    from openhands.sdk.workspace import LocalWorkspace
    from openhands.tools.terminal import TerminalTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from .evidence_tool import CycleEvidenceTool
    from .sandbox import launcher

    if any(version(p) != VERSION for p in ("openhands-sdk", "openhands-tools")):
        raise Blocked("Require installed standalone SDK/tools 1.55.1")
    persisted = state / "conversations" / UUID(bound["conversationId"]).hex / "base_state.json"
    if any((state / name).exists() for name in ("preparation-intent.json", "preparation.json", "runs")) and not persisted.is_file():
        raise Blocked("Native SDK persistence missing; never replace the prepared conversation")
    control = state / "control"
    control.mkdir(exist_ok=True, mode=0o700)
    agent = Agent(llm=LLM(model=task["model"], usage_id="oss-remediation",
                         stream=False, num_retries=0, timeout=120),
        tools=[Tool(name=TerminalTool.name, params=dict(terminal_type="subprocess",
                    shell_path=str(launcher(state)))),
               Tool(name=TaskTrackerTool.name), Tool(name=CycleEvidenceTool.name)],
        system_prompt_kwargs=dict(cli_mode=True), agent_context=AgentContext(
            system_message_suffix=INSTRUCTIONS, load_user_skills=False,
            load_public_skills=False, load_project_skills=False, load_memory=False))
    conversation = Conversation(agent=None if persisted.is_file() else agent,
        workspace=LocalWorkspace(working_dir=control),
        conversation_id=UUID(bound["conversationId"]), persistence_dir=state / "conversations",
        hook_config=hook_config(state, task), max_iteration_per_run=task["limits"]["max_iterations"],
        visualizer=None)
    # SDK reloads persisted state by ID; refuse stale/different agent settings.
    actual = conversation.state
    if (str(actual.id) != bound["conversationId"]
            or Path(actual.workspace.working_dir) != control
            # SDK-generated prompt time is persisted context, not task policy.
            or actual.agent.model_dump(mode="json", exclude={"agent_context": {"current_datetime"}})
                != agent.model_dump(mode="json", exclude={"agent_context": {"current_datetime"}})
            or actual.max_iterations != task["limits"]["max_iterations"]):
        conversation.close()
        raise Blocked("Persisted SDK identity/workspace/model/tools differ")
    return conversation


def verify_ready(conversation, state, task):
    """After SDK lazy initialization, reject unexpected hooks/MCP/plugins/tools."""
    actual = conversation.state
    if (actual.hook_config != hook_config(state, task) or actual.agent.mcp_config
            or [t.name for t in actual.agent.tools] != ["terminal", "task_tracker", "cycle_evidence"]
            or actual.agent.agent_context.system_message_suffix != INSTRUCTIONS):
        raise Blocked("Effective native hooks/tools/context differ; no model execution allowed")


def task_message(state, bound, task, baseline):
    return ("Task and constraints (stable):\n" + json.dumps(task, indent=2)
        + "\nApproved base: " + task["base_sha"]
        + "\nRead-only baseline in terminal: /baseline.json and /baseline/"
        + "\nBaseline findings: " + json.dumps(baseline["findings"])
        + "\nResolved graphs and effective POMs are in the baseline evidence directory."
        + "\nUse cycle_evidence(record_type=intent|outcome, document={...}) for cycle records."
        + "\nNative terminal runs in an offline isolated container; edit via ordinary shell tools."
        + "\nRepository is the terminal's initial directory. Use /tmp for scratch files."
        + "\nIntent fields: facts, uncertainties, assumptions, success_criteria, candidates (list), chosen_strategy, rationale."
        + "\nOutcome fields: changes, self_checks, observations, goal_status, next_action."
        + "\nSet goal_status to candidate_ready or bounded_failure; only the trusted gate can accept success."
        + "\nUse explicit 'none established' statements when appropriate; do not invent facts."
        + "\nOptional SBRI/research references are capabilities, not a mandated strategy.")
