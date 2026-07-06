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
    """Build a consistent, status-driven ADK Web summary model."""
    workspace = Path(workspace_root)
    internal_status = str(manifest.get("status") or "UNKNOWN").upper()
    status = str(display_status or internal_status).upper()

    outcome = _latest_outcome_analysis(manifest, workspace)
    latest_attempt = _latest_attempt(manifest)
    baseline = manifest.get("baseline") or {}
    patch_plan = _read_artifact(workspace, latest_attempt.get("patchPlan") or (manifest.get("planning") or {}).get("lastDecision"))
    validation = _read_artifact(workspace, latest_attempt.get("validationResult"))
    baseline_build = _read_artifact(workspace, baseline.get("baselineBuildResult"))
    vulnerability_assessment = _read_artifact(workspace, baseline.get("vulnerabilityAssessmentReport"))
    publication = _read_artifact(workspace, (manifest.get("final") or {}).get("pullRequestPublication"))
    pr_summary = _read_artifact(workspace, (manifest.get("final") or {}).get("prSummary"))

    if internal_status in _INTERNAL_FAILURE_LABELS:
        return _internal_failure_summary(manifest, workspace, internal_status, patch_plan, validation, outcome, fallback_message)
    if status == "PULL_REQUEST_CREATED":
        return _pull_request_created_summary(manifest, patch_plan, vulnerability_assessment, validation, pr_summary, workspace)
    if status == "VALIDATION_SUCCEEDED":
        return _validation_succeeded_summary(manifest, validation, patch_plan, vulnerability_assessment, workspace)
    if status == "VALIDATION_FAILED":
        return _validation_failed_summary(manifest, outcome, validation, patch_plan, workspace, fallback_message)
    if status == "PR_CREATION_FAILED":
        return _pr_creation_failed_summary(manifest, publication, validation, pr_summary, workspace, fallback_message)
    if status == "BASELINE_BUILD_FAILED":
        return _baseline_build_failed_summary(manifest, baseline_build, workspace, fallback_message)
    if status == "MANUAL_REVIEW_REQUIRED":
        return _manual_review_required_summary(manifest, outcome, patch_plan, pr_summary, workspace, fallback_message)
    return _generic_summary(manifest, workspace, display_status, fallback_message)


def _pull_request_created_summary(
    manifest: dict[str, Any],
    patch_plan: dict[str, Any],
    vulnerability_assessment: dict[str, Any],
    validation: dict[str, Any],
    pr_summary: dict[str, Any],
    workspace: Path,
) -> dict[str, Any]:
    final = manifest.get("final") or {}
    pull_request = final.get("pullRequest") or {}
    pr_type = str(final.get("prType") or "FULL_REMEDIATION")
    counts = _patch_plan_counts(patch_plan)
    accepted_count = _accepted_count(manifest)
    resolved_count = accepted_count or counts["patchDecisionCount"]
    pending_count = counts["manualReviewCount"]
    partial = pr_type == "PARTIAL_REMEDIATION" or pending_count > 0

    outcome_label = "Partial Remediation Draft PR Created" if partial else "Draft Pull Request Created"
    outcome_summary = _success_outcome_summary(
        resolved_count=resolved_count,
        resolved_severity=_severity_summary(patch_plan, "PATCH", vulnerability_assessment),
        pending_count=pending_count,
        pending_severity=_severity_summary(patch_plan, "MANUAL_REVIEW", vulnerability_assessment),
        delivery_label="Partial Draft PR created for validated fixes" if partial else "Draft PR created",
    )

    return _summary_model(
        workflow_outcome=outcome_label,
        outcome_summary=outcome_summary,
        root_cause=_DEFAULT_NA,
        planning_assessment=_success_planning_assessment(counts, partial),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=False),
        recommended_next_step="Review the Draft PR and verify the validated dependency-only changes before merge. Handle pending manual-review items separately if any remain.",
        pr_status=_pr_status_created(pull_request),
    )


def _validation_succeeded_summary(
    manifest: dict[str, Any],
    validation: dict[str, Any],
    patch_plan: dict[str, Any],
    vulnerability_assessment: dict[str, Any],
    workspace: Path,
) -> dict[str, Any]:
    counts = _patch_plan_counts(patch_plan)
    resolved_count = _accepted_count(manifest) or counts["patchDecisionCount"]
    pending_count = counts["manualReviewCount"]
    return _summary_model(
        workflow_outcome="Validation Succeeded",
        outcome_summary=_success_outcome_summary(
            resolved_count=resolved_count,
            resolved_severity=_severity_summary(patch_plan, "PATCH", vulnerability_assessment),
            pending_count=pending_count,
            pending_severity=_severity_summary(patch_plan, "MANUAL_REVIEW", vulnerability_assessment),
            delivery_label="PR handling pending or policy-controlled",
        ),
        root_cause=_DEFAULT_NA,
        planning_assessment=_success_planning_assessment(counts, pending_count > 0),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=False),
        recommended_next_step="Proceed with PR creation policy handling or review the accepted patch set if manual approval is required.",
        pr_status="Draft PR has not been created yet; validation completed successfully and PR handling is pending or policy-controlled.",
    )


def _validation_failed_summary(
    manifest: dict[str, Any],
    outcome: dict[str, Any],
    validation: dict[str, Any],
    patch_plan: dict[str, Any],
    workspace: Path,
    fallback_message: str,
) -> dict[str, Any]:
    what_happened = outcome.get("whatHappened") if isinstance(outcome.get("whatHappened"), dict) else {}
    root_cause = outcome.get("rootCauseAnalysis") if isinstance(outcome.get("rootCauseAnalysis"), dict) else {}
    planning = outcome.get("planningContextAssessment") if isinstance(outcome.get("planningContextAssessment"), dict) else {}
    failed_stage = what_happened.get("failedStage") or (validation.get("summary") or {}).get("failedStage") or "VALIDATION"
    failure_summary = what_happened.get("failureSummary") or (validation.get("summary") or {}).get("failureSummary") or fallback_message or "Validation failed."
    primary_cause = root_cause.get("primaryCause") or failure_summary
    planning_assessment = planning.get("assessment") or _planning_assessment_from_counts(patch_plan)
    next_step = _first_text(outcome.get("recommendedFocusForPlanner")) or "Review validation artifacts, update the remediation plan, and rerun validation."
    return _summary_model(
        workflow_outcome="Validation Failed",
        outcome_summary=f"{str(failed_stage).replace('_', ' ').title()}: {failure_summary}",
        root_cause=str(primary_cause),
        planning_assessment=str(planning_assessment),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=True),
        recommended_next_step=next_step,
        pr_status="Draft PR was not created because validation did not pass and no validated PR-ready patch set was available.",
    )


def _pr_creation_failed_summary(
    manifest: dict[str, Any],
    publication: dict[str, Any],
    validation: dict[str, Any],
    pr_summary: dict[str, Any],
    workspace: Path,
    fallback_message: str,
) -> dict[str, Any]:
    final = manifest.get("final") or {}
    reason = final.get("prCreationFailure") or publication.get("failureCode") or publication.get("error") or publication.get("reason") or fallback_message or "PR creation failed."
    validated = (manifest.get("acceptedPatchSet") or {}).get("status") == "VALIDATED" or validation.get("status") == "SUCCESS"
    summary = "Validation succeeded, but Draft PR creation failed." if validated else "Draft PR creation failed before a validated PR-ready state was confirmed."
    return _summary_model(
        workflow_outcome="PR Creation Failed",
        outcome_summary=summary,
        root_cause=str(reason),
        planning_assessment="The remediation planning and validation artifacts should be reviewed separately from the PR publication failure; this status reflects delivery failure, not necessarily remediation logic failure.",
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=True),
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
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=False),
        recommended_next_step="Fix the baseline build failure first, then rerun the OSS remediation workflow from a clean baseline.",
        pr_status="Draft PR was not created because remediation cannot proceed without a successful baseline build.",
    )


def _manual_review_required_summary(
    manifest: dict[str, Any],
    outcome: dict[str, Any],
    patch_plan: dict[str, Any],
    pr_summary: dict[str, Any],
    workspace: Path,
    fallback_message: str,
) -> dict[str, Any]:
    final = manifest.get("final") or {}
    counts = _patch_plan_counts(patch_plan)
    planning = outcome.get("planningContextAssessment") if isinstance(outcome.get("planningContextAssessment"), dict) else {}
    root_cause = outcome.get("rootCauseAnalysis") if isinstance(outcome.get("rootCauseAnalysis"), dict) else {}
    pr_policy = final.get("prCreationPolicy") or {}
    if pr_policy.get("mode") == "MANUAL_APPROVAL":
        summary = "Manual approval is required by PR creation policy after summary generation."
        pr_status = "Draft PR was not created automatically because policy requires manual approval."
    else:
        summary = fallback_message or "Manual review is required before the workflow can create a validated Draft PR."
        pr_status = "Draft PR was not created because manual review is required."
    if counts["manualReviewCount"]:
        summary += f" {counts['manualReviewCount']} dependency decision(s) require manual review."
    return _summary_model(
        workflow_outcome="Manual Review Required",
        outcome_summary=summary,
        root_cause=str(root_cause.get("primaryCause") or final.get("prCreationFailure") or summary),
        planning_assessment=str(planning.get("assessment") or _planning_assessment_from_counts(patch_plan)),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=bool(outcome)),
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
        planning_assessment=_internal_failure_planning_assessment(internal_status, patch_plan),
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=bool(outcome)),
        recommended_next_step=_internal_failure_next_step(internal_status),
        pr_status=_internal_failure_pr_status(internal_status),
    )


def _success_outcome_summary(
    resolved_count: int,
    resolved_severity: str,
    pending_count: int,
    pending_severity: str,
    delivery_label: str,
) -> str:
    resolved_severity_text = resolved_severity or "severity not available"
    pending_severity_text = pending_severity or ("none" if pending_count == 0 else "severity not available")
    return "\n".join(
        [
            f"- Resolved: {resolved_count} vulnerability item(s)",
            f"- Resolved severity: {resolved_severity_text}",
            f"- Pending manual review: {pending_count} item(s)",
            f"- Pending severity: {pending_severity_text}",
            f"- Delivery: {delivery_label}",
        ]
    )


def _internal_failure_reason(manifest: dict[str, Any], internal_status: str, validation: dict[str, Any], outcome: dict[str, Any], fallback_message: str) -> str:
    what_happened = outcome.get("whatHappened") if isinstance(outcome.get("whatHappened"), dict) else {}
    root_cause = outcome.get("rootCauseAnalysis") if isinstance(outcome.get("rootCauseAnalysis"), dict) else {}
    validation_summary = validation.get("summary") if isinstance(validation.get("summary"), dict) else {}
    reason = root_cause.get("primaryCause") or what_happened.get("failureSummary") or validation_summary.get("failureSummary") or (manifest.get("final") or {}).get("prCreationFailure") or fallback_message
    if reason:
        return str(reason)
    defaults = {
        "CHECKOUT_FAILED": "Repository checkout failed before baseline assessment could complete.",
        "SCANNING_FAILED": "OSS vulnerability assessment failed before remediation planning could complete.",
        "PROJECT_ANALYSIS_FAILED": "Maven project analysis failed before remediation planning could safely continue.",
        "PATCH_DRY_RUN_FAILED": "The remediation patch plan could not be safely dry-run against the attempt workspace.",
        "PATCH_APPLICATION_FAILED": "The remediation patch plan could not be applied successfully to the attempt workspace.",
        "FAILED_MAX_ATTEMPTS": "The workflow exhausted the configured maximum remediation attempts without reaching a validated PR-ready state.",
        "PLANNING_CONSTRAINT_VIOLATION": "The planning output violated workflow constraints and could not proceed to patch application.",
    }
    return defaults.get(internal_status, "Workflow failed before a final PR-ready state was reached.")


def _internal_failure_next_step(internal_status: str) -> str:
    next_steps = {
        "CHECKOUT_FAILED": "Verify repository URL, branch, credentials, and checkout permissions, then rerun the workflow.",
        "SCANNING_FAILED": "Review scanner configuration and vulnerability assessment logs, then rerun assessment.",
        "PROJECT_ANALYSIS_FAILED": "Review Maven project analysis artifacts, effective POM generation, dependency tree generation, and parser errors before replanning.",
        "PATCH_DRY_RUN_FAILED": "Review the patch plan and dry-run result, correct exact-text patch targets, and rerun the dry run.",
        "PATCH_APPLICATION_FAILED": "Review patch application proof, fix unmatched or unsafe patch entries, and rerun patch application.",
        "FAILED_MAX_ATTEMPTS": "Review outcome-analysis summaries across attempts, resolve recurring blockers manually, and increase attempts only after updating the planning strategy.",
        "PLANNING_CONSTRAINT_VIOLATION": "Review the planner output against allowed files and change types, then regenerate a compliant patch plan.",
    }
    return next_steps.get(internal_status, "Review generated artifacts, correct the failing stage, and rerun the workflow.")


def _internal_failure_planning_assessment(internal_status: str, patch_plan: dict[str, Any]) -> str:
    if internal_status in {"CHECKOUT_FAILED", "SCANNING_FAILED", "PROJECT_ANALYSIS_FAILED"}:
        return "Not applicable; the workflow failed before remediation planning could safely complete."
    if internal_status == "PLANNING_CONSTRAINT_VIOLATION":
        return "The generated plan must be corrected because it violated workflow constraints such as allowed files, change types, or automation scope."
    return _planning_assessment_from_counts(patch_plan)


def _internal_failure_pr_status(internal_status: str) -> str:
    if internal_status in {"PATCH_DRY_RUN_FAILED", "PATCH_APPLICATION_FAILED", "FAILED_MAX_ATTEMPTS", "PLANNING_CONSTRAINT_VIOLATION"}:
        return "Draft PR was not created because the workflow did not produce a validated PR-ready patch set."
    return "Draft PR was not created because the workflow failed before remediation reached a PR-ready stage."


def _generic_summary(manifest: dict[str, Any], workspace: Path, display_status: str, fallback_message: str) -> dict[str, Any]:
    return _summary_model(
        workflow_outcome=str(display_status or manifest.get("status") or "Unknown"),
        outcome_summary=fallback_message or "Workflow completed with the recorded status. Review artifacts for details.",
        root_cause="No status-specific root cause was available.",
        planning_assessment="No status-specific planning assessment was available.",
        evidence_reviewed=_evidence_reviewed(manifest, workspace, include_outcome=True),
        recommended_next_step="Review the generated artifacts and rerun or continue the workflow as appropriate.",
        pr_status="PR status was not available for this workflow outcome.",
    )


def _summary_model(workflow_outcome: str, outcome_summary: str, root_cause: str, planning_assessment: str, evidence_reviewed: list[dict[str, str]], recommended_next_step: str, pr_status: str) -> dict[str, Any]:
    return {
        "workflowOutcome": workflow_outcome or "Unknown",
        "outcomeSummary": outcome_summary or "No summary was available.",
        "rootCause": root_cause or _DEFAULT_NA,
        "planningAssessment": planning_assessment or _DEFAULT_NA,
        "evidenceReviewed": evidence_reviewed,
        "recommendedNextStep": recommended_next_step or "Review generated artifacts for next steps.",
        "prStatus": pr_status or "PR status was not available.",
    }


def _success_planning_assessment(counts: dict[str, int], partial: bool) -> str:
    if partial:
        return f"The planning agent separated automatable fixes from manual-review items: {counts['patchDecisionCount']} patch decision(s) validated and {counts['manualReviewCount']} item(s) pending manual review."
    return f"The planning agent produced {counts['patchDecisionCount']} dependency-only patch decision(s) that passed validation."


def _planning_assessment_from_counts(patch_plan: dict[str, Any]) -> str:
    counts = _patch_plan_counts(patch_plan)
    if not counts["totalDecisionCount"]:
        return "No patch-plan decision details were available."
    return f"The remediation plan included {counts['patchDecisionCount']} patch decision(s) and {counts['manualReviewCount']} manual-review decision(s). Review validation and outcome artifacts to decide whether replanning is required."


def _patch_plan_counts(patch_plan: dict[str, Any]) -> dict[str, int]:
    decisions = patch_plan.get("vulnerabilityDecisions", []) if isinstance(patch_plan, dict) else []
    patch_count = 0
    manual_count = 0
    for decision in decisions or []:
        decision_type = str(decision.get("decision") or "").upper()
        if decision_type == "PATCH":
            patch_count += 1
        if decision_type == "MANUAL_REVIEW" or decision.get("manualReviewCategory"):
            manual_count += 1
    summary = patch_plan.get("summary", {}) if isinstance(patch_plan, dict) else {}
    return {
        "totalDecisionCount": len(decisions or []),
        "patchDecisionCount": patch_count or _safe_int(summary.get("patchDecisionCount")),
        "manualReviewCount": manual_count or _safe_int(summary.get("manualReviewDecisionCount")),
    }


def _severity_summary(patch_plan: dict[str, Any], decision_type: str, vulnerability_assessment: dict[str, Any] | None = None) -> str:
    decisions = patch_plan.get("vulnerabilityDecisions", []) if isinstance(patch_plan, dict) else []
    severity_by_id = _severity_by_vulnerability_id(vulnerability_assessment or {})
    counts: dict[str, int] = {}
    target = decision_type.upper()
    for decision in decisions or []:
        current_type = str(decision.get("decision") or "").upper()
        matches = current_type == target or (target == "MANUAL_REVIEW" and bool(decision.get("manualReviewCategory")))
        if not matches:
            continue
        severity = _decision_severity(decision, severity_by_id)
        if not severity:
            continue
        counts[severity] = counts.get(severity, 0) + 1
    ordered = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    return ", ".join(f"{counts[level]} {level.lower()}" for level in ordered if counts.get(level))


def _decision_severity(decision: dict[str, Any], severity_by_id: dict[str, str]) -> str:
    for key in ("severity", "maxSeverity", "cvssSeverity"):
        severity = _normalize_severity(decision.get(key))
        if severity:
            return severity
    for key in ("vulnerabilityId", "id", "osvId", "ghsaId", "advisoryId"):
        vulnerability_id = str(decision.get(key) or "").strip()
        if vulnerability_id and severity_by_id.get(vulnerability_id):
            return severity_by_id[vulnerability_id]
    return ""


def _severity_by_vulnerability_id(payload: Any) -> dict[str, str]:
    result: dict[str, str] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            severity = _normalize_severity(value.get("severity") or value.get("maxSeverity") or value.get("cvssSeverity"))
            identifiers = _vulnerability_identifiers(value)
            if severity:
                for identifier in identifiers:
                    result.setdefault(identifier, severity)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return result


def _vulnerability_identifiers(value: dict[str, Any]) -> list[str]:
    identifiers: list[str] = []
    for key in ("vulnerabilityId", "id", "osvId", "ghsaId", "advisoryId"):
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            identifiers.append(raw.strip())
    aliases = value.get("aliases") or value.get("cves") or []
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                identifiers.append(alias.strip())
    return identifiers


def _normalize_severity(value: Any) -> str:
    severity = str(value or "").strip().upper()
    if severity in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        return severity
    return ""


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _accepted_count(manifest: dict[str, Any]) -> int:
    accepted = manifest.get("acceptedPatchSet") or {}
    return len(accepted.get("vulnerabilityIds", []) or accepted.get("patchIds", []) or [])


def _pr_status_created(pull_request: dict[str, Any]) -> str:
    url = pull_request.get("prUrl")
    branch = pull_request.get("branchName")
    draft = pull_request.get("draft")
    label = "Draft PR" if draft is not False else "PR"
    pieces = [f"{label} created successfully."]
    if url:
        pieces.append(f"URL: {url}")
    if branch:
        pieces.append(f"Branch: {branch}")
    return " ".join(pieces)


def _evidence_reviewed(manifest: dict[str, Any], workspace: Path, include_outcome: bool) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []

    def add(label: str, ref: Any) -> None:
        if not ref:
            return
        path = str(ref)
        if not any(item.get("path") == path for item in items):
            items.append({"name": label, "path": path})

    baseline = manifest.get("baseline") or {}
    planning = manifest.get("planning") or {}
    final = manifest.get("final") or {}
    add("Baseline Build Result", baseline.get("baselineBuildResult"))
    add("Vulnerability Assessment Report", baseline.get("vulnerabilityAssessmentReport"))
    add("Project Analyzer Report", baseline.get("projectAnalyzerReport"))
    add("Planning Context", planning.get("context"))
    add("Remediation Patch Plan", planning.get("lastDecision"))
    for attempt in manifest.get("attempts", []) or []:
        add("Patch Dry Run Result", attempt.get("patchDryRunResult"))
        add("Patch Application Proof", attempt.get("patchApplicationProof"))
        add("Validation Result", attempt.get("validationResult"))
        if include_outcome:
            add("Outcome Analysis Summary", attempt.get("outcomeAnalysisSummary"))
    add("PR Summary", final.get("prSummary"))
    add("Pull Request Publication", final.get("pullRequestPublication"))
    return items


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
