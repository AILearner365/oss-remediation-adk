"""Controlled Intent repair cases for the existing acceptance runner (no delivery)."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json

from google.adk.agents.invocation_context import LlmCallsLimitExceededError

from autonomous_oss_remediation_agent.agent import (
    IntentToolRecoveryExhausted, IrrecoverableAgentSessionError, default_agent_session_factory,
)
from autonomous_oss_remediation_agent.capabilities import DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO
from autonomous_oss_remediation_agent.capabilities.isolation import ExperimentalIsolationUnavailable
from autonomous_oss_remediation_agent.capabilities.execution import BudgetExceeded
from autonomous_oss_remediation_agent.capabilities.research import HttpResearchProvider
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig, RuntimePolicy
from autonomous_oss_remediation_agent.journal import INTENT_SECTIONS, JournalLifecycle, JournalPhase, JournalStore
from autonomous_oss_remediation_agent.prompt import intent_questionnaire, intent_retry_message
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore

CASES = ("intent-missing-section", "intent-missing-answer")
TASK = (
    "Choose the compatible adapter mode for a fixture service from its diagnostic report. "
    "The allowed modes are stream and batch; the choice must match the observed report. "
    "Record the evidence and submit the normal Cycle Intent. This task requests a decision "
    "record only, with no implementation or delivery."
)
REPORT = "ADAPTER_MODE=stream\nThe fixture service consumes records incrementally; batch mode is not supported.\n"


def seed_answers(reference: str) -> list[dict]:
    """Substantive generic input; the live model never receives corrected answer objects."""
    texts = [
        "The service needs an adapter compatible with its observed diagnostic setting. "
        "The decision must use the report rather than guess a mode; implementation is outside this task.",
        "The diagnostic report identifies stream mode and incremental record consumption. "
        "It excludes batch mode. This supports a configuration decision, not a claim of runtime validation.",
        "The controlling consideration is compatibility with incremental consumption. "
        "Stream matches that requirement; batch is eliminated by the report rather than preference. "
        "No code change is needed for this decision-only task.",
        "One candidate is supported: stream mode. Batch is not a viable alternative under the observed contract. "
        "Compatibility evidence and future validation limits are recorded with the candidate.",
        "Select stream mode because it matches the observed diagnostic contract. "
        "A later implementation would still need to verify service behavior in its deployment environment.",
    ]
    answers = [{"section": section, "answer": text} for section, text in zip(INTENT_SECTIONS, texts)]
    answers[1]["evidence"] = [{
        "question": "Which adapter mode does the fixture support?", "source": reference,
        "finding": REPORT.strip(), "uncertainty": "Deployment behavior was not executed; the report supports the decision only.",
    }]
    answers[3]["candidates"] = [{
        "id": "stream_adapter", "name": "Stream adapter", "solution": "Choose stream mode for incremental consumption.",
        "evidence": f"The report specifies ADAPTER_MODE=stream and excludes batch ({reference}).",
        "constraints": "Matches the observed mode; no implementation or delivery is requested.",
        "validation": "Confirm the decision matches the report. Deployment testing would belong to a future implementation task.",
        "classification": "COMPLETE",
    }]
    answers[4]["selection"] = {
        "candidate_id": "stream_adapter", "rationale": "The observed report directly supports incremental stream processing.",
        "challenge": "The report does not prove behavior in a future deployment; verify that separately before claiming implementation success.",
    }
    return answers


def repository_digest(workspace: RunWorkspace) -> str:
    data = [(str(p.relative_to(workspace.repository)), hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(workspace.repository.rglob("*")) if p.is_file()]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


@dataclass
class RecoveryCase:
    trace: TraceStore
    budget: ExecutionBudget
    capabilities: DeveloperCapabilitySet
    lifecycle: JournalLifecycle
    seed: dict
    message: str
    checks: dict


def prepare_recovery(workspace: RunWorkspace, case: str) -> RecoveryCase:
    if case not in CASES:
        raise ValueError(f"Unknown Intent recovery case: {case}")
    workspace.repository.mkdir()
    (workspace.repository / "diagnostic.txt").write_text(REPORT, encoding="utf-8")
    trace = TraceStore(workspace)
    reference = trace.issue_evidence_reference(trace.write_text("fixture/diagnostic.txt", REPORT))
    before = repository_digest(workspace)
    # Same bounds as the existing retained-command fixture; no new limits or overrides.
    budget = ExecutionBudget(ExecutionBudgetConfig(
        max_cycles=1, max_tool_calls=80, max_llm_calls_per_turn=60, max_returned_output_chars=2000))
    lifecycle = JournalLifecycle(JournalStore(trace), trace, "Controlled generic Intent repair fixture",
                                 lambda: repository_digest(workspace) != before)
    lifecycle.append_task_to_solve(TASK)
    lifecycle.begin_cycle(1)
    capabilities = DeveloperCapabilitySet(
        WorkspaceIO(workspace, trace),
        ProcessRunner(workspace, trace, budget, RuntimePolicy(True, True, True, allow_network=False)),
        budget, trace, lifecycle, research_provider=HttpResearchProvider(enabled=False))
    capabilities.begin_cycle(1)
    answers = seed_answers(reference)
    if case == "intent-missing-section":
        answers[4].pop("section")
        expected_errors = ["answers[4].section: missing required 'section' field"]
        retained = answers[:4]
    else:
        for index in (3, 4):
            answers[index].pop("answer")
        expected_errors = [f"answers[{i}] (section: {INTENT_SECTIONS[i]}).answer: missing required 'answer' field"
                           for i in (3, 4)]
        retained = answers[:3]
    arguments = {"cycle_number": 1, "answers": answers}
    # This is a supported capability invocation, not an invented model/ADK event.
    trace.append_event("controlled_intent_seed", cycle=1, arguments=arguments,
                       origin="fixture", sessionId=None, case=case)
    response = capabilities.submit_cycle_intent(**arguments)
    continuation = intent_retry_message(1, list(lifecycle.cycles[1].last_intent_errors))
    draft = deepcopy(list(lifecycle._intent_drafts.get(1, {}).values()))
    denial = capabilities.edit_workspace_text("write", "pre-intent-probe.txt", content="must be denied",
                                              workspace="authoritative")
    checks = {
        "indexedShapeRejection": response["status"] == "rejected" and all(e in response["errors"] for e in expected_errors),
        "payloadSpecificGuidance": "content" not in json.dumps(response["errors"] + response["repairInstructions"]),
        "callbackContinuationAgree": all(e in continuation for e in response["errors"] + response["repairInstructions"]),
        "validDraftRetained": draft == retained,
        "preIntentMutationDenied": denial.get("failureCode") == "PHASE_CAPABILITY_UNAVAILABLE"
                                   and repository_digest(workspace) == before,
        "seedAccounting": lifecycle.cycles[1].intent_attempts == 1 and lifecycle.cycles[1].rejected_intents == 1
                          and lifecycle.phase == JournalPhase.INTENT_REQUIRED and lifecycle.cycles[1].intent is None,
    }
    seed = {"case": case, "classification": "controlled_integration", "arguments": arguments,
            "response": response, "continuation": continuation, "retainedDraft": draft,
            "mutationProbe": denial, "repositoryDigestBefore": before,
            "repositoryDigestAfterProbe": repository_digest(workspace), "checks": checks,
            "limits": {**asdict(budget.config), "max_checkpoint_attempts": lifecycle.max_checkpoint_attempts},
            "checkpointAttemptsAfterSeed": lifecycle.cycles[1].intent_attempts,
            "toolCallsAfterSeed": budget.tool_calls, "seedSessionId": None}
    trace.write_json("fixture/seed.json", seed)
    trace.append_event("controlled_seed_checked", cycle=1, checks=checks)
    message = (TASK + "\n\nThis controlled integration fixture submitted the following draft through "
               "the real capability before this model session. It was rejected; repair it using the "
               "supported tool and the feedback below.\n\nSubmitted payload:\n" + json.dumps(arguments, indent=2)
               + "\n\nActual capability response:\n" + json.dumps(response, indent=2)
               + "\n\n" + continuation + "\n\n" + intent_questionnaire(1))
    trace.write_text("fixture/model-input.txt", message)
    return RecoveryCase(trace, budget, capabilities, lifecycle, seed, message, checks)


def score_recovery(fixture: RecoveryCase, *, live: bool, terminal_error: Exception | None = None,
                   stop_reason: str = "not_run") -> dict:
    from scripts.retained_evidence_acceptance import _accepted_intent_answers, _interaction_payload
    trace, lifecycle, budget = fixture.trace, fixture.lifecycle, fixture.budget
    events = [_interaction_payload(trace, json.loads(line)) for line in trace.events_path.read_text(encoding="utf-8").splitlines()]
    acceptance = next((e for e in events if e["type"] == "intent_submission_accepted" and e["cycle"] == 1), None)
    boundary = events.index(acceptance) if acceptance else len(events)
    prior = events[:boundary]
    calls = [e for e in prior if e.get("interactionType") == "tool_call" and e.get("name") == "submit_cycle_intent"
             and e.get("cycle") == 1 and e.get("arguments", {}).get("cycle_number") == 1]
    # Pure replay projection: the retained seed remains explicitly fixture-originated.
    # No synthetic calls/responses are inserted into ADK session state or its trace.
    replay = [{**e, "type": "adk_interaction", "interactionType": "tool_call", "name": "submit_cycle_intent"}
              if e["type"] == "controlled_intent_seed" else e for e in events]
    merged = _accepted_intent_answers(replay, lifecycle, acceptance) if acceptance else None
    attempts = [e for e in prior if e["type"] == "checkpoint_attempt_recorded" and e.get("checkpoint") == "intent"]
    sessions = sorted({e["sessionId"] for e in events if e.get("type") == "adk_interaction" and e.get("sessionId")})
    turns = sum(e.get("interactionType") == "turn_started" for e in events)
    seed_ok = all(fixture.checks.values())
    checks = {**fixture.checks,
              "acceptedRecordVerified": merged is not None,
              "liveResubmissionObserved": bool(calls),
              "sameSessionAndCycle": len(sessions) == 1 and all(e.get("cycle") == 1 for e in events if e.get("type") == "adk_interaction"),
              "attemptAccounting": [e["attempt"] for e in attempts] == list(range(1, len(attempts) + 1))
                                   and len(attempts) == lifecycle.cycles[1].intent_attempts,
              "withinLimits": lifecycle.cycles[1].intent_attempts <= lifecycle.max_checkpoint_attempts
                              and budget.tool_calls <= budget.config.max_tool_calls
                              and budget.elapsed_seconds <= budget.config.overall_timeout_seconds}
    exhausted = isinstance(terminal_error, (BudgetExceeded, IntentToolRecoveryExhausted, LlmCallsLimitExceededError)) or stop_reason in {
        "checkpoint_attempts_exhausted", "continuation_turns_exhausted"}
    # Provider/auth/session failures block live observation; generic fixture errors fail it.
    infrastructure = recovery_blocked(terminal_error)
    if not seed_ok:
        outcome = "FAILED"
    elif not live:
        outcome = "NOT_EXERCISED"
    elif infrastructure:
        outcome = "BLOCKED"
    else:
        outcome = "PASSED" if all(checks.values()) and terminal_error is None else "FAILED"
    last_sections = {item.get("section", "").strip() for item in calls[-1].get("arguments", {}).get("answers", [])
                     if isinstance(item, dict) and isinstance(item.get("section"), str)} if calls else set()
    section_only = bool(acceptance and last_sections and last_sections < set(INTENT_SECTIONS))
    return {"classification": "controlled_integration", "outcome": outcome,
            "passed": outcome == "PASSED" if live else seed_ok,
            "offlineMechanics": "PASSED" if seed_ok else "FAILED",
            "controlledLiveIntegration": outcome if live else "NOT_EXERCISED",
            "naturalAutonomousRecovery": "NOT_EXERCISED", "checks": checks,
            "checkpointAccepted": acceptance is not None, "sectionOnlyRepairObserved": section_only,
            "acceptedSubmissionKind": ("section_only" if section_only else "complete_or_other") if acceptance else None,
            "acceptedContentHash": acceptance.get("contentHash") if acceptance else None,
            "checkpointAttempts": lifecycle.cycles[1].intent_attempts, "seedCheckpointAttempts": 1,
            "attemptEvents": attempts, "sessionIds": sessions, "seedSessionId": None, "cycle": 1,
            "continuationTurns": turns, "toolCalls": budget.tool_calls,
            "elapsedSeconds": budget.elapsed_seconds, "limits": fixture.seed["limits"],
            "recoveryExhausted": exhausted, "stopReason": stop_reason,
            "terminalError": f"{type(terminal_error).__name__}: {terminal_error}" if terminal_error else None,
            "unexercisedPaths": [name for name, done in (("natural_autonomous_recovery", False),
                                  ("controlled_live_recovery", live and acceptance is not None),
                                  ("section_only_repair", section_only)) if not done],
            "trace": str(trace.events_path)}


def recovery_blocked(error: Exception | None) -> bool:
    """Distinguish unavailable infrastructure from fixture/model failures."""
    if isinstance(error, (IrrecoverableAgentSessionError, ExperimentalIsolationUnavailable)):
        return True
    if error is None:
        return False
    module = type(error).__module__
    return (module.startswith(("google.auth", "httpx")) or
            (module.startswith("google.genai") and getattr(error, "code", None) in
             {401, 403, 408, 429, 500, 502, 503, 504}))


async def run_recovery(fixture: RecoveryCase, model: str) -> dict:
    from scripts.retained_evidence_acceptance import run_until_intent
    session = None
    error = None
    stop = "seed_checks_failed"
    if all(fixture.checks.values()):
        try:
            session = default_agent_session_factory(fixture.capabilities, model)
            continuation = await run_until_intent(session, fixture.lifecycle, fixture.message)
            stop = continuation["stopReason"]
        except Exception as exc:
            error, stop = exc, "terminal_error"
        finally:
            if session is not None:
                try:
                    await session.close()
                except Exception as exc:
                    error = error or exc
    return score_recovery(fixture, live=True, terminal_error=error, stop_reason=stop)
