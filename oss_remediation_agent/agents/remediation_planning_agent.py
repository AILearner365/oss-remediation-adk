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
_MAX_DEPENDENCY_EVIDENCE = 40
_MAX_POM_EVIDENCE = 80
_MAX_ADDITIONAL_INVESTIGATION_SUMMARIES = 5


def load_prompt() -> str:
    """Load the reviewable prompt for the LLM-backed planning agent."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_planning_context(workspace_root: str | Path, attempt_number: int = 1) -> dict[str, Any]:
    """Build the artifact-reference and compact-evidence context for the Planning Agent LLM.

    The Planning Agent is an AI reasoning component, not a deterministic tool.
    This helper intentionally does not select fixed versions or synthesize
    patches. It packages artifact references for traceability and compact
    evidence from persisted deterministic artifacts so the LLM does not have to
    reason from file paths alone.
    """
    workspace = Path(workspace_root)
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

    vulnerability_assessment = _read_json(vulnerability_assessment_path) if vulnerability_assessment_path else {}
    project_analyzer = _read_json(project_analyzer_path) if project_analyzer_path else {}
    evidence = {
        "vulnerabilityAssessment": _compact_vulnerability_assessment(vulnerability_assessment),
        "projectAnalyzer": _compact_project_analyzer(project_analyzer, workspace, vulnerability_assessment),
        "previousAttempt": _compact_previous_attempt(
            previous_patch_plan_path=previous_patch_plan_path,
            previous_patch_application_proof_path=previous_patch_application_proof_path,
            previous_validation_result_path=previous_validation_result_path,
            previous_outcome_analysis_path=previous_outcome_analysis_path,
        ),
        "additionalInvestigations": _compact_additional_investigations(additional_investigation_artifacts, workspace, vulnerability_assessment),
        "notes": [
            "artifactReferences provide traceability paths; evidence contains compact artifact contents for reasoning.",
            "Do not infer vulnerabilities, dependency coordinates, fixed versions, or patch files beyond this evidence.",
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


def _compact_vulnerability_assessment(report: dict[str, Any]) -> dict[str, Any]:
    vulnerabilities = []
    for index, item in enumerate(report.get("vulnerabilities", [])):
        vulnerabilities.append({
            "nodeRef": f"baseline/vulnerability-assessment-report.json#/vulnerabilities/{index}",
            "vulnerabilityId": item.get("vulnerabilityId"),
            "aliases": item.get("aliases", []),
            "severity": item.get("severity"),
            "status": item.get("status"),
            "dependency": item.get("dependency", {}),
            "fixedVersions": item.get("fixedVersions", []),
            "scannerSummary": item.get("scannerEvidence", {}).get("summary"),
        })
    return {
        "status": report.get("status"),
        "summary": report.get("summary", {}),
        "severityScope": report.get("severityScope", []),
        "vulnerabilities": vulnerabilities,
    }


def _compact_project_analyzer(project_analyzer: dict[str, Any], workspace: Path, vulnerability_assessment: dict[str, Any]) -> dict[str, Any]:
    vulnerable_coordinates = _vulnerable_coordinates(vulnerability_assessment)
    prioritized: list[dict[str, Any]] = []
    unrelated: list[dict[str, Any]] = []

    for item in project_analyzer.get("dependencyResolutionEvidence", []):
        compact = {
            "dependency": item.get("dependency"),
            "dependencyType": item.get("dependencyType"),
            "resolvedVersion": item.get("resolvedVersion"),
            "scope": item.get("scope"),
            "depth": item.get("depth"),
            "introducedBy": item.get("introducedBy"),
            "modulesAffected": item.get("modulesAffected", []),
            "dependencyPaths": item.get("dependencyPaths", [])[:3],
        }

        if item.get("dependency") in vulnerable_coordinates:
            prioritized.append(compact)
        else:
            unrelated.append(compact)

    # Vulnerable-related evidence is always retained; only unrelated dependencies
    # are subject to truncation so the planner never loses evidence it needs.
    capacity = max(_MAX_DEPENDENCY_EVIDENCE - len(prioritized), 0)
    dependency_evidence = prioritized + unrelated[:capacity]

    pom_evidence, pom_evidence_truncated = _compact_pom_evidence(project_analyzer, vulnerability_assessment)

    pom_files = _read_pom_index(project_analyzer, workspace) or project_analyzer.get("projectFacts", {}).get("pomFiles", [])

    return {
        "status": project_analyzer.get("status"),
        "artifactReferences": project_analyzer.get("artifactReferences", {}),
        "projectFacts": _compact_project_facts(project_analyzer),
        "pomFiles": pom_files,
        "pomEvidence": pom_evidence,
        "pomEvidenceTruncated": pom_evidence_truncated,
        "dependencyResolutionEvidence": dependency_evidence,
        "unrelatedDependencyEvidenceTruncated": len(unrelated) > capacity,
    }

def _compact_pom_evidence(project_analyzer: dict[str, Any], vulnerability_assessment: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Forward exact editable POM snippets (the source of patch oldText).

    Snippets that reference a vulnerable artifactId are prioritized so they are
    never dropped by the cap. This is the evidence EXACT_TEXT_ONLY patching needs.
    """

    artifact_tokens = _vulnerable_artifact_ids(vulnerability_assessment)
    prioritized: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []

    for item in project_analyzer.get("pomEvidence", []):
        snippet = item.get("snippet", "")
        compact = {
            "file": item.get("file"),
            "lineStart": item.get("lineStart"),
            "lineEnd": item.get("lineEnd"),
            "occurrenceCount": item.get("occurrenceCount"),
            "snippet": snippet,
            "snippetType": item.get("snippetType"),
        }

        if any(token and token in snippet for token in artifact_tokens):
            prioritized.append(compact)
        else:
            remaining.append(compact)

    capacity = max(_MAX_POM_EVIDENCE - len(prioritized), 0)
    return prioritized + remaining[:capacity], len(remaining) > capacity

def _compact_project_facts(project_analyzer: dict[str, Any]) -> dict[str, Any]:
    """Forward the ownership-relevant project facts (properties, parent, modules)."""
    facts = project_analyzer.get("projectFacts", {})
    if not isinstance(facts, dict) or not facts:
        return {}

    return {
        "projectType": facts.get("projectType"),
        "isMultiModule": facts.get("isMultiModule"),
        "rootPom": facts.get("rootPom"),
        "pomFiles": facts.get("pomFiles", []),
        "modules": facts.get("modules", []),
        "parentHierarchy": facts.get("parentHierarchy", []),
        "mavenProperties": facts.get("mavenProperties", {}),
        "dependencyManagementPresent": facts.get("dependencyManagementPresent"),
        "springBoot": facts.get("springBoot", {}),
        "java": facts.get("java", {}),
    }


def _compact_previous_attempt(
    *,
    previous_patch_plan_path: str | None,
    previous_patch_application_proof_path: str | None,
    previous_validation_result_path: str | None,
    previous_outcome_analysis_path: str | None,
) -> dict[str, Any]:
    patch_plan = _read_json(previous_patch_plan_path) if previous_patch_plan_path else {}
    proof = _read_json(previous_patch_application_proof_path) if previous_patch_application_proof_path else {}
    validation = _read_json(previous_validation_result_path) if previous_validation_result_path else {}
    outcome = _read_json(previous_outcome_analysis_path) if previous_outcome_analysis_path else {}
    return {
        "patchPlan": _compact_patch_plan(patch_plan) if patch_plan else None,
        "patchApplicationProof": _compact_patch_application_proof(proof) if proof else None,
        "validationResult": _compact_validation_result(validation) if validation else None,
        "outcomeAnalysisSummary": _compact_outcome_analysis(outcome) if outcome else None,
    }


def _compact_additional_investigations(artifact_paths: list[str], workspace: Path, vulnerability_assessment: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for artifact_path in artifact_paths[:_MAX_ADDITIONAL_INVESTIGATION_SUMMARIES]:
        payload = _read_json(artifact_path)
        result = payload.get("result", {})
        summary: dict[str, Any] = {
            "artifactPath": artifact_path,
            "requestedTool": payload.get("requestedTool"),
            "status": payload.get("status"),
            "toolStatus": result.get("status"),
            "failureCode": result.get("failureCode"),
            "payload": result.get("payload", {}),
        }
        analyzer_path = result.get("artifactPath")
        if analyzer_path:
            analyzer_report = _read_json(analyzer_path)
            if analyzer_report:
                summary["projectAnalyzer"] = _compact_project_analyzer(analyzer_report, workspace, vulnerability_assessment)
        summaries.append(summary)
    return summaries


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


def _compact_patch_application_proof(proof: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": proof.get("status"),
        "patchResults": proof.get("patchResults", []),
        "filesChanged": proof.get("filesChanged", []),
        "errors": proof.get("errors", []),
    }


def _compact_validation_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": validation.get("status"),
        "summary": validation.get("summary", {}),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
    }


def _compact_outcome_analysis(outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": outcome.get("status"),
        "failureCategory": outcome.get("failureCategory"),
        "responsibilityArea": outcome.get("responsibilityArea"),
        "whatWeTried": outcome.get("whatWeTried"),
        "whatChanged": outcome.get("whatChanged"),
        "whatHappened": outcome.get("whatHappened"),
        "newFactsLearned": outcome.get("newFactsLearned", []),
        "recommendedFocusForPlanner": outcome.get("recommendedFocusForPlanner", []),
        "capabilityGaps": outcome.get("capabilityGaps", []),
        "warnings": outcome.get("warnings", []),
    }


def _vulnerable_coordinates(report: dict[str, Any]) -> set[str]:
    coordinates: set[str] = set()
    for item in report.get("vulnerabilities", []):
        dependency = item.get("dependency", {})
        package_name = dependency.get("packageName")
        group_id = dependency.get("groupId")
        artifact_id = dependency.get("artifactId")
        if package_name:
            coordinates.add(package_name)
        if group_id and artifact_id:
            coordinates.add(f"{group_id}:{artifact_id}")
    return coordinates


def _read_pom_index(project_analyzer: dict[str, Any], workspace: Path) -> list[str]:
    pom_index = project_analyzer.get("artifactReferences", {}).get("pomIndex")
    if not pom_index:
        return []
    path = Path(pom_index)
    if not path.is_absolute():
        path = workspace / path
    payload = _read_json(path)
    return payload.get("pomFiles", []) if isinstance(payload.get("pomFiles", []), list) else []


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


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
