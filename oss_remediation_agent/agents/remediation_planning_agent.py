from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.tools.workspace_artifact_tool import (
    list_workspace_artifacts,
    read_workspace_artifact,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "remediation_planning_agent.md"

_ALLOWED_DECISION_TYPES = {
    "PATCH_PLAN",
    "MANUAL_REVIEW",
    "REQUEST_ADDITIONAL_EVIDENCE",
}
_MAX_DEPENDENCY_EVIDENCE = 40
_MAX_POM_EVIDENCE = 80
_MAX_ADDITIONAL_INVESTIGATION_SUMMARIES = 5


def load_prompt() -> str:
    """Load the reviewable prompt for the LLM-backed planning agent."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_planning_context(workspace_root: str | Path, attempt_number: int = 1) -> dict[str, Any]:
    """Build metadata-first, reusable-tool-backed context for the Planning Agent LLM.

    The Planning Agent is an AI reasoning component, not a deterministic tool.
    This helper does not select fixed versions or synthesize patches. It exposes
    artifact metadata and compact artifact reads through the same reusable
    WorkspaceArtifactTool used by Outcome Analysis.
    """
    workspace = Path(workspace_root).resolve()
    manifest = _read_json(workspace / "manifest.json")
    baseline = manifest.get("baseline", {})
    attempts = manifest.get("attempts", [])
    current_attempt = _attempt_by_number(attempts, attempt_number)
    previous_attempt = _previous_attempt(attempts, attempt_number)

    vulnerability_assessment_path = _resolve(workspace, baseline.get("vulnerabilityAssessmentReport"))
    project_analyzer_path = _resolve(workspace, baseline.get("projectAnalyzerReport"))
    previous_patch_plan_path = _resolve(workspace, previous_attempt.get("patchPlan") if previous_attempt else None)
    previous_patch_application_proof_path = _resolve(workspace, previous_attempt.get("patchApplicationProof") if previous_attempt else None)
    previous_validation_result_path = _resolve(workspace, previous_attempt.get("validationResult") if previous_attempt else None)
    previous_outcome_analysis_path = _resolve(workspace, previous_attempt.get("outcomeAnalysisSummary") if previous_attempt else None)
    additional_investigation_artifacts = _resolve_artifact_list(
        workspace,
        (current_attempt or {}).get("additionalInvestigationArtifacts") or manifest.get("additionalInvestigationArtifacts", []),
    )

    artifact_listing = list_workspace_artifacts(str(workspace), attempt_number=attempt_number)
    relevant_artifacts = artifact_listing.get("relevantArtifacts", [])
    compact_artifact_reads = [
        read_workspace_artifact(str(workspace), str(item.get("path")), mode="compact", attempt_number=attempt_number)
        for item in relevant_artifacts
        if item.get("path")
    ]

    vulnerability_assessment_read = _read_artifact_if_available(workspace, baseline.get("vulnerabilityAssessmentReport"), attempt_number)
    project_analyzer_read = _read_artifact_if_available(workspace, baseline.get("projectAnalyzerReport"), attempt_number)

    evidence = {
        "workspaceArtifactTool": {
            "availableFunctions": [
                {
                    "name": "list_workspace_artifacts",
                    "purpose": "Return workspace artifact metadata from manifest.json for baseline, current attempt, previous attempts, and final delivery artifacts.",
                },
                {
                    "name": "read_workspace_artifact",
                    "purpose": "Safely read one workspace artifact by path in metadata, compact, full_json, or log_excerpt mode.",
                    "supportedModes": ["metadata", "compact", "full_json", "log_excerpt"],
                },
                {
                    "name": "read_workspace_log_excerpt",
                    "purpose": "Safely read bounded failure-oriented excerpts from logs inside the workspace.",
                },
            ],
            "pathSafety": "Artifact reads are restricted to files under workspaceRoot.",
        },
        "artifactListing": artifact_listing,
        "artifactCatalog": artifact_listing.get("artifactCatalog", {}),
        "relevantArtifacts": relevant_artifacts,
        "compactArtifactReads": compact_artifact_reads,
        "vulnerabilityAssessment": vulnerability_assessment_read.get("content", {}),
        "projectAnalyzer": project_analyzer_read.get("content", {}),
        "previousAttempt": _compact_previous_attempt(
            previous_patch_plan_path=previous_patch_plan_path,
            previous_patch_application_proof_path=previous_patch_application_proof_path,
            previous_validation_result_path=previous_validation_result_path,
            previous_outcome_analysis_path=previous_outcome_analysis_path,
        ),
        "additionalInvestigations": _compact_additional_investigations(additional_investigation_artifacts, workspace, vulnerability_assessment_read.get("content", {})),
        "notes": [
            "artifactReferences provide traceability paths; evidence contains compact artifact contents for reasoning.",
            "workspaceArtifactTool metadata and compactArtifactReads are the preferred reusable evidence layer for planning.",
            "Do not infer vulnerabilities, dependency coordinates, fixed versions, or patch files beyond this evidence.",
            "When replanning, review previous outcome analysis and validation evidence before proposing a new plan.",
        ],
    }

    return {
        "agent": "RemediationPlanningAgent",
        "attemptNumber": attempt_number,
        "prompt": load_prompt(),
        "workspaceRoot": str(workspace),
        "manifestPath": str(workspace / "manifest.json"),
        "artifactReferences": {
            "manifest": str(workspace / "manifest.json"),
            "vulnerabilityAssessmentReport": vulnerability_assessment_path,
            "projectAnalyzerReport": project_analyzer_path,
            "previousPatchPlan": previous_patch_plan_path,
            "previousPatchApplicationProof": previous_patch_application_proof_path,
            "previousValidationResult": previous_validation_result_path,
            "previousOutcomeAnalysisSummary": previous_outcome_analysis_path,
            "additionalInvestigationArtifacts": additional_investigation_artifacts,
        },
        "evidence": evidence,
        "workflowPolicy": manifest.get("policy", {}),
        "plannerConstraint": manifest.get("plannerConstraint"),
        "acceptedPatchSet": manifest.get("acceptedPatchSet", {}),
        "additionalInvestigationRequests": (current_attempt or {}).get("additionalInvestigationRequests", []),
        "outputContract": {
            "allowedDecisionTypes": sorted(_ALLOWED_DECISION_TYPES),
            "requiredBehavior": "Return structured JSON only. Do not run tools, mutate files, update manifest, or create pull requests.",
        },
    }


def persist_planning_agent_output(
    workspace_root: str | Path,
    llm_output: str | dict[str, Any],
    attempt_number: int = 1,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Persist and return a structured Planning Agent LLM decision.

    The LLM must produce one of the Phase 4 planner outputs:
    PATCH_PLAN, MANUAL_REVIEW, or REQUEST_ADDITIONAL_EVIDENCE. This wrapper only
    parses, validates the decision type, stores the JSON artifact, and returns a
    compact routing object for the orchestrator. It does not create a plan by
    applying Python remediation rules.
    """
    workspace = Path(workspace_root)
    decision = _parse_json_object(llm_output)
    decision_type = decision.get("decisionType") or decision.get("type")
    if decision_type not in _ALLOWED_DECISION_TYPES:
        raise ValueError(f"Unsupported planning decisionType: {decision_type!r}")

    artifact_path = Path(output_path) if output_path else _default_output_path(workspace, decision_type, attempt_number)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result: dict[str, Any] = {
        "status": "SUCCESS",
        "decisionType": decision_type,
        "artifactPath": str(artifact_path),
    }
    if decision_type == "PATCH_PLAN":
        result["patchPlanPath"] = str(artifact_path)
    elif decision_type == "REQUEST_ADDITIONAL_EVIDENCE":
        result.update({
            "requestedTool": decision.get("requestedTool"),
            "reason": decision.get("reason"),
            "requiredArtifact": decision.get("requiredArtifact"),
        })
    elif decision_type == "MANUAL_REVIEW":
        result.update({
            "reason": decision.get("reason") or decision.get("statusReason"),
            "manualReviewCategory": decision.get("manualReviewCategory"),
        })
    return result


def create_remediation_planning_decision(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Deprecated compatibility guard."""
    raise RuntimeError(
        "Deterministic planning is disabled. Invoke the LLM Remediation Planning Agent "
        "and persist its structured JSON output with persist_planning_agent_output()."
    )


def _read_artifact_if_available(workspace: Path, artifact_ref: str | None, attempt_number: int) -> dict[str, Any]:
    if not artifact_ref:
        return {"status": "SKIPPED", "content": {}}
    return read_workspace_artifact(str(workspace), artifact_ref, mode="compact", attempt_number=attempt_number)


def _compact_previous_attempt(
    previous_patch_plan_path: str | None,
    previous_patch_application_proof_path: str | None,
    previous_validation_result_path: str | None,
    previous_outcome_analysis_path: str | None,
) -> dict[str, Any] | None:
    if not any([previous_patch_plan_path, previous_patch_application_proof_path, previous_validation_result_path, previous_outcome_analysis_path]):
        return None
    return {
        "patchPlan": _read_json(previous_patch_plan_path) if previous_patch_plan_path else None,
        "patchApplicationProof": _read_json(previous_patch_application_proof_path) if previous_patch_application_proof_path else None,
        "validationResult": _read_json(previous_validation_result_path) if previous_validation_result_path else None,
        "outcomeAnalysisSummary": _read_json(previous_outcome_analysis_path) if previous_outcome_analysis_path else None,
    }


def _compact_additional_investigations(
    artifact_paths: list[str],
    workspace: Path,
    vulnerability_assessment: dict[str, Any],
) -> list[dict[str, Any]]:
    summaries = []
    for artifact_path in artifact_paths[:_MAX_ADDITIONAL_INVESTIGATION_SUMMARIES]:
        payload = _read_json(artifact_path)
        result = payload.get("result", payload)
        summaries.append({
            "artifactPath": artifact_path,
            "requestedTool": payload.get("requestedTool") or result.get("requestedTool"),
            "status": payload.get("status") or result.get("status"),
            "failureCode": result.get("failureCode"),
            "summary": result.get("summary", {}),
            "artifactReferences": result.get("artifactReferences", {}),
        })
    return summaries


def _attempt_by_number(attempts: list[dict[str, Any]], attempt_number: int) -> dict[str, Any] | None:
    for attempt in attempts:
        if int(attempt.get("attemptNumber") or 0) == int(attempt_number):
            return attempt
    return None


def _previous_attempt(attempts: list[dict[str, Any]], attempt_number: int) -> dict[str, Any] | None:
    previous = [attempt for attempt in attempts if int(attempt.get("attemptNumber") or 0) < int(attempt_number)]
    if not previous:
        return None
    return sorted(previous, key=lambda item: int(item.get("attemptNumber") or 0))[-1]


def _resolve(workspace: Path, reference: str | None) -> str | None:
    if not reference:
        return None
    path = Path(reference)
    return str(path if path.is_absolute() else workspace / path)


def _resolve_artifact_list(workspace: Path, values: list[Any]) -> list[str]:
    resolved: list[str] = []
    for value in values:
        artifact_ref = value.get("artifactPath") if isinstance(value, dict) else value
        path = _resolve(workspace, artifact_ref)
        if path:
            resolved.append(path)
    return resolved


def _parse_json_object(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Planning Agent output must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Planning Agent output must be a JSON object.")
    return parsed


def _default_output_path(workspace: Path, decision_type: str, attempt_number: int) -> Path:
    if decision_type == "PATCH_PLAN":
        return workspace / f"attempt-{attempt_number}" / "remediation-patch-plan.json"
    if decision_type == "MANUAL_REVIEW":
        return workspace / f"attempt-{attempt_number}" / "manual-review-decision.json"
    return workspace / f"attempt-{attempt_number}" / "additional-evidence-request.json"


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
