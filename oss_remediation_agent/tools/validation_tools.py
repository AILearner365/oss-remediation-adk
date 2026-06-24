"""Pull request creation tool for the ADK OSS remediation workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from oss_remediation_agent.tools.scanner_tools import _run, _trim

PR_ALLOWED_STATUSES = {"SUCCESS", "PARTIAL_SUCCESS"}


def create_pull_request_from_remediation_report(remediation_report: dict[str, Any], workspace_path: str | None = None) -> dict[str, Any]:
    """Validate Agent 2's Remediation Report, then commit, push, and create a PR.

    Manual review does not automatically block PR creation. A PR is allowed for
    PARTIAL_SUCCESS when all remaining Critical/High findings are explicitly
    marked MANUAL_REVIEW and build/tests passed.
    """

    report = remediation_report or {}
    reason = _validate_pr_report(report)
    if reason:
        return _blocked(report, reason)

    repo_dir = Path(workspace_path or report.get("workspacePath") or ".").resolve()
    if not repo_dir.exists():
        return _blocked(report, f"Workspace path not found: {repo_dir}")

    changed_files = _changed_files(repo_dir)
    invalid_files = [path for path in changed_files if Path(path).name != "pom.xml"]
    if invalid_files:
        return _blocked(report, "Files other than pom.xml were modified.", {"invalidFiles": invalid_files})

    if changed_files:
        _run(["git", "add", *changed_files], repo_dir)
        commit = _run(["git", "commit", "-m", "Apply OSS dependency remediation"], repo_dir)
        if commit["returncode"] != 0:
            return _blocked(report, "Unable to create remediation commit.", {"details": _trim(commit)})

    source_branch = report["featureBranch"]
    target_branch = report["referenceBranch"]
    push = _run(["git", "push", "-u", "origin", source_branch], repo_dir)
    if push["returncode"] != 0:
        return _blocked(report, "Unable to push remediation branch.", {"details": _trim(push)})

    body_file = repo_dir / ".oss-remediation-pr-body.md"
    body_file.write_text(_build_pr_body(report), encoding="utf-8")
    pr = _run([
        "gh",
        "pr",
        "create",
        "--base",
        target_branch,
        "--head",
        source_branch,
        "--title",
        "OSS vulnerability remediation",
        "--body-file",
        str(body_file),
    ], repo_dir)
    body_file.unlink(missing_ok=True)

    if pr["returncode"] != 0:
        return _blocked(report, "Unable to create pull request using GitHub CLI.", {"details": _trim(pr)})

    return {
        "pullRequestCreated": True,
        "repositoryUrl": report.get("repositoryUrl"),
        "sourceBranch": source_branch,
        "targetBranch": target_branch,
        "pullRequestUrl": pr["stdout"].strip().splitlines()[-1] if pr["stdout"].strip() else None,
        "status": "SUCCESS",
    }


def validate_repository(repo_url: str) -> dict[str, Any]:
    """Backward-compatible alias for the previous sample validation tool."""
    return {
        "status": "manual_review",
        "repo_url": repo_url,
        "message": "Use create_pull_request_from_remediation_report with Agent 2's Remediation Report.",
    }


def _validate_pr_report(report: dict[str, Any]) -> str | None:
    if report.get("buildStatus") != "SUCCESS":
        return "Build status is not SUCCESS."
    if report.get("testStatus") != "SUCCESS":
        return "Test status is not SUCCESS."
    if report.get("remediationStatus") not in PR_ALLOWED_STATUSES:
        return "remediationStatus must be SUCCESS or PARTIAL_SUCCESS."
    if not report.get("featureBranch"):
        return "featureBranch is missing."
    if not report.get("referenceBranch"):
        return "referenceBranch is missing."

    all_items = []
    all_items.extend(report.get("remediatedVulnerabilities", []))
    all_items.extend(report.get("manualReviewItems", []))
    all_items.extend(report.get("failedItems", []))
    for item in all_items:
        if item.get("status") == "FAILED":
            return "At least one vulnerability has FAILED status."

    for item in report.get("postRemediationScan", {}).get("remainingCriticalOrHighItems", []):
        if item.get("status") != "MANUAL_REVIEW":
            return "A remaining Critical or High vulnerability is not marked MANUAL_REVIEW."
    return None


def _changed_files(repo_dir: Path) -> list[str]:
    status = _run(["git", "status", "--porcelain"], repo_dir)
    return [line[3:].strip() for line in status.get("stdout", "").splitlines() if len(line) > 3]


def _blocked(report: dict[str, Any], reason: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "pullRequestCreated": False,
        "status": "BLOCKED",
        "reason": reason,
        "repositoryUrl": report.get("repositoryUrl"),
        "sourceBranch": report.get("featureBranch"),
        "targetBranch": report.get("referenceBranch"),
    }
    if extra:
        result.update(extra)
    return result


def _build_pr_body(report: dict[str, Any]) -> str:
    scan = report.get("postRemediationScan", {})
    lines = [
        "# OSS Vulnerability Remediation",
        "",
        "## Summary",
        "",
        "This PR updates Maven dependency versions to remediate Critical and High OSS vulnerabilities identified by OSV Scanner.",
        "",
        "Manual-review items may be included when remediation requires changes outside the automation scope, such as JDK upgrades or Java source changes.",
        "",
        "## Validation",
        "",
        "| Check | Status |",
        "|---|---|",
        f"| Maven Build | {report.get('buildStatus')} |",
        f"| Tests | {report.get('testStatus')} |",
        f"| Remediation Status | {report.get('remediationStatus')} |",
        f"| Critical Vulnerabilities Remaining | {scan.get('criticalRemaining', 0)} |",
        f"| High Vulnerabilities Remaining | {scan.get('highRemaining', 0)} |",
        f"| Manual Review Items | {len(report.get('manualReviewItems', []))} |",
        "",
        "## Remediation Details",
        "",
        "| Dependency Name | Severity | Current Version | Suggested Fix Versions | Fixed Version | Status | Comments |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in report.get("remediatedVulnerabilities", []):
        lines.append(
            f"| {item.get('dependencyName')} | {item.get('severity')} | {item.get('previousVersion')} | {', '.join(item.get('suggestedFixVersions', []))} | {item.get('updatedVersion')} | FIXED | {_cell(item.get('selectedVersionReason'))} |"
        )
    for item in report.get("manualReviewItems", []):
        lines.append(
            f"| {item.get('dependencyName')} | {item.get('severity')} | {item.get('currentVersion')} | {', '.join(item.get('suggestedFixVersions', []))} | N/A | MANUAL_REVIEW | {_cell(item.get('manualReviewReason'))} |"
        )
    lines.extend(["", "## Modified Files", ""])
    lines.extend([f"- `{path}`" for path in report.get("modifiedFiles", [])])
    lines.extend(["", "## Notes", "", "No Java source code was modified. Only Maven dependency versions were updated."])
    return "\n".join(lines) + "\n"


def _cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")
