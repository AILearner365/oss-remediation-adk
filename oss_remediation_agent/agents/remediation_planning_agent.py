from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "remediation_planning_agent.md"

_ALLOWED_DECISION_TYPES = {
    "PATCH_PLAN",
    "MANUAL_REVIEW",
    "REQUEST_ADDITIONAL_EVIDENCE",
}


def load_prompt() -> str:
    """Load the reviewable prompt for the LLM-backed planning agent."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_planning_context(workspace_root: str | Path, attempt_number: int = 1) -> dict[str, Any]:
    """Build the artifact-reference context for the Planning Agent LLM.

    The Planning Agent is an AI reasoning component, not a deterministic tool.
    This helper intentionally does not inspect repository files, select fixed
    versions, or synthesize patches. It only gives the runtime a small,
    artifact-driven context to pass to the LLM prompt.
    """
    workspace = Path(workspace_root)
    manifest = _read_json(workspace / "manifest.json")
    baseline = manifest.get("baseline", {})
    attempts = manifest.get("attempts", [])
    current_attempt = _attempt_by_number(attempts, attempt_number)
    previous_attempt = _previous_attempt(attempts, attempt_number)
    additional_investigation_artifacts = _resolve_artifact_list(
        workspace,
        (current_attempt or {}).get("additionalInvestigationArtifacts") or manifest.get("additionalInvestigationArtifacts", []),
    )

    return {
        "agent": "RemediationPlanningAgent",
        "attemptNumber": attempt_number,
        "prompt": load_prompt(),
        "workspaceRoot": str(workspace),
        "manifestPath": str(workspace / "manifest.json"),
        "artifactReferences": {
            "manifest": str(workspace / "manifest.json"),
            "vulnerabilityAssessmentReport": _resolve(workspace, baseline.get("vulnerabilityAssessmentReport")),
            "projectAnalyzerReport": _resolve(workspace, baseline.get("projectAnalyzerReport")),
            "previousPatchPlan": _resolve(workspace, previous_attempt.get("patchPlan") if previous_attempt else None),
            "previousPatchApplicationProof": _resolve(workspace, previous_attempt.get("patchApplicationProof") if previous_attempt else None),
            "previousValidationResult": _resolve(workspace, previous_attempt.get("validationResult") if previous_attempt else None),
            "previousOutcomeAnalysisSummary": _resolve(workspace, previous_attempt.get("outcomeAnalysisSummary") if previous_attempt else None),
            "additionalInvestigationArtifacts": additional_investigation_artifacts,
        },
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
    """Deprecated compatibility guard.

    Planning decisions must be produced by the LLM-backed Remediation Planning
    Agent and then passed through persist_planning_agent_output(). This function
    intentionally refuses deterministic patch synthesis so the implementation
    remains aligned with the frozen Phase 1-6 architecture.
    """
    raise RuntimeError(
        "Deterministic planning is disabled. Invoke the LLM Remediation Planning Agent "
        "and persist its structured JSON output with persist_planning_agent_output()."
    )


def _default_output_path(workspace: Path, decision_type: str, attempt_number: int) -> Path:
    if decision_type == "PATCH_PLAN":
        return workspace / f"attempt-{attempt_number}" / "remediation-patch-plan.json"
    if decision_type == "REQUEST_ADDITIONAL_EVIDENCE":
        return workspace / f"attempt-{attempt_number}" / "additional-investigation-request.json"
    return workspace / f"attempt-{attempt_number}" / "manual-review-decision.json"


def _attempt_by_number(attempts: list[dict[str, Any]], attempt_number: int) -> dict[str, Any] | None:
    for attempt in attempts:
        if int(attempt.get("attemptNumber", 0)) == attempt_number:
            return attempt
    return None


def _previous_attempt(attempts: list[dict[str, Any]], attempt_number: int) -> dict[str, Any] | None:
    previous = [attempt for attempt in attempts if int(attempt.get("attemptNumber", 0)) < attempt_number]
    if not previous:
        return None
    return sorted(previous, key=lambda item: int(item.get("attemptNumber", 0)))[-1]


def _resolve_artifact_list(workspace: Path, references: list[Any]) -> list[str]:
    resolved: list[str] = []
    for item in references:
        if isinstance(item, dict):
            ref = item.get("artifactPath") or item.get("path") or item.get("ref")
        else:
            ref = item
        value = _resolve(workspace, ref)
        if value:
            resolved.append(value)
    return resolved


def _resolve(workspace: Path, reference: str | None) -> str | None:
    if not reference:
        return None
    path = Path(reference)
    return str(path if path.is_absolute() else workspace / path)


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


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
