from __future__ import annotations

import shutil
from pathlib import Path

from oss_remediation_agent.contracts import ToolResult
from oss_remediation_agent.utils import run_command

TOOL = "RepoCheckoutTool"


def checkout_baseline(repository_url: str, reference_branch: str, workspace_root: str) -> dict:
    root = Path(workspace_root)
    target = root / "baseline" / "repository"
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = run_command(["git", "clone", repository_url, str(target)])
    if result["exitCode"] != 0:
        return ToolResult.failed(TOOL, "checkout_baseline", "CHECKOUT_FAILED", [result.get("stderr", "")]).to_dict()
    result = run_command(["git", "checkout", reference_branch], cwd=target)
    if result["exitCode"] != 0:
        return ToolResult.failed(TOOL, "checkout_baseline", "CHECKOUT_FAILED", [result.get("stderr", "")]).to_dict()
    commit = run_command(["git", "rev-parse", "HEAD"], cwd=target)
    return ToolResult.success(TOOL, "checkout_baseline", repositoryPath=str(target), baselineCommit=commit.get("stdout", "").strip()).to_dict()


def restore_attempt_workspace(workspace_root: str, attempt_number: int, baseline_path: str = "baseline/repository") -> dict:
    root = Path(workspace_root)
    source = root / baseline_path
    target = root / f"attempt-{attempt_number}" / "repository"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return ToolResult.success(TOOL, "restore_attempt_workspace", attemptWorkspace=str(target)).to_dict()
