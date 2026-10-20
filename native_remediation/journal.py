"""Agent-authored concise evidence/intent/outcome, not hidden chain of thought."""
import time

from .contract import context
from .files import Blocked, read, write
from .repository import snapshot, text

INTENT_FIELDS = {"facts", "uncertainties", "assumptions", "success_criteria", "candidates", "chosen_strategy", "rationale"}
OUTCOME_FIELDS = {"changes", "self_checks", "observations", "goal_status", "next_action"}


def record(state, kind, document):
    state, bound, task = context(state)
    if kind == "decision" or kind == "outcome" and isinstance(document, dict) and "summary" in document:
        return decision_record(state, bound, task, kind, document)
    if kind not in ("intent", "outcome"):
        raise Blocked("Record intent or outcome")
    journal = state / "journal"
    journal.mkdir(exist_ok=True, mode=0o700)
    intents = sorted(journal.glob("*.intent.json"))
    if kind == "intent":
        number = len(intents) + 1
        if number > task["limits"]["max_cycles"]:
            raise Blocked("Cycle budget exhausted")
        tree = snapshot(state / "workspace", task)
        if number == 1 and tree != text(state / "workspace", "rev-parse", task["base_sha"] + "^{tree}"):
            raise Blocked("First cycle intent must precede material edits")
        if number > 1:
            previous = read(journal / f"{number - 1}.outcome.json")
            if previous["tree"] != tree:
                raise Blocked("Unrecorded changes after previous cycle outcome")
        fields = INTENT_FIELDS
    else:
        number = len(intents)
        if not number:
            raise Blocked("Cycle intent required first")
        tree = snapshot(state / "workspace", task)
        fields = OUTCOME_FIELDS
    if not isinstance(document, dict) or set(document) != fields or any(not v for v in document.values()):
        raise Blocked("Incomplete cycle " + kind + ": require " + ", ".join(sorted(fields)))
    if kind == "intent" and (not isinstance(document["candidates"], list) or not document["candidates"]):
        raise Blocked("Record credible whole-goal candidates (one is acceptable if justified)")
    if kind == "outcome" and document["goal_status"] not in ("candidate_ready", "bounded_failure"):
        raise Blocked("Outcome goal_status must be candidate_ready or bounded_failure")
    evidence = dict(conversationId=bound["conversationId"], taskDigest=bound["taskDigest"],
                    cycle=number, kind=kind, tree=tree, recordedAt=time.time(), document=document)
    write(journal / f"{number}.{kind}.json", evidence, exclusive=True)
    return evidence


def final_outcome(state, tree):
    _, bound, _ = context(state)
    modern = sorted((state / "journal").glob("outcome-*.json"))
    decisions = list((state / "journal").glob("decision-*.json"))
    if modern:
        outcome = read(modern[-1])
        if (outcome["tree"] == tree and outcome["conversationId"] == bound["conversationId"]
                and outcome["taskDigest"] == bound["taskDigest"]):
            return outcome
    intents = list((state / "journal").glob("*.intent.json"))
    if not intents:
        # Absence/staleness is recorded honestly. Native Finish requests testing;
        # no agent report (or this fallback) constitutes independent acceptance.
        return dict(conversationId=bound["conversationId"], taskDigest=bound["taskDigest"],
            tree=tree, cycle=len(decisions), source="native_stop_request", document=dict(
                goal_status="candidate_ready", summary="No current explicit outcome record",
                remaining_uncertainty="Not supplied; inspect native trajectory and independent validation"))
    outcome = read(state / "journal" / f"{len(intents)}.outcome.json")
    if (outcome["tree"] != tree or outcome["taskDigest"] != bound["taskDigest"]
            or outcome["conversationId"] != bound["conversationId"]):
        raise Blocked("Cycle outcome does not describe the submitted candidate tree")
    return outcome


def decision_record(state, bound, task, kind, document):
    required = {"strategy", "rationale"} if kind == "decision" else {"summary", "goal_status"}
    allowed = required | ({"observations", "evidence_refs"} if kind == "decision"
                          else {"remaining_uncertainty", "evidence_refs"})
    if (not isinstance(document, dict) or not required <= set(document) <= allowed
            or any(not isinstance(document[k], str) or not document[k].strip() for k in required)
            or len(str(document)) > 12000):
        raise Blocked("Record a concise material decision/outcome, not a per-command questionnaire")
    if kind == "outcome" and document["goal_status"] not in ("candidate_ready", "bounded_failure"):
        raise Blocked("Outcome is candidate_ready or bounded_failure; only validation can accept")
    refs = document.get("evidence_refs", [])
    from pathlib import Path
    if (not isinstance(refs, list) or any(not isinstance(r, str) or not r or Path(r).is_absolute()
            or ".." in Path(r).parts or not (state / r).resolve().is_relative_to(state)
            or not (state / r).exists() for r in refs)):
        raise Blocked("Evidence references must name retained, task-local artifacts")
    journal = state / "journal"
    number = len(list(journal.glob(kind + "-*.json"))) + 1
    if number > task["limits"]["max_decisions"] + (task["limits"]["max_cycles"] if kind == "outcome" else 0):
        raise Blocked("Decision/outcome evidence budget exhausted")
    result = dict(conversationId=bound["conversationId"], taskDigest=bound["taskDigest"], kind=kind,
        tree=snapshot(state / "workspace", task), cycle=(number if kind == "decision" else
        len(list(journal.glob("decision-*.json")))), recordedAt=time.time(), document=document)
    write(journal / f"{kind}-{number:04d}.json", result, exclusive=True)
    return result
