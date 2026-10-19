"""Short-lived preparation, native submission, explicit dispatch and Stop gate."""
import time
import uuid

from .contract import context, load_task
from .delivery import deliver
from .files import Blocked, digest, lock, read, write
from .journal import final_outcome
from .native import request_config, task_message, verify_effective
from .repository import check_paths, prepare, snapshot, text, verify_base
from .validation import compare, evaluate


def prepare_task(task, state):
    task = load_task(task)
    state = state.expanduser().resolve()
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    bound = dict(task=task, taskDigest=digest(task), conversationId=str(uuid.uuid4()), createdAt=time.time())
    write(state / "task.json", bound, exclusive=True)
    workspace = prepare(state, task)
    (state / "agent").mkdir(mode=0o700)
    tree = text(workspace, "rev-parse", task["base_sha"] + "^{tree}")
    baseline = evaluate(workspace, tree, task, state / "baseline", deadline=min(
        bound["createdAt"] + task["limits"]["task_seconds"], time.time() + task["limits"]["validation_seconds"]))
    write(state / "baseline.json", baseline, exclusive=True)
    if baseline["outcome"] != "COMPLETE":
        write(state / "result.json", dict(outcome="BLOCKED", reasons=baseline["reasons"]))
        raise Blocked("Baseline incomplete; inspect evidence, no model dispatch permitted")
    return bound


def attach(state, native, *, reconcile=False):
    state, bound, task = context(state)
    with lock(state):
        baseline = read(state / "baseline.json")
        if baseline["outcome"] != "COMPLETE":
            raise Blocked("Complete deterministic baseline required")
        if snapshot(state / "workspace", task) != baseline["tree"]:
            raise Blocked("Workspace changed before native attachment")
        native.versions()
        config = request_config(state, bound, task)
        uid = bound["conversationId"]
        if reconcile:
            if read(state / "submission.json")["request"] != config:
                raise Blocked("Persisted submission differs; cannot reconcile")
            actual = native.request("GET", f"/api/conversations/{uid}")
            if actual["execution_status"] != "idle":
                raise Blocked("Only idle attachment can be reconciled")
            events = native.request("GET", f"/api/conversations/{uid}/events/search?limit=100&sort_order=TIMESTAMP")
            rows = events.get("items", [])
            messages = [e for e in rows if e.get("kind") == "MessageEvent"]
            if (events.get("next_page_id") or len(rows) >= 100
                    or any(e.get("kind") in ("ActionEvent", "ObservationEvent") for e in rows)
                    or len(messages) > 1):
                raise Blocked("Ambiguous/executed native history; do not replay attachment")
            if messages and messages[0].get("llm_message", {}).get("content") != [dict(type="text",
                    text=task_message(state, bound, task, baseline))]:
                # Native content adds serialization defaults such as cache_prompt.
                content = messages[0].get("llm_message", {}).get("content", [])
                if len(content) != 1 or content[0].get("text") != task_message(state, bound, task, baseline):
                    raise Blocked("Existing native message differs from bound task")
        else:
            write(state / "submission.json", dict(state="CREATE_INTENT", request=config), exclusive=True)
            native.request("POST", "/api/conversations?include_skills=true", config)
            messages = []
        # This initializes pending hooks without inference in 1.55.1.
        if not messages:
            native.request("POST", f"/api/conversations/{uid}/events", dict(role="user", run=False,
                content=[dict(type="text", text=task_message(state, bound, task, baseline))]))
        actual = native.request("GET", f"/api/conversations/{uid}")
        verify_effective(actual, config)
        if actual["execution_status"] != "idle":
            raise Blocked("Unexpected native execution during idle attachment")
        if not (state / "attached.json").exists():
            write(state / "attached.json", dict(conversationId=uid, effectiveHooksVerified=True), exclusive=True)
        return dict(conversationId=uid, status="idle")


def dispatch(state, native, *, resume_reason=None):
    state, bound, task = context(state)
    with lock(state):
        if (state / "result.json").exists() or (state / "delivery.json").exists():
            raise Blocked("Task has a result/delivery intent; inspect or reconcile, do not run")
        if time.time() >= bound["createdAt"] + task["limits"]["task_seconds"]:
            raise Blocked("Task time budget exhausted")
        read(state / "attached.json")
        runs = list((state / "runs").glob("*.json"))
        if (runs and not resume_reason) or len(runs) >= task["limits"]["max_runs"]:
            raise Blocked("Run already claimed or run budget exhausted; explicit bounded recovery required")
        verify_base(task)
        if not runs and snapshot(state / "workspace", task) != read(state / "baseline.json")["tree"]:
            raise Blocked("Workspace drifted before the first model dispatch")
        uid = bound["conversationId"]
        native.versions()
        actual = native.request("GET", f"/api/conversations/{uid}")
        verify_effective(actual, request_config(state, bound, task))
        if actual["execution_status"] not in ("idle", "paused", "stuck", "error"):
            raise Blocked("Native conversation is running/terminal; never dispatch again")
        if resume_reason:
            for reservation in (state / "attempts").glob("*/intent.json"):
                validation = reservation.with_name("validation.json")
                if not validation.exists():
                    write(validation, dict(outcome="INCONCLUSIVE", reasons=["Interrupted attempt; explicit recovery: " + resume_reason],
                        validatedTree=read(reservation)["tree"], attempt=int(reservation.parent.name)), exclusive=True)
            # Explicitly authorized recovery carries evidence, not a new reasoning engine.
            feedback = read(state / "feedback.json") if (state / "feedback.json").exists() else {}
            native.request("POST", f"/api/conversations/{uid}/events", dict(role="user", run=False,
                content=[dict(type="text", text="Bounded recovery: " + resume_reason
                    + "\nStable task digest: " + bound["taskDigest"]
                    + "\nGoal: " + task["goal"] + "\nAcceptance policy: " + str(task["policy"])
                    + "\nCurrent candidate tree: " + snapshot(state / "workspace", task)
                    + "\nReview journal intent/outcome, current Git state and feedback: " + str(feedback)
                    + "\nReassess the whole goal; do not automatically repeat the prior strategy.")]))
        write(state / "runs" / f"{len(runs) + 1}.json", dict(conversationId=uid,
            state="RUN_INTENT", reason=resume_reason, at=time.time()), exclusive=True)
        native.request("POST", f"/api/conversations/{uid}/run", {})
        return dict(conversationId=uid, dispatched=True)


def hook(state, event, *, evaluator=evaluate, delivery=deliver):
    state, bound, task = context(state)
    with lock(state):
        if (event.get("event_type") != "Stop" or event.get("session_id") != bound["conversationId"]
                or event.get("metadata", {}).get("reason") != "agent_finished"
                or event.get("working_dir") != str(state / "workspace")):
            raise Blocked("Native Stop event identity mismatch")
        workspace = state / "workspace"
        tree = snapshot(workspace, task)
        outcome = final_outcome(state, tree)
        if outcome["document"]["goal_status"] == "bounded_failure":
            write(state / "result.json", dict(outcome="BOUNDED_FAILURE", conversationId=bound["conversationId"], journal=outcome))
            return dict(decision="allow", reason="BOUNDED FAILURE recorded; not accepted, no delivery")
        changed = check_paths(workspace, task, tree)
        if not changed:
            raise Blocked("No deliverable change; report bounded failure rather than success")
        attempts = state / "attempts"
        previous = sorted(attempts.glob("*/validation.json"), key=lambda p: int(p.parent.name))
        if any(not p.with_name("validation.json").exists() for p in attempts.glob("*/intent.json")):
            raise Blocked("Interrupted validation reservation; explicit bounded resume required, no automatic rescan")
        if previous:
            accepted = read(previous[-1])
            if accepted["outcome"] == "PASS" and accepted["validatedTree"] == tree:
                delivered = delivery(state, accepted)
                write(state / "result.json", dict(outcome="DELIVERED", **delivered))
                return dict(decision="allow", reason="Independent PASS; draft PR confirmed: " + delivered["prUrl"])
            if accepted["validatedTree"] == tree and accepted.get("cycle") == outcome["cycle"]:
                return dict(decision="deny", reason="Candidate already rejected in this cycle",
                    additionalContext="Review recorded validation feedback and reassess before a new bounded cycle; no repeated scan was run.")
        if (state / "delivery.json").exists():
            raise Blocked("Delivery already claimed for another candidate; reconcile before continuing")
        number = len(list(attempts.glob("*/intent.json"))) + 1
        expired = time.time() >= bound["createdAt"] + task["limits"]["task_seconds"]
        if number > task["limits"]["max_cycles"] or expired:
            result = dict(outcome="BOUNDED_FAILURE", reason="Validation/time budget exhausted", conversationId=bound["conversationId"])
            write(state / "result.json", result)
            return dict(decision="allow", reason="BOUNDED FAILURE; not accepted, no delivery")
        attempt = attempts / str(number)
        # Reserve before expensive commands. An interrupted reservation is not retried.
        write(attempt / "intent.json", dict(tree=tree, at=time.time()), exclusive=True)
        evaluation_dir = attempt / "candidate"
        candidate = evaluator(workspace, tree, task, evaluation_dir, deadline=min(
            bound["createdAt"] + task["limits"]["task_seconds"], time.time() + task["limits"]["validation_seconds"]))
        write(attempt / "evaluation.json", candidate)
        result = compare(read(state / "baseline.json"), candidate, task["policy"])
        accepted = dict(result, conversationId=bound["conversationId"], taskDigest=bound["taskDigest"],
            baseCommit=task["base_sha"], validatedTree=tree, attempt=number, cycle=outcome["cycle"], changedFiles=changed)
        write(attempt / "validation.json", accepted, exclusive=True)
        write(state / "feedback.json", accepted)
        if accepted["outcome"] != "PASS":
            if number >= task["limits"]["max_cycles"]:
                write(state / "result.json", dict(outcome="BOUNDED_FAILURE", validation=accepted))
                return dict(decision="allow", reason="BOUNDED FAILURE; independent validation did not pass; no delivery")
            return dict(decision="deny", reason="Independent " + accepted["outcome"],
                        additionalContext="Reassess facts/candidates and record the next bounded cycle. "
                        + str(accepted["reasons"])[:3000])
        delivered = delivery(state, accepted)
        write(state / "result.json", dict(outcome="DELIVERED", **delivered))
        return dict(decision="allow", reason="Independent PASS; draft PR confirmed: " + delivered["prUrl"])


def status(state, native=None):
    state, bound, task = context(state)
    result = read(state / "result.json") if (state / "result.json").exists() else dict(outcome="PENDING")
    native_status, usage = None, None
    if native:
        observed = native.request("GET", f"/api/conversations/{bound['conversationId']}")
        native_status, usage = observed["execution_status"], observed.get("stats")
    # A native fail-open finish without independent evidence is explicitly blocked.
    if native_status in ("finished", "stuck", "error") and result["outcome"] == "PENDING":
        result = dict(outcome="BLOCKED" if native_status == "finished" else "BOUNDED_FAILURE",
                      reason="Native terminal without trusted acceptance/delivery result",
                      feedback=read(state / "feedback.json") if (state / "feedback.json").exists() else None)
    if result["outcome"] == "DELIVERED":
        claim = read(state / "delivery.json")
        accepted = read(state / "attempts" / str(read(state / "feedback.json")["attempt"]) / "validation.json")
        if claim.get("state") != "DELIVERED" or accepted["outcome"] != "PASS" or claim["validatedTree"] != accepted["validatedTree"]:
            raise Blocked("Delivery result lacks exact-tree independent acceptance")
        if native_status != "finished":
            result = dict(result, outcome="DELIVERED_AWAITING_NATIVE_FINISH")
    return dict(conversationId=bound["conversationId"], goal=task["goal"],
                nativeStatus=native_status, modelUsage=usage, result=result,
                validation=read(state / "feedback.json") if (state / "feedback.json").exists() else None,
                evidence=dict(baseline="baseline.json", cycles="journal/", attempts="attempts/", delivery="delivery.json"))
