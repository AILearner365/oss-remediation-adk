from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.contracts import ToolResult, common_artifact

TOOL = "PatchPlanEvidenceValidator"


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dependency_key(dependency: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    return (
        dependency.get("groupId"),
        dependency.get("artifactId"),
        dependency.get("packageName"),
        dependency.get("currentVersion"),
    )


def _assessment_index(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item.get("vulnerabilityId"): item
        for item in assessment.get("vulnerabilities", [])
        if item.get("vulnerabilityId")
    }


def _load_pom_index(project_analyzer: dict[str, Any]) -> set[str]:
    pom_index_path = project_analyzer.get("artifactReferences", {}).get("pomIndex")
    if not pom_index_path:
        return set()
    path = Path(pom_index_path)
    if not path.exists():
        return set()
    try:
        payload = _read_json(path)
    except Exception:
        return set()
    return {str(item) for item in payload.get("pomFiles", [])}


def _is_safe_relative_path(path: str) -> bool:
    candidate = Path(path)
    return bool(path) and not candidate.is_absolute() and ".." not in candidate.parts


def _validate_decision(
    decision: dict[str, Any],
    assessment_by_id: dict[str, dict[str, Any]],
    repository_path: Path,
    pom_files: set[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    vulnerability_id = decision.get("vulnerabilityId")
    assessment_node = assessment_by_id.get(vulnerability_id)
    if not assessment_node:
        findings.append({
            "severity": "ERROR",
            "code": "UNKNOWN_VULNERABILITY_ID",
            "message": f"vulnerabilityId {vulnerability_id!r} is not present in the vulnerability assessment report.",
        })
        return findings

    expected_dependency = assessment_node.get("dependency", {})
    actual_dependency = decision.get("dependency", {})
    if _dependency_key(actual_dependency) != _dependency_key(expected_dependency):
        findings.append({
            "severity": "ERROR",
            "code": "DEPENDENCY_MISMATCH",
            "message": "decision dependency does not match the dependency on the bound vulnerability assessment node.",
            "expected": expected_dependency,
            "actual": actual_dependency,
        })

    if decision.get("decision") == "PATCH":
        fixed_version = decision.get("fixedVersionSelected")
        fixed_versions = assessment_node.get("fixedVersions") or []
        if fixed_version not in fixed_versions:
            findings.append({
                "severity": "ERROR",
                "code": "FIXED_VERSION_NOT_IN_ASSESSMENT",
                "message": "fixedVersionSelected is not present in the bound vulnerability node fixedVersions list.",
                "fixedVersionSelected": fixed_version,
                "allowedFixedVersions": fixed_versions,
            })

        patches = decision.get("patches") or []
        if not patches:
            findings.append({
                "severity": "ERROR",
                "code": "PATCH_DECISION_WITHOUT_PATCHES",
                "message": "PATCH decision does not include any patches.",
            })
        for patch in patches:
            file_name = str(patch.get("file") or "")
            patch_id = patch.get("patchId")
            if not _is_safe_relative_path(file_name):
                findings.append({
                    "severity": "ERROR",
                    "code": "UNSAFE_PATCH_FILE_PATH",
                    "message": f"patch {patch_id!r} file path must be a safe relative path.",
                    "file": file_name,
                })
                continue
            if not file_name.endswith("pom.xml"):
                findings.append({
                    "severity": "ERROR",
                    "code": "NON_POM_PATCH_FILE",
                    "message": f"patch {patch_id!r} targets a non-pom.xml file.",
                    "file": file_name,
                })
            if pom_files and file_name not in pom_files:
                findings.append({
                    "severity": "ERROR",
                    "code": "PATCH_FILE_NOT_IN_POM_INDEX",
                    "message": f"patch {patch_id!r} file is not present in Project Analyzer pomIndex.",
                    "file": file_name,
                    "knownPomFiles": sorted(pom_files),
                })
            if not (repository_path / file_name).exists():
                findings.append({
                    "severity": "ERROR",
                    "code": "PATCH_FILE_NOT_FOUND",
                    "message": f"patch {patch_id!r} file does not exist in the attempt workspace.",
                    "file": file_name,
                })
            old_text = patch.get("oldText")
            if not isinstance(old_text, str) or old_text == "":
                findings.append({
                    "severity": "ERROR",
                    "code": "PATCH_OLD_TEXT_MISSING",
                    "message": f"patch {patch_id!r} does not provide non-empty oldText.",
                })

    return findings


def validate(
    *,
    attempt_number: int,
    repository_path: str,
    patch_plan_path: str,
    vulnerability_assessment_path: str,
    project_analyzer_report_path: str,
    output_path: str,
) -> dict[str, Any]:
    patch_plan = _read_json(patch_plan_path)
    assessment = _read_json(vulnerability_assessment_path)
    project_analyzer = _read_json(project_analyzer_report_path)
    repository = Path(repository_path)

    assessment_by_id = _assessment_index(assessment)
    pom_files = _load_pom_index(project_analyzer)
    findings: list[dict[str, Any]] = []

    for decision in patch_plan.get("vulnerabilityDecisions", []):
        findings.extend(_validate_decision(decision, assessment_by_id, repository, pom_files))

    status = "FAILED" if any(item.get("severity") == "ERROR" for item in findings) else "SUCCESS"
    artifact = common_artifact(
        artifact_id=f"patch-plan-evidence-validation-attempt-{attempt_number}",
        workflow_id=patch_plan.get("workflowId", assessment.get("workflowId", "unknown")),
        created_by=TOOL,
        status=status,
        attemptNumber=attempt_number,
        artifactReferences={
            "patchPlan": patch_plan_path,
            "vulnerabilityAssessmentReport": vulnerability_assessment_path,
            "projectAnalyzerReport": project_analyzer_report_path,
        },
        findingCount=len(findings),
        findings=findings,
        errors=[item.get("message", "validation error") for item in findings if item.get("severity") == "ERROR"],
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return ToolResult(
        tool_name=TOOL,
        tool_version="1.0.0",
        operation="validate_patch_plan_evidence",
        status=status,
        artifact_path=output_path,
        failure_code="PATCH_PLAN_EVIDENCE_VALIDATION_FAILED" if status != "SUCCESS" else None,
        payload={"findingCount": len(findings)},
        errors=[item.get("message", "validation error") for item in findings if item.get("severity") == "ERROR"],
    ).to_dict()
