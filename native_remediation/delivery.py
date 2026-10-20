"""PASS-only GitHub delivery, derived from the verified native smoke guards."""
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from .contract import context
from .files import Blocked, digest, read, write, require_independent_authority
from .repository import commit_tree, snapshot, text, url


class GitHub:
    def __init__(self, repository):
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
        if result.returncode or not result.stdout.strip():
            raise Blocked("Existing gh credentials unavailable")
        self.token = result.stdout.strip()
        self.repository = repository

    def request(self, method, endpoint, body=None):
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request("https://api.github.com/repos/" + self.repository + endpoint,
            data=None if body is None else json.dumps(body).encode(), method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if method == "GET" and exc.code == 404:
                return None
            raise Blocked("GitHub operation failed: HTTP " + str(exc.code)) from None


def deliver(state, accepted, *, github=None):
    require_independent_authority()
    state, bound, task = context(state)
    if task["delivery"]["mode"] != "draft_pr" or not task["delivery"]["authorized"]:
        raise Blocked("Draft delivery not explicitly authorized; report_only never mutates GitHub")
    if bound.get("executionFramework"):
        from .runtime import require_preparation
        require_preparation(state)
    workspace = state / "workspace"
    if (accepted.get("outcome") != "PASS" or accepted.get("conversationId") != bound["conversationId"]
            or accepted.get("baseCommit") != task["base_sha"] or accepted.get("taskDigest") != bound["taskDigest"]):
        raise Blocked("Independent acceptance identity mismatch")
    attempt = state / "attempts" / str(accepted["attempt"])
    persisted = read(attempt / "validation.json")
    candidate = read(attempt / "evaluation.json")
    if (persisted != accepted or accepted["candidateDigest"] != digest(candidate)
            or accepted["baselineDigest"] != digest(read(state / "baseline.json"))
            or candidate.get("outcome") != "COMPLETE" or candidate["tree"] != accepted["validatedTree"]
            or snapshot(workspace, task) != accepted["validatedTree"]):
        raise Blocked("Validated evidence or workspace drifted")
    gh = github or GitHub(task["repository"])
    base = urllib.parse.quote(task["base_branch"], safe="")
    remote_base = gh.request("GET", "/branches/" + base)
    if not remote_base or remote_base["commit"]["sha"] != task["base_sha"]:
        raise Blocked("Approved remote base moved")
    branch = "openhands/remediate-" + bound["conversationId"]
    path = state / "delivery.json"
    identity = dict(conversationId=bound["conversationId"], baseCommit=task["base_sha"],
                    validatedTree=accepted["validatedTree"], taskDigest=bound["taskDigest"], branch=branch)
    claim = read(path) if path.exists() else None
    encoded = urllib.parse.quote(branch, safe="")
    remote = gh.request("GET", "/git/ref/heads/" + encoded)
    if claim is None:
        if remote:
            raise Blocked("Unclaimed remote task branch exists")
        claim = dict(identity, state="CLAIMED")
        write(path, claim, exclusive=True)
    elif any(claim.get(key) != value for key, value in identity.items()):
        raise Blocked("Delivery claim identity differs")
    if "commit" not in claim:
        if remote:
            raise Blocked("Remote branch exists without durable commit intent")
        claim["commit"] = commit_tree(workspace, task, accepted["validatedTree"], bound["conversationId"])
        write(path, claim)
    commit = claim["commit"]
    if (text(workspace, "show", "-s", "--format=%T", commit) != accepted["validatedTree"]
            or text(workspace, "show", "-s", "--format=%P", commit) != task["base_sha"]):
        raise Blocked("Delivery commit tree/parent mismatch")
    if remote is None:
        if claim["state"] != "CLAIMED":
            raise Blocked("Prior push is uncertain; inspect remote, never blindly repeat")
        claim["state"] = "PUSH_STARTED"
        write(path, claim)
        text(workspace, "push", "--force-with-lease=refs/heads/" + branch + ":", url(task), commit + ":refs/heads/" + branch)
        remote = gh.request("GET", "/git/ref/heads/" + encoded)
    if remote is None or remote["object"]["sha"] != commit:
        raise Blocked("Remote task branch SHA differs or push is uncertain")
    query = urllib.parse.urlencode(dict(state="all", head=task["repository"].split("/")[0] + ":" + branch,
                                       base=task["base_branch"]))
    prs = gh.request("GET", "/pulls?" + query)
    if not isinstance(prs, list) or len(prs) > 1:
        raise Blocked("Ambiguous remote PR result")
    if not prs:
        if claim["state"] in ("PR_POST_STARTED", "DELIVERED"):
            raise Blocked("Prior PR POST uncertain; reconcile only, no duplicate POST")
        claim["state"] = "PR_POST_STARTED"
        write(path, claim)
        prs = [gh.request("POST", "/pulls", dict(title="Verified OSS remediation",
            head=branch, base=task["base_branch"], draft=True,
            body="Goal: " + task["goal"] + "\n\nNative conversation: " + bound["conversationId"]
            + "\nIndependent PASS tree: " + accepted["validatedTree"]
            + "\nApproved base: " + task["base_sha"]
            + "\nValidation attempt: " + str(accepted["attempt"]))) ]
    pr = prs[0]
    if (not pr or pr.get("draft") is not True or pr.get("state") != "open"
            or pr["head"]["sha"] != commit or pr["head"]["ref"] != branch
            or pr["head"]["repo"]["full_name"] != task["repository"]
            or pr["base"]["ref"] != task["base_branch"] or pr["base"]["repo"]["full_name"] != task["repository"]
            or pr["base"]["sha"] != task["base_sha"]
            or not pr.get("html_url", "").startswith("https://github.com/" + task["repository"] + "/pull/")):
        raise Blocked("Remote PR is not the exact authorized open draft")
    claim.update(state="DELIVERED", prUrl=pr["html_url"])
    write(path, claim)
    return claim
