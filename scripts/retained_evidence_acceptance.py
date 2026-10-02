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
from autonomous_oss_remediation_agent.journal import JournalLifecycle, JournalPhase, JournalStore
from autonomous_oss_remediation_agent.prompt import intent_questionnaire, intent_retry_message
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


FACT = "ADAPTER_MODE=stream"
QUESTION = (
    "# Task to Solve\n\nChoose the compatible adapter mode, `stream` or `batch`, "
    "for this fixture service. A captured diagnostic report contains the controlling "
    "ADAPTER_MODE setting. The mode must be supported by that report; guessing is not "
    "acceptable. Record the evidence and submit the normal Cycle Intent checkpoint."
)


def prepare(parent: Path, workspace: RunWorkspace | None = None):
    workspace = workspace or RunWorkspace.create(parent)
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


def verify_partial_read_offline(workspace: RunWorkspace, trace: TraceStore) -> dict:
    """Exercise actual current-revision read/edit protections on a generic file."""
    workspace.repository.mkdir(exist_ok=True)
    path = workspace.repository / "settings.conf"
    path.write_text("mode=slow\n" + "".join(f"item.{n}=keep\n" for n in range(900))
                    + "[unrelated]\nsentinel=preserve\n", encoding="utf-8")
    io = WorkspaceIO(workspace, trace)
    first = io.read_text("settings.conf")
    if not first["moreExists"] or first["readReceipt"] is not None:
        raise RuntimeError("The fixture did not produce a partial read")
    rejected = {}
    for label, receipt in (("missing", None), ("fabricated", first["fileSha256"])):
        try:
            io.edit_text("write", "settings.conf", content="mode=fast\n", read_receipt=receipt)
        except ValueError as exc:
            rejected[label] = str(exc)
    if len(rejected) != 2:
        raise RuntimeError("Missing or fabricated receipt permitted an existing-file rewrite")
    next_line, next_column = first["nextStartLine"], first["nextStartColumn"]
    pages = 1
    last = first
    while last["moreExists"]:
        last = io.read_text("settings.conf", start_line=next_line, start_column=next_column)
        next_line, next_column = last["nextStartLine"], last["nextStartColumn"]
        pages += 1
    if not last["readCoverageComplete"] or not last["readReceipt"]:
        raise RuntimeError("Complete current-revision read did not issue a receipt")
    io.edit_text("replace", "settings.conf", old_text="mode=slow", new_text="mode=fast")
    if "sentinel=preserve" not in path.read_text(encoding="utf-8"):
        raise RuntimeError("Targeted edit lost the unrelated trailing section")
    try:
        io.edit_text("write", "settings.conf", content="mode=fast\n", read_receipt=last["readReceipt"])
    except ValueError:
        rejected["stale"] = "rejected"
    if "stale" not in rejected:
        raise RuntimeError("Stale receipt permitted a later rewrite")
    return {"readPages": pages, "missingReceiptRejected": True,
            "fabricatedReceiptRejected": True, "staleReceiptRejected": True,
            "trailingSentinelPreserved": True}


async def run_until_intent(session, lifecycle: JournalLifecycle, message: str) -> dict:
    """Mirror production's bounded same-session Intent continuation."""
    turns = 0
    for _ in range(lifecycle.max_checkpoint_attempts):
        await session.run_turn(message)
        turns += 1
        if lifecycle.phase == JournalPhase.EXECUTION:
            return {"turns": turns, "stopReason": "accepted"}
        capture = lifecycle.cycles[lifecycle.active_cycle]
        if capture.intent_attempts >= lifecycle.max_checkpoint_attempts:
            return {"turns": turns, "stopReason": "checkpoint_attempts_exhausted"}
        errors = list(capture.last_intent_errors) or [
            "No Problem Analysis and Solution Decision submission was received in the previous turn"
        ]
        message = intent_retry_message(lifecycle.active_cycle, errors)
    return {"turns": turns, "stopReason": "continuation_turns_exhausted"}


def score_live_trace(trace: TraceStore, lifecycle: JournalLifecycle, display: dict,
                     budget: ExecutionBudget, continuation: dict) -> dict:
    events = [json.loads(line) for line in trace.events_path.read_text(encoding="utf-8").splitlines()]
    calls = [event for event in events if event.get("type") == "adk_interaction"
             and event.get("interactionType") == "tool_call"]
    targeted = [event for event in calls if event.get("name") == "retrieve_retained_evidence"
                and event.get("arguments", {}).get("reference") == display["stdoutReference"]
                and event.get("arguments", {}).get("query")]
    recovered = [event for event in events if event.get("type") == "adk_interaction"
                 and event.get("interactionType") == "tool_response"
                 and event.get("name") == "retrieve_retained_evidence"
                 and event.get("response", {}).get("reference") == display["stdoutReference"]
                 and any(FACT in match.get("text", "")
                         for match in event.get("response", {}).get("matches", []))]
    accepted = [event for event in events if event.get("type") == "intent_submission_accepted"]
    rejected = [event for event in events if event.get("type") == "intent_submission_rejected"]
    accepted_after_retrieval = bool(accepted and recovered and
                                    accepted[0]["timestamp"] > recovered[0]["timestamp"])
    submissions = [event for event in calls if event.get("name") == "submit_cycle_intent"]
    selected_consistent = False
    provenance = False
    if accepted_after_retrieval and submissions:
        answers = submissions[-1].get("arguments", {}).get("answers", [])
        by_section = {item.get("section"): item for item in answers if isinstance(item, dict)}
        selected = by_section.get("Selected solution", {}).get("selection", {})
        candidate_id = selected.get("candidate_id") if isinstance(selected, dict) else None
        candidates = by_section.get("Concrete candidate solutions", {}).get("candidates", [])
        candidate = next((item for item in candidates if item.get("id") == candidate_id), {})
        selected_text = " ".join(str(candidate.get(key, "")) for key in ("name", "solution"))
        selected_consistent = "stream" in selected_text.lower() and "batch" not in selected_text.lower()
        evidence = by_section.get("Information, investigation and remaining uncertainty", {}).get("evidence", [])
        provenance = any(FACT in str(item.get("finding", "")) and
                         display["stdoutReference"] in str(item.get("source", ""))
                         for item in evidence if isinstance(item, dict))
    retrieval_success = bool(targeted and recovered)
    evidence_supported = bool(accepted_after_retrieval and selected_consistent and provenance)
    return {
        "retrievalSuccess": retrieval_success,
        "targetedRetrievalCalls": len(targeted),
        "noCheckpointSubmission": not submissions,
        "rejectedSubmissions": len(rejected),
        "recoveryExhausted": continuation["stopReason"] in {
            "checkpoint_attempts_exhausted", "continuation_turns_exhausted"},
        "checkpointAccepted": bool(accepted),
        "acceptedAfterRetrieval": accepted_after_retrieval,
        "selectedCandidateConsistentWithFact": selected_consistent,
        "selectedEvidenceCitesIssuedReference": provenance,
        "evidenceSupportedSelectedDecision": evidence_supported,
        "liveTraceMeetsMechanicalCriteria": retrieval_success and evidence_supported,
        "checkpointAttempts": lifecycle.cycles[1].intent_attempts,
        "continuationTurns": continuation["turns"],
        "stopReason": continuation["stopReason"],
        "remainingToolCalls": budget.config.max_tool_calls - budget.tool_calls,
        "trace": str(trace.events_path),
        "unexercisedPaths": [name for name, exercised in (
            ("checkpoint_submission", bool(submissions)),
            ("checkpoint_rejection", bool(rejected)),
            ("incomplete_turn", continuation["turns"] > 1),
            ("accepted_checkpoint", bool(accepted)),
        ) if not exercised],
    }


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
        continuation = await run_until_intent(session, lifecycle, message)
        return score_live_trace(trace, lifecycle, display, budget, continuation)
    except Exception as exc:
        events = [json.loads(line) for line in trace.events_path.read_text(encoding="utf-8").splitlines()]
        turns = sum(event.get("type") == "adk_interaction" and
                    event.get("interactionType") == "turn_started" for event in events)
        result = score_live_trace(trace, lifecycle, display, budget,
                                  {"turns": turns, "stopReason": "terminal_error"})
        result["terminalError"] = f"{type(exc).__name__}: {exc}"
        result["liveTraceMeetsMechanicalCriteria"] = False
        return result
    finally:
        await session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Opt in to a paid model trial")
    parser.add_argument("--scenario", choices=("retained-command", "partial-read-edit"),
                        default="retained-command")
    parser.add_argument("--trials", type=int, default=1, help="Independent workspaces and sessions")
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--workspace-parent", type=Path,
                        help="Retain live trace here; offline runs use a temporary directory")
    args = parser.parse_args()
    if not 1 <= args.trials <= 10:
        parser.error("--trials must be between 1 and 10")
    if args.live and args.workspace_parent is None:
        parser.error("--live requires --workspace-parent so its trace is retained")
    if args.live and args.scenario != "retained-command":
        parser.error("Live partial-read/edit orchestration is deferred; run its offline boundary check")
    temporary = tempfile.TemporaryDirectory() if args.workspace_parent is None else None
    try:
        parent = args.workspace_parent if args.live else Path(temporary.name)
        results = []
        for trial in range(1, args.trials + 1):
            workspace = None
            try:
                if args.scenario == "partial-read-edit":
                    workspace = RunWorkspace.create(parent)
                    trace = TraceStore(workspace)
                    result = verify_partial_read_offline(workspace, trace)
                else:
                    workspace = RunWorkspace.create(parent)
                    workspace, trace, budget, capabilities, display = prepare(parent, workspace)
                    result = (asyncio.run(verify_live(trace, budget, capabilities, display, args.model))
                              if args.live else verify_offline(capabilities, display))
                result["passed"] = (result["liveTraceMeetsMechanicalCriteria"] if args.live else True)
            except Exception as exc:
                result = {"passed": False, "terminalError": f"{type(exc).__name__}: {exc}"}
            result.update({"scenario": args.scenario, "trial": trial,
                           "workspace": str(workspace.root) if workspace else None,
                           "artifactsRetained": temporary is None})
            if workspace:
                result.setdefault("trace", str(workspace.artifacts / "events.jsonl"))
            results.append(result)
        print(json.dumps({"mode": "live" if args.live else "offline", "trials": results}, indent=2))
        return 0 if all(result["passed"] for result in results) else 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
