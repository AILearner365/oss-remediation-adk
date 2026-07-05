from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_artifact_catalog(workspace_root: str | Path, manifest: dict[str, Any], attempt_number: int) -> dict[str, Any]:
    """Build metadata describing workspace artifacts for outcome analysis.

    This module does not classify failures. It describes what artifacts exist,
    what they are for, what they contain, and their current status so the
    Outcome Analysis Agent can choose evidence deliberately.
    """
    workspace = Path(workspace_root)
    catalog: dict[str, Any] = {
        "manifest": _artifact_meta(
            workspace,
            "manifest.json",
            stage="WORKFLOW",
            artifact_type="MANIFEST",
            purpose="Workflow index containing repository, baseline, attempt, final, and policy references.",
            producer="WorkflowOrchestrator",
            contains=["workflow status", "repository metadata", "baseline references", "attempt references", "final references", "policy snapshot"],
        ),
        "baseline": [],
        "currentAttempt": [],
        "previousAttempts": [],
        "final": [],
    }

    baseline = manifest.get("baseline") or {}
    baseline_specs = {
        "baselineBuildResult": (
            "BASELINE_BUILD_RESULT",
            "Baseline repository build result before remediation.",
            "BaselineBuildTool",
            ["build status", "command", "exit code", "log reference", "failure summary"],
        ),
        "vulnerabilityAssessmentReport": (
            "VULNERABILITY_ASSESSMENT_REPORT",
            "OSV vulnerability assessment for the baseline repository.",
            "VulnerabilityAssessmentAgent",
            ["vulnerability IDs", "aliases", "severity", "dependency coordinates", "current versions", "fixed versions"],
        ),
        "projectAnalyzerReport": (
            "PROJECT_ANALYZER_REPORT",
            "Maven project structure and dependency ownership evidence.",
            "ProjectAnalyzerAgent",
            ["project facts", "modules", "pom evidence", "dependency resolution evidence", "dependency management"],
        ),
    }
    for key, (artifact_type, purpose, producer, contains) in baseline_specs.items():
        ref = baseline.get(key)
        if ref:
            catalog["baseline"].append(_artifact_meta(workspace, ref, "BASELINE", artifact_type, purpose, producer, contains))

    planning_context = (manifest.get("planning") or {}).get("context")
    if planning_context:
        catalog["currentAttempt"].append(_artifact_meta(
            workspace,
            planning_context,
            "REMEDIATION_PLANNING",
            "REMEDIATION_PLANNING_CONTEXT",
            "Exact compact evidence and prompt context shared with the Remediation Planning Agent.",
            "WorkflowOrchestrator",
            ["planner prompt", "vulnerability assessment evidence", "project analyzer evidence", "pom evidence", "dependency resolution evidence", "previous attempt evidence"],
            attempt_number=attempt_number,
        ))

    for attempt in manifest.get("attempts", []) or []:
        number = int(attempt.get("attemptNumber") or 0)
        artifacts = _attempt_artifacts(workspace, attempt, number)
        if number == attempt_number:
            catalog["currentAttempt"].extend(artifacts)
        elif artifacts:
            catalog["previousAttempts"].append({"attemptNumber": number, "artifacts": artifacts})

    final = manifest.get("final") or {}
    final_specs = {
        "prSummary": ("PR_SUMMARY", "Reviewer-facing PR summary artifact.", "PRSummaryTool", ["summary", "remediated vulnerabilities", "validation", "notes"]),
        "prDescription": ("PR_DESCRIPTION", "Markdown PR body generated from validated remediation artifacts.", "PRSummaryTool", ["reviewer summary", "remediation table", "validation summary"]),
        "pullRequestPublication": ("PULL_REQUEST_PUBLICATION", "GitHub Draft PR publication result.", "PRPublisherTool", ["publication status", "branch name", "commit SHA", "PR URL", "failure reason"]),
    }
    for key, (artifact_type, purpose, producer, contains) in final_specs.items():
        ref = final.get(key)
        if ref:
            catalog["final"].append(_artifact_meta(workspace, ref, "DELIVERY", artifact_type, purpose, producer, contains))

    return catalog


def select_relevant_artifacts(catalog: dict[str, Any], manifest: dict[str, Any], attempt_number: int) -> list[dict[str, Any]]:
    """Select a small evidence set for the current failure state."""
    status = str(manifest.get("status") or "UNKNOWN").upper()
    selected: list[dict[str, Any]] = [catalog["manifest"]]

    def add(items: list[dict[str, Any]], *artifact_types: str) -> None:
        for item in items:
            if artifact_types and item.get("artifactType") not in artifact_types:
                continue
            if item not in selected:
                selected.append(item)

    if status == "BASELINE_BUILD_FAILED":
        add(catalog.get("baseline", []), "BASELINE_BUILD_RESULT")
        return selected

    add(catalog.get("baseline", []), "VULNERABILITY_ASSESSMENT_REPORT", "PROJECT_ANALYZER_REPORT")
    add(catalog.get("currentAttempt", []), "REMEDIATION_PLANNING_CONTEXT", "REMEDIATION_PATCH_PLAN")

    if "PATCH_DRY_RUN" in status:
        add(catalog.get("currentAttempt", []), "PATCH_DRY_RUN_RESULT")
    elif "PATCH_APPLICATION" in status:
        add(catalog.get("currentAttempt", []), "PATCH_DRY_RUN_RESULT", "PATCH_APPLICATION_PROOF")
    elif "VALIDATION" in status or "OUTCOME_ANALYSIS" in status or status == "FAILED_MAX_ATTEMPTS":
        add(catalog.get("currentAttempt", []), "PATCH_DRY_RUN_RESULT", "PATCH_APPLICATION_PROOF", "VALIDATION_RESULT")
    else:
        add(catalog.get("currentAttempt", []), "PATCH_DRY_RUN_RESULT", "PATCH_APPLICATION_PROOF", "VALIDATION_RESULT", "OUTCOME_ANALYSIS_SUMMARY")

    for previous in catalog.get("previousAttempts", [])[-2:]:
        add(previous.get("artifacts", []), "REMEDIATION_PATCH_PLAN", "VALIDATION_RESULT", "OUTCOME_ANALYSIS_SUMMARY")

    return selected


def compact_selected_artifacts(workspace_root: str | Path, selected: list[dict[str, Any]]) -> dict[str, Any]:
    """Read selected artifacts and return compact evidence for reasoning."""
    workspace = Path(workspace_root)
    compact: dict[str, Any] = {}
    for item in selected:
        ref = item.get("path")
        if not ref:
            continue
        path = _resolve_path(workspace, ref)
        payload = _read_json(path) if path and path.suffix == ".json" else {}
        compact[str(ref)] = _compact_by_type(str(item.get("artifactType")), payload)
        log_refs = _find_log_references(payload)
        if log_refs:
            compact[str(ref)]["logReferences"] = log_refs
    return compact


def _attempt_artifacts(workspace: Path, attempt: dict[str, Any], attempt_number: int) -> list[dict[str, Any]]:
    specs = {
        "patchPlan": ("REMEDIATION_PATCH_PLAN", "REMEDIATION_PLANNING", "Planner decision and patch instructions for this attempt.", "RemediationPlanningAgent", ["vulnerability decisions", "patches", "manual review decisions", "selected versions", "rationale"]),
        "patchDryRunResult": ("PATCH_DRY_RUN_RESULT", "PATCH_DRY_RUN", "Dry-run result for exact patch instructions.", "PatchApplyTool", ["patch results", "occurrence checks", "errors", "warnings"]),
        "patchApplicationProof": ("PATCH_APPLICATION_PROOF", "PATCH_APPLICATION", "Proof of repository modifications made by the patch tool.", "PatchApplyTool", ["applied patches", "changed files", "patch results", "errors", "warnings"]),
        "validationResult": ("VALIDATION_RESULT", "VALIDATION", "Validation of scope, build, tests, and vulnerability state after patch application.", "ValidationTool", ["validation status", "failed stage", "build result", "test result", "OSV validation", "log references"]),
        "outcomeAnalysisContext": ("OUTCOME_ANALYSIS_CONTEXT", "OUTCOME_ANALYSIS", "Context provided to the Outcome Analysis Agent.", "WorkflowOrchestrator", ["artifact catalog", "selected artifacts", "compact evidence"]),
        "outcomeAnalysisSummary": ("OUTCOME_ANALYSIS_SUMMARY", "OUTCOME_ANALYSIS", "Evidence-backed failure analysis and disposition.", "RemediationOutcomeAnalysisAgent", ["what failed", "cause", "evidence references", "recommended disposition", "planner focus"]),
    }
    artifacts: list[dict[str, Any]] = []
    for key, (artifact_type, stage, purpose, producer, contains) in specs.items():
        ref = attempt.get(key)
        if ref:
            artifacts.append(_artifact_meta(workspace, ref, stage, artifact_type, purpose, producer, contains, attempt_number))
    return artifacts


def _artifact_meta(workspace: Path, ref: str, stage: str, artifact_type: str, purpose: str, producer: str, contains: list[str], attempt_number: int | None = None) -> dict[str, Any]:
    path = _resolve_path(workspace, ref)
    payload = _read_json(path) if path and path.suffix == ".json" else {}
    item: dict[str, Any] = {
        "path": ref,
        "stage": stage,
        "artifactType": artifact_type,
        "purpose": purpose,
        "producer": producer,
        "contains": contains,
        "exists": bool(path and path.exists()),
        "status": payload.get("status") if payload else None,
    }
    if attempt_number is not None:
        item["attemptNumber"] = attempt_number
    logs = _find_log_references(payload)
    if logs:
        item["referencedLogs"] = logs[:10]
    return item


def _compact_by_type(artifact_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if artifact_type == "MANIFEST":
        return {"status": payload.get("status"), "repository": payload.get("repository", {}), "baseline": payload.get("baseline", {}), "planning": payload.get("planning", {}), "attempts": payload.get("attempts", []), "acceptedPatchSet": payload.get("acceptedPatchSet", {}), "final": payload.get("final", {})}
    if artifact_type == "REMEDIATION_PATCH_PLAN":
        return {"status": payload.get("status"), "decisionType": payload.get("decisionType"), "summary": payload.get("summary", {}), "vulnerabilityDecisions": payload.get("vulnerabilityDecisions", [])}
    if artifact_type == "VALIDATION_RESULT":
        return {"status": payload.get("status"), "summary": payload.get("summary", {}), "failedStage": payload.get("failedStage"), "failureSummary": payload.get("failureSummary"), "buildResult": payload.get("buildResult", {}), "testResult": payload.get("testResult", {}), "osvValidation": payload.get("osvValidation", {}), "errors": payload.get("errors", []), "warnings": payload.get("warnings", [])}
    if artifact_type == "REMEDIATION_PLANNING_CONTEXT":
        evidence = payload.get("evidence") or {}
        project = evidence.get("projectAnalyzer") or {}
        return {"agent": payload.get("agent"), "attemptNumber": payload.get("attemptNumber"), "artifactReferences": payload.get("artifactReferences", {}), "pomEvidenceCount": len(project.get("pomEvidence", []) or []) if isinstance(project, dict) else 0, "dependencyResolutionEvidenceCount": len(project.get("dependencyResolutionEvidence", []) or []) if isinstance(project, dict) else 0, "previousAttempt": evidence.get("previousAttempt")}
    if artifact_type == "PROJECT_ANALYZER_REPORT":
        return {"status": payload.get("status"), "projectFacts": payload.get("projectFacts", {}), "pomEvidence": payload.get("pomEvidence", [])[:50], "dependencyResolutionEvidence": payload.get("dependencyResolutionEvidence", [])[:50]}
    if artifact_type == "VULNERABILITY_ASSESSMENT_REPORT":
        return {"status": payload.get("status"), "summary": payload.get("summary", {}), "vulnerabilities": payload.get("vulnerabilities", [])[:50]}
    return {key: payload.get(key) for key in ("status", "artifactId", "workflowId", "summary", "failureCode", "failureSummary", "patchResults", "filesChanged", "errors", "warnings") if key in payload}


def _find_log_references(payload: Any) -> list[str]:
    refs: list[str] = []
    def walk(value: Any, key_hint: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, str(key))
        elif isinstance(value, list):
            for item in value:
                walk(item, key_hint)
        elif isinstance(value, str):
            lowered = value.lower()
            if ("log" in key_hint.lower() or lowered.endswith(".log") or ".log" in lowered) and value not in refs:
                refs.append(value)
    walk(payload)
    return refs


def _resolve_path(workspace: Path, reference: str | None) -> Path | None:
    if not reference:
        return None
    path = Path(reference)
    return path if path.is_absolute() else workspace / path


def _read_json(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
