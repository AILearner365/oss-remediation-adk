"""Agent-authored concise evidence/intent/outcome, not hidden chain of thought."""
import time

from .contract import context
from .files import Blocked, read, write
from .repository import snapshot, text

INTENT_FIELDS = {"facts", "uncertainties", "assumptions", "success_criteria", "candidates", "chosen_strategy", "rationale"}
OUTCOME_FIELDS = {"changes", "self_checks", "observations", "goal_status", "next_action"}


def record(state, kind, document):
    state, bound, task = context(state)
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
    intents = list((state / "journal").glob("*.intent.json"))
    if not intents:
        raise Blocked("Record a cycle intent and honest outcome before finishing")
    outcome = read(state / "journal" / f"{len(intents)}.outcome.json")
    if (outcome["tree"] != tree or outcome["taskDigest"] != bound["taskDigest"]
            or outcome["conversationId"] != bound["conversationId"]):
        raise Blocked("Cycle outcome does not describe the submitted candidate tree")
    return outcome
