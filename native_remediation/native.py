"""Standalone native SDK 1.55.1 configuration. No HTTP transport or model loop."""
import json
from pathlib import Path
import shlex
import sys

from .files import Blocked
from . import guidance

VERSION = "1.55.1"
ENTRY = Path(__file__).with_name("__main__.py").resolve()
INSTRUCTIONS = """One native autonomous agent owns investigation, strategy, implementation,
self-validation and reassessment. The task controls constraints; domain Skills
supply evidence methods, not prescribed versions or a fixed solution recipe.
At a material strategy choice/change, preserve a concise rationale and observations
using cycle_evidence(record_type=decision), or normal native messages. Do not write
a questionnaire for every command, small edit or debugging step.
At completion, preserve a concise outcome and remaining uncertainty. Optional
structured records help recovery but never establish acceptance.
Use validate_remediation for whole-project self-checks when useful; only the
separate native Stop event can independently accept the actual candidate tree.
Use sbri_intelligence only when it resolves relevant uncertainty; rank is not a
mandatory framework upgrade or a compatibility verdict.
Do not modify trusted task/policy/baseline/acceptance/claims or handle credentials.
Do not push or create PRs. report_only never delivers; draft_pr requires explicit
authorization and independent PASS. Respect bounds and report honest failure.
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
    from .agent_tools import ValidateRemediationTool, SbriIntelligenceTool

    if any(version(p) != VERSION for p in ("openhands-sdk", "openhands-tools")):
        raise Blocked("Require installed standalone SDK/tools 1.55.1")
    persisted = state / "conversations" / UUID(bound["conversationId"]).hex / "base_state.json"
    if any((state / name).exists() for name in ("preparation-intent.json", "preparation.json", "runs")) and not persisted.is_file():
        raise Blocked("Native SDK persistence missing; never replace the prepared conversation")
    workspace = state / "workspace"
    workspace.mkdir(exist_ok=True, mode=0o700)
    agent = Agent(llm=LLM(model=task["model"], usage_id="oss-remediation",
                         stream=False, num_retries=0, timeout=120),
        tools=[Tool(name=TerminalTool.name, params=dict(terminal_type="subprocess")),
               Tool(name=TaskTrackerTool.name), Tool(name=CycleEvidenceTool.name),
               Tool(name=ValidateRemediationTool.name), Tool(name=SbriIntelligenceTool.name)],
        system_prompt_kwargs=dict(cli_mode=True), agent_context=AgentContext(
            skills=guidance.load(task), system_message_suffix=system_context(task), load_user_skills=False,
            load_public_skills=False, load_project_skills=False, load_memory=False))
    conversation = Conversation(agent=None if persisted.is_file() else agent,
        workspace=LocalWorkspace(working_dir=workspace),
        conversation_id=UUID(bound["conversationId"]), persistence_dir=state / "conversations",
        hook_config=hook_config(state, task), max_iteration_per_run=task["limits"]["max_iterations"],
        visualizer=None)
    # SDK reloads persisted state by ID; refuse stale/different agent settings.
    actual = conversation.state
    if (str(actual.id) != bound["conversationId"]
            or Path(actual.workspace.working_dir) != workspace
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
            or [t.name for t in actual.agent.tools] != ["terminal", "task_tracker", "cycle_evidence", "validate_remediation", "sbri_intelligence"]
            or actual.agent.agent_context.system_message_suffix != system_context(task)):
        raise Blocked("Effective native hooks/tools/context differ; no model execution allowed")


def system_context(task):
    return guidance.general() + "\n\n" + INSTRUCTIONS + "\nApproved project context (verify observed facts):\n" + task["guidance"]["project_context"]


def task_message(state, bound, task, baseline):
    message = ("Maven dependency vulnerability remediation. Task and constraints (stable):\n" + json.dumps(task, indent=2)
        + "\nApproved base: " + task["base_sha"]
        + "\nBaseline findings: " + json.dumps(baseline["findings"])
        + "\nEvidence references are relative to the task state (parent of this workspace): baseline.json, baseline/, native conversations/, self-validation/, sbri/. Read evidence; never alter trusted records."
        + "\nUse validate_remediation for complete-project self-checks; it never accepts or delivers."
        + "\nNative terminal executes on the host; edit via ordinary shell tools. It is not a sandbox."
        + "\nUse authorized host networking/proxies for Maven, OSV and research."
        + "\nRepository is the terminal's initial directory. Use /tmp for scratch files."
        + "\nOptional decision record: strategy, rationale; observations/evidence_refs optional."
        + "\nOptional outcome: summary, goal_status; remaining_uncertainty/evidence_refs optional."
        + "\nSet goal_status to candidate_ready or bounded_failure; only the trusted gate can accept success."
        + "\nOptional SBRI/research references are capabilities, not a mandated strategy.")
    intelligence = state / "sbri-pre-edit.json"
    if intelligence.exists():
        from .files import read
        message += "\nPre-edit SBRI evidence (bounded scope, not a strategy):\n" + json.dumps(read(intelligence))
    return message
