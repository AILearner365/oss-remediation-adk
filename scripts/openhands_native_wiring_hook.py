#!/usr/bin/env python3
"""One-file native Stop validator/delivery; no product state or model calls."""
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
import urllib.error
import urllib.request
import uuid

# Narrow stdlib-only equivalents of the Git/API/commit helpers in
# openhands_pr_delivery.py. Do not import its product audit/SQLite lifecycle.
REPO = "AILearner365/maven-multimodule-app"
BASE = "main-runrunning"
URL = "https://github.com/" + REPO + ".git"
SHA = re.compile(r"^[0-9a-f]{40}$")

FILE = "openhands-native-wiring-test.txt"
MESSAGE = b"Native OpenHands wiring test passed.\n"


def git(path, *args):
    env = {k: v for k, v in os.environ.items() if k not in {
        "GITHUB_TOKEN", "GH_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}}
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c",
        "core.fsmonitor=false", "-C", str(path), *args], env=env,
        capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError("Git prerequisite failed; inspect repository locally")
    return result.stdout.strip()


def request_github(method, endpoint, token, data=None):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    body = None if data is None else json.dumps(data).encode()
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request("https://api.github.com/repos/" + REPO + endpoint,
                                     data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError("GitHub delivery failed with HTTP " + str(exc.code)) from None


def delivery_commit(workspace, details):
    env = {**{k: v for k, v in os.environ.items() if k not in {"GITHUB_TOKEN", "GH_TOKEN"}},
           "GIT_AUTHOR_NAME": "OpenHands Remediation",
           "GIT_AUTHOR_EMAIL": "openhands-remediation@users.noreply.github.com",
           "GIT_COMMITTER_NAME": "OpenHands Remediation",
           "GIT_COMMITTER_EMAIL": "openhands-remediation@users.noreply.github.com"}
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(workspace),
        "commit-tree", details["validatedTree"], "-p", details["baseCommit"]],
        input="Native OpenHands wiring test (" + details["conversationId"] + ")\n",
        capture_output=True, text=True, env=env, timeout=30)
    if result.returncode or not SHA.fullmatch(result.stdout.strip()):
        raise ValueError("Cannot create delivery commit")
    return result.stdout.strip()


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def validate(contract):
    if (contract["repository"] != REPO or contract["base"] != BASE
            or not SHA.fullmatch(contract["baseCommit"])
            or str(uuid.UUID(contract["conversationId"])) != contract["conversationId"]):
        raise ValueError("Contract is not bound to the approved repository/base/conversation")
    workspace = Path(contract["workspace"])
    base = contract["baseCommit"]
    if git(workspace, "rev-parse", "HEAD") != base:
        raise ValueError("HEAD changed from approved base")
    if git(workspace, "remote", "get-url", "origin") != URL:
        raise ValueError("Repository mismatch")
    target = workspace / FILE
    if target.is_symlink() or not target.is_file() or target.read_bytes() != MESSAGE:
        raise ValueError("Required regular file or exact contents missing")
    if git(workspace, "ls-files", "--others", "--ignored", "--exclude-standard"):
        raise ValueError("Unexpected ignored files")
    with tempfile.TemporaryDirectory(prefix="native-wiring-index-") as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"))
        for args in (("read-tree", base), ("add", "-A"), ("write-tree",)):
            result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C",
                str(workspace), *args], env=env, capture_output=True, text=True, check=True)
        tree = result.stdout.strip()
    if git(workspace, "diff", "--name-status", base, tree, "--") != "A\t" + FILE:
        raise ValueError("Change is not exactly the allowed added file")
    if git(workspace, "ls-tree", tree, "--", FILE).split()[0] != "100644":
        raise ValueError("File must be non-executable")
    expected_blob = hashlib.sha1(b"blob " + str(len(MESSAGE)).encode() + b"\0" + MESSAGE).hexdigest()
    if git(workspace, "rev-parse", tree + ":" + FILE) != expected_blob:
        raise ValueError("Snapshot file contents changed during validation")
    return tree


def run(directory, event):
    contract = json.loads((directory / "contract.json").read_text())
    if event.get("session_id") != contract["conversationId"]:
        raise ValueError("Native hook conversation mismatch")
    if (event.get("event_type") != "Stop"
            or Path(event.get("working_dir", "")).resolve() != Path(contract["workspace"]).resolve()):
        raise ValueError("Native hook event/workspace mismatch")
    if event.get("metadata", {}).get("reason") != "agent_finished":
        raise ValueError("Not an agent-finished Stop event")
    tree = validate(contract)
    evidence = dict(contract, validatedTree=tree, outcome="PASS", hookEvent=event)
    evidence["diff"] = git(Path(contract["workspace"]), "diff", "--no-ext-diff",
                           contract["baseCommit"], tree, "--")
    save(directory / "validation.json", evidence)
    token = subprocess.run(["gh", "auth", "token"], capture_output=True,
                           text=True, check=True).stdout.strip()
    def api(method, endpoint, data=None):
        return request_github(method, endpoint, token, data)
    if api("GET", "/branches/" + BASE)["commit"]["sha"] != contract["baseCommit"]:
        raise ValueError("Approved remote base moved")
    branch = "openhands/native-wiring-" + contract["conversationId"]
    claim_path = directory / "delivery-claim.json"
    if claim_path.exists():
        claim = json.loads(claim_path.read_text())
        if (any(claim.get(k) != v for k, v in contract.items())
                or claim["validatedTree"] != tree or claim["branch"] != branch):
            raise ValueError("Claim tree/base mismatch; inspect, do not retry")
    else:
        refs = api("GET", "/git/matching-refs/heads/" + branch)
        if refs:
            raise ValueError("Unclaimed branch exists")
        claim = dict(contract, validatedTree=tree, branch=branch, state="CLAIMED")
        save(claim_path, claim)
    workspace = Path(contract["workspace"])
    if "commit" not in claim:
        claim["commit"] = delivery_commit(workspace, claim)
        save(claim_path, claim)
    commit = claim["commit"]
    if git(workspace, "show", "-s", "--format=%T", commit) != tree or git(
            workspace, "show", "-s", "--format=%P", commit) != contract["baseCommit"]:
        raise ValueError("Delivery commit tree/base mismatch")
    refs = api("GET", "/git/matching-refs/heads/" + branch)
    exact = [r for r in refs if r["ref"] == "refs/heads/" + branch]
    if not exact:
        if claim["state"] != "CLAIMED":
            raise ValueError("Prior push uncertain; no replay")
        claim["state"] = "PUSH_STARTED"
        save(claim_path, claim)
        git(workspace, "push", "--force-with-lease=refs/heads/" + branch + ":",
            URL, commit + ":refs/heads/" + branch)
        exact = [api("GET", "/git/ref/heads/" + branch)]
    if len(exact) != 1 or exact[0]["object"]["sha"] != commit:
        raise ValueError("Remote branch mismatch")
    query = urlencode(dict(state="all", head="AILearner365:" + branch, base=BASE))
    prs = api("GET", "/pulls?" + query)
    if not prs:
        if claim["state"] in ("PR_POST_STARTED", "DELIVERED"):
            raise ValueError("Prior PR response uncertain; no replay")
        claim["state"] = "PR_POST_STARTED"
        save(claim_path, claim)
        prs = [api("POST", "/pulls", dict(title="Native OpenHands one-file wiring test",
            head=branch, base=BASE, draft=True, body="Native conversation: " + contract["conversationId"]
            + "\nIndependent PASS tree: " + tree + "\nOne harmless file; no application changes."))]
    if len(prs) != 1:
        raise ValueError("Ambiguous PR result")
    pr = prs[0]
    if not (pr["draft"] and pr["state"] == "open" and pr["head"]["sha"] == commit
            and pr["head"]["ref"] == branch and pr["base"]["ref"] == BASE
            and pr["base"]["repo"]["full_name"] == REPO):
        raise ValueError("PR is not the exact authorized draft")
    claim.update(state="DELIVERED", prUrl=pr["html_url"])
    save(claim_path, claim)
    return pr["html_url"]


if __name__ == "__main__":
    directory = Path(sys.argv[1]).resolve(strict=True)
    with (directory / "hook.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            event = json.load(sys.stdin)
            with (directory / "hook-invocations.jsonl").open("a") as log:
                log.write(json.dumps(event) + "\n")
            url = run(directory, event)
            print(json.dumps(dict(decision="allow", reason="Independent PASS; draft PR delivered: " + url)))
        except Exception as exc:
            reason = "Delivery blocked: " + type(exc).__name__ + ": " + str(exc)[:180]
            save(directory / "blocked.json", dict(reason=reason))
            print(json.dumps(dict(decision="deny", reason=reason,
                                  additionalContext=reason + ". Do not retry delivery or change other files.")))
            sys.exit(2)
