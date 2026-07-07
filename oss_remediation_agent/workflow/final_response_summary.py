from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DEFAULT_NA = "Not applicable for this workflow outcome."

_INTERNAL_FAILURE_LABELS = {
    "CHECKOUT_FAILED": "Repository Checkout Failed",
    "SCANNING_FAILED": "OSS Vulnerability Assessment Failed",
    "PROJECT_ANALYSIS_FAILED": "Maven Project Analysis Failed",
    "PATCH_DRY_RUN_FAILED": "Patch Dry Run Failed",
    "PATCH_APPLICATION_FAILED": "Patch Application Failed",
    "FAILED_MAX_ATTEMPTS": "Maximum Remediation Attempts Reached",
    "PLANNING_CONSTRAINT_VIOLATION": "Planning Constraint Violation",
}

_INTERNAL_FAILURE_STAGE = {
    "CHECKOUT_FAILED": "Repository Preparation",
    "SCANNING_FAILED": "Assessment",
    "PROJECT_ANALYSIS_FAILED": "Assessment",
    "PATCH_DRY_RUN_FAILED": "Remediation",
    "PATCH_APPLICATION_FAILED": "Remediation",
    "FAILED_MAX_ATTEMPTS": "Remediation",
    "PLANNING_CONSTRAINT_VIOLATION": "Remediation Planning",
}


def build_final_response_summary(
    manifest: dict[str, Any],
    workspace_root: str | Path,
    display_status: str,
    fallback_message: str = "",
) -> dict[str, Any]:
    """Build a consistent, status-driven ADK Web summary model.

    Final success/partial facts come from the deterministic remediation
    verification report. Failure/manual-review narrative remains sourced from the
    Outcome Analysis Agent when available.
    """
    workspace = Path(workspace_root)
    internal_status = str(manifest.get("status") or "UNKNOWN").upper()
    status = str(display_status or internal_status).upper()

    outcome = _latest_outcome_analysis(manifest, workspace)
    latest_attempt = _latest_attempt(manifest)
    baseline = manifest.get("baseline") or {}
    patch_plan = _read_artifact(workspace, latest_attempt.get("patchPlan") or (manifest.get("planning") or {}).get("lastDecision"))
    validation = _read_artifact(workspace, latest_attempt.get("validationResult"))
    baseline_build = _read_artifact(workspace, baseline.get("baselineBuildResult"))
    publication = _read_artifact(workspace, (manifest.get("final") or {}).get("pullRequestPublication"))
    pr_summary = _read_artifact(workspace, (manifest.get("final") or {}).get("prSummary"))
    verification_report = _read_artifact(workspace, (manifest.get("final") or {}).get("remediationVerificationReport"))

    if internal_status in _INTERNAL_FAILURE_LABELS:
        return _internal_failure_summary(manifest, workspace, internal_status, patch_plan, validation, outcome, fallback_message)
    if status == "PULL_REQUEST_CREATED":
        if verification_report:
            return _verification_success_summary(
                manifest=manifest,
                report=verification_report,
                workspace=workspace,
                workflow_outcome_suffix="Draft PR Created",
                delivery_label="Draft PR created",
                pr_status=_pr_status_created((manifest.get("final") or {}).get("pullRequest") or {}),
            )
        return _generic_summary(manifest, workspace, display_status, fallback_message)
    if status == "VALIDATION_SUCCEEDED":
        if verification_report:
            return _verification_success_summary(
                manifest=manifest,
                report=verification_report,
                workspace=workspace,
                workflow_outcome_suffix="Validation Succeeded",
                delivery_label="PR handling pending or policy-controlled",
                pr_status="Draft PR has not been created yet; validation completed successfully and PR handling is pending or policy-controlled.",
            )
        return _generic_summary(manifest, workspace, display_status, fallback_message)
    if status == "VALIDATION_FAILED":
        return _validation_failed_summary(manifest, outcome, validation, workspace, fallback_message)
    if status == "PR_CREATION_FAILED":
        return _pr_creation_failed_summary(manifest, publication, validation, pr_summary, verification_report, workspace, fallback_message)
    if status == "BASELINE_BUILD_FAILED":
        return _baseline_build_failed_summary(manifest, baseline_build, workspace, fallback_message)
    if status == "MANUAL_REVIEW_REQUIRED":
        return _manual_review_required_summary(manifest, outcome, patch_plan, pr_summary, verification_report, workspace, fallback_message)
    return _generic_summary(manifest, workspace, display_status, fallback_message)


def _verification_success_summary(
    manifest: dict[str, Any],
    report: dict[str, Any],
    workspace: Path,
    workflow_outcome_suffix: str,
    delivery_label: str,
    pr_status: str,
) -> dict[str, Any]:
    summary = report.get("summary") or {}
    outcome = str(summary.get("verificationOutcome") or "UNKNOWN")
    partial = outcome != "FULL_REMEDIATION"
    workflow_label = f"Partial Remediation {workflow_outcome_suffix}" if partial else workflow_outcome_suffix
    return _summary_model(
        workflow_outcome=workflow_label,
        outcome_summary=_verification_outcome_summary(summary, delivery_label),
        root_cause=_DEFAULT_NA,
        planning_assessment=_verification_planning_assessment(report),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=False, include_verification=True),
        recommended_next_step=_verification_next_step(partial),
        pr_status=pr_status,
    )


def _validation_failed_summary(
    manifest: dict[str, Any],
    outcome: dict[str, Any],
    validation: dict[str, Any],
    workspace: Path,
    fallback_message: str,
) -> dict[str, Any]:
    what_happened = outcome.get("whatHappened") if isinstance(outcome.get("whatHappened"), dict) else {}
    root_cause = outcome.get("rootCauseAnalysis") if isinstance(outcome.get("rootCauseAnalysis"), dict) else {}
    planning = outcome.get("planningContextAssessment") if isinstance(outcome.get("planningContextAssessment"), dict) else {}
    failed_stage = what_happened.get("failedStage") or (validation.get("summary") or {}).get("failedStage") or "VALIDATION"
    failure_summary = what_happened.get("failureSummary") or (validation.get("summary") or {}).get("failureSummary") or fallback_message or "Validation failed."
    primary_cause = root_cause.get("primaryCause") or failure_summary
    planning_assessment = planning.get("assessment") or "The remediation plan requires review because validation did not complete successfully."
    next_step = _first_text(outcome.get("recommendedFocusForPlanner")) or "Review validation artifacts, update the remediation plan, and rerun validation."
    return _summary_model(
        workflow_outcome="Validation Failed",
        outcome_summary=f"{str(failed_stage).replace('_', ' ').title()}: {failure_summary}",
        root_cause=str(primary_cause),
        planning_assessment=str(planning_assessment),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=True, include_verification=False),
        recommended_next_step=next_step,
        pr_status="Draft PR was not created because validation did not pass and no validated PR-ready patch set was available.",
    )


def _pr_creation_failed_summary(
    manifest: dict[str, Any],
    publication: dict[str, Any],
    validation: dict[str, Any],
    pr_summary: dict[str, Any],
    verification_report: dict[str, Any],
    workspace: Path,
    fallback_message: str,
) -> dict[str, Any]:
    final = manifest.get("final") or {}
    reason = final.get("prCreationFailure") or publication.get("failureCode") or publication.get("error") or publication.get("reason") or fallback_message or "PR creation failed."
    if verification_report:
        summary = _verification_outcome_summary(
            verification_report.get("summary") or {},
            delivery_label="PR creation failed after verification",
        )
        planning_assessment = _verification_planning_assessment(verification_report)
    else:
        validated = (manifest.get("acceptedPatchSet") or {}).get("status") == "VALIDATED" or validation.get("status") == "SUCCESS"
        summary = "Validation succeeded, but Draft PR creation failed." if validated else "Draft PR creation failed before a validated PR-ready state was confirmed."
        planning_assessment = "The remediation planning and validation artifacts should be reviewed separately from the PR publication failure; this status reflects delivery failure, not necessarily remediation logic failure."
    return _summary_model(
        workflow_outcome="PR Creation Failed",
        outcome_summary=summary,
        root_cause=str(reason),
        planning_assessment=planning_assessment,
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=True, include_verification=bool(verification_report)),
        recommended_next_step="Review final PR publication artifacts, policy settings, branch permissions, and GitHub publishing errors, then retry PR creation if the patch set is validated.",
        pr_status=f"Draft PR was not created. Reason: {reason}",
    )


def _baseline_build_failed_summary(manifest: dict[str, Any], baseline_build: dict[str, Any], workspace: Path, fallback_message: str) -> dict[str, Any]:
    summary = (baseline_build.get("summary") or {}).get("failureSummary") or baseline_build.get("failureSummary") or fallback_message or "Baseline build failed before remediation could safely proceed."
    return _summary_model(
        workflow_outcome="Baseline Build Failed",
        outcome_summary="The repository could not produce a clean baseline build, so automated remediation was not attempted.",
        root_cause=str(summary),
        planning_assessment="Not applicable; remediation planning requires a stable baseline and was not the cause of this failure.",
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=False, include_verification=False),
        recommended_next_step="Fix the baseline build failure first, then rerun the OSS remediation workflow from a clean baseline.",
        pr_status="Draft PR was not created because remediation cannot proceed without a successful baseline build.",
    )


def _manual_review_required_summary(
    manifest: dict[str, Any],
    outcome: dict[str, Any],
    patch_plan: dict[str, Any],
    pr_summary: dict[str, Any],
    verification_report: dict[str, Any],
    workspace: Path,
    fallback_message: str,
) -> dict[str, Any]:
    final = manifest.get("final") or {}
    planning = outcome.get("planningContextAssessment") if isinstance(outcome.get("planningContextAssessment"), dict) else {}
    root_cause = outcome.get("rootCauseAnalysis") if isinstance(outcome.get("rootCauseAnalysis"), dict) else {}
    pr_policy = final.get("prCreationPolicy") or {}
    if verification_report:
        report_summary = verification_report.get("summary") or {}
        finding_counts = report_summary.get("findingCounts") or {}
        pending_count = int(finding_counts.get("pending") or 0)
        summary = _verification_outcome_summary(report_summary, delivery_label="Manual review required")
        if pending_count:
            summary += f"\n- Pending rationale: {_pending_reason_summary(verification_report)}"
        planning_assessment = planning.get("assessment") or _verification_planning_assessment(verification_report)
    else:
        manual_count = _manual_review_count(patch_plan)
        summary = "Manual approval is required by PR creation policy after summary generation." if pr_policy.get("mode") == "MANUAL_APPROVAL" else (fallback_message or "Manual review is required before the workflow can create a validated Draft PR.")
        if manual_count:
            summary += f" {manual_count} dependency decision(s) require manual review."
        planning_assessment = planning.get("assessment") or "The planner identified dependency decisions that require manual review."
    pr_status = "Draft PR was not created automatically because policy requires manual approval." if pr_policy.get("mode") == "MANUAL_APPROVAL" else "Draft PR was not created because manual review is required."
    return _summary_model(
        workflow_outcome="Manual Review Required",
        outcome_summary=summary,
        root_cause=str(root_cause.get("primaryCause") or final.get("prCreationFailure") or _pending_reason_summary(verification_report) or summary),
        planning_assessment=str(planning_assessment),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=bool(outcome), include_verification=bool(verification_report)),
        recommended_next_step=_first_text(outcome.get("recommendedFocusForPlanner")) or "Review manual-review decisions, resolve unsupported dependency changes, and rerun the workflow when the project is ready for automated validation.",
        pr_status=pr_status,
    )


def _internal_failure_summary(
    manifest: dict[str, Any],
    workspace: Path,
    internal_status: str,
    patch_plan: dict[str, Any],
    validation: dict[str, Any],
    outcome: dict[str, Any],
    fallback_message: str,
) -> dict[str, Any]:
    label = _INTERNAL_FAILURE_LABELS.get(internal_status, internal_status.replace("_", " ").title())
    stage = _INTERNAL_FAILURE_STAGE.get(internal_status, "Workflow")
    reason = _internal_failure_reason(manifest, internal_status, validation, outcome, fallback_message)
    return _summary_model(
        workflow_outcome=label,
        outcome_summary=f"Workflow stopped during {stage}. {reason}",
        root_cause=reason,
        planning_assessment=_internal_failure_planning_assessment(internal_status),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=bool(outcome), include_verification=False),
        recommended_next_step=_internal_failure_next_step(internal_status),
        pr_status=_internal_failure_pr_status(internal_status),
    )


def _verification_outcome_summary(summary: dict[str, Any], delivery_label: str) -> str:
    finding_counts = summary.get("findingCounts") or {}
    severity = summary.get("severityCounts") or {}
    package_counts = summary.get("packageCounts") or {}
    return "\n".join([
        f"- Verification outcome: {summary.get('verificationOutcome') or 'UNKNOWN'}",
        f"- Affected packages: {package_counts.get('affected', 0)}",
        f"- Resolved packages: {package_counts.get('resolved', 0)}",
        f"- Partially resolved packages: {package_counts.get('partiallyResolved', 0)}",
        f"- Pending packages: {package_counts.get('pending', 0)}",
        f"- Baseline findings: {finding_counts.get('baseline', 0)}",
        f"- Resolved findings: {finding_counts.get('resolved', 0)}",
        f"- Pending findings: {finding_counts.get('pending', 0)}",
        f"- New introduced findings: {finding_counts.get('newIntroduced', 0)}",
        f"- Resolved severity: {_severity_counts_text(severity.get('resolved') or {})}",
        f"- Pending severity: {_severity_counts_text(severity.get('pending') or {})}",
        f"- Delivery: {delivery_label}",
    ])


def _verification_planning_assessment(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    outcome = summary.get("verificationOutcome") or "UNKNOWN"
    counts = summary.get("findingCounts") or {}
    if outcome == "FULL_REMEDIATION":
        return "The final response uses the deterministic remediation verification report. Post-remediation validation confirms all in-scope findings represented in the baseline assessment were resolved."
    return "The final response uses the deterministic remediation verification report. Some findings remain pending or could not be verified; review package-level findings and finalReason fields for the evidence-backed rationale."


def _verification_next_step(partial: bool) -> str:
    if partial:
        return "Review the Draft PR for validated dependency-only changes, then separately address pending findings listed in final/remediation-verification-report.json."
    return "Review the Draft PR and verify the dependency-only changes before merge."


def _pending_reason_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    reasons: list[str] = []
    for package in report.get("packages", []) or []:
        for finding in package.get("findings", []) or []:
            if finding.get("finalStatus") == "RESOLVED":
                continue
            package_name = package.get("packageName") or "UNKNOWN"
            vulnerability_id = finding.get("vulnerabilityId") or "UNKNOWN"
            reason = finding.get("finalReason") or package.get("packageVerificationSummary") or "Manual review required."
            reasons.append(f"{package_name} / {vulnerability_id}: {reason}")
    return "; ".join(reasons[:5]) if reasons else "No pending finding reason was available."


def _severity_counts_text(counts: dict[str, Any]) -> str:
    ordered = ["critical", "high", "medium", "low", "unknown"]
    parts = [f"{key}={int(counts.get(key) or 0)}" for key in ordered if int(counts.get(key) or 0)]
    return ", ".join(parts) if parts else "none"


def _internal_failure_reason(manifest: dict[str, Any], internal_status: str, validation: dict[str, Any], outcome: dict[str, Any], fallback_message: str) -> str:
    what_happened = outcome.get("whatHappened") if isinstance(outcome.get("whatHappened"), dict) else {}
    root_cause = outcome.get("rootCauseAnalysis") if isinstance(outcome.get("rootCauseAnalysis"), dict) else {}
    validation_summary = validation.get("summary") if isinstance(validation.get("summary"), dict) else {}
    reason = root_cause.get("primaryCause") or what_happened.get("failureSummary") or validation_summary.get("failureSummary") or fallback_message
    if reason:
        return str(reason)
    return f"Workflow entered {internal_status}; review generated artifacts for details."


def _internal_failure_planning_assessment(internal_status: str) -> str:
    if internal_status in {"PATCH_DRY_RUN_FAILED", "PATCH_APPLICATION_FAILED", "FAILED_MAX_ATTEMPTS", "PLANNING_CONSTRAINT_VIOLATION"}:
        return "Review planning output and patch evidence. The failure happened before a deterministic successful verification report could be used as the final fact source."
    return _DEFAULT_NA


def _internal_failure_next_step(internal_status: str) -> str:
    if internal_status == "CHECKOUT_FAILED":
        return "Verify repository URL, branch, and access permissions, then rerun the workflow."
    if internal_status == "SCANNING_FAILED":
        return "Review OSV scanner setup and scanner output, then rerun assessment."
    if internal_status == "PROJECT_ANALYSIS_FAILED":
        return "Review Maven project structure and analyzer artifacts before replanning."
    if internal_status == "PATCH_DRY_RUN_FAILED":
        return "Review patch dry-run output and planner exact-text evidence before replanning."
    if internal_status == "PATCH_APPLICATION_FAILED":
        return "Review patch application proof and exact-text patch assumptions before replanning."
    if internal_status == "FAILED_MAX_ATTEMPTS":
        return "Review all attempt artifacts and outcome analysis before deciding manual remediation or broader compatibility work."
    return "Review generated artifacts and rerun the workflow after correcting the blocking issue."


def _internal_failure_pr_status(internal_status: str) -> str:
    return "Draft PR was not created because the workflow did not reach a validated PR-ready state."


def _pr_status_created(pull_request: dict[str, Any]) -> str:
    pr_url = pull_request.get("prUrl")
    draft = pull_request.get("draft")
    if pr_url:
        label = "Draft PR" if draft is not False else "PR"
        return f"{label} created: {pr_url}"
    return "Pull request metadata indicates a PR was created."


def _manual_review_count(patch_plan: dict[str, Any]) -> int:
    return sum(1 for item in patch_plan.get("vulnerabilityDecisions", []) or [] if str(item.get("decision") or "").upper() == "MANUAL_REVIEW")


def _generic_summary(manifest: dict[str, Any], workspace: Path, display_status: str, fallback_message: str) -> dict[str, Any]:
    status = str(display_status or manifest.get("status") or "UNKNOWN")
    return _summary_model(
        workflow_outcome=status.replace("_", " ").title(),
        outcome_summary=fallback_message or "Workflow completed with the recorded status.",
        root_cause=_DEFAULT_NA,
        planning_assessment=_DEFAULT_NA,
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=False, include_verification=True),
        recommended_next_step="Review generated artifacts for next steps.",
        pr_status="PR status was not available.",
    )


def _summary_model(
    workflow_outcome: str,
    outcome_summary: str,
    root_cause: str,
    planning_assessment: str,
    evidence_reviewed: list[dict[str, str]],
    recommended_next_step: str,
    pr_status: str,
) -> dict[str, Any]:
    return {
        "workflowOutcome": workflow_outcome,
        "outcomeSummary": outcome_summary,
        "rootCause": root_cause,
        "planningAssessment": planning_assessment,
        "evidenceReviewed": evidence_reviewed,
        "recommendedNextStep": recommended_next_step,
        "prStatus": pr_status,
    }


def _evidence_reviewed(manifest: dict[str, Any], workspace: Path, include_outcome: bool, include_verification: bool = True) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    baseline = manifest.get("baseline") or {}
    final = manifest.get("final") or {}
    candidates: list[tuple[str, Any]] = [
        ("Baseline Build Result", baseline.get("baselineBuildResult")),
        ("Vulnerability Assessment Report", baseline.get("vulnerabilityAssessmentReport")),
        ("Project Analyzer Report", baseline.get("projectAnalyzerReport")),
        ("Remediation Patch Plan", (manifest.get("planning") or {}).get("lastDecision")),
    ]
    latest_attempt = _latest_attempt(manifest)
    candidates.extend([
        ("Patch Application Proof", latest_attempt.get("patchApplicationProof")),
        ("Validation Result", latest_attempt.get("validationResult")),
    ])
    if include_verification:
        candidates.append(("Remediation Verification Report", final.get("remediationVerificationReport")))
    if include_outcome:
        candidates.append(("Outcome Analysis Summary", latest_attempt.get("outcomeAnalysisSummary")))
    candidates.extend([
        ("PR Summary", final.get("prSummary")),
        ("Pull Request Publication Result", final.get("pullRequestPublication")),
    ])
    seen: set[str] = set()
    for name, ref in candidates:
        if not ref:
            continue
        ref_text = str(ref)
        if ref_text in seen:
            continue
        evidence.append({"name": name, "path": ref_text})
        seen.add(ref_text)
    return evidence


def _latest_outcome_analysis(manifest: dict[str, Any], workspace: Path) -> dict[str, Any]:
    for attempt in reversed(manifest.get("attempts", []) or []):
        artifact = _read_artifact(workspace, attempt.get("outcomeAnalysisSummary"))
        if artifact:
            return artifact
    return {}


def _latest_attempt(manifest: dict[str, Any]) -> dict[str, Any]:
    attempts = manifest.get("attempts", []) or []
    if not attempts:
        return {}
    return sorted(attempts, key=lambda item: _safe_int(item.get("attemptNumber")))[-1]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _read_artifact(workspace: Path, artifact_ref: Any) -> dict[str, Any]:
    if not artifact_ref:
        return {}
    path = Path(str(artifact_ref))
    if not path.is_absolute():
        path = workspace / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return ""
    if isinstance(value, dict):
        for key in ("statement", "summary", "description", "reason", "message"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()
