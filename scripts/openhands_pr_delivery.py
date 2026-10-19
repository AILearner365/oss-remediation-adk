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
import sqlite3
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openhands_real_run_audit import audit
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.contracts import (TaskResult, ResultOutcome, ExecutionStatus,
    ValidationStatus, DeliveryStatus, canonical_json)

REPO = "AILearner365/maven-multimodule-app"
BASE = "main-runrunning"
URL = "https://github.com/" + REPO + ".git"
APPROVAL = "I_AUTHORIZE_PUSH_AND_PR"
SHA = re.compile(r"^[0-9a-f]{40}$")
TASK_ID = re.compile(r"^task_[0-9a-f]{32}$")


def git(path: Path, *args: str) -> str:
    # A delivery child never needs the product's GitHub API token. Git uses
    # the operator's existing HTTPS credential helper; repository hooks and
    # fsmonitor programs cannot run with control-plane credentials.
    environment = {k: v for k, v in os.environ.items() if k not in {
        "GITHUB_TOKEN", "GH_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}}
    process = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                             "-C", str(path), *args], env=environment,
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
        if request.delivery_mode != "github_pr":
            raise ValueError("Task does not authorize GitHub PR delivery; contract integration required")
        workspace = Path(prep.workspace_path).resolve(strict=True)
        if workspace.is_symlink():
            raise ValueError("Unsafe workspace")
        git(workspace, "merge-base", "--is-ancestor", expected_base, "HEAD")
        # The independent validator captures tracked, staged and new files in
        # this exact tree. Review that accepted snapshot, including agent-made
        # commits, rather than imposing a POM-only or unstaged-edit recipe.
        diff = git(workspace, "diff", "--no-ext-diff", "--name-only", expected_base,
                   summary["validatedTree"], "--")
        changed = sorted(line for line in diff.splitlines() if line)
        if not changed:
            raise ValueError("Delivery requires validated changes")
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



def claim_delivery(database: Path, details: dict) -> None:
    """Write an irreversible delivery claim before the first external mutation."""
    with sqlite3.connect(database, timeout=30) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS openhands_delivery_claims (
            task_id TEXT PRIMARY KEY, base_commit TEXT NOT NULL,
            validated_tree TEXT NOT NULL, delivery_branch TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('CLAIMED', 'PR_CREATED')),
            pr_url TEXT, commit_sha TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        if db.execute("SELECT 1 FROM openhands_delivery_claims WHERE task_id = ?",
                      (details["taskId"],)).fetchone():
            raise ValueError("Delivery already claimed; inspect GitHub and durable state, do not replay")
        task = db.execute(
            "SELECT request_json, status, accepted, validation_status FROM tasks WHERE task_id = ?",
            (details["taskId"],)).fetchone()
        if task is None or task[1] != "ACCEPTED" or task[2] != 1 or task[3] != "PASSED":
            raise ValueError("Delivery claim requires durable accepted validation")
        if json.loads(task[0])["delivery"]["mode"] != "github_pr":
            raise ValueError("Registered task does not authorize GitHub PR delivery")
        if db.execute("UPDATE tasks SET status = ?, stage = ?, delivery_status = ? "
                      "WHERE task_id = ? AND status = ? AND delivery_status = ? AND result_json IS NULL",
                      ("DELIVERING", "delivery", "RUNNING", details["taskId"], "ACCEPTED", "PENDING")).rowcount != 1:
            raise ValueError("Task is not awaiting an unclaimed authorized delivery")
        db.execute("""INSERT INTO openhands_delivery_claims
            (task_id, base_commit, validated_tree, delivery_branch, state)
            VALUES (?, ?, ?, ?, 'CLAIMED')""",
            (details["taskId"], details["baseCommit"], details["validatedTree"], details["branch"]))
        db.commit()


def record_delivery(database: Path, task_id: str, url: str, commit: str) -> None:
    """Record one successful PR result; never silently overwrite a prior record."""
    with sqlite3.connect(database, timeout=30) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT state FROM openhands_delivery_claims WHERE task_id = ?",
                         (task_id,)).fetchone()
        if row != ("CLAIMED",):
            raise ValueError("Delivery claim absent or already completed")
        task = db.execute("SELECT status, execution_status, validation_status, delivery_status "
                          "FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if task != ("DELIVERING", "COMPLETED", "PASSED", "RUNNING"):
            raise ValueError("Durable task is not in validated delivery-running state")
        attempt = db.execute("""SELECT attempt, validated_tree, report_artifact_id
            FROM validation_attempts WHERE task_id = ? AND state = 'COMPLETED' AND outcome = 'PASS'
            ORDER BY attempt DESC LIMIT 1""", (task_id,)).fetchone()
        runtime = db.execute("SELECT baseline_commit, conversation_id FROM openhands_runtimes WHERE task_id = ?",
                             (task_id,)).fetchone()
        if attempt is None or runtime is None:
            raise ValueError("Validated evidence or native execution association missing")
        artifact_ids = tuple(row[0] for row in db.execute(
            "SELECT artifact_id FROM artifacts WHERE task_id = ? ORDER BY created_at, artifact_id", (task_id,)))
        result = TaskResult(task_id=task_id, outcome=ResultOutcome.SUCCEEDED,
                            execution_status=ExecutionStatus.COMPLETED,
                            validation_status=ValidationStatus.PASSED,
                            delivery_status=DeliveryStatus.COMPLETED,
                            baseline_commit=runtime[0], validated_tree=attempt[1],
                            validation_attempt=attempt[0], validation_report_artifact_id=attempt[2],
                            conversation_id=runtime[1], pull_request_url=url, artifact_ids=artifact_ids)
        db.execute("""UPDATE openhands_delivery_claims
            SET state = 'PR_CREATED', pr_url = ?, commit_sha = ? WHERE task_id = ?""",
            (url, commit, task_id))
        if db.execute("""UPDATE tasks SET status = 'SUCCEEDED', stage = 'complete',
                    delivery_status = 'COMPLETED', result_json = ?, updated_at = ?
                    WHERE task_id = ? AND status = 'DELIVERING' AND result_json IS NULL""",
                    (canonical_json(result.to_dict()), result.completed_at, task_id)).rowcount != 1:
            raise ValueError("Delivery result race; no overwrite permitted")
        db.commit()


def delivery_claim(database: Path, task_id: str):
    with sqlite3.connect(database, timeout=30) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='openhands_delivery_claims'").fetchone():
            return None
        row = db.execute("SELECT * FROM openhands_delivery_claims WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None


def _optional_branch(branch: str, token: str):
    from urllib.parse import quote
    try:
        return request_github("GET", "/branches/" + quote(branch, safe=""), token)
    except ValueError as exc:
        if "HTTP 404" not in str(exc):
            raise
        return None


def _delivery_commit(workspace: Path, details: dict) -> str:
    # Commit the accepted Git tree directly; leave the independently validated
    # workspace/index/HEAD untouched. This is also restart-safe before push.
    env = {**{k: v for k, v in os.environ.items() if k not in {"GITHUB_TOKEN", "GH_TOKEN"}},
           "GIT_AUTHOR_NAME": "OpenHands Remediation",
           "GIT_AUTHOR_EMAIL": "openhands-remediation@users.noreply.github.com",
           "GIT_COMMITTER_NAME": "OpenHands Remediation",
           "GIT_COMMITTER_EMAIL": "openhands-remediation@users.noreply.github.com"}
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(workspace),
        "commit-tree", details["validatedTree"], "-p", details["baseCommit"]],
        input="Remediate validated Maven vulnerabilities (" + details["taskId"] + ")\n",
        capture_output=True, text=True, env=env, timeout=30)
    if result.returncode or not SHA.fullmatch(result.stdout.strip()):
        raise ValueError("Cannot create delivery commit")
    return result.stdout.strip()


def deliver(details: dict, approval: str, token: str) -> dict:
    if approval != APPROVAL or not token:
        raise ValueError("Explicit PR approval and GitHub token required")
    if (details.get("status") != "READY_FOR_EXPLICIT_PR_APPROVAL"
            or details.get("repository") != REPO or details.get("base") != BASE
            or not TASK_ID.fullmatch(details.get("taskId", ""))
            or details.get("branch") != "openhands/remediate-" + details["taskId"]
            or not SHA.fullmatch(details.get("baseCommit", ""))
            or not SHA.fullmatch(details.get("validatedTree", ""))):
        raise ValueError("Invalid approved delivery plan")
    workspace = Path(details["workspace"])
    database, config = load_stop_hook_config(Path(details["hookConfig"]).resolve(strict=True))
    prior = delivery_claim(database, details["taskId"])
    if prior and (prior["base_commit"], prior["validated_tree"], prior["delivery_branch"]) != (
            details["baseCommit"], details["validatedTree"], details["branch"]):
        raise ValueError("Delivery claim identity mismatch")
    # Independent acceptance is rechecked before every attempt. Native finish
    # alone cannot authorize push. Reconciliation does not rerun a scanner.
    from openhands_shared.validation import SharedValidationService
    with SQLiteTaskStore(database) as store:
        request = store.get_request(details["taskId"])
        prep = store.get_preparation(details["taskId"])
        attempts = store.list_validation_attempts(details["taskId"])
        status = store.get_status(details["taskId"])
        if (request.repository.url != URL or request.repository.base_ref != "refs/heads/" + BASE
                or request.repository.expected_commit != details["baseCommit"]
                or request.delivery_mode != "github_pr" or prep is None
                or Path(prep.workspace_path).resolve() != workspace.resolve()
                or not status.accepted or status.validation_status.value != "PASSED"
                or not attempts or attempts[-1].outcome.value != "PASS"
                or attempts[-1].validated_tree != details["validatedTree"]
                or not SharedValidationService(store, config).verify_validated_state(details["taskId"], attempts[-1].attempt)):
            raise ValueError("Accepted task or validated tree changed")
        if prior and prior["state"] == "PR_CREATED":
            return {"status": "PR_CREATED", "url": prior["pr_url"], "commit": prior["commit_sha"],
                    "taskId": details["taskId"], "branch": details["branch"], "reconciled": True}
    branch_info = request_github("GET", "/branches/" + BASE, token)
    if branch_info["commit"]["sha"] != details["baseCommit"]:
        raise ValueError("Remote base moved; require new baseline and acceptance")
    remote = _optional_branch(details["branch"], token)
    if not prior:
        if remote:
            raise ValueError("Unclaimed delivery branch already exists; never overwrite")
        refreshed = plan(details["taskId"], Path(details["hookConfig"]), expected_base=details["baseCommit"])
        for key in ("changedFiles", "validatedTree", "workspace", "branch"):
            if refreshed[key] != details[key]:
                raise ValueError("Delivery plan drift")
        claim_delivery(database, details)
        prior = delivery_claim(database, details["taskId"])
    commit = prior["commit_sha"]
    if not commit:
        if remote:
            raise ValueError("Remote branch without durable commit intent; inspect ownership")
        commit = _delivery_commit(workspace, details)
        with sqlite3.connect(database, timeout=30) as db:
            db.execute("UPDATE openhands_delivery_claims SET commit_sha=? WHERE task_id=? AND commit_sha IS NULL",
                       (commit, details["taskId"]))
        commit = delivery_claim(database, details["taskId"])["commit_sha"]
    if (git(workspace, "show", "-s", "--format=%T", commit) != details["validatedTree"]
            or git(workspace, "show", "-s", "--format=%P", commit) != details["baseCommit"]):
        raise ValueError("Delivery commit differs from accepted tree/base")
    if remote:
        if remote["commit"]["sha"] != commit:
            raise ValueError("Remote task branch differs from durable delivery commit; never overwrite")
    else:
        # Create-only compare-and-swap: fail even if a competing branch points
        # to an ancestor. An empty lease requires the ref to be absent.
        git(workspace, "push", "--force-with-lease=refs/heads/" + details["branch"] + ":",
            URL, commit + ":refs/heads/" + details["branch"])
        remote = _optional_branch(details["branch"], token)
        if not remote or remote["commit"]["sha"] != commit:
            raise ValueError("Push response uncertain; reconcile remote before retry")
    from urllib.parse import urlencode
    query = urlencode({"state": "all", "head": REPO.split("/")[0] + ":" + details["branch"], "base": BASE})
    existing = request_github("GET", "/pulls?" + query, token)
    if len(existing) > 1:
        raise ValueError("Ambiguous task PRs require inspection")
    if existing:
        payload = existing[0]
    else:
        body = ("Independent validation passed.\n\nTask: " + details["taskId"] +
                "\nValidated tree: " + details["validatedTree"] +
                "\nResolved vulnerabilities: " + str(details["findingCountResolved"]) + "\n")
        payload = request_github("POST", "/pulls", token, {
            "title": "Remediate Maven vulnerabilities (" + details["taskId"] + ")",
            "head": details["branch"], "base": BASE, "body": body, "draft": True})
    if (payload.get("head", {}).get("sha") != commit or payload.get("head", {}).get("ref") != details["branch"]
            or payload.get("base", {}).get("ref") != BASE or payload.get("base", {}).get("repo", {}).get("full_name") != REPO
            or payload.get("draft") is not True or payload.get("state") != "open"
            or not payload.get("html_url", "").startswith("https://github.com/" + REPO + "/pull/")):
        raise ValueError("Existing PR is not the exact open draft authorized for this task")
    record_delivery(database, details["taskId"], payload["html_url"], commit)
    return {"status": "PR_CREATED", "url": payload["html_url"], "number": payload["number"],
            "commit": commit, "branch": details["branch"], "taskId": details["taskId"], "noModelRun": True}


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
