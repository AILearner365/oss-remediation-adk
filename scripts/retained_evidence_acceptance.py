"""Small retained-evidence fixture. Live mode is opt-in and uses a model."""
from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from autonomous_oss_remediation_agent.agent import GoogleAdkAgentSession, create_remediation_agent
from autonomous_oss_remediation_agent.capabilities import DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO
from autonomous_oss_remediation_agent.capabilities.research import HttpResearchProvider
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig, RuntimePolicy
from autonomous_oss_remediation_agent.journal import JournalLifecycle, JournalStore
from autonomous_oss_remediation_agent.prompt import intent_questionnaire
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


FACT = "ADAPTER_MODE=stream"
QUESTION = (
    "# Task to Solve\n\nChoose the compatible adapter mode, `stream` or `batch`, "
    "for this fixture service. A captured diagnostic report contains the controlling "
    "ADAPTER_MODE setting. The mode must be supported by that report; guessing is not "
    "acceptable. Record the evidence and submit the normal Cycle Intent checkpoint."
)


def prepare(parent: Path):
    workspace = RunWorkspace.create(parent)
    workspace.repository.mkdir()
    generator = workspace.repository / "emit_report.py"
    generator.write_text(
        "import sys\n"
        "sys.stdout.write('progress=unrelated\\n' * 7000)\n"
        f"sys.stdout.write({FACT!r} + '\\n')\n"
        "sys.stdout.write('progress=unrelated\\n' * 9000)\n",
        encoding="utf-8",
    )
    trace = TraceStore(workspace)
    budget = ExecutionBudget(ExecutionBudgetConfig(
        max_cycles=1, max_tool_calls=80, max_llm_calls_per_turn=60,
        max_returned_output_chars=2000,
    ))
    runner = ProcessRunner(workspace, trace, budget, RuntimePolicy(
        trusted_repository=True, dedicated_runner=True,
        enable_autonomous_shell=True, allow_network=False,
    ))
    capabilities = DeveloperCapabilitySet(
        WorkspaceIO(workspace, trace), runner, budget, trace,
        research_provider=HttpResearchProvider(enabled=False),
    )
    try:
        result = capabilities.run_workspace_shell("python emit_report.py")
    finally:
        generator.unlink()
    if result.get("exitCode") != 0 or not result.get("stdoutReference"):
        raise RuntimeError(f"Fixture command failed: {result.get('stderr', result)}")
    if FACT in result["stdout"] or result["stdoutComplete"]:
        raise RuntimeError("Fixture fact leaked into the displayed excerpt")
    display = {key: result[key] for key in (
        "stdout", "stdoutReference", "stdoutBytes", "stdoutComplete",
        "stdoutMoreExists", "stdoutRecovery", "remainingToolCalls",
    )}
    return workspace, trace, budget, capabilities, display


def verify_offline(capabilities: DeveloperCapabilitySet, display: dict) -> dict:
    before = capabilities.budget.tool_calls
    found = capabilities.retrieve_retained_evidence(display["stdoutReference"], query="ADAPTER_MODE=")
    if found.get("status") != "ok" or len(found["matches"]) != 1:
        raise RuntimeError(f"Targeted retrieval failed: {found}")
    match = found["matches"][0]
    if FACT not in match["text"] or match["offset"] < 100_000:
        raise RuntimeError("Relevant fact was not recovered from the omitted middle")
    if len(match["text"]) > 400 or capabilities.budget.tool_calls != before + 1:
        raise RuntimeError("Targeted retrieval exceeded its bounded output or call cost")
    if found["remainingToolCalls"] != capabilities.budget.config.max_tool_calls - capabilities.budget.tool_calls:
        raise RuntimeError("Reported remaining tool allowance is incorrect")
    retained = capabilities.trace.resolve_evidence_reference(display["stdoutReference"])
    if retained.stat().st_size != found["totalBytes"] or FACT not in retained.read_text(encoding="utf-8"):
        raise RuntimeError("Full retained artifact is unavailable")
    return {"artifactBytes": found["totalBytes"], "matchOffset": match["offset"],
            "contextChars": len(match["text"]), "toolCallsConsumed": 1,
            "remainingToolCalls": found["remainingToolCalls"], "fullArtifactRetained": True}


async def verify_live(trace: TraceStore, budget: ExecutionBudget,
                      capabilities: DeveloperCapabilitySet, display: dict, model: str) -> dict:
    lifecycle = JournalLifecycle(JournalStore(trace), trace, "Generic retained-evidence acceptance fixture",
                                 lambda: False)
    lifecycle.append_task_to_solve(QUESTION)
    lifecycle.begin_cycle(1)
    capabilities.journal = lifecycle
    capabilities.begin_cycle(1)
    session = GoogleAdkAgentSession(
        create_remediation_agent(capabilities, model), budget, trace=trace,
        cycle_provider=lambda: lifecycle.active_cycle,
    )
    message = (QUESTION + "\n\nCaptured diagnostic command evidence (its stdout excerpt is incomplete):\n"
               + json.dumps(display, indent=2) + "\n\n" + intent_questionnaire(1))
    try:
        await session.run_turn(message)
    finally:
        await session.close()
    events = [json.loads(line) for line in trace.events_path.read_text(encoding="utf-8").splitlines()]
    targeted = [event for event in events if event.get("type") == "adk_interaction"
                and event.get("interactionType") == "tool_call"
                and event.get("name") == "retrieve_retained_evidence"
                and event.get("arguments", {}).get("reference") == display["stdoutReference"]
                and event.get("arguments", {}).get("query")]
    recovered = [event for event in events if event.get("type") == "adk_interaction"
                 and event.get("interactionType") == "tool_response"
                 and event.get("name") == "retrieve_retained_evidence"
                 and event.get("response", {}).get("reference") == display["stdoutReference"]
                 and any(FACT in match.get("text", "")
                         for match in event.get("response", {}).get("matches", []))]
    accepted_events = [event for event in events if event.get("type") == "intent_submission_accepted"]
    accepted = bool(accepted_events and recovered and
                    accepted_events[0]["timestamp"] > recovered[0]["timestamp"])
    recorded = lifecycle.cycles[1].intent_answers if accepted else {}
    used_fact = FACT in json.dumps(recorded)
    return {"targetedRetrievalCalls": len(targeted), "intentAccepted": accepted,
            "targetedResponseContainedFact": bool(recovered),
            "acceptedIntentUsesRecoveredFact": used_fact,
            "liveTraceMeetsMechanicalCriteria": bool(targeted and accepted and used_fact),
            "remainingToolCalls": budget.config.max_tool_calls - budget.tool_calls}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Opt in to a paid model turn")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--workspace-parent", type=Path,
                        help="Retain live trace here; offline runs use a temporary directory")
    args = parser.parse_args()
    if args.live and args.workspace_parent is None:
        parser.error("--live requires --workspace-parent so its trace is retained")
    temporary = tempfile.TemporaryDirectory() if not args.live else None
    try:
        parent = args.workspace_parent if args.live else Path(temporary.name)
        workspace, trace, budget, capabilities, display = prepare(parent)
        if args.live:
            result = asyncio.run(verify_live(trace, budget, capabilities, display, args.model))
            result["workspace"] = str(workspace.root)
            print(json.dumps(result, indent=2))
            return 0 if result["liveTraceMeetsMechanicalCriteria"] else 1
        print(json.dumps(verify_offline(capabilities, display), indent=2))
        return 0
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
