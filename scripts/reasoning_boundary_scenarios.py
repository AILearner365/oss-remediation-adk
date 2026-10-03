"""Controlled evidence, autonomous decisions; development-only acceptance cases."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from autonomous_oss_remediation_agent.agent import default_agent_session_factory
from autonomous_oss_remediation_agent.capabilities import DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO
from autonomous_oss_remediation_agent.capabilities.research import ResearchResult, ResearchStatus
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig, RemediationRequest, RuntimePolicy
from autonomous_oss_remediation_agent.journal import JournalLifecycle, JournalStore
from autonomous_oss_remediation_agent.models import ConstraintBaseline, RepositoryBaseline, ScanReport, VulnerabilityFinding
from autonomous_oss_remediation_agent.prompt import canonical_task_to_solve, intent_questionnaire
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore
from scripts.intent_recovery_scenarios import recovery_blocked, repository_digest

CASES = ("finding-coverage", "evidence-conflict")
OFFICIAL_URL = "https://atlas.example/releases/4.0"
OFFICIAL = (
    "Controlled fixture publisher record, not a real-world release claim.\n"
    "Atlas Runtime 4.0 is an official public release. The publisher supports the 4.x line.\n"
    "This release record establishes availability only. Compatibility with this repository's "
    "legacy adapter has not been evaluated.\n"
)
PROJECT = (
    "Controlled fixture repository. Runtime: Atlas Runtime 4.0.\n"
    "The current runtime must be preserved. Legacy adapter compatibility is unresolved.\n"
    "An old, unverified maintainer note says: 'I expect only Atlas 3.x to be official; "
    "4.x is probably custom.' No evidence accompanies that expectation.\n"
)
COVERAGE = (
    "Controlled fixture support record for example:gateway, current version 2.4.0.\n"
    "Within the 2.4 line, fixes are cumulative. 2.4.2 fixes FINDING-A and FINDING-B. "
    "2.4.5 additionally fixes FINDING-C. Both versions are published and support "
    "the project's API and runtime. The root gateway.version setting controls the dependency; "
    "no module overrides exist. Tests after implementation remain necessary.\n"
)


class FixtureResearch:
    """Inject source acquisition only; normal capability retention/feedback stays active."""
    def search(self, query):
        return ResearchResult(ResearchStatus.BLOCKED, "https://search.example/", error="Source returned a bot challenge",
                              failure_code="BOT_CHALLENGE", http_status=202, acquisition_succeeded=True,
                              raw_content="Controlled bot challenge", recovery="Use another accessible source or preserve uncertainty.")

    def fetch(self, url):
        if url == OFFICIAL_URL:
            return ResearchResult(ResearchStatus.SUCCESS, url, content=OFFICIAL, raw_content=OFFICIAL,
                                  acquisition_succeeded=True, http_status=200)
        return ResearchResult(ResearchStatus.UNAVAILABLE, url, error="Source outside controlled fixture")


@dataclass
class DecisionCase:
    case: str
    trace: TraceStore
    budget: ExecutionBudget
    capabilities: DeveloperCapabilitySet
    lifecycle: JournalLifecycle
    message: str
    evidence: dict


def prepare_decision(workspace: RunWorkspace, case: str) -> DecisionCase:
    if case not in CASES:
        raise ValueError(case)
    workspace.repository.mkdir()
    trace = TraceStore(workspace)
    budget = ExecutionBudget(ExecutionBudgetConfig(max_cycles=1, max_tool_calls=80,
                            max_llm_calls_per_turn=60, max_returned_output_chars=2000))
    evidence = {}
    if case == "finding-coverage":
        (workspace.repository / "settings.conf").write_text("gateway.version=2.4.0\n", encoding="utf-8")
        (workspace.repository / "support.txt").write_text(COVERAGE, encoding="utf-8")
        findings = tuple(VulnerabilityFinding("FINDING-" + label, (), "HIGH", "example", "gateway",
                         "example:gateway", "2.4.0", (fixed,))
                         for label, fixed in [("A", "2.4.2"), ("B", "2.4.2"), ("C", "2.4.5")])
        request = RemediationRequest(repository_url="https://fixture.example/project")
        baseline = RepositoryBaseline(str(workspace.repository), "fixture", "main", request.repository_url,
                       (), ScanReport(True, findings, None, "fixture"), ConstraintBaseline(), findings)
        task = canonical_task_to_solve(request, baseline)
        reference = trace.issue_evidence_reference(trace.write_text("fixture/support.txt", COVERAGE))
        evidence = {"supportReference": reference, "support": COVERAGE}
        task += "\n\nControlled fixture scope: record the intended remediation decision only; do not implement or deliver. " \
                "The support record and repository files are supplied evidence for this synthetic project.\n" + json.dumps(evidence)
    else:
        (workspace.repository / "project.txt").write_text(PROJECT, encoding="utf-8")
        task = ("# Task to Solve\n\nDecide how to investigate unresolved legacy adapter compatibility in this "
                "Atlas Runtime 4.0 project while preserving the current runtime. Establish the available "
                "release evidence and a supported next action. Record a normal Cycle Intent, without "
                "implementation or delivery. This is a synthetic fixture: publisher evidence is authoritative "
                "within this scenario only. Repository context:\n" + PROJECT)
    before = repository_digest(workspace)
    lifecycle = JournalLifecycle(JournalStore(trace), trace, "Controlled reasoning boundary", lambda: repository_digest(workspace) != before)
    lifecycle.append_task_to_solve(task)
    lifecycle.begin_cycle(1)
    capabilities = DeveloperCapabilitySet(WorkspaceIO(workspace, trace),
        ProcessRunner(workspace, trace, budget, RuntimePolicy(True, True, True, allow_network=False)),
        budget, trace, lifecycle, research_provider=FixtureResearch())
    capabilities.begin_cycle(1)
    if case == "evidence-conflict":
        # Explicit fixture-originated acquisition, never model-originated tool history or a seeded Intent.
        for name, args in [("research_search", {"query": "Atlas Runtime official 4.x availability"}),
                           ("research_fetch", {"url": OFFICIAL_URL})]:
            response = getattr(capabilities, name)(**args)
            trace.append_event("controlled_evidence_acquisition", origin="fixture", name=name, arguments=args, response=response)
            evidence[name] = response
        task += "\n\nCaptured research through the production capabilities:\n" + json.dumps(evidence, indent=2)
    message = task + "\n\n" + intent_questionnaire(1)
    trace.write_text("fixture/model-input.txt", message)
    trace.write_json("fixture/setup.json", {"case": case, "evidence": evidence, "limits": asdict(budget.config),
                     "checkpointAttempts": lifecycle.cycles[1].intent_attempts, "origin": "controlled_fixture"})
    return DecisionCase(case, trace, budget, capabilities, lifecycle, message, evidence)


def score_decision(fixture, *, live=False, error=None, stop="not_run"):
    from scripts.retained_evidence_acceptance import _interaction_payload, _accepted_intent_answers
    events = [_interaction_payload(fixture.trace, json.loads(line)) for line in fixture.trace.events_path.read_text().splitlines()]
    accepted = next((e for e in events if e.get("type") == "intent_submission_accepted" and e.get("cycle") == 1), None)
    answers = _accepted_intent_answers(events, fixture.lifecycle, accepted) if accepted else None
    selected = None
    if answers:
        sections = {a['section']: a for a in answers}
        selection = sections['Selected solution']['selection']
        selected = next(c for c in sections['Concrete candidate solutions']['candidates'] if c['id'] == selection['candidate_id'])
        fixture.trace.write_json("fixture/accepted-decision.json", {"acceptedContentHash": accepted['contentHash'],
                                 "answers": answers, "selectedCandidate": selected, "selection": selection})
    outcome = "NOT_EXERCISED" if not live else "BLOCKED" if recovery_blocked(error) else "FAILED" if error or not answers else "NOT_EXERCISED"
    return {"passed": not live, "captureOnly": True,
            "outcome": outcome, "classification": "controlled_evidence_autonomous_decision",
            "offlineMechanics": "PASSED", "decisionReview": "PENDING" if answers else "NOT_EXERCISED",
            "capture": "PASSED" if answers else "NOT_EXERCISED" if not live else outcome,
            "acceptedRecordVerified": answers is not None,
            "acceptedContentHash": accepted.get('contentHash') if accepted else None,
            "selectedCandidate": selected, "stopReason": stop,
            "terminalError": f"{type(error).__name__}: {error}" if error else None,
            "toolCalls": fixture.budget.tool_calls, "checkpointAttempts": fixture.lifecycle.cycles[1].intent_attempts,
            "elapsedSeconds": fixture.budget.elapsed_seconds,
            "naturalEndToEnd": "NOT_EXERCISED",
            "reviewRequired": "Inspect accepted-decision.json, cited evidence and pre-acceptance trace using catalogue criteria. Capture is not reasoning acceptance."}


async def run_decision(fixture, model):
    from scripts.retained_evidence_acceptance import run_until_intent
    session, error, stop = None, None, "not_started"
    try:
        session = default_agent_session_factory(fixture.capabilities, model)
        stop = (await run_until_intent(session, fixture.lifecycle, fixture.message))["stopReason"]
    except Exception as exc:
        error = exc
    finally:
        if session:
            try:
                await session.close()
            except Exception as exc:
                error = error or exc
    return score_decision(fixture, live=True, error=error, stop=stop)


REVIEW_CRITERIA = {
    "finding-coverage": ("all_findings", "selected_solution_coverage", "constraints", "cited_support", "validation_limits"),
    "evidence-conflict": ("authoritative_availability", "blocked_is_not_absence", "expectation_reconciled",
                          "compatibility_uncertain", "selected_action_and_citations"),
}


def retain_review(workspace, review):
    """Bind explicit human/agent semantic review to the verified accepted record.

    This validates review completeness/integrity, not the truth of the reviewer's prose.
    No regex, candidate-name heuristic or second model judges reasoning automatically.
    """
    import hashlib
    from pathlib import Path
    from autonomous_oss_remediation_agent.journal import render_checkpoint
    artifacts = Path(workspace) / 'artifacts'
    result = json.loads((artifacts / 'acceptance-result.json').read_text())
    decision = json.loads((artifacts / 'fixture/accepted-decision.json').read_text())
    expected = (render_checkpoint(1, 'Problem Analysis and Solution Decision', decision['answers']).rstrip() + '\n\n').encode()
    digest = hashlib.sha256(expected).hexdigest()
    if (not result['acceptedRecordVerified'] or digest != result['acceptedContentHash']
            or digest != decision['acceptedContentHash'] or digest != review.get('acceptedContentHash')
            or expected not in (artifacts / 'agent/decision-journal.md').read_bytes()):
        raise ValueError('Review does not bind to the verified accepted journal')
    sections = {item['section']: item for item in decision['answers']}
    selection = sections['Selected solution']['selection']
    selected = next(item for item in sections['Concrete candidate solutions']['candidates']
                    if item['id'] == selection['candidate_id'])
    if selected != decision['selectedCandidate'] or selection != decision['selection']:
        raise ValueError('Exported selection differs from the accepted answers')
    if review.get('selectedCandidateId') != decision['selectedCandidate']['id']:
        raise ValueError('Review must assess the accepted selected candidate')
    criteria = review.get('criteria', {})
    if set(criteria) != set(REVIEW_CRITERIA[result['scenario']]):
        raise ValueError('Review must cover every scenario criterion')
    for value in criteria.values():
        if (value.get('status') not in {'PASSED', 'FAILED', 'BLOCKED', 'NOT_EXERCISED'}
                or not value.get('rationale') or not value.get('evidence')):
            raise ValueError('Each criterion requires status, rationale and artifact/trace evidence')
    statuses = {c['status'] for c in criteria.values()}
    outcome = next((s for s in ('FAILED', 'BLOCKED', 'NOT_EXERCISED') if s in statuses), 'PASSED')
    reviewed = {**result, 'passed': outcome == 'PASSED', 'outcome': outcome,
                'decisionReview': review, 'reviewMethod': 'explicit semantic review; not automated proof'}
    (artifacts / 'reviewed-result.json').write_text(json.dumps(reviewed, indent=2) + '\n')
    return reviewed


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Retain a semantic review bound to an accepted decision')
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(retain_review(args.workspace, json.loads(args.review.read_text())), indent=2))
