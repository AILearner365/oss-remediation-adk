from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.tools.workspace_artifact_tool import (
    list_workspace_artifacts,
    read_workspace_artifact,
)

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
    """Build metadata-first context for the Outcome Analysis Agent LLM.

    The Outcome Analysis Agent is an AI reasoning component, not a deterministic
    classifier. This context exposes reusable artifact-tool results: a metadata
    catalog, selected artifact metadata, and compact artifact reads with bounded
    log excerpts where available.
    """

    workspace = Path(workspace_root).resolve()
    manifest = _read_json(workspace / "manifest.json")
    attempt = _attempt(manifest.get("attempts", []), attempt_number)

    patch_plan_ref = _resolve(workspace, patch_plan_path or attempt.get("patchPlan"))
    patch_application_proof_ref = _resolve(workspace, patch_application_proof_path or attempt.get("patchApplicationProof"))
    validation_result_ref = _resolve(workspace, validation_result_path or attempt.get("validationResult"))
    dry_run_result_ref = _resolve(workspace, dry_run_result_path or attempt.get("patchDryRunResult"))
    planning_context_ref = _resolve(workspace, (manifest.get("planning") or {}).get("context"))

    artifact_listing = list_workspace_artifacts(str(workspace), attempt_number=attempt_number)
    relevant_artifacts = artifact_listing.get("relevantArtifacts", [])
    compact_artifact_reads = [
        read_workspace_artifact(str(workspace), str(item.get("path")), attempt_number=attempt_number)
        for item in relevant_artifacts
        if item.get("path")
    ]

    legacy_evidence = _legacy_compact_evidence(
        patch_plan_ref=patch_plan_ref,
        patch_application_proof_ref=patch_application_proof_ref,
        validation_result_ref=validation_result_ref,
        dry_run_result_ref=dry_run_result_ref,
    )

    evidence = {
        "workspaceArtifactTool": {
            "availableFunctions": [
                {
                    "name": "list_workspace_artifacts",
                    "purpose": "Return workspace artifact metadata when artifactListing/artifactCatalog/relevantArtifacts are missing or stale. These metadata fields are already included in the default context.",
                },
                {
                    "name": "read_workspace_artifact",
                    "purpose": "Safely read one workspace artifact by path. Default read is compact. Request mode='full' only when compact evidence is insufficient.",
                    "defaultMode": "compact",
                    "supportedPublicModes": ["compact", "full"],
                    "preferredUsage": "read_workspace_artifact(artifact_path) for compact evidence; read_workspace_artifact(artifact_path, mode='full') only when explicitly needed.",
                },
            ],
            "pathSafety": "Artifact reads are restricted to files under workspaceRoot.",
        },
        "artifactListing": artifact_listing,
        "artifactCatalog": artifact_listing.get("artifactCatalog", {}),
        "relevantArtifacts": relevant_artifacts,
        "compactArtifactReads": compact_artifact_reads,
        **legacy_evidence,
        "notes": [
            "artifactListing, artifactCatalog, and relevantArtifacts are default metadata context; do not request list_workspace_artifacts unless metadata is missing or stale.",
            "Use relevantArtifacts as the first evidence shortlist for the current failure state.",
            "Use compactArtifactReads as the primary readable evidence; each item is produced by read_workspace_artifact default compact mode.",
            "Request read_workspace_artifact with mode='full' only when compact evidence is insufficient for a required outcome conclusion.",
            "When deciding whether the patch plan contributed, compare remediation-patch-plan.json with remediation-planning-context.json when available.",
            "Do not invent occurrence counts, file paths, log details, fields, dependency paths, or patch results.",
        ],
    }

    return {
        "agent": "RemediationOutcomeAnalysisAgent",
        "attemptNumber": attempt_number,
        "prompt": load_prompt(),
        "workspaceRoot": str(workspace),
        "manifestPath": str(workspace / "manifest.json"),
        "artifactReferences": {
            "manifest": str(workspace / "manifest.json"),
            "planningContext": planning_context_ref,
            "patchPlan": patch_plan_ref,
            "patchApplicationProof": patch_application_proof_ref,
            "validationResult": validation_result_ref,
            "dryRunResult": dry_run_result_ref,
        },
        "evidence": evidence,
        "outputContract": {
            "artifactType": "Outcome Analysis Summary",
            "requiredFields": sorted(_REQUIRED_OUTCOME_FIELDS),
            "requiredBehavior": "Return structured JSON only. Do not create patches, run tools, mutate files, update manifest, or create pull requests.",
        },
    }


def _legacy_compact_evidence(
    patch_plan_ref: str | None,
    patch_application_proof_ref: str | None,
    validation_result_ref: str | None,
    dry_run_result_ref: str | None,
) -> dict[str, Any]:
    patch_plan = _read_json(patch_plan_ref) if patch_plan_ref else {}
    dry_run_result = _read_json(dry_run_result_ref) if dry_run_result_ref else {}
    patch_application_proof = _read_json(patch_application_proof_ref) if patch_application_proof_ref else {}
    validation_result = _read_json(validation_result_ref) if validation_result_ref else {}
    return {
        "patchPlan": _compact_patch_plan(patch_plan) if patch_plan else None,
        "patchDryRunResult": _compact_dry_run_result(dry_run_result) if dry_run_result else None,
        "patchApplicationProof": _compact_patch_application_proof(patch_application_proof) if patch_application_proof else None,
        "validationResult": _compact_validation_result(validation_result) if validation_result else None,
    }


def _compact_patch_plan(plan: dict[str, Any]) -> dict[str, Any]:
    decisions = []

    for decision in plan.get("vulnerabilityDecisions", []):
        decisions.append({
            "vulnerabilityId": decision.get("vulnerabilityId"),
            "decision": decision.get("decision"),
            "dependency": decision.get("dependency", {}),
            "fixedVersionSelected": decision.get("fixedVersionSelected"),
            "manualReviewCategory": decision.get("manualReviewCategory"),
            "patches": [
                {
                    "patchId": patch.get("patchId"),
                    "file": patch.get("file"),
                    "changeType": patch.get("changeType"),
                    "oldText": patch.get("oldText"),
                    "newText": patch.get("newText"),
                    "oldVersion": patch.get("oldVersion"),
                    "newVersion": patch.get("newVersion"),
                    "expectedOccurrences": patch.get("expectedOccurrences"),
                }
                for patch in decision.get("patches", [])
            ],
        })

    return {
        "artifactId": plan.get("artifactId"),
        "decisionType": plan.get("decisionType"),
        "attemptNumber": plan.get("attemptNumber"),
        "summary": plan.get("summary", {}),
        "vulnerabilityDecisions": decisions,
    }


def _compact_dry_run_result(dry_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": dry_run.get("status"),
        "patchResults": dry_run.get("patchResults", []),
        "errors": dry_run.get("errors", []),
        "warnings": dry_run.get("warnings", []),
    }


def _compact_patch_application_proof(proof: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": proof.get("status"),
        "patchResults": proof.get("patchResults", []),
        "filesChanged": proof.get("filesChanged", []),
        "errors": proof.get("errors", []),
        "warnings": proof.get("warnings", []),
    }


def _compact_validation_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": validation.get("status"),
        "summary": validation.get("summary", {}),
        "buildResult": validation.get("buildResult", {}),
        "buildValidation": validation.get("buildValidation", {}),
        "testValidation": validation.get("testValidation", {}),
        "osvValidation": validation.get("osvValidation", {}),
        "residualVulnerabilities": validation.get("residualVulnerabilities", []),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
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


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
