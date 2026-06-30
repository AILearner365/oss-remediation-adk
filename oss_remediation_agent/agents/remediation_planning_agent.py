from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.contracts import common_artifact

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "remediation_planning_agent.md"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def create_remediation_planning_decision(workspace_root: str | Path) -> dict[str, Any]:
    """Create an MVP planner decision from stored workflow artifacts.

    This is a deterministic runtime bridge for Phase S1. It does not replace the
    future LLM-backed Planning Agent prompt. Instead, it keeps the ADK runtime in
    line with the frozen architecture by ensuring the executable workflow always
    routes through a planning step after assessment and project analysis.

    The function consumes only persisted artifacts from the workspace and returns
    one of the structured planner decisions used by ``WorkflowOrchestrator``:

    * ``PATCH_PLAN`` when a safe exact-text Maven version patch can be produced.
    * ``MANUAL_REVIEW`` when the MVP planner cannot safely produce an exact patch.

    It never mutates the manifest and never applies patches.
    """
    workspace = Path(workspace_root)
    manifest = _read_json(workspace / "manifest.json")
    baseline = manifest.get("baseline", {})
    assessment_path = workspace / baseline.get("vulnerabilityAssessmentReport", "baseline/vulnerability-assessment-report.json")
    analyzer_path = workspace / baseline.get("projectAnalyzerReport", "baseline/project-analyzer-report.json")
    repository_path = Path(baseline.get("repositoryPath") or "")

    assessment = _read_json(assessment_path)
    analyzer = _read_json(analyzer_path)
    vulnerabilities = assessment.get("vulnerabilities", [])

    if not vulnerabilities:
        return _manual_review_decision(
            workspace,
            manifest,
            reason="NO_IN_SCOPE_VULNERABILITIES",
            details="No Critical/High Maven vulnerabilities were present in the assessment artifact.",
        )

    decisions: list[dict[str, Any]] = []
    unsupported: list[dict[str, str]] = []
    for index, vulnerability in enumerate(vulnerabilities, start=1):
        fixed_version = _select_fixed_version(vulnerability.get("fixedVersions", []))
        dependency = vulnerability.get("dependency") or {}
        if not fixed_version:
            unsupported.append({
                "vulnerabilityId": vulnerability.get("vulnerabilityId", "UNKNOWN"),
                "reason": "NO_FIXED_VERSION",
            })
            continue
        patch = _build_exact_patch(repository_path, analyzer, dependency, fixed_version, index)
        if not patch:
            unsupported.append({
                "vulnerabilityId": vulnerability.get("vulnerabilityId", "UNKNOWN"),
                "reason": "NO_SAFE_EXACT_TEXT_PATCH_FOUND",
            })
            continue
        decisions.append({
            "vulnerabilityId": vulnerability.get("vulnerabilityId"),
            "aliases": vulnerability.get("aliases", []),
            "decision": "PATCH",
            "dependency": dependency,
            "fixedVersionSelected": fixed_version,
            "patches": [patch],
            "rationale": "MVP planner found an exact Maven version value update within pom.xml scope.",
        })

    if unsupported:
        return _manual_review_decision(
            workspace,
            manifest,
            reason="MVP_PLANNER_UNABLE_TO_CREATE_SAFE_PATCH_PLAN",
            details="One or more in-scope vulnerabilities could not be mapped to an exact-text pom.xml version update.",
            unsupported=unsupported,
        )

    output_path = workspace / "baseline" / "remediation-patch-plan.json"
    artifact = common_artifact(
        artifact_id="remediation-patch-plan-001",
        workflow_id=manifest.get("workflowId", "unknown"),
        created_by="RemediationPlanningAgent",
        status="SUCCESS",
        reportType="EXACT_REMEDIATION_PATCH_PLAN",
        planId="remediation-patch-plan-001",
        decisionType="PATCH_PLAN",
        vulnerabilityDecisions=decisions,
        constraints={
            "allowedFiles": ["**/pom.xml"],
            "patchingMode": "EXACT_TEXT_ONLY",
            "requiresValidation": True,
        },
        artifactReferences={
            "vulnerabilityAssessmentReport": str(assessment_path),
            "projectAnalyzerReport": str(analyzer_path),
        },
        errors=[],
        warnings=[],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "SUCCESS",
        "decisionType": "PATCH_PLAN",
        "patchPlanPath": str(output_path),
        "artifactPath": str(output_path),
        "vulnerabilitiesPlanned": len(decisions),
    }


def _manual_review_decision(
    workspace: Path,
    manifest: dict[str, Any],
    reason: str,
    details: str,
    unsupported: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    output_path = workspace / "baseline" / "planning-manual-review-decision.json"
    artifact = common_artifact(
        artifact_id="planning-manual-review-decision-001",
        workflow_id=manifest.get("workflowId", "unknown"),
        created_by="RemediationPlanningAgent",
        status="MANUAL_REVIEW_REQUIRED",
        reportType="PLANNING_DECISION",
        decisionType="MANUAL_REVIEW",
        reason=reason,
        details=details,
        unsupportedVulnerabilities=unsupported or [],
        errors=[],
        warnings=["MVP planner refused to synthesize an unsafe or unsupported patch plan."],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "SUCCESS",
        "decisionType": "MANUAL_REVIEW",
        "reason": reason,
        "details": details,
        "artifactPath": str(output_path),
    }


def _build_exact_patch(repository_path: Path, analyzer: dict[str, Any], dependency: dict[str, Any], fixed_version: str, index: int) -> dict[str, Any] | None:
    current_version = dependency.get("currentVersion")
    artifact_id = dependency.get("artifactId")
    group_id = dependency.get("groupId")
    if not repository_path or not current_version or not artifact_id:
        return None
    pom_files = (analyzer.get("projectFacts") or {}).get("pomFiles") or ["pom.xml"]
    candidates = sorted(set(pom_files), key=lambda value: (0 if value == "pom.xml" else 1, value))
    for rel_path in candidates:
        pom_path = repository_path / rel_path
        if not pom_path.exists() or pom_path.name != "pom.xml":
            continue
        text = pom_path.read_text(encoding="utf-8", errors="replace")
        property_patch = _property_patch(text, rel_path, artifact_id, current_version, fixed_version, index)
        if property_patch:
            return property_patch
        dependency_patch = _dependency_version_patch(text, rel_path, group_id, artifact_id, current_version, fixed_version, index)
        if dependency_patch:
            return dependency_patch
    return None


def _property_patch(text: str, rel_path: str, artifact_id: str, current_version: str, fixed_version: str, index: int) -> dict[str, Any] | None:
    # Prefer property-managed versions such as <snakeyaml.version>1.33</snakeyaml.version>.
    for property_name in (f"{artifact_id}.version", f"{artifact_id.replace('-', '.')}.version"):
        old_text = f"<{property_name}>{current_version}</{property_name}>"
        if text.count(old_text) == 1:
            return _patch(index, rel_path, old_text, f"<{property_name}>{fixed_version}</{property_name}>", current_version, fixed_version, "MAVEN_PROPERTY_VERSION_VALUE")
    return None


def _dependency_version_patch(text: str, rel_path: str, group_id: str | None, artifact_id: str, current_version: str, fixed_version: str, index: int) -> dict[str, Any] | None:
    old_text = f"<version>{current_version}</version>"
    if old_text not in text:
        return None
    blocks = text.split("<dependency>")
    for block in blocks[1:]:
        dependency_block = "<dependency>" + block.split("</dependency>", 1)[0] + "</dependency>"
        has_artifact = f"<artifactId>{artifact_id}</artifactId>" in dependency_block
        has_group = not group_id or f"<groupId>{group_id}</groupId>" in dependency_block
        if has_artifact and has_group and old_text in dependency_block and text.count(old_text) == 1:
            return _patch(index, rel_path, old_text, f"<version>{fixed_version}</version>", current_version, fixed_version, "DEPENDENCY_VERSION_VALUE")
    return None


def _patch(index: int, rel_path: str, old_text: str, new_text: str, old_version: str, new_version: str, change_type: str) -> dict[str, Any]:
    return {
        "patchId": f"planner-patch-{index}",
        "file": rel_path,
        "oldText": old_text,
        "newText": new_text,
        "expectedOccurrences": 1,
        "oldVersion": old_version,
        "newVersion": new_version,
        "changeType": change_type,
    }


def _select_fixed_version(fixed_versions: list[Any]) -> str | None:
    values = [str(value) for value in fixed_versions if value]
    return values[-1] if values else None


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
