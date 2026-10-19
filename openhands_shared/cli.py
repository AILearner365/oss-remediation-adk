"""Thin HTTP client: python3 -m openhands_shared.cli --help."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("REMEDIATION_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--key-file", type=Path, default=Path(os.environ.get("REMEDIATION_KEY_FILE",
        str(Path.home() / ".openhands/oss-remediation/product/api-key.txt"))))
    sub = parser.add_subparsers(dest="action", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("file", type=Path)
    submit.add_argument("--idempotency-key", default=None)
    sub.add_parser("list")
    for action in ("status", "result", "events", "reports", "diff", "delivery", "delivery-plan", "reconcile"):
        p = sub.add_parser(action)
        p.add_argument("task_id")
        if action == "events":
            p.add_argument("--page-id")
    for action in ("execute", "authorize-delivery"):
        p = sub.add_parser(action)
        p.add_argument("task_id")
        p.add_argument("authorization", type=Path, help="Explicit exact authorization JSON file")
    p = sub.add_parser("artifact")
    p.add_argument("task_id")
    p.add_argument("artifact_id")
    args = parser.parse_args(argv)
    path, method, value, headers = "/v1/remediations", "GET", None, {}
    if args.action == "submit":
        method, value = "POST", json.loads(args.file.read_text())
        key = args.idempotency_key or "submit-" + uuid4().hex
        # Print BEFORE HTTP, so a lost response can be recovered using the same key.
        print("Idempotency-Key: " + key, file=sys.stderr)
        headers["Idempotency-Key"] = key
    elif args.action != "list":
        path += "/" + args.task_id
        resource = {"status": "", "execute": "execute", "authorize-delivery": "delivery"}.get(args.action, args.action)
        if args.action == "artifact":
            from urllib.parse import quote
            resource = "artifacts/" + quote(args.artifact_id, safe="")
        if resource:
            path += "/" + resource
        if args.action == "events" and args.page_id:
            from urllib.parse import urlencode
            path += "?" + urlencode({"pageId": args.page_id})
        if args.action in {"execute", "authorize-delivery", "reconcile"}:
            method = "POST"
            value = {} if args.action == "reconcile" else json.loads(args.authorization.read_text())
    try:
        headers.update({"Authorization": "Bearer " + args.key_file.read_text().strip(), "Content-Type": "application/json"})
        request = Request(args.url.rstrip("/") + path, headers=headers, method=method,
            data=json.dumps(value).encode() if value is not None else None)
        with build_opener(ProxyHandler({})).open(request, timeout=120) as response:
            print(json.dumps(json.load(response), indent=2))
        return 0
    except HTTPError as exc:
        print(exc.read().decode(), file=sys.stderr)
    except (OSError, URLError):
        print("Service or key unavailable; check startup status and --key-file", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
