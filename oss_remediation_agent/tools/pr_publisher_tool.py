from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from oss_remediation_agent.contracts import ToolResult, common_artifact
from oss_remediation_agent.tools.generic_patch_apply_tool import apply as apply_patch_plan
from oss_remediation_agent.utils import run_command

TOOL = "PullRequestPublisherTool"


def publish_pull_request(
    *,
    manifest_path: str,
    pr_summary_path: str,
    pr_description_path: str,
    output_path: str,
    draft: bool = True,
) -> dict:
    """Create a remediation branch, replay the validated patch set, and open a GitHub PR.

    This deterministic publisher is intentionally policy-neutral. The orchestrator
    decides whether publishing is allowed and invokes this tool only after a
    validated accepted patch set exists.
    """
    manifest = _read_json(manifest_path)
    workspace_root = Path(manifest.get("workspaceRoot") or Path(manifest_path).parent).resolve()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    accepted = manifest.get("acceptedPatchSet", {})
    repository = manifest.get("repository", {})
    repository_url = repository.get("repositoryUrl")
    reference_branch = repository.get("referenceBranch")
    baseline_commit = repository.get("baselineCommit")

    errors: list[str] = []
    if accepted.get("status") != "VALIDATED" or not accepted.get("patchIds"):
        errors.append("Validated accepted patch set is required before PR publishing.")
    if not repository_url:
        errors.append("repository.repositoryUrl is required before PR publishing.")
    if not reference_branch:
        errors.append("repository.referenceBranch is required before PR publishing.")
    if not baseline_commit:
        errors.append("repository.baselineCommit is required before PR publishing.")
    if errors:
        artifact = _artifact(manifest, "FAILED", errors=errors)
        _write(output, artifact)
        return ToolResult(
            tool_name=TOOL,
            tool_version="1.0.0",
            operation="publish_pull_request",
            status="FAILED",
            artifact_path=str(output),
            failure_code="PR_PUBLISH_PRECONDITION_FAILED",
            errors=errors,
        ).to_dict()

    branch_name = build_remediation_branch_name(str(reference_branch), str(baseline_commit))
    repo_full_name = _repo_full_name(str(repository_url))
    worktree = workspace_root / "final" / "pr-publisher-worktree"
    if worktree.exists():
        _run(["rm", "-rf", str(worktree)], cwd=workspace_root)

    commands: list[dict[str, Any]] = []

    def run(command: list[str], cwd: str | Path | None = None, timeout: int = 1800) -> dict[str, Any]:
        result = _run(command, cwd=cwd, timeout=timeout)
        commands.append(result)
        return result

    clone = run(["git", "clone", str(repository_url), str(worktree)], cwd=workspace_root)
    if clone["exitCode"] != 0:
        return _fail(output, manifest, "GIT_CLONE_FAILED", commands)

    checkout_base = run(["git", "checkout", str(baseline_commit)], cwd=worktree)
    if checkout_base["exitCode"] != 0:
        return _fail(output, manifest, "GIT_CHECKOUT_BASELINE_FAILED", commands)

    create_branch = run(["git", "checkout", "-b", branch_name], cwd=worktree)
    if create_branch["exitCode"] != 0:
        return _fail(output, manifest, "GIT_CREATE_BRANCH_FAILED", commands)

    replay = _replay_accepted_patch_set(
        manifest=manifest,
        workspace_root=workspace_root,
        target_repository=str(worktree),
        publisher_dir=output.parent,
    )
    commands.extend(replay.get("commands", []))
    if replay.get("status") != "SUCCESS":
        artifact = _artifact(
            manifest,
            "FAILED",
            branch_name=branch_name,
            repo_full_name=repo_full_name,
            commands=commands,
            replay=replay,
            errors=["Accepted patch set replay failed before PR publishing."],
            failure_code="ACCEPTED_PATCH_SET_REPLAY_FAILED",
        )
        _write(output, artifact)
        return ToolResult(
            tool_name=TOOL,
            tool_version="1.0.0",
            operation="publish_pull_request",
            status="FAILED",
            artifact_path=str(output),
            failure_code="ACCEPTED_PATCH_SET_REPLAY_FAILED",
            payload={"branchName": branch_name},
            errors=artifact["errors"],
        ).to_dict()

    status = run(["git", "status", "--porcelain"], cwd=worktree)
    changed_files = _changed_files(status.get("stdout") or "")
    if not changed_files:
        return _fail(output, manifest, "NO_CHANGES_TO_PUBLISH", commands, branch_name=branch_name, repo_full_name=repo_full_name, replay=replay)

    add = run(["git", "add", "--"] + changed_files, cwd=worktree)
    if add["exitCode"] != 0:
        return _fail(output, manifest, "GIT_ADD_FAILED", commands, branch_name=branch_name, repo_full_name=repo_full_name, replay=replay)

    commit_message = "Remediate OSS vulnerabilities"
    commit = run(["git", "commit", "-m", commit_message], cwd=worktree)
    if commit["exitCode"] != 0:
        return _fail(output, manifest, "GIT_COMMIT_FAILED", commands, branch_name=branch_name, repo_full_name=repo_full_name, replay=replay)

    commit_sha_result = run(["git", "rev-parse", "HEAD"], cwd=worktree)
    commit_sha = (commit_sha_result.get("stdout") or "").strip()

    push = run(["git", "push", "origin", branch_name], cwd=worktree)
    if push["exitCode"] != 0:
        return _fail(output, manifest, "GIT_PUSH_FAILED", commands, branch_name=branch_name, repo_full_name=repo_full_name, replay=replay, commit_sha=commit_sha)

    title = _pr_title(pr_summary_path)
    body_file = str(Path(pr_description_path))
    gh_command = [
        "gh",
        "pr",
        "create",
        "--repo",
        str(repo_full_name or repository_url),
        "--base",
        str(reference_branch),
        "--head",
        branch_name,
        "--title",
        title,
        "--body-file",
        body_file,
    ]
    if draft:
        gh_command.append("--draft")
    pr_create = run(gh_command, cwd=worktree)
    if pr_create["exitCode"] != 0:
        return _fail(output, manifest, "GITHUB_PR_CREATE_FAILED", commands, branch_name=branch_name, repo_full_name=repo_full_name, replay=replay, commit_sha=commit_sha)

    pr_url = (pr_create.get("stdout") or "").strip().splitlines()[-1] if (pr_create.get("stdout") or "").strip() else None
    artifact = _artifact(
        manifest,
        "SUCCESS",
        branch_name=branch_name,
        repo_full_name=repo_full_name,
        base_branch=str(reference_branch),
        commit_sha=commit_sha,
        pr_url=pr_url,
        draft=draft,
        commands=commands,
        replay=replay,
        changed_files=changed_files,
    )
    _write(output, artifact)
    return ToolResult.success(
        TOOL,
        "publish_pull_request",
        str(output),
        branchName=branch_name,
        commitSha=commit_sha,
        prUrl=pr_url,
        draft=draft,
    ).to_dict()


def build_remediation_branch_name(reference_branch: str, baseline_commit: str, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    safe_reference = re.sub(r"[^A-Za-z0-9._-]+", "-", reference_branch).strip("-") or "branch"
    return f"oss-remediation-{safe_reference}-{baseline_commit[:4]}-{timestamp}"


def _replay_accepted_patch_set(
    *,
    manifest: dict[str, Any],
    workspace_root: Path,
    target_repository: str,
    publisher_dir: Path,
) -> dict[str, Any]:
    accepted_patch_ids = set(manifest.get("acceptedPatchSet", {}).get("patchIds", []))
    replay_results: list[dict[str, Any]] = []
    for source_attempt in manifest.get("acceptedPatchSet", {}).get("sourceAttempts", []):
        attempt = _find_attempt(manifest, int(source_attempt))
        patch_plan_ref = attempt.get("patchPlan") if attempt else None
        if not patch_plan_ref:
            replay_results.append({"status": "SKIPPED", "sourceAttempt": source_attempt, "reason": "Patch plan not found."})
            continue
        source_plan_path = _resolve(workspace_root, patch_plan_ref)
        filtered_plan_path = publisher_dir / f"accepted-patch-plan-source-attempt-{source_attempt}.json"
        _write(filtered_plan_path, _filtered_patch_plan(_read_json(source_plan_path), accepted_patch_ids))
        proof_path = publisher_dir / f"patch-application-proof-source-attempt-{source_attempt}.json"
        diff_path = publisher_dir / f"patch-source-attempt-{source_attempt}.diff"
        result = apply_patch_plan(int(source_attempt), target_repository, str(filtered_plan_path), str(proof_path), str(diff_path))
        replay_results.append({
            "status": result.get("status"),
            "sourceAttempt": source_attempt,
            "patchPlan": str(filtered_plan_path),
            "patchApplicationProof": str(proof_path),
            "diff": str(diff_path),
            "failureCode": result.get("failureCode"),
        })
        if result.get("status") != "SUCCESS":
            return {"status": "FAILED", "replayResults": replay_results, "commands": []}
    return {"status": "SUCCESS", "replayResults": replay_results, "commands": []}


def _filtered_patch_plan(plan: dict[str, Any], accepted_patch_ids: set[str]) -> dict[str, Any]:
    filtered_decisions = []
    for decision in plan.get("vulnerabilityDecisions", []) or []:
        accepted_patches = [patch for patch in decision.get("patches", []) or [] if patch.get("patchId") in accepted_patch_ids]
        if not accepted_patches:
            continue
        filtered_decision = dict(decision)
        filtered_decision["patches"] = accepted_patches
        filtered_decisions.append(filtered_decision)
    replay_plan = dict(plan)
    replay_plan["artifactId"] = f"{plan.get('artifactId', 'patch-plan')}-publisher-replay"
    replay_plan["acceptedPatchIds"] = sorted(accepted_patch_ids)
    replay_plan["vulnerabilityDecisions"] = filtered_decisions
    replay_plan.setdefault("warnings", []).append("Publisher replay plan was filtered to acceptedPatchSet.patchIds.")
    return replay_plan


def _fail(output: Path, manifest: dict[str, Any], failure_code: str, commands: list[dict[str, Any]], **extra: Any) -> dict:
    artifact = _artifact(manifest, "FAILED", commands=commands, failure_code=failure_code, errors=[failure_code], **extra)
    _write(output, artifact)
    return ToolResult(
        tool_name=TOOL,
        tool_version="1.0.0",
        operation="publish_pull_request",
        status="FAILED",
        artifact_path=str(output),
        failure_code=failure_code,
        payload={key: value for key, value in extra.items() if key in {"branch_name", "branchName", "commit_sha", "commitSha"}},
        errors=[failure_code],
    ).to_dict()


def _artifact(manifest: dict[str, Any], status: str, **kwargs: Any) -> dict[str, Any]:
    return common_artifact(
        artifact_id="pull-request-publication-001",
        workflow_id=manifest.get("workflowId", "unknown"),
        created_by=TOOL,
        status=status,
        repository=manifest.get("repository", {}),
        branchName=kwargs.get("branch_name"),
        repoFullName=kwargs.get("repo_full_name"),
        baseBranch=kwargs.get("base_branch"),
        commitSha=kwargs.get("commit_sha"),
        prUrl=kwargs.get("pr_url"),
        draft=kwargs.get("draft"),
        changedFiles=kwargs.get("changed_files", []),
        replay=kwargs.get("replay", {}),
        commands=_summarize_commands(kwargs.get("commands", [])),
        failureCode=kwargs.get("failure_code"),
        errors=kwargs.get("errors", []),
        warnings=kwargs.get("warnings", []),
    )


def _summarize_commands(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summarized = []
    for item in commands:
        summarized.append({
            "command": item.get("command", []),
            "exitCode": item.get("exitCode"),
            "stderrTail": (item.get("stderr") or "")[-1000:],
            "stdoutTail": (item.get("stdout") or "")[-1000:],
        })
    return summarized


def _run(command: list[str], cwd: str | Path | None = None, timeout: int = 1800) -> dict[str, Any]:
    return run_command(command, cwd=cwd, timeout=timeout)


def _changed_files(status_stdout: str) -> list[str]:
    files = []
    for line in status_stdout.splitlines():
        if not line.strip():
            continue
        files.append(line[3:].strip())
    return files


def _pr_title(pr_summary_path: str) -> str:
    summary = _read_json(pr_summary_path)
    return summary.get("prTitle") or "OSS vulnerability remediation"


def _repo_full_name(repository_url: str) -> str | None:
    parsed = urlparse(repository_url)
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if path.count("/") >= 1:
        parts = path.split("/")
        return f"{parts[-2]}/{parts[-1]}"
    return None


def _find_attempt(manifest: dict[str, Any], attempt_number: int) -> dict[str, Any] | None:
    for attempt in manifest.get("attempts", []) or []:
        if int(attempt.get("attemptNumber", 0)) == attempt_number:
            return attempt
    return None


def _resolve(workspace_root: Path, reference: str) -> str:
    path = Path(reference)
    return str(path if path.is_absolute() else workspace_root / path)


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(path: str | Path, data: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
