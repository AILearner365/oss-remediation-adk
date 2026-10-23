"""Standalone SDK initialization/preparation/run gate and independent native Stop."""
import time
import uuid

from .contract import context, load_task
from .delivery import deliver
from .files import Blocked, digest, lock, read, write, require_independent_authority
from .journal import final_outcome
from .native import task_message
from .repository import check_paths, prepare, snapshot, text, verify_base
from .validation import compare, evaluate, require_baseline


def prepare_task(task, state, *, factory=None, preparer=None, evaluator=None):
    """Create an idle native conversation, then deterministic preparation only.

    An interrupted preparation is never silently repeated. No task message or
    model execution is possible here.
    """
    from pathlib import Path
    from .native import open_conversation
    default_preparation = preparer is None and evaluator is None
    factory = factory or open_conversation
    preparer = preparer or prepare
    evaluator = evaluator or evaluate
    task = load_task(task)
    state = Path(state).expanduser().resolve()
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    bound = dict(task=task, taskDigest=digest(task), conversationId=str(uuid.uuid4()),
                 executionFramework="standalone-sdk-1.55.1", createdAt=time.time())
    write(state / "task.json", bound, exclusive=True)
    conversation = factory(state, bound, task)
    try:
        if factory is open_conversation:
            from .guidance import delivery_evidence
            write(state / "guidance.json", delivery_evidence(conversation.agent.agent_context,
                task_message(state, bound, task, dict(findings=[]))))
        with lock(state):
            write(state / "preparation-intent.json", dict(conversationId=bound["conversationId"],
                  taskDigest=bound["taskDigest"], at=time.time()), exclusive=True)
            if default_preparation:
                require_independent_authority()
            workspace = preparer(state, task)
            tree = text(workspace, "rev-parse", task["base_sha"] + "^{tree}")
            baseline = evaluator(workspace, tree, task, state / "baseline", deadline=min(
                bound["createdAt"] + task["limits"]["task_seconds"],
                time.time() + task["limits"]["validation_seconds"]))
            write(state / "baseline.json", baseline, exclusive=True)
            require_baseline(baseline, tree, task)
            if task["sbri"]["pre_edit"]:
                from .capabilities import sbri
                # SBRI holds its own evidence lock; run below outside this lock.
                intelligence_pending = True
            else:
                intelligence_pending = False
            receipt = dict(outcome="COMPLETE", conversationId=bound["conversationId"],
                taskDigest=bound["taskDigest"], repository=task["repository"],
                baseCommit=task["base_sha"], baseTree=tree, baselineDigest=digest(baseline),
                completedAt=time.time())
        if intelligence_pending:
            write(state / "sbri-pre-edit.json", sbri(state), exclusive=True)
        with lock(state):
            receipt.update(completedAt=time.time(), sbriDigest=digest(read(state / "sbri-pre-edit.json"))
                           if (state / "sbri-pre-edit.json").exists() else None)
            write(state / "preparation.json", receipt, exclusive=True)
            require_preparation(state)
        return bound
    finally:
        from .evidence import capture
        try:
            capture(state, "preparation", conversation)
        finally:
            conversation.close()


def require_preparation(state):
    """Revalidate durable evidence on every run/recovery, never trust a message."""
    state, bound, task = context(state)
    try:
        receipt = read(state / "preparation.json")
        baseline = read(state / "baseline.json")
    except (FileNotFoundError, ValueError):
        raise Blocked("Preparation/baseline evidence missing or invalid; no model execution permitted") from None
    expected = dict(outcome="COMPLETE", conversationId=bound["conversationId"],
        taskDigest=bound["taskDigest"], repository=task["repository"], baseCommit=task["base_sha"],
        baseTree=text(state / "workspace", "rev-parse", task["base_sha"] + "^{tree}"),
        baselineDigest=digest(baseline))
    require_baseline(baseline, expected["baseTree"], task)
    if "sbriDigest" in receipt:
        expected["sbriDigest"] = digest(read(state / "sbri-pre-edit.json")) if (state / "sbri-pre-edit.json").exists() else None
    packages = baseline.get("inventory", {}).get("packages", [])
    count = len({(p["name"], p["version"]) for p in packages})
    if (bound.get("executionFramework") != "standalone-sdk-1.55.1"
            or any(receipt.get(k) != v for k, v in expected.items())
            or baseline.get("outcome") != "COMPLETE" or baseline.get("tree") != receipt["baseTree"]
            or not count
            or not bound["createdAt"] <= receipt.get("completedAt", 0) <= time.time()
            or time.time() >= bound["createdAt"] + task["limits"]["task_seconds"]):
        raise Blocked("Preparation missing, incomplete, stale or identity/evidence mismatch")
    return state, bound, task


def dispatch(state, *, resume_reason=None, factory=None, preflight=None):
    """Application gate around the official SDK run; OpenHands owns every step."""
    import fcntl
    from .native import open_conversation
    from .preflight import check
    factory = factory or open_conversation
    preflight = preflight or check
    state, bound, task = require_preparation(state)
    require_independent_authority()
    # A separate lifetime lock avoids deadlocking synchronous Stop/journal hooks.
    with (state / "execution.lock").open("a") as execution:
        try:
            fcntl.flock(execution, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked("Another SDK process owns this task; never execute concurrently") from None
        with lock(state):
            require_preparation(state)
            if (state / "result.json").exists() or (state / "delivery.json").exists():
                raise Blocked("Task has a result/delivery intent; reconcile, do not run")
            runs = list((state / "runs").glob("*.json"))
            if ((runs and not resume_reason) or (resume_reason and not runs)
                    or len(runs) >= task["limits"]["max_runs"]):
                raise Blocked("Run already claimed or run budget exhausted; explicit bounded recovery required")
            if not runs and snapshot(state / "workspace", task) != read(state / "baseline.json")["tree"]:
                raise Blocked("Workspace drifted before first model execution")
            verify_base(task)
            preflight(task)
        conversation = factory(state, bound, task)
        try:
            observed = conversation.state.execution_status.value
            if observed not in ("idle", "paused", "stuck", "error", "running"):
                raise Blocked("Native conversation is terminal; do not restart")
            message = task_message(state, bound, task, read(state / "baseline.json"))
            messages = [e for e in conversation.state.events if getattr(e, "source", None) == "user"
                        and type(e).__name__ == "MessageEvent"]
            if not runs:
                if messages:
                    raise Blocked("Unexpected message before first claimed run; inspect native history")
                conversation.send_message(message)
            else:
                if not messages:
                    raise Blocked("Missing original task in persisted native history")
                if [getattr(c, "text", None) for c in messages[0].llm_message.content] != [message]:
                    raise Blocked("Persisted original task differs; do not resume")
                # No replacement conversation, baseline rerun or history mirroring.
                with lock(state):
                    for reservation in (state / "attempts").glob("*/intent.json"):
                        if not reservation.with_name("validation.json").exists():
                            write(reservation.with_name("validation.json"), dict(outcome="INCONCLUSIVE",
                                reasons=["Interrupted attempt; explicit recovery: " + resume_reason],
                                validatedTree=read(reservation)["tree"], attempt=int(reservation.parent.name)),
                                exclusive=True)
                feedback = read(state / "feedback.json") if (state / "feedback.json").exists() else {}
                conversation.send_message("Bounded recovery: " + resume_reason
                    + "\nStable task digest: " + bound["taskDigest"]
                    + "\nGoal: " + task["goal"] + "\nAcceptance policy: " + str(task["policy"])
                    + "\nCurrent candidate tree: " + snapshot(state / "workspace", task)
                    + "\nValidation feedback: " + str(feedback)
                    + "\nReview cycle records; reassess the whole goal, not just the prior strategy.")
            with lock(state):
                require_preparation(state)
                if factory is open_conversation:
                    from .native import verify_ready
                    verify_ready(conversation, state, task)
                write(state / "runs" / f"{len(runs) + 1}.json", dict(conversationId=bound["conversationId"],
                    state="RUN_INTENT", reason=resume_reason, at=time.time()), exclusive=True)
                from .guidance import delivery_evidence
                if factory is open_conversation:
                    write(state / "guidance.json", delivery_evidence(conversation.agent.agent_context, message))
            from .evidence import capture
            capture(state, "pre-run", conversation)
            conversation.run()
            return status(state, conversation)
        finally:
            from .evidence import capture
            try:
                capture(state, "post-run", conversation)
            finally:
                conversation.close()


def hook(state, event, *, evaluator=None, delivery=deliver):
    state, bound, task = context(state)
    default_acceptance = evaluator is None
    evaluator = evaluator or evaluate
    working_dir = state / "workspace"
    with lock(state):
        if (event.get("event_type") != "Stop" or event.get("session_id") != bound["conversationId"]
                or event.get("metadata", {}).get("reason") != "agent_finished"
                or event.get("working_dir") != str(working_dir)):
            raise Blocked("Native Stop event identity mismatch")
        if bound.get("executionFramework"):
            require_preparation(state)
        if default_acceptance:
            require_independent_authority()
        workspace = state / "workspace"
        tree = snapshot(workspace, task)
        outcome = final_outcome(state, tree)
        if outcome["document"]["goal_status"] == "bounded_failure":
            write(state / "result.json", dict(outcome="BOUNDED_FAILURE", conversationId=bound["conversationId"], journal=outcome))
            return dict(decision="allow", reason="BOUNDED FAILURE recorded; not accepted, no delivery")
        changed = check_paths(workspace, task, tree)
        if not changed and task["delivery"]["mode"] == "draft_pr":
            raise Blocked("No deliverable change; report bounded failure rather than success")
        attempts = state / "attempts"
        previous = sorted(attempts.glob("*/validation.json"), key=lambda p: int(p.parent.name))
        if any(not p.with_name("validation.json").exists() for p in attempts.glob("*/intent.json")):
            raise Blocked("Interrupted validation reservation; explicit bounded resume required, no automatic rescan")
        if previous:
            accepted = read(previous[-1])
            if accepted["outcome"] == "PASS" and accepted["validatedTree"] == tree:
                return complete(state, accepted, delivery=delivery)
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
                        additionalContext="Reassess facts/candidates using this evidence; preserve a concise material decision when useful. "
                        + str(accepted["reasons"])[:2000] + '\nFinding counts: ' + str(accepted.get('summary', {}))
                        + '\nComplete findings, paths and evidence: ' + str(attempt / 'validation.json'))
        return complete(state, accepted, delivery=delivery)


def terminal_hook(state, event):
    """Native PreToolUse policy; bound foreground waits, not a process sandbox.

    Direct SDK execute_tool bypasses native action hooks and is trusted-caller
    functionality, not a product agent execution path. Hook infrastructure can
    fail open in the installed SDK; this does not establish P0 authority.
    """
    import math
    state, bound, task = context(state)
    if (event.get("event_type") != "PreToolUse" or event.get("tool_name") != "terminal"
            or event.get("session_id") != bound["conversationId"]
            or event.get("working_dir") != str(state / "workspace")):
        raise Blocked("Native terminal event identity mismatch")
    action = event.get("tool_input") or {}
    if action.get("is_input") is True and action.get("command") in ("C-c", "C-d", "C-z"):
        return dict(decision="allow", reason="Terminal control input")
    require_preparation(state)
    timeout = action.get("timeout")
    maximum = min(task["limits"]["command_seconds"],
                  bound["createdAt"] + task["limits"]["task_seconds"] - time.time())
    if (type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= maximum):
        return dict(decision="deny", reason="Terminal needs an explicit finite timeout in (0, " + str(maximum) + "] seconds",
                    additionalContext="Use native soft-timeout/polling and interrupt when necessary; no command was started.")
    return dict(decision="allow", reason="Foreground wait within configured command/task admission budget")


def complete(state, accepted, *, delivery=deliver):
    _, bound, task = context(state)
    if (accepted.get("outcome") != "PASS" or accepted.get("taskDigest") != bound["taskDigest"]
            or accepted.get("conversationId") != bound["conversationId"]
            or snapshot(state / "workspace", task) != accepted["validatedTree"]):
        raise Blocked("Completion requires exact-tree independent PASS")
    if task["delivery"]["mode"] == "report_only":
        write(state / "result.json", dict(outcome="VALIDATED", validationOutcome="PASS",
            remediationSuccess=True, deliveryStatus="NOT_REQUESTED", validatedTree=accepted["validatedTree"],
            conversationId=bound["conversationId"], attempt=accepted["attempt"]))
        return dict(decision="allow", reason="Independent PASS; report_only, no branch push or PR")
    if not task["delivery"]["authorized"]:
        raise Blocked("Independent PASS retained; draft delivery is not explicitly authorized")
    delivered = delivery(state, accepted)
    write(state / "result.json", dict(outcome="DELIVERED", validationOutcome="PASS",
          remediationSuccess=True, deliveryStatus="CONFIRMED", **delivered))
    return dict(decision="allow", reason="Independent PASS; draft PR confirmed: " + delivered["prUrl"])


def status(state, conversation=None):
    state, bound, task = context(state)
    result = read(state / "result.json") if (state / "result.json").exists() else dict(outcome="PENDING")
    native_status, usage = None, None
    if conversation:
        native_status = conversation.state.execution_status.value
        usage = conversation.state.stats.model_dump(mode="json")
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
    if result["outcome"] == "VALIDATED":
        accepted = read(state / "attempts" / str(result["attempt"]) / "validation.json")
        if (accepted["outcome"] != "PASS" or accepted["validatedTree"] != result["validatedTree"]
                or accepted["taskDigest"] != bound["taskDigest"] or accepted["conversationId"] != bound["conversationId"]):
            raise Blocked("Report-only result lacks bound independent acceptance")
        if native_status != "finished":
            result = dict(result, outcome="VALIDATED_AWAITING_NATIVE_FINISH")
    return dict(conversationId=bound["conversationId"], goal=task["goal"],
                nativeStatus=native_status, modelUsage=usage, result=result,
                validation=read(state / "feedback.json") if (state / "feedback.json").exists() else None,
                evidence=dict(baseline="baseline.json", cycles="journal/", attempts="attempts/", delivery="delivery.json"))
