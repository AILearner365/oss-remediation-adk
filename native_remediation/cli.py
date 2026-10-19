"""Short commands around the native runtime; no daemon, polling loop or database."""
import argparse
import json
from pathlib import Path
import sys
import time

from .contract import context, load_task
from .files import Blocked, lock, read, write
from .native import Native
from . import journal, preflight, runtime
from .delivery import deliver


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="action", required=True)
    validate = sub.add_parser("check-task", help="Offline contract validation only")
    validate.add_argument("--task", type=Path, required=True)
    prep = sub.add_parser("prepare", help="Clone approved revision; build/resolve/scan baseline, no model")
    prep.add_argument("--task", type=Path, required=True)
    prep.add_argument("--state", type=Path, required=True)
    for name in ("attach", "doctor", "run", "resume", "status", "reconcile-delivery", "hook", "record"):
        p = sub.add_parser(name)
        p.add_argument("--state", type=Path, required=True)
        if name in ("attach", "doctor", "run", "resume", "status"):
            p.add_argument("--server", default="http://127.0.0.1:18910")
            p.add_argument("--key-file", type=Path, required=True)
        if name in ("run", "resume"):
            p.add_argument("--authorize-run-and-delivery", action="store_true")
        if name == "attach":
            p.add_argument("--reconcile", action="store_true", help="Inspect/reuse the claimed idle conversation; never repeat create")
        if name == "resume":
            p.add_argument("--reason", required=True)
        if name == "record":
            p.add_argument("--kind", choices=("intent", "outcome"), required=True)
            p.add_argument("--document", type=Path, required=True)
    return root


def execute(args):
    if args.action == "check-task":
        task = load_task(read(args.task))
        return dict(outcome="VALID_TASK", repository=task["repository"], model=task["model"])
    if args.action == "prepare":
        bound = runtime.prepare_task(read(args.task), args.state)
        return dict(outcome="BASELINE_COMPLETE", conversationId=bound["conversationId"])
    if args.action == "hook":
        return runtime.hook(args.state, json.load(sys.stdin))
    if args.action == "record":
        with lock(args.state):
            return journal.record(args.state, args.kind, read(args.document))
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
    native = Native(args.server, args.key_file)
    if args.action == "doctor":
        return preflight.check(native, task)
    if args.action == "attach":
        return runtime.attach(state, native, reconcile=args.reconcile)
    if args.action in ("run", "resume"):
        if not args.authorize_run_and_delivery:
            raise Blocked("Explicit authorization required for paid execution and PASS-only draft delivery")
        preflight.check(native, task)
        return runtime.dispatch(state, native, resume_reason=args.reason if args.action == "resume" else None)
    return runtime.status(state, native)


def main():
    args = parser().parse_args()
    try:
        result = execute(args)
        print(json.dumps(result, sort_keys=True))
        if args.action == "hook" and result.get("decision") == "deny":
            raise SystemExit(2)
    except Exception as exc:
        # Native command hooks can fail open for uncaught errors; emit explicit
        # DENY for all handled failures. Product status still requires PASS + delivery.
        if args.action == "hook":
            reason = str(exc)[:1000] if isinstance(exc, Blocked) else "Validator infrastructure error: " + type(exc).__name__
            result = dict(decision="deny", reason=reason,
                          additionalContext=reason + ". Inspect evidence; do not claim success or perform delivery yourself.")
            try:
                write(args.state / "hook-error.json", dict(errorType=type(exc).__name__, reason=reason, at=time.time()))
            except Exception:
                pass
            print(json.dumps(result))
            raise SystemExit(2)
        print(json.dumps(dict(outcome="BLOCKED", reason=str(exc) if isinstance(exc, Blocked) else type(exc).__name__,
                              inspectBeforeRetry=True)), file=sys.stderr)
        raise SystemExit(1)
