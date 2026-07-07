from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPORT_REF = "final/remediation-verification-report.json"


def build_remediation_verification_report(
    workspace_root: str | Path,
    attempt_number: int | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the deterministic package-centric remediation verification report.

    The report is intentionally fact-oriented. It derives final package/finding
    status from persisted deterministic artifacts, especially the baseline
    vulnerability assessment and the post-remediation OSV validation result. It
    does not rely on the Outcome Analysis Agent to decide counts or status.
    """
    workspace = Path(workspace_root).resolve()
    manifest_path = workspace / "manifest.json"
    manifest = _read_json(manifest_path)
    attempt = _select_attempt(manifest, attempt_number)
    attempt_no = int(attempt.get("attemptNumber") or attempt_number or 1)

    baseline_ref = (manifest.get("baseline") or {}).get("vulnerabilityAssessmentReport")
    baseline_assessment = _read_json(_resolve(workspace, baseline_ref))
    baseline_findings = [item for item in baseline_assessment.get("vulnerabilities", []) or [] if isinstance(item, dict)]

    patch_plan_ref = attempt.get("patchPlan") or (manifest.get("planning") or {}).get("lastDecision")
    patch_plan = _read_json(_resolve(workspace, patch_plan_ref))
    planner_index = _planner_decision_index(patch_plan)

    proof_ref = attempt.get("patchApplicationProof")
    patch_application_proof = _read_json(_resolve(workspace, proof_ref))
    applied_patch_ids = {
        str(item.get("patchId"))
        for item in patch_application_proof.get("patchResults", []) or []
        if item.get("patchId") and item.get("status") == "APPLIED"
    }

    validation_ref = attempt.get("validationResult")
    validation = _read_json(_resolve(workspace, validation_ref))
    osv_validation = validation.get("osvValidation") if isinstance(validation.get("osvValidation"), dict) else {}
    post_osv_scan_ref = osv_validation.get("scanResultFile")
    remaining_findings = [item for item in osv_validation.get("remainingVulnerabilities", []) or [] if isinstance(item, dict)]

    baseline_keys = {_finding_key(item) for item in baseline_findings}
    remaining_by_key = {_finding_key(item): item for item in remaining_findings}
    new_findings = [item for item in remaining_findings if _finding_key(item) not in baseline_keys]

    package_map: dict[str, dict[str, Any]] = {}
    all_finding_rows: list[dict[str, Any]] = []
    for index, finding in enumerate(baseline_findings):
        row = _build_finding_row(
            workspace=workspace,
            finding=finding,
            finding_index=index,
            attempt_number=attempt_no,
            planner_decision=planner_index.get(_finding_key(finding)) or planner_index.get(_finding_package_key(finding)),
            remaining_by_key=remaining_by_key,
            applied_patch_ids=applied_patch_ids,
            patch_plan_ref=patch_plan_ref,
            proof_ref=proof_ref,
            validation_ref=validation_ref,
            post_osv_scan_ref=post_osv_scan_ref,
        )
        all_finding_rows.append(row)
        package_name = row["packageName"]
        package = package_map.setdefault(package_name, _new_package(row))
        package["findings"].append(_public_finding_row(row))
        _merge_package_version(package, row)

    for package in package_map.values():
        _finalize_package(package)

    packages = sorted(package_map.values(), key=lambda item: item.get("packageName") or "")
    summary = _summary(packages, all_finding_rows, new_findings, validation)

    report = {
        "schemaVersion": "1.0",
        "artifactId": "remediation-verification-report",
        "createdBy": "RemediationVerificationReportBuilder",
        "status": "SUCCESS" if summary["validationStatus"] == "SUCCESS" else "PARTIAL",
        "summary": summary,
        "packages": packages,
        "artifactReferences": {
            "manifest": "manifest.json",
            "baselineAssessment": str(baseline_ref or ""),
            "latestPatchPlan": str(patch_plan_ref or ""),
            "latestPatchApplicationProof": str(proof_ref or ""),
            "latestValidationResult": str(validation_ref or ""),
            "latestPostOsvScan": str(post_osv_scan_ref or ""),
        },
    }

    destination = Path(output_path) if output_path else workspace / REPORT_REF
    if not destination.is_absolute():
        destination = workspace / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = _read_json(manifest_path)
    manifest.setdefault("final", {})["remediationVerificationReport"] = _relative_ref(workspace, destination)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "status": "SUCCESS",
        "artifactPath": _relative_ref(workspace, destination),
        "verificationOutcome": summary.get("verificationOutcome"),
        "packageCounts": summary.get("packageCounts"),
        "findingCounts": summary.get("findingCounts"),
    }


def _build_finding_row(
    workspace: Path,
    finding: dict[str, Any],
    finding_index: int,
    attempt_number: int,
    planner_decision: dict[str, Any] | None,
    remaining_by_key: dict[tuple[str, str, str], dict[str, Any]],
    applied_patch_ids: set[str],
    patch_plan_ref: Any,
    proof_ref: Any,
    validation_ref: Any,
    post_osv_scan_ref: Any,
) -> dict[str, Any]:
    dependency = finding.get("dependency") if isinstance(finding.get("dependency"), dict) else {}
    package_name = dependency.get("packageName") or _coordinate(dependency) or "UNKNOWN"
    baseline_version = str(dependency.get("currentVersion") or "UNKNOWN")
    vulnerability_id = str(finding.get("vulnerabilityId") or "UNKNOWN")
    severity = str(finding.get("severity") or "UNKNOWN").upper()
    key = _finding_key(finding)
    remaining = remaining_by_key.get(key)
    decision_type = str((planner_decision or {}).get("decision") or (planner_decision or {}).get("decisionType") or "NOT_PLANNED").upper()
    selected_version = _selected_version(planner_decision)
    patch_ids = _decision_patch_ids(planner_decision)
    applied_for_decision = [patch_id for patch_id in patch_ids if patch_id in applied_patch_ids]

    if remaining:
        final_status = "PENDING_MANUAL_REVIEW" if decision_type == "MANUAL_REVIEW" else "REMAINING"
    else:
        final_status = "RESOLVED"

    if final_status == "RESOLVED" and applied_for_decision:
        resolution_type = "DIRECT_PACKAGE_UPGRADE"
    elif final_status == "RESOLVED":
        resolution_type = "INDIRECT_TRANSITIVE_RESOLUTION"
    elif final_status == "PENDING_MANUAL_REVIEW":
        resolution_type = "NOT_AUTOMATED"
    else:
        resolution_type = "UNRESOLVED_AFTER_VALIDATION"

    reason = _final_reason(final_status, resolution_type, planner_decision, selected_version)
    planner_rationale = str((planner_decision or {}).get("rationale") or (planner_decision or {}).get("statusReason") or (planner_decision or {}).get("reason") or "No planner rationale was available.")

    return {
        "findingKey": "|".join(key),
        "findingIndex": finding_index,
        "vulnerabilityId": vulnerability_id,
        "aliases": finding.get("aliases") or [],
        "severity": severity,
        "packageName": package_name,
        "ecosystem": dependency.get("ecosystem") or "Maven",
        "baselineVersion": baseline_version,
        "fixedVersions": finding.get("fixedVersions") or [],
        "selectedVersion": selected_version,
        "finalStatus": final_status,
        "resolutionType": resolution_type,
        "finalReason": reason,
        "attemptHistory": [
            {
                "attemptNumber": attempt_number,
                "plannerDecision": decision_type,
                "plannerRationale": planner_rationale,
                "validationStatusAfterAttempt": final_status,
                "evidence": {
                    "plannerDecisionRef": _decision_ref(patch_plan_ref, planner_decision),
                    "patchApplicationProofRef": str(proof_ref or ""),
                    "validationRef": str(validation_ref or ""),
                },
            }
        ],
        "evidence": {
            "assessmentRef": f"baseline/vulnerability-assessment-report.json#/vulnerabilities/{finding_index}",
            "postOsvScanRef": str(post_osv_scan_ref or ""),
        },
    }


def _planner_decision_index(patch_plan: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for decision_index, decision in enumerate(patch_plan.get("vulnerabilityDecisions", []) or []):
        if not isinstance(decision, dict):
            continue
        decision = dict(decision)
        decision["_decisionIndex"] = decision_index
        dependency = decision.get("dependency") if isinstance(decision.get("dependency"), dict) else {}
        package_name = dependency.get("packageName") or _coordinate(dependency) or str(decision.get("packageName") or "UNKNOWN")
        version = str(dependency.get("currentVersion") or dependency.get("oldVersion") or decision.get("oldVersion") or "UNKNOWN")
        vulnerability_id = str(decision.get("vulnerabilityId") or "UNKNOWN")
        index[(vulnerability_id, package_name, version)] = decision
        index[("*", package_name, version)] = decision
    return index


def _new_package(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "packageName": row["packageName"],
        "ecosystem": row.get("ecosystem") or "Maven",
        "baselineVersion": row.get("baselineVersion"),
        "selectedVersion": row.get("selectedVersion"),
        "overallStatus": "UNKNOWN",
        "summary": {},
        "packageVerificationSummary": "",
        "findings": [],
    }


def _merge_package_version(package: dict[str, Any], row: dict[str, Any]) -> None:
    if not package.get("selectedVersion") and row.get("selectedVersion"):
        package["selectedVersion"] = row.get("selectedVersion")


def _finalize_package(package: dict[str, Any]) -> None:
    findings = package.get("findings", []) or []
    resolved = [item for item in findings if item.get("finalStatus") == "RESOLVED"]
    pending = [item for item in findings if item.get("finalStatus") in {"PENDING_MANUAL_REVIEW", "REMAINING"}]
    package["overallStatus"] = _package_status(len(findings), len(resolved), len(pending))
    package["summary"] = {
        "findingCounts": {
            "baseline": len(findings),
            "resolved": len(resolved),
            "pending": len(pending),
            "newIntroduced": 0,
        },
        "severityCounts": {
            "baseline": _severity_counts(findings),
            "resolved": _severity_counts(resolved),
            "pending": _severity_counts(pending),
        },
    }
    package["packageVerificationSummary"] = _package_summary_text(package, resolved, pending)


def _public_finding_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "vulnerabilityId": row["vulnerabilityId"],
        "aliases": row.get("aliases", []),
        "severity": row.get("severity"),
        "baselineVersion": row.get("baselineVersion"),
        "fixedVersions": row.get("fixedVersions", []),
        "selectedVersion": row.get("selectedVersion"),
        "finalStatus": row.get("finalStatus"),
        "resolutionType": row.get("resolutionType"),
        "finalReason": row.get("finalReason"),
        "attemptHistory": row.get("attemptHistory", []),
        "evidence": row.get("evidence", {}),
    }


def _summary(packages: list[dict[str, Any]], findings: list[dict[str, Any]], new_findings: list[dict[str, Any]], validation: dict[str, Any]) -> dict[str, Any]:
    resolved_findings = [item for item in findings if item.get("finalStatus") == "RESOLVED"]
    pending_findings = [item for item in findings if item.get("finalStatus") in {"PENDING_MANUAL_REVIEW", "REMAINING"}]
    status_counts = {
        "affected": len(packages),
        "resolved": sum(1 for item in packages if item.get("overallStatus") == "RESOLVED"),
        "partiallyResolved": sum(1 for item in packages if item.get("overallStatus") == "PARTIALLY_RESOLVED"),
        "pending": sum(1 for item in packages if item.get("overallStatus") in {"PENDING_MANUAL_REVIEW", "REMAINING"}),
    }
    validation_status = str(validation.get("status") or "UNKNOWN").upper()
    verification_outcome = "FULL_REMEDIATION"
    if validation_status != "SUCCESS":
        verification_outcome = "VALIDATION_FAILED"
    elif pending_findings or new_findings:
        verification_outcome = "PARTIAL_REMEDIATION"
    return {
        "verificationOutcome": verification_outcome,
        "validationStatus": validation_status,
        "packageCounts": status_counts,
        "findingCounts": {
            "baseline": len(findings),
            "resolved": len(resolved_findings),
            "pending": len(pending_findings),
            "newIntroduced": len(new_findings),
        },
        "severityCounts": {
            "baseline": _severity_counts(findings),
            "resolved": _severity_counts(resolved_findings),
            "pending": _severity_counts(pending_findings),
            "newIntroduced": _severity_counts(new_findings),
        },
    }


def _package_status(total: int, resolved: int, pending: int) -> str:
    if total and resolved == total:
        return "RESOLVED"
    if resolved and pending:
        return "PARTIALLY_RESOLVED"
    if pending:
        return "PENDING_MANUAL_REVIEW"
    return "UNKNOWN"


def _package_summary_text(package: dict[str, Any], resolved: list[dict[str, Any]], pending: list[dict[str, Any]]) -> str:
    package_name = package.get("packageName") or "package"
    selected = package.get("selectedVersion")
    if pending and resolved:
        return f"{package_name} is partially resolved: {len(resolved)} finding(s) resolved and {len(pending)} finding(s) still require review."
    if pending:
        return f"{package_name} has {len(pending)} pending finding(s) that require manual review."
    if selected:
        return f"Selected version {selected} resolved all in-scope findings for this package."
    return "All in-scope findings for this package were resolved by the validated remediation."


def _final_reason(final_status: str, resolution_type: str, decision: dict[str, Any] | None, selected_version: str | None) -> str:
    reason = str((decision or {}).get("statusReason") or (decision or {}).get("reason") or "").strip()
    if final_status == "RESOLVED" and resolution_type == "DIRECT_PACKAGE_UPGRADE":
        version_text = f" version {selected_version}" if selected_version else " an assessment-supported fixed version"
        return f"Planner selected{version_text} and post-remediation OSV validation confirmed this finding is no longer present."
    if final_status == "RESOLVED":
        return "Post-remediation OSV validation confirmed this finding is no longer present; it was resolved indirectly by another validated dependency update."
    if reason:
        return reason
    if final_status == "PENDING_MANUAL_REVIEW":
        return "Planner did not automate this finding; manual dependency review is required."
    return "Post-remediation OSV validation still reports this finding."


def _selected_version(decision: dict[str, Any] | None) -> str | None:
    if not decision:
        return None
    if decision.get("fixedVersionSelected"):
        return str(decision.get("fixedVersionSelected"))
    if decision.get("newVersion"):
        return str(decision.get("newVersion"))
    for patch in decision.get("patches", []) or []:
        for key in ("newVersion", "targetVersion"):
            if patch.get(key):
                return str(patch.get(key))
    return None


def _decision_patch_ids(decision: dict[str, Any] | None) -> list[str]:
    if not decision:
        return []
    return [str(patch.get("patchId")) for patch in decision.get("patches", []) or [] if patch.get("patchId")]


def _decision_ref(patch_plan_ref: Any, decision: dict[str, Any] | None) -> str:
    if not patch_plan_ref:
        return ""
    if decision and decision.get("_decisionIndex") is not None:
        return f"{patch_plan_ref}#/vulnerabilityDecisions/{decision['_decisionIndex']}"
    return str(patch_plan_ref)


def _select_attempt(manifest: dict[str, Any], attempt_number: int | None) -> dict[str, Any]:
    attempts = manifest.get("attempts", []) or []
    if attempt_number is not None:
        for attempt in attempts:
            if int(attempt.get("attemptNumber") or 0) == int(attempt_number):
                return attempt
    if not attempts:
        return {"attemptNumber": attempt_number or 1}
    return sorted(attempts, key=lambda item: int(item.get("attemptNumber") or 0))[-1]


def _finding_key(item: dict[str, Any]) -> tuple[str, str, str]:
    dependency = item.get("dependency") if isinstance(item.get("dependency"), dict) else {}
    return (
        str(item.get("vulnerabilityId") or "UNKNOWN"),
        str(dependency.get("packageName") or _coordinate(dependency) or "UNKNOWN"),
        str(dependency.get("currentVersion") or "UNKNOWN"),
    )


def _finding_package_key(item: dict[str, Any]) -> tuple[str, str, str]:
    _, package_name, version = _finding_key(item)
    return ("*", package_name, version)


def _severity_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
    for item in items:
        severity = str(item.get("severity") or "UNKNOWN").lower()
        if severity not in counts:
            severity = "unknown"
        counts[severity] += 1
    return counts


def _coordinate(dependency: dict[str, Any]) -> str | None:
    group_id = dependency.get("groupId")
    artifact_id = dependency.get("artifactId")
    if group_id and artifact_id:
        return f"{group_id}:{artifact_id}"
    return dependency.get("packageName") or artifact_id or group_id


def _resolve(workspace: Path, reference: Any) -> Path:
    if not reference:
        return workspace / "__missing__"
    path = Path(str(reference))
    return path if path.is_absolute() else workspace / path


def _relative_ref(workspace: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace))
    except ValueError:
        return str(path)


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
