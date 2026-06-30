from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "remediation_outcome_analysis_agent.md"

_REQUIRED_OUTCOME_FIELDS = {
    "failureCategory",
    "responsibilityArea",
    "whatWeTried",
    "whatChanged",
    "whatHappened",
    "newFactsLearned",
    "recommendedFocusForPlanner",
}


def load_prompt() -> str:
    """Load the reviewable prompt for the LLM-backed outcome analysis agent."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_outcome_analysis_context(
    workspace_root: str | Path,
    attempt_number: int,
    patch_plan_path: str | None = None,
    patch_application_proof_path: str | None = None,
    validation_result_path: str | None = None,
    dry_run_result_path: str | None = None,
) -> dict[str, Any]:
    """Build artifact-reference context for the Outcome Analysis Agent LLM.

    The Outcome Analysis Agent is an AI reasoning component, not a deterministic
    classifier. This helper does not inspect logs or classify failures. It only
    packages the persisted artifact references that the orchestrator can pass to
    the LLM prompt.
    """
    workspace = Path(workspace_root)
    manifest = _read_json(workspace / "manifest.json")
    attempt = _attempt(manifest.get("attempts", []), attempt_number)

    return {
        "agent": "RemediationOutcomeAnalysisAgent",
        "attemptNumber": attempt_number,
        "prompt": load_prompt(),
        "workspaceRoot": str(workspace),
        "manifestPath": str(workspace / "manifest.json"),
        "artifactReferences": {
            "manifest": str(workspace / "manifest.json"),
            "patchPlan": _resolve(workspace, patch_plan_path or attempt.get("patchPlan")),
            "patchApplicationProof": _resolve(workspace, patch_application_proof_path or attempt.get("patchApplicationProof")),
            "validationResult": _resolve(workspace, validation_result_path or attempt.get("validationResult")),
            "dryRunResult": _resolve(workspace, dry_run_result_path or attempt.get("patchDryRunResult")),
        },
        "outputContract": {
            "artifactType": "Outcome Analysis Summary",
            "requiredFields": sorted(_REQUIRED_OUTCOME_FIELDS),
            "requiredBehavior": "Return structured JSON only. Do not create patches, run tools, mutate files, update manifest, or create pull requests.",
        },
    }


def persist_outcome_analysis_agent_output(
    workspace_root: str | Path,
    llm_output: str | dict[str, Any],
    attempt_number: int,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Persist the LLM-generated Outcome Analysis Summary artifact.

    This wrapper parses and minimally validates the LLM output, writes it to the
    remediation workspace, and returns a compact artifact reference for the
    orchestrator. It intentionally does not classify failures using Python rules.
    """
    workspace = Path(workspace_root)
    outcome = _parse_json_object(llm_output)
    missing = sorted(field for field in _REQUIRED_OUTCOME_FIELDS if field not in outcome)
    if missing:
        raise ValueError(f"Outcome Analysis Agent output is missing required fields: {', '.join(missing)}")

    artifact_path = Path(output_path) if output_path else workspace / f"attempt-{attempt_number}" / "outcome-analysis-summary.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schemaVersion": outcome.get("schemaVersion", "1.0"),
        "artifactId": outcome.get("artifactId", f"outcome-analysis-summary-attempt-{attempt_number}"),
        "workflowId": outcome.get("workflowId", _read_json(workspace / "manifest.json").get("workflowId", "unknown")),
        "createdBy": outcome.get("createdBy", "RemediationOutcomeAnalysisAgent"),
        "status": outcome.get("status", "COMPLETED"),
        "attemptNumber": outcome.get("attemptNumber", attempt_number),
        **outcome,
    }
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "SUCCESS",
        "artifactPath": str(artifact_path),
        "failureCategory": artifact.get("failureCategory"),
        "responsibilityArea": artifact.get("responsibilityArea"),
    }


def create_outcome_analysis_summary(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Deprecated compatibility guard.

    Outcome summaries must be produced by the LLM-backed Remediation Outcome
    Analysis Agent and then persisted with persist_outcome_analysis_agent_output().
    This function intentionally refuses deterministic failure classification so
    the implementation remains aligned with the frozen Phase 1-6 architecture.
    """
    raise RuntimeError(
        "Deterministic outcome analysis is disabled. Invoke the LLM Remediation "
        "Outcome Analysis Agent and persist its structured JSON output with "
        "persist_outcome_analysis_agent_output()."
    )


def _attempt(attempts: list[dict[str, Any]], attempt_number: int) -> dict[str, Any]:
    for attempt in attempts:
        if int(attempt.get("attemptNumber", 0)) == attempt_number:
            return attempt
    return {}


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
        raise ValueError("Outcome Analysis Agent output must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Outcome Analysis Agent output must be a JSON object.")
    return parsed


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
