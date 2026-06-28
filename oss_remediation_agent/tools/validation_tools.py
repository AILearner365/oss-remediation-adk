"""Pull request creation tool for the ADK OSS remediation workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from oss_remediation_agent.policy import RemediationPolicy
from oss_remediation_agent.schemas import PrDecision, validate_remediation_report
from oss_remediation_agent.tools.scanner_tools import _run, _trim

PR_ALLOWED_STATUSES = {"SUCCESS"}


def create_pull_request_from_remediation_report(remediation_report: dict[str, Any], workspace_path: str | None = None) -> dict[str, Any]:
    """Validate Agent 2's report, then commit, push, and create a PR only for full success."""
    policy = RemediationPolicy.from_env()
    report = remediation_report or {}
    decision = evaluate_pr_creation(report, policy)
    if not decision["allowed"]:
        return _blocked(report, decision["reason"], {"policyDecision": decision})

    repo_dir = Path(workspace_path or report.get("workspacePath") or ".").resolve()
    if not repo_dir.exists():
        return _blocked(report, f"Workspace path not found: {repo_dir}")

    changed_files = _changed_files(repo_dir)
    if not changed_files:
        return _blocked(report, "No repository changes were found to commit.")
    invalid_files = [path for path in changed_files if not policy.allows_file(path)]
    if invalid_files:
        return _blocked(report, "Files outside the configured remediation allowlist were modified.", {"invalidFiles": invalid_files})
    unreported_files = [path for path in changed_files if path not in set(report.get("modifiedFiles") or [])]
    if unreported_files:
        return _blocked(report, "Working tree contains pom.xml changes that are not present in the Remediation Report.", {"unreportedFiles": unreported_files})

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
    body_file.write_text(build_pr_body(report, policy), encoding="utf-8")
    pr = _run(["gh", "pr", "create", "--base", target_branch, "--head", source_branch, "--title", policy.pr_title, "--body-file", str(body_file)], repo_dir)
    body_file.unlink(missing_ok=True)
    if pr["returncode"] != 0:
        return _blocked(report, "Unable to create pull request using GitHub CLI.", {"details": _trim(pr)})

    return {
        "pullRequestCreated": True,
        "repositoryUrl": report.get("repositoryUrl"),
        "sourceBranch": source_branch,
        "targetBranch": target_branch,
        "pullRequestUrl": pr["stdout"].strip().splitlines()[-1] if pr["stdout"].strip() else None,
        "status": PrDecision.SUCCESS.value,
    }


def validate_repository(repo_url: str) -> dict[str, Any]:
    return {"status": "manual_review", "repo_url": repo_url, "message": "Use create_pull_request_from_remediation_report with Agent 2's Remediation Report."}


def evaluate_pr_creation(report: dict[str, Any], policy: RemediationPolicy | None = None) -> dict[str, Any]:
    """Return a deterministic policy decision for Agent 3 PR creation."""
    active_policy = policy or RemediationPolicy.from_env()
    schema_result = validate_remediation_report(report)
    if not schema_result.valid:
        return _decision(False, "INVALID_REMEDIATION_REPORT", "Invalid Remediation Report.", {"schemaErrors": list(schema_result.errors)})
    if report.get("buildStatus") != "SUCCESS":
        return _decision(False, "BUILD_NOT_SUCCESS", "Build status is not SUCCESS.")
    if report.get("testStatus") != "SUCCESS":
        return _decision(False, "TEST_NOT_SUCCESS", "Test status is not SUCCESS.")
    if str(report.get("remediationStatus") or "").upper() not in active_policy.pr_allowed_statuses:
        return _decision(False, "REMEDIATION_STATUS_BLOCKED", "remediationStatus must be SUCCESS. Manual-review or partial remediation results do not create PRs.")
    if not report.get("featureBranch"):
        return _decision(False, "FEATURE_BRANCH_MISSING", "featureBranch is missing.")
    if not report.get("referenceBranch"):
        return _decision(False, "REFERENCE_BRANCH_MISSING", "referenceBranch is missing.")

    modified_files = report.get("modifiedFiles") or []
    if not modified_files:
        return _decision(False, "NO_MODIFIED_FILES", "No modified pom.xml files are present in the Remediation Report.")
    invalid_report_files = [path for path in modified_files if not active_policy.allows_file(path)]
    if invalid_report_files:
        return _decision(False, "INVALID_MODIFIED_FILES", "Remediation Report contains files outside the configured allowlist.", {"invalidFiles": invalid_report_files})
    if report.get("manualReviewItems"):
        return _decision(False, "MANUAL_REVIEW_PRESENT", "Manual-review items are present; PR creation is blocked until they are resolved outside automation.")
    for item in [*report.get("remediatedVulnerabilities", []), *report.get("failedItems", [])]:
        if item.get("status") == "FAILED":
            return _decision(False, "FAILED_ITEM_PRESENT", "At least one vulnerability has FAILED status.")

    scan = report.get("postRemediationScan") or {}
    if scan.get("newCriticalOrHighIntroduced"):
        return _decision(False, "NEW_CRITICAL_OR_HIGH", "Post-remediation scan introduced a new Critical or High vulnerability.")
    if int(scan.get("criticalRemaining") or 0) > 0:
        return _decision(False, "CRITICAL_REMAINING", "Critical vulnerabilities remain after remediation.")
    if int(scan.get("highRemaining") or 0) > 0:
        return _decision(False, "HIGH_REMAINING", "High vulnerabilities remain after remediation.")
    if scan.get("remainingCriticalOrHighItems"):
        return _decision(False, "REMAINING_ITEMS", "A Critical or High vulnerability remains after remediation.")
    return _decision(True, "PR_ALLOWED", "All configured PR safety gates passed.")


def _validate_pr_report(report: dict[str, Any]) -> str | None:
    """Backward-compatible validator that returns only the blocked reason."""
    decision = evaluate_pr_creation(report)
    return None if decision["allowed"] else decision["reason"]


def _changed_files(repo_dir: Path) -> list[str]:
    status = _run(["git", "status", "--porcelain"], repo_dir)
    files: list[str] = []
    for line in status.get("stdout", "").splitlines():
        if len(line) > 3:
            path = line[3:].strip()
            files.append(path.split(" -> ", 1)[-1])
    return files


def _blocked(report: dict[str, Any], reason: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "pullRequestCreated": False,
        "status": PrDecision.BLOCKED.value,
        "reason": reason,
        "repositoryUrl": report.get("repositoryUrl"),
        "sourceBranch": report.get("featureBranch"),
        "targetBranch": report.get("referenceBranch"),
    }
    if extra:
        result.update(extra)
    return result


def build_pr_body(report: dict[str, Any], policy: RemediationPolicy | None = None) -> str:
    active_policy = policy or RemediationPolicy.from_env()
    if active_policy.pr_template_path:
        template_path = Path(active_policy.pr_template_path)
        if template_path.exists():
            return render_template(template_path.read_text(encoding="utf-8"), report)
    return default_pr_body(report)


def _build_pr_body(report: dict[str, Any]) -> str:
    return default_pr_body(report)


def default_pr_body(report: dict[str, Any]) -> str:
    scan = report.get("postRemediationScan", {})
    lines = [
        "# OSS Vulnerability Remediation",
        "",
        "## Summary",
        "",
        "This PR updates Maven dependency versions to remediate all Critical and High OSS vulnerabilities identified by the configured scanner policy.",
        "",
        "PR creation is blocked by design when any item requires manual review, validation fails, or any Critical/High vulnerability remains.",
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
        f"| New Critical/High Introduced | {scan.get('newCriticalOrHighIntroduced', False)} |",
        "",
        "## Remediation Details",
        "",
        "| Dependency Name | Severity | Current Version | Suggested Fix Versions | Fixed Version | Strategy | Status | Comments |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in report.get("remediatedVulnerabilities", []):
        lines.append(f"| {_cell(item.get('dependencyName'))} | {_cell(item.get('severity'))} | {_cell(item.get('previousVersion'))} | {_cell(', '.join(item.get('suggestedFixVersions', [])))} | {_cell(item.get('updatedVersion'))} | {_cell(item.get('updateStrategy'))} | FIXED | {_cell(item.get('selectedVersionReason'))} |")
    lines.extend(["", "## Modified Files", "", *[f"- `{path}`" for path in report.get("modifiedFiles", [])], "", "## Notes", "", "No Java source code was modified. Only Maven dependency versions were updated."])
    return "\n".join(lines) + "\n"


def render_template(template: str, report: dict[str, Any]) -> str:
    scan = report.get("postRemediationScan", {})
    values = {
        "buildStatus": report.get("buildStatus", ""),
        "testStatus": report.get("testStatus", ""),
        "remediationStatus": report.get("remediationStatus", ""),
        "criticalRemaining": scan.get("criticalRemaining", 0),
        "highRemaining": scan.get("highRemaining", 0),
        "modifiedFiles": "\n".join(f"- `{path}`" for path in report.get("modifiedFiles", [])),
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def _decision(allowed: bool, code: str, reason: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    decision = {"allowed": allowed, "code": code, "reason": reason}
    if extra:
        decision.update(extra)
    return decision


def _cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")
