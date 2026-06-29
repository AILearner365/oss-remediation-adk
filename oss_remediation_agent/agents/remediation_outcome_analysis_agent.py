from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.contracts import common_artifact

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "remediation_outcome_analysis_agent.md"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def create_outcome_analysis_summary(
    attempt_number: int,
    output_path: str,
    workflow_id: str = "unknown",
    patch_plan_path: str | None = None,
    patch_application_proof_path: str | None = None,
    validation_result_path: str | None = None,
    dry_run_result_path: str | None = None,
) -> dict[str, Any]:
    """Create a deterministic Outcome Analysis Summary artifact.

    This is an integration stub for the Remediation Outcome Analysis Agent. It
    summarizes a failed attempt and deliberately does not produce the next
    remediation plan.
    """
    plan = _read_json(patch_plan_path)
    proof = _read_json(patch_application_proof_path)
    validation = _read_json(validation_result_path)
    dry_run = _read_json(dry_run_result_path)

    failure_category = _failure_category(dry_run, proof, validation)
    what_happened = {
        "patchDryRun": dry_run.get("status") if dry_run else None,
        "patchApplication": proof.get("status") if proof else None,
        "changeScopeValidation": (validation.get("changeScopeValidation") or {}).get("status") if validation else None,
        "buildValidation": (validation.get("buildValidation") or {}).get("status") if validation else None,
        "testValidation": (validation.get("testValidation") or {}).get("status") if validation else None,
        "osvValidation": (validation.get("osvValidation") or {}).get("status") if validation else None,
    }
    changed = []
    for result in proof.get("patchResults", []) if proof else []:
        if result.get("status") == "APPLIED":
            changed.append({"file": result.get("file"), "summary": f"Applied patch {result.get('patchId')}."})

    artifact = common_artifact(
        artifact_id=f"outcome-analysis-summary-attempt-{attempt_number}",
        workflow_id=workflow_id,
        created_by="RemediationOutcomeAnalysisAgent",
        status="COMPLETED",
        attemptNumber=attempt_number,
        basedOnArtifacts={
            "patchPlan": patch_plan_path,
            "patchApplicationProof": patch_application_proof_path,
            "validationResult": validation_result_path,
            "dryRunResult": dry_run_result_path,
        },
        failureCategory=failure_category,
        responsibilityArea=_responsibility_area(failure_category),
        whatWeTried=_summarize_plan(plan),
        whatChanged=changed,
        whatHappened=what_happened,
        newFactsLearned=_new_facts(dry_run, proof, validation),
        recommendedFocusForPlanner=_planner_focus(failure_category),
        capabilityGaps=_capability_gaps(failure_category),
        artifactReferences={
            "patchPlan": patch_plan_path,
            "patchApplicationProof": patch_application_proof_path,
            "validationResult": validation_result_path,
            "dryRunResult": dry_run_result_path,
        },
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def _read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _failure_category(dry_run: dict, proof: dict, validation: dict) -> str:
    if dry_run and dry_run.get("status") == "FAILED":
        return _classify_patch_errors(dry_run)
    if proof and proof.get("status") == "FAILED":
        return _classify_patch_errors(proof)
    failed_stage = (validation.get("summary") or {}).get("failedStage") if validation else None
    if failed_stage == "CHANGE_SCOPE_VALIDATION":
        return "CHANGE_SCOPE_FAILURE"
    if failed_stage == "BUILD_VALIDATION":
        return "BUILD_FAILURE"
    if failed_stage == "TEST_VALIDATION":
        return "TEST_FAILURE"
    if failed_stage == "OSV_VALIDATION":
        return "OSV_VALIDATION_FAILURE"
    return "WORKFLOW_FAILURE"


def _classify_patch_errors(source: dict[str, Any]) -> str:
    text = " ".join(str(item) for item in source.get("errors", []))
    for result in source.get("patchResults", []):
        text += " " + " ".join(str(value) for value in result.values())
    lower = text.lower()
    if "file not found" in lower:
        return "PATCH_FILE_NOT_FOUND"
    if "unsupported file" in lower or "unsupported file type" in lower:
        return "PATCH_UNSUPPORTED_FILE"
    if "expected" in lower and "occurrence" in lower:
        return "PATCH_OCCURRENCE_MISMATCH"
    if "oldtext" in lower or "old text" in lower:
        return "PATCH_TEXT_INCORRECT"
    return "PATCH_TOOL_LIMITATION"


def _responsibility_area(category: str) -> str:
    if category in {"PATCH_TEXT_INCORRECT", "PATCH_OCCURRENCE_MISMATCH", "PATCH_FILE_NOT_FOUND", "PATCH_UNSUPPORTED_FILE"}:
        return "PLANNER_DECISION"
    if category == "PATCH_TOOL_LIMITATION":
        return "PATCH_TOOL"
    if category in {"CHANGE_SCOPE_FAILURE", "BUILD_FAILURE", "TEST_FAILURE", "OSV_VALIDATION_FAILURE"}:
        return "VALIDATION"
    return "REPOSITORY_STRUCTURE"


def _summarize_plan(plan: dict) -> str:
    decisions = plan.get("vulnerabilityDecisions", []) if plan else []
    patch_count = sum(1 for decision in decisions if decision.get("decision") == "PATCH")
    manual_count = sum(1 for decision in decisions if decision.get("decision") == "MANUAL_REVIEW")
    return f"Attempted plan with {patch_count} patch decision(s) and {manual_count} manual-review decision(s)."


def _new_facts(dry_run: dict, proof: dict, validation: dict) -> list[str]:
    facts: list[str] = []
    for source in (dry_run, proof, validation):
        for error in source.get("errors", []) if source else []:
            if error:
                facts.append(str(error))
    summary = validation.get("summary") if validation else {}
    if summary and summary.get("failureSummary"):
        facts.append(summary["failureSummary"])
    return facts or ["The previous attempt did not complete successfully."]


def _planner_focus(category: str) -> list[str]:
    if category in {"PATCH_TEXT_INCORRECT", "PATCH_OCCURRENCE_MISMATCH"}:
        return ["Review exact oldText/newText evidence and produce a corrected patch plan."]
    if category == "PATCH_FILE_NOT_FOUND":
        return ["Verify the editable file path in the patch plan against project analyzer POM evidence."]
    if category == "PATCH_UNSUPPORTED_FILE":
        return ["Restrict the next patch plan to supported pom.xml files only."]
    if category == "PATCH_TOOL_LIMITATION":
        return ["Review whether the patch tool needs enhancement or whether manual review is safer."]
    if category == "CHANGE_SCOPE_FAILURE":
        return ["Ensure the next plan only changes intended dependency version text in pom.xml files."]
    if category == "BUILD_FAILURE":
        return ["Review build logs and consider manual review if the fix requires source, JDK, plugin, or framework changes."]
    if category == "TEST_FAILURE":
        return ["Review test logs and consider manual review if behavior changes are outside POM-only remediation scope."]
    if category == "OSV_VALIDATION_FAILURE":
        return ["Review remaining vulnerabilities and dependency resolution evidence before replanning."]
    return ["Review failed attempt artifacts before replanning."]


def _capability_gaps(category: str) -> list[dict[str, str]]:
    if category == "PATCH_TOOL_LIMITATION":
        return [{"tool": "GenericPatchApplyTool", "summary": "Patch tool could not apply an otherwise valid exact patch plan."}]
    return []
