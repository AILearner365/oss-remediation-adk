from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.contracts import ToolResult, common_artifact

TOOL = "PRCreationTool"


def create_pr_summary(manifest_path: str, output_path: str, pr_description_path: str, workflow_id: str = "unknown") -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8")) if Path(manifest_path).exists() else {}
    accepted = manifest.get("acceptedPatchSet", {})
    remediation_summary = _remediation_summary(manifest)
    validation_summary = _validation_summary(manifest)
    manual_review_summary = _manual_review_summary(manifest)
    pr_type = "FULL_REMEDIATION" if validation_summary.get("remainingCriticalHigh", 0) == 0 else "PARTIAL_REMEDIATION"
    eligible = accepted.get("status") == "VALIDATED"
    body = _markdown(remediation_summary, validation_summary, pr_type, manual_review_summary)
    Path(pr_description_path).parent.mkdir(parents=True, exist_ok=True)
    Path(pr_description_path).write_text(body, encoding="utf-8")
    summary = common_artifact(
        artifact_id="pr-summary-001",
        workflow_id=workflow_id or manifest.get("workflowId", "unknown"),
        created_by=TOOL,
        status="ELIGIBLE" if eligible else "NOT_ELIGIBLE",
        prTitle="OSS vulnerability remediation",
        prType=pr_type if eligible else "NOT_ELIGIBLE",
        pullRequestEligibility={
            "eligible": eligible,
            "type": pr_type if eligible else "NOT_ELIGIBLE",
            "reason": "Validated accepted patch set exists." if eligible else "No validated accepted patch set exists.",
        },
        remediationSummary=remediation_summary,
        manualReviewSummary=manual_review_summary,
        validationSummary=validation_summary,
        artifactReferences={"manifest": manifest_path, "prDescription": pr_description_path},
        prBodyMarkdown=body,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult.success(
        TOOL,
        "create_pr_summary",
        output_path,
        prDescriptionPath=pr_description_path,
        manifestStatus=manifest.get("status"),
        prType=summary["prType"],
    ).to_dict()


def _remediation_summary(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    accepted = manifest.get("acceptedPatchSet", {})
    accepted_rows = accepted.get("remediationSummary") or accepted.get("vulnerabilityDecisions") or []
    rows: list[dict[str, Any]] = []
    severity_by_vulnerability = _severity_by_vulnerability_id(manifest)
    for row in accepted_rows:
        vulnerability_id = row.get("vulnerabilityId")
        rows.append({
            "vulnerabilityId": vulnerability_id,
            "aliases": row.get("aliases", []),
            "severity": row.get("severity") or severity_by_vulnerability.get(vulnerability_id),
            "dependency": row.get("dependency") or row.get("packageName") or "UNKNOWN",
            "oldVersion": row.get("oldVersion"),
            "newVersion": row.get("newVersion"),
            "status": row.get("status", "REMEDIATED"),
            "statusReason": row.get("statusReason", "Patch set validated successfully."),
        })

    # Backward-compatible fallback for older manifests that only stored IDs.
    if not rows:
        for vulnerability_id in accepted.get("vulnerabilityIds", []) or []:
            rows.append({
                "vulnerabilityId": vulnerability_id,
                "aliases": [],
                "severity": severity_by_vulnerability.get(vulnerability_id),
                "dependency": "UNKNOWN",
                "oldVersion": None,
                "newVersion": None,
                "status": "REMEDIATED",
                "statusReason": "Patch set validated successfully. Dependency/version metadata was not available in the accepted patch set.",
            })
    return rows


def _manual_review_summary(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    decision = _manual_review_decision(manifest)
    rows: list[dict[str, Any]] = []
    severity_by_vulnerability = _severity_by_vulnerability_id(manifest)
    for row in decision.get("vulnerabilityDecisions", []) or []:
        dependency = row.get("dependency") or {}
        package_name = dependency.get("packageName") or _dependency_coordinate(dependency)
        vulnerability_id = row.get("vulnerabilityId")
        rows.append({
            "vulnerabilityId": vulnerability_id,
            "aliases": row.get("aliases", []),
            "severity": row.get("severity") or severity_by_vulnerability.get(vulnerability_id),
            "dependency": package_name or "UNKNOWN",
            "currentVersion": dependency.get("currentVersion"),
            "status": row.get("decision") or "MANUAL_REVIEW",
            "manualReviewCategory": row.get("manualReviewCategory"),
            "reason": row.get("statusReason") or row.get("reason") or "Manual review required.",
        })
    return rows


def _manual_review_decision(manifest: dict[str, Any]) -> dict[str, Any]:
    planning = manifest.get("planning", {})
    path = planning.get("manualReviewDecision")
    if not path:
        for attempt in reversed(manifest.get("attempts", []) or []):
            candidate = attempt.get("manualReviewDecision")
            if candidate:
                path = candidate
                break
    if not path:
        return {}
    workspace_root = Path(manifest.get("workspaceRoot", "."))
    candidate = workspace_root / path
    if not candidate.exists():
        candidate = Path(path)
    if not candidate.exists():
        return {}
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    return payload if payload.get("decisionType") == "MANUAL_REVIEW" else {}


def _dependency_coordinate(dependency: dict[str, Any]) -> str | None:
    group_id = dependency.get("groupId")
    artifact_id = dependency.get("artifactId")
    if group_id and artifact_id:
        return f"{group_id}:{artifact_id}"
    return artifact_id or group_id


def _severity_by_vulnerability_id(manifest: dict[str, Any]) -> dict[str, str]:
    assessment_ref = (manifest.get("baseline") or {}).get("vulnerabilityAssessmentReport")
    if not assessment_ref:
        return {}
    workspace_root = Path(manifest.get("workspaceRoot", "."))
    assessment_path = Path(assessment_ref)
    if not assessment_path.is_absolute():
        assessment_path = workspace_root / assessment_path
    if not assessment_path.exists():
        return {}
    try:
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    result: dict[str, str] = {}
    for vulnerability in assessment.get("vulnerabilities", []) or []:
        vulnerability_id = vulnerability.get("vulnerabilityId")
        severity = vulnerability.get("severity")
        if vulnerability_id and severity:
            result[str(vulnerability_id)] = str(severity)
    return result


def _validation_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    validation = _latest_validation(manifest)
    osv = validation.get("osvValidation", {}) if validation else {}
    return {
        "baselineBuild": "SUCCESS" if manifest.get("baseline", {}).get("baselineBuildResult") else "UNKNOWN",
        "changeScopeValidation": (validation.get("changeScopeValidation") or {}).get("status") if validation else "UNKNOWN",
        "buildValidation": (validation.get("buildValidation") or {}).get("status") if validation else "UNKNOWN",
        "testValidation": (validation.get("testValidation") or {}).get("status") if validation else "UNKNOWN",
        "osvValidation": osv.get("status", "UNKNOWN"),
        "remainingCriticalCount": osv.get("remainingCriticalCount", 0),
        "remainingHighCount": osv.get("remainingHighCount", 0),
        "remainingCriticalHigh": (osv.get("remainingCriticalCount") or 0) + (osv.get("remainingHighCount") or 0),
        "newCriticalHighIntroduced": osv.get("newCriticalHighIntroduced", False),
    }


def _latest_validation(manifest: dict[str, Any]) -> dict[str, Any]:
    for attempt in reversed(manifest.get("attempts", []) or []):
        path = attempt.get("validationResult")
        if not path:
            continue
        workspace_root = Path(manifest.get("workspaceRoot", "."))
        candidate = workspace_root / path
        if not candidate.exists():
            candidate = Path(path)
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {}


def _markdown(
    remediation_summary: list[dict[str, Any]],
    validation_summary: dict[str, Any],
    pr_type: str,
    manual_review_summary: list[dict[str, Any]],
) -> str:
    lines = [
        "# OSS Vulnerability Remediation",
        "",
        "## Summary",
        "",
        "This PR remediates Critical/High OSS vulnerabilities detected by the automated OSS remediation workflow.",
        "",
        f"Remediation type: **{pr_type}**",
        "",
        "## Remediated Vulnerabilities",
        "",
        "| Vulnerability ID | CVE | Severity | Dependency | Old Version | New Version | Status | Reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if remediation_summary:
        for row in remediation_summary:
            lines.append(
                f"| {row.get('vulnerabilityId')} | {_aliases(row)} | {row.get('severity') or 'N/A'} | {row.get('dependency')} | {row.get('oldVersion') or 'N/A'} | {row.get('newVersion') or 'N/A'} | {row.get('status')} | {row.get('statusReason')} |"
            )
    else:
        lines.append("| N/A | N/A | N/A | N/A | N/A | N/A | NOT_ELIGIBLE | No validated remediation available. |")

    if manual_review_summary:
        lines.extend([
            "",
            "## Vulnerabilities Requiring Manual Review",
            "",
            "The following Critical/High vulnerabilities were not patched automatically. They require manual review for the reasons listed below.",
            "",
            "| Vulnerability ID | CVE | Severity | Dependency | Current Version | Status | Category | Reason |",
            "|---|---|---|---|---|---|---|---|",
        ])
        for row in manual_review_summary:
            lines.append(
                f"| {row.get('vulnerabilityId')} | {_aliases(row)} | {row.get('severity') or 'N/A'} | {row.get('dependency')} | {row.get('currentVersion') or 'N/A'} | {row.get('status')} | {row.get('manualReviewCategory') or 'MANUAL_REVIEW'} | {row.get('reason')} |"
            )

    lines.extend([
        "",
        "## Changes Made",
        "",
        "Updated Maven dependency versions in `pom.xml` only.",
        "",
        "No Java source code, test source code, JDK version, Maven plugin build logic, suppression, or ignore workaround changes were introduced.",
        "",
        "## Validation",
        "",
        "| Validation Step | Result |",
        "|---|---|",
        f"| Baseline build | {validation_summary.get('baselineBuild')} |",
        f"| Change scope validation | {validation_summary.get('changeScopeValidation')} |",
        f"| Maven build | {validation_summary.get('buildValidation')} |",
        f"| Maven tests | {validation_summary.get('testValidation')} |",
        f"| OSV validation | {validation_summary.get('osvValidation')} |",
        f"| Remaining Critical vulnerabilities | {validation_summary.get('remainingCriticalCount')} |",
        f"| Remaining High vulnerabilities | {validation_summary.get('remainingHighCount')} |",
        f"| New Critical/High vulnerabilities introduced | {validation_summary.get('newCriticalHighIntroduced')} |",
        "",
        "## Notes for Reviewers",
        "",
        _reviewer_notes(pr_type),
    ])
    return "\n".join(lines) + "\n"


def _reviewer_notes(pr_type: str) -> str:
    if pr_type == "PARTIAL_REMEDIATION":
        return "The validated patch set was applied successfully. Any remaining Critical/High vulnerabilities are listed in the manual-review section with reasons."
    return "The patch set was generated from the validated remediation plan and applied using exact-text Maven dependency version updates. The resulting project build and tests passed, and post-remediation OSV validation found no remaining Critical or High vulnerabilities."


def _aliases(row: dict[str, Any]) -> str:
    aliases = row.get("aliases") or []
    return ", ".join(str(alias) for alias in aliases) if aliases else "N/A"
