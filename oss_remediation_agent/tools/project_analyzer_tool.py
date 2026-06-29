from __future__ import annotations

from .maven_project_tool import collect_maven_facts


def analyze_project(
    repository_path: str,
    vulnerability_assessment_path: str,
    output_path: str,
    artifact_output_dir: str,
    workflow_id: str = "unknown",
) -> dict:
    return collect_maven_facts(
        repository_path=repository_path,
        output_path=output_path,
        artifact_output_dir=artifact_output_dir,
        workflow_id=workflow_id,
    )
