"""Automated Maven-only remediation tool for the ADK OSS workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from oss_remediation_agent.policy import RemediationPolicy
from oss_remediation_agent.schemas import ItemStatus, RemediationStatus, make_remediation_report, validate_assessment_report, vulnerability_key
from oss_remediation_agent.tools.maven_tools import PomTarget, apply_target, changed_poms, find_version_targets, insert_dependency_management_target, restore_poms, snapshot_poms
from oss_remediation_agent.tools.scanner_tools import _extract_vulnerabilities, _run, _trim, _version_key, run_maven, run_osv


def generate_remediation_report(vulnerability_assessment_report: dict[str, Any], workspace_path: str | None = None) -> dict[str, Any]:
    """Plan, apply, validate, and report Maven dependency remediations."""
    policy = RemediationPolicy.from_env()
    assessment = vulnerability_assessment_report or {}
    repo_dir = Path(workspace_path or assessment.get("workspacePath") or ".").resolve()
    report = make_remediation_report(assessment, repo_dir, policy_metadata=policy.as_report_metadata())

    schema_result = validate_assessment_report(assessment)
    if not schema_result.valid:
        report["failedItems"].append(_fail("Invalid Vulnerability Assessment Report.", {"errors": list(schema_result.errors)}))
        return report

    vulnerabilities = [vulnerability for vulnerability in assessment.get("vulnerabilities", []) if policy.allows_severity(vulnerability.get("severity"))]
    original_vulnerability_keys = {vulnerability_key(vulnerability) for vulnerability in vulnerabilities}

    if assessment.get("buildStatus") != "SUCCESS":
        report["failedItems"].append(_fail("Agent 1 buildStatus is not SUCCESS."))
        return report
    if not repo_dir.exists():
        report["failedItems"].append(_fail(f"Workspace path not found: {repo_dir}"))
        return report

    feature_branch = assessment.get("featureBranch")
    if feature_branch:
        checkout = _run(["git", "checkout", "-B", feature_branch], repo_dir)
        if checkout["returncode"] != 0:
            report["failedItems"].append(_fail("Cannot checkout remediation branch.", _trim(checkout)))
            return report

    workflow_snapshot = snapshot_poms(repo_dir)
    for vulnerability in vulnerabilities:
        item = remediate_one_vulnerability(repo_dir, vulnerability, original_vulnerability_keys, policy)
        report["decisionLog"].append({"dependencyName": item.get("dependencyName"), "status": item.get("status"), "reason": item.get("manualReviewReason") or item.get("reason") or item.get("selectedVersionReason")})
        bucket = {ItemStatus.FIXED.value: "remediatedVulnerabilities", ItemStatus.MANUAL_REVIEW.value: "manualReviewItems"}.get(item.get("status"), "failedItems")
        report[bucket].append(item)

    if report["failedItems"]:
        restore_poms(workflow_snapshot)
        return report

    report["modifiedFiles"] = changed_poms(repo_dir, workflow_snapshot)
    build_result = run_maven(repo_dir, policy.build_goals, policy=policy, timeout=1800)
    report["buildStatus"] = "SUCCESS" if build_result["returncode"] == 0 else "FAILED"
    if build_result["returncode"] != 0:
        restore_poms(workflow_snapshot)
        report["modifiedFiles"] = []
        report["failedItems"].append(_fail("buildStatus failed after remediation.", _trim(build_result)))
        return report

    test_result = run_maven(repo_dir, policy.test_goals, policy=policy, timeout=1800)
    report["testStatus"] = "SUCCESS" if test_result["returncode"] == 0 else "FAILED"
    if test_result["returncode"] != 0:
        restore_poms(workflow_snapshot)
        report["modifiedFiles"] = []
        report["failedItems"].append(_fail("testStatus failed after remediation.", _trim(test_result)))
        return report

    post_scan = run_osv(repo_dir, policy=policy)
    if post_scan["returncode"] != 0 and not post_scan.get("json"):
        restore_poms(workflow_snapshot)
        report["modifiedFiles"] = []
        report["failedItems"].append(_fail("Post-remediation OSV scan failed.", _trim(post_scan)))
        return report

    remaining_vulnerabilities = _extract_vulnerabilities(post_scan.get("json") or {})
    manual_review_keys = {vulnerability_key(vulnerability) for vulnerability in report["manualReviewItems"]}
    remaining_items = [
        {
            "dependencyName": vulnerability.get("dependencyName"),
            "severity": vulnerability.get("severity"),
            "vulnerabilityIds": vulnerability.get("vulnerabilityIds", []),
            "status": ItemStatus.MANUAL_REVIEW.value if vulnerability_key(vulnerability) in manual_review_keys else ItemStatus.UNRESOLVED.value,
        }
        for vulnerability in remaining_vulnerabilities
    ]
    report["postRemediationScan"] = {
        "criticalRemaining": sum(item["severity"] == "CRITICAL" for item in remaining_items),
        "highRemaining": sum(item["severity"] == "HIGH" for item in remaining_items),
        "newCriticalOrHighIntroduced": any(vulnerability_key(vulnerability) not in original_vulnerability_keys for vulnerability in remaining_vulnerabilities),
        "remainingCriticalOrHighItems": remaining_items,
    }

    unresolved_items = [item for item in remaining_items if item["status"] != ItemStatus.MANUAL_REVIEW.value]
    if unresolved_items or report["postRemediationScan"]["newCriticalOrHighIntroduced"]:
        report["failedItems"].extend(unresolved_items)
        report["remediationStatus"] = RemediationStatus.FAILED.value
    elif report["manualReviewItems"]:
        report["remediationStatus"] = RemediationStatus.PARTIAL_SUCCESS.value
    else:
        report["remediationStatus"] = RemediationStatus.SUCCESS.value
    return report


def apply_remediation(repo_url: str, dependency: str, recommended_version: str) -> dict[str, Any]:
    return {"status": "manual_review", "repo_url": repo_url, "dependency": dependency, "requested_version": recommended_version, "message": "Use generate_remediation_report with Agent 1's report."}


def remediate_one_vulnerability(repo_dir: Path, vulnerability: dict[str, Any], original_vulnerability_keys: set[tuple[str, tuple[str, ...]]], policy: RemediationPolicy) -> dict[str, Any]:
    dependency_name = str(vulnerability.get("dependencyName") or "")
    coordinate = dependency_name.split(":")
    candidate_versions = sorted({str(version) for version in vulnerability.get("suggestedFixVersions", []) if version}, key=_version_key)

    if len(coordinate) < 2:
        return _manual(vulnerability, f"Not a Maven coordinate: {dependency_name}")
    if not candidate_versions:
        return _manual(vulnerability, "No suggested fixed versions from OSV.")
    if policy.block_java_or_jdk_upgrade and _appears_to_require_java_or_jdk_upgrade(vulnerability):
        return _manual(vulnerability, "Fix appears to require JDK/Java upgrade, out of scope.")

    group_id, artifact_id = coordinate[0], coordinate[1]
    targets = find_version_targets(repo_dir, group_id, artifact_id, str(vulnerability.get("affectedPomFile") or "pom.xml"), bool(vulnerability.get("isDirectDependency")))
    if not targets and not bool(vulnerability.get("isDirectDependency")):
        transitive_target = plan_transitive_dependency_management_override(repo_dir, group_id, artifact_id, policy)
        if transitive_target:
            targets.append(transitive_target)
    if not targets:
        return _manual(vulnerability, "No safe Maven version target found; external parent, imported BOM, or non-version build change may be required.")

    vulnerability_snapshot = snapshot_poms(repo_dir)
    attempts: list[dict[str, Any]] = []
    for candidate_version in candidate_versions:
        for target in targets:
            restore_poms(vulnerability_snapshot)
            update_result = apply_target(target, candidate_version)
            if not update_result["updated"]:
                attempts.append({"version": candidate_version, "target": target.label(repo_dir), "reason": update_result["reason"], "evidence": target.evidence})
                continue

            validation_ok, validation_reason = validate_candidate(repo_dir, vulnerability, original_vulnerability_keys, policy)
            if not validation_ok:
                attempts.append({"version": candidate_version, "target": target.label(repo_dir), "reason": validation_reason, "evidence": target.evidence})
                continue

            pom_file = str(target.pom_path.relative_to(repo_dir))
            return {
                "dependencyName": dependency_name,
                "previousVersion": vulnerability.get("currentVersion"),
                "updatedVersion": candidate_version,
                "severity": str(vulnerability.get("severity", "")).upper(),
                "vulnerabilityIds": vulnerability.get("vulnerabilityIds", []),
                "affectedPomFile": pom_file,
                "suggestedFixVersions": candidate_versions,
                "selectedVersionReason": selected_version_reason(candidate_version, target),
                "rejectedVersions": [{"version": version, "reason": rejected_version_reason(version, candidate_version, attempts)} for version in candidate_versions if version != candidate_version],
                "status": ItemStatus.FIXED.value,
                "modifiedFiles": [pom_file],
                "updateStrategy": target.strategy,
                "remediationEvidence": target.evidence,
            }

    restore_poms(vulnerability_snapshot)
    return _manual(vulnerability, "No suggested fixed version passed build, tests, and OSV validation.", attempts)


def plan_transitive_dependency_management_override(repo_dir: Path, group_id: str, artifact_id: str, policy: RemediationPolicy) -> PomTarget | None:
    if not policy.allow_dependency_management_overrides:
        return None
    evidence = dependency_tree_evidence(repo_dir, group_id, artifact_id, policy)
    if policy.require_transitive_dependency_evidence and not evidence.get("confirmed"):
        return None
    return insert_dependency_management_target(repo_dir, group_id, artifact_id, evidence)


def validate_candidate(repo_dir: Path, vulnerability: dict[str, Any], original_vulnerability_keys: set[tuple[str, tuple[str, ...]]], policy: RemediationPolicy) -> tuple[bool, str]:
    for label, goals in (("build", policy.build_goals), ("tests", policy.test_goals)):
        result = run_maven(repo_dir, goals, policy=policy, timeout=1800)
        if result["returncode"] != 0:
            return False, java_or_jdk_failure_reason(result) or f"Maven {label} failed for candidate."

    scan = run_osv(repo_dir, policy=policy)
    if scan["returncode"] != 0 and not scan.get("json"):
        return False, "OSV validation scan failed for candidate."
    remaining_vulnerabilities = _extract_vulnerabilities(scan.get("json") or {})
    remaining_keys = {vulnerability_key(item) for item in remaining_vulnerabilities}
    if vulnerability_key(vulnerability) in remaining_keys:
        return False, "OSV still reports original vulnerability."
    if any(vulnerability_key(item) not in original_vulnerability_keys for item in remaining_vulnerabilities):
        return False, "Candidate introduced new Critical/High vulnerability."
    return True, ""


def dependency_tree_evidence(repo_dir: Path, group_id: str, artifact_id: str, policy: RemediationPolicy) -> dict[str, Any]:
    includes = f"-Dincludes={group_id}:{artifact_id}"
    result = run_maven(repo_dir, ["dependency:tree", includes], policy=policy, timeout=1800)
    output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
    matching_lines = [line.strip() for line in output.splitlines() if f"{group_id}:{artifact_id}" in line]
    return {"source": "mvn dependency:tree", "command": result.get("command"), "returncode": result.get("returncode"), "confirmed": result.get("returncode") == 0 and bool(matching_lines), "matchingLines": matching_lines[:20]}


def _appears_to_require_java_or_jdk_upgrade(vulnerability: dict[str, Any]) -> bool:
    text = json.dumps(vulnerability, default=str).lower()
    return bool(re.search(r"\b(jdk|java)\s*(17|21|22|23)\b|requires?\s+(jdk|java)|minimum\s+(jdk|java)", text))


def java_or_jdk_failure_reason(result: dict[str, Any]) -> str | None:
    text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    indicators = ["invalid target release", "release version", "unsupported class file major version", "compiled by a more recent version", "source release", "target release"]
    if any(indicator in text for indicator in indicators):
        return "Candidate fixed version appears to require a JDK upgrade, which is out of scope."
    return None


def _manual(vulnerability: dict[str, Any], reason: str, attempts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "dependencyName": vulnerability.get("dependencyName"),
        "currentVersion": vulnerability.get("currentVersion"),
        "severity": str(vulnerability.get("severity", "")).upper(),
        "vulnerabilityIds": vulnerability.get("vulnerabilityIds", []),
        "suggestedFixVersions": vulnerability.get("suggestedFixVersions", []),
        "affectedPomFile": vulnerability.get("affectedPomFile"),
        "status": ItemStatus.MANUAL_REVIEW.value,
        "manualReviewRequired": True,
        "manualReviewReason": reason,
    }
    if attempts:
        item["attemptedVersions"] = attempts
    return item


def _fail(reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"status": ItemStatus.FAILED.value, "reason": reason}
    if details:
        item["details"] = details
    return item


def selected_version_reason(version: str, target: PomTarget) -> str:
    return f"Selected {version} after build, test, and OSV validation; updated Maven {target.strategy} without source-code or JDK changes."


def rejected_version_reason(version: str, selected_version: str, attempts: list[dict[str, Any]]) -> str:
    for attempt in attempts:
        if attempt.get("version") == version:
            return str(attempt.get("reason") or "Rejected during validation.")
    return f"Not selected because {selected_version} was the lowest suggested version that passed validation."


_k = vulnerability_key
_jdk_fail = java_or_jdk_failure_reason
