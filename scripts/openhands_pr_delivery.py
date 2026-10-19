#!/usr/bin/env python3
"""Deterministic, approval-gated PR delivery for a separately accepted task.

This is a delivery-only utility; it never runs an agent or scanner. It requires
a previously accepted task, an exact source-commit binding, a clean allowlisted
destination and a validated Git tree. Default mode is dry-run. Live mode pushes
a uniquely named branch and creates a PR; recovery must inspect remote state.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openhands_real_run_audit import audit
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore

REPO = "AILearner365/maven-multimodule-app"
BASE = "main-runrunning"
URL = "https://github.com/" + REPO + ".git"
APPROVAL = "I_AUTHORIZE_PUSH_AND_PR"
SHA = re.compile(r"^[0-9a-f]{40}$")
TASK_ID = re.compile(r"^task_[0-9a-f]{32}$")


def git(path: Path, *args: str) -> str:
    process = subprocess.run(["git", "-C", str(path), *args],
                             capture_output=True, text=True, timeout=60, check=False)
    if process.returncode:
        raise ValueError("Git prerequisite failed; inspect repository locally")
    return process.stdout.strip()


def plan(task_id: str, hook: Path, *, expected_base: str, source_repo: str = REPO) -> dict:
    if source_repo != REPO or not TASK_ID.fullmatch(task_id) or not SHA.fullmatch(expected_base):
        raise ValueError("Destination or task/base identity is not allowlisted")
    summary = audit(task_id, hook, check_native=True)
    db, _ = load_stop_hook_config(hook.resolve(strict=True))
    with SQLiteTaskStore(db) as store:
        request = store.get_request(task_id)
        prep = store.get_preparation(task_id)
        if prep is None or request.repository.url.rstrip("/").removesuffix(".git") != URL.removesuffix(".git"):
            raise ValueError("Task contract is not bound to approved remote")
        if request.repository.base_ref != "refs/heads/" + BASE or request.repository.expected_commit != expected_base:
            raise ValueError("Task base binding differs from explicit approval")
        workspace = Path(prep.workspace_path).resolve(strict=True)
        if workspace.is_symlink():
            raise ValueError("Unsafe workspace")
        if git(workspace, "rev-parse", "HEAD") != expected_base:
            raise ValueError("Workspace HEAD is not authorized base commit")
        if git(workspace, "status", "--porcelain", "--untracked-files=all"):
            # Accepted remediation is normally an uncommitted tracked diff.
            untracked = git(workspace, "ls-files", "--others", "--exclude-standard")
            if untracked:
                raise ValueError("Untracked workspace content requires operator review")
        diff = git(workspace, "diff", "--name-only", "HEAD", "--")
        changed = sorted(line for line in diff.splitlines() if line)
        if not changed or any(not (x == "pom.xml" or x.endswith("/pom.xml")) for x in changed):
            raise ValueError("Delivery only accepts tracked Maven pom.xml edits")
        staged = git(workspace, "diff", "--cached", "--name-only")
        if staged:
            raise ValueError("Staged files are not permitted")
        branch = "openhands/remediate-" + task_id
        return {"status": "READY_FOR_EXPLICIT_PR_APPROVAL", "taskId": task_id,
                "repository": REPO, "base": BASE, "baseCommit": expected_base,
                "branch": branch, "changedFiles": changed,
                "validatedTree": summary["validatedTree"], "findingCountResolved": summary["resolvedFindingCount"],
                "workspace": str(workspace), "noPush": True, "noModelRun": True}


def request_github(method: str, endpoint: str, token: str, data: dict | None = None):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    body = None if data is None else json.dumps(data).encode("utf-8")
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request("https://api.github.com/repos/" + REPO + endpoint,
                                 data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=25) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise ValueError("GitHub API delivery request failed with HTTP " + str(exc.code)) from None


def deliver(details: dict, approval: str, token: str) -> dict:
    if approval != APPROVAL or not token:
        raise ValueError("Explicit PR approval and GitHub token required")
    workspace = Path(details["workspace"])
    if details["status"] != "READY_FOR_EXPLICIT_PR_APPROVAL" or details["repository"] != REPO:
        raise ValueError("Invalid approved delivery plan")
    # All remote checks before any mutation; no force push or base-branch write.
    branch_info = request_github("GET", "/branches/" + BASE, token)
    if branch_info["commit"]["sha"] != details["baseCommit"]:
        raise ValueError("Remote base moved; require new baseline and acceptance")
    branch = details["branch"]
    try:
        existing = request_github("GET", "/branches/" + branch.replace("/", "%2F"), token)
        raise ValueError("Delivery branch already exists; inspect it, never overwrite")
    except ValueError as exc:
        if "HTTP 404" not in str(exc):
            raise
    # Before any local commit, independently repeat acceptance/tree verification.
    refreshed = plan(details["taskId"], Path(details["hookConfig"]),
                     expected_base=details["baseCommit"])
    if refreshed["changedFiles"] != details["changedFiles"] or refreshed["validatedTree"] != details["validatedTree"]:
        raise ValueError("Delivery plan drift")
    git(workspace, "checkout", "-b", branch)
    git(workspace, "add", "--", *details["changedFiles"])
    git(workspace, "-c", "user.name=OpenHands Remediation",
        "-c", "user.email=openhands-remediation@users.noreply.github.com",
        "commit", "-m", "Remediate validated Maven vulnerabilities")
    # Use existing Git credential helper; don't log tokens or embed in Git URL.
    git(workspace, "push", URL, "HEAD:refs/heads/" + branch)
    body = ("Independent validation passed.\n\n"
            "Task: " + details["taskId"] + "\n"
            "Validated tree: " + details["validatedTree"] + "\n"
            "Resolved vulnerabilities: " + str(details["findingCountResolved"]) + "\n"
            "Changes: " + ", ".join(details["changedFiles"]) + "\n")
    payload = request_github("POST", "/pulls", token, {
        "title": "Remediate Maven vulnerabilities (" + details["taskId"] + ")",
        "head": branch, "base": BASE, "body": body, "draft": True})
    return {"status": "PR_CREATED", "url": payload["html_url"], "number": payload["number"],
            "commit": git(workspace, "rev-parse", "HEAD"), "branch": branch,
            "taskId": details["taskId"], "noModelRun": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--hook-config", type=Path, required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--approve-delivery", default="")
    args = parser.parse_args()
    try:
        result = plan(args.task_id, args.hook_config, expected_base=args.expected_base)
        if args.approve_delivery:
            result["hookConfig"] = str(args.hook_config)
            result = deliver(result, args.approve_delivery, os.environ.get("GITHUB_TOKEN", ""))
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:200], "doNotRetryWithoutInspection": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"READY_FOR_EXPLICIT_PR_APPROVAL", "PR_CREATED"} else 1


if __name__ == "__main__":
    sys.exit(main())
