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
    pr_type = "FULL_REMEDIATION" if validation_summary.get("remainingCriticalHigh", 0) == 0 else "PARTIAL_REMEDIATION"
    eligible = accepted.get("status") == "VALIDATED"
    body = _markdown(remediation_summary, validation_summary, pr_type)
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
    for row in accepted_rows:
        rows.append({
            "vulnerabilityId": row.get("vulnerabilityId"),
            "aliases": row.get("aliases", []),
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
                "dependency": "UNKNOWN",
                "oldVersion": None,
                "newVersion": None,
                "status": "REMEDIATED",
                "statusReason": "Patch set validated successfully. Dependency/version metadata was not available in the accepted patch set.",
            })
    return rows


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


def _markdown(remediation_summary: list[dict[str, Any]], validation_summary: dict[str, Any], pr_type: str) -> str:
    lines = [
        "# OSS Vulnerability Remediation",
        "",
        f"PR Type: {pr_type}",
        "",
        "## Remediation Summary",
        "",
        "| Vulnerability ID | Dependency | Old Version | New Version | Status | Status Reason |",
        "|---|---|---|---|---|---|",
    ]
    if remediation_summary:
        for row in remediation_summary:
            lines.append(
                f"| {row.get('vulnerabilityId')} | {row.get('dependency')} | {row.get('oldVersion') or 'N/A'} | {row.get('newVersion') or 'N/A'} | {row.get('status')} | {row.get('statusReason')} |"
            )
    else:
        lines.append("| N/A | N/A | N/A | N/A | NOT_ELIGIBLE | No validated remediation available. |")
    lines.extend(["", "## Validation Summary", ""])
    for key, value in validation_summary.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"
