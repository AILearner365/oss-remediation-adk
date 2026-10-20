"""Autonomous OSS Vulnerability Remediation using the standalone OpenHands SDK."""
import argparse
import json
from pathlib import Path
import sys
import time

from .contract import context, load_task
from .files import Blocked, lock, read, write
from . import journal, preflight, runtime
from .delivery import deliver


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="action", required=True)
    validate = sub.add_parser("check-task", help="Offline contract validation only")
    validate.add_argument("--task", type=Path, required=True)
    for name in ("start", "prepare"):
        prep = sub.add_parser(name, help="Initialize SDK and prepare baseline" + ("; then execute" if name == "start" else "; no inference"))
        prep.add_argument("--task", type=Path, required=True)
        prep.add_argument("--state", type=Path, required=True)
        if name == "start":
            prep.add_argument("--authorize-model-execution", "--authorize-run-and-delivery",
                              dest="authorize_run_and_delivery", action="store_true")
    for name in ("doctor", "run", "resume", "status", "reconcile-delivery", "hook", "terminal-hook", "record", "self-validate", "sbri"):
        p = sub.add_parser(name)
        p.add_argument("--state", type=Path, required=True)
        if name in ("run", "resume"):
            p.add_argument("--authorize-model-execution", "--authorize-run-and-delivery",
                           dest="authorize_run_and_delivery", action="store_true")
        if name == "resume":
            p.add_argument("--reason", required=True)
        if name == "record":
            p.add_argument("--kind", choices=("decision", "intent", "outcome"), required=True)
            p.add_argument("--document", type=Path, required=True)
        if name == "sbri":
            selection = p.add_mutually_exclusive_group()
            selection.add_argument("--versions", nargs="+")
            selection.add_argument("--ranges", nargs="+")
            p.add_argument("--scopes", nargs="+")
            p.add_argument("--refresh", action="store_true", help="Refresh completed intelligence within the existing call budget; never replay uncertain claims")
    return root


def execute(args):
    if args.action == "check-task":
        task = load_task(read(args.task))
        return dict(outcome="VALID_TASK", repository=task["repository"], model=task["model"])
    if args.action in ("start", "prepare"):
        if args.action == "start" and not args.authorize_run_and_delivery:
            raise Blocked("Explicit authorization required for paid model execution; task policy separately controls delivery")
        bound = runtime.prepare_task(read(args.task), args.state)
        if args.action == "start":
            return runtime.dispatch(args.state)
        return dict(outcome="BASELINE_COMPLETE", conversationId=bound["conversationId"])
    if args.action == "hook":
        return runtime.hook(args.state, json.load(sys.stdin))
    if args.action == "terminal-hook":
        return runtime.terminal_hook(args.state, json.load(sys.stdin))
    if args.action == "record":
        with lock(args.state):
            return journal.record(args.state, args.kind, read(args.document))
    if args.action in ("self-validate", "sbri"):
        from . import capabilities
        return capabilities.self_validate(args.state) if args.action == "self-validate" else capabilities.sbri(
            args.state, versions=args.versions, ranges=args.ranges, scopes=args.scopes, refresh=args.refresh)
    state, bound, task = context(args.state)
    if args.action == "reconcile-delivery":
        with lock(state):
            # Reconcile only a previously validated/claimed delivery; never create a new acceptance.
            claim = read(state / "delivery.json")
            accepted = read(state / "feedback.json")
            if claim["validatedTree"] != accepted["validatedTree"] or accepted["outcome"] != "PASS":
                raise Blocked("No exact-tree accepted delivery to reconcile")
            delivered = deliver(state, accepted)
            write(state / "result.json", dict(outcome="DELIVERED", **delivered))
            return delivered
    if args.action == "doctor":
        return preflight.check(task)
    if args.action in ("run", "resume"):
        if not args.authorize_run_and_delivery:
            raise Blocked("Explicit authorization required for paid model execution; task policy separately controls delivery")
        return runtime.dispatch(state, resume_reason=args.reason if args.action == "resume" else None)
    from .native import open_conversation
    conversation = open_conversation(state, bound, task)
    try:
        return runtime.status(state, conversation)
    finally:
        conversation.close()


def main():
    args = parser().parse_args()
    try:
        result = execute(args)
        print(json.dumps(result, sort_keys=True))
        if args.action in ("hook", "terminal-hook") and result.get("decision") == "deny":
            raise SystemExit(2)
    except Exception as exc:
        # Native command hooks can fail open for uncaught errors; emit explicit
        # DENY for all handled failures. Product status still requires PASS + delivery.
        if args.action in ("hook", "terminal-hook"):
            reason = str(exc)[:1000] if isinstance(exc, Blocked) else "Validator infrastructure error: " + type(exc).__name__
            result = dict(decision="deny", reason=reason,
                          additionalContext=reason + ". Inspect evidence; do not claim success or perform delivery yourself.")
            try:
                if args.action == "hook":
                    write(args.state / "hook-error.json", dict(errorType=type(exc).__name__, reason=reason, at=time.time()))
            except Exception:
                pass
            print(json.dumps(result))
            raise SystemExit(2)
        print(json.dumps(dict(outcome="BLOCKED", reason=str(exc) if isinstance(exc, Blocked) else type(exc).__name__,
                              inspectBeforeRetry=True)), file=sys.stderr)
        raise SystemExit(1)
