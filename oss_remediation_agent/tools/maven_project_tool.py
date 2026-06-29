from __future__ import annotations

import json
from pathlib import Path

from oss_remediation_agent.contracts import ToolResult, common_artifact

TOOL = "MavenProjectTool"


def collect_maven_facts(repository_path: str, output_path: str, artifact_output_dir: str, workflow_id: str = "unknown") -> dict:
    repo = Path(repository_path)
    pom_files = sorted(str(path.relative_to(repo)) for path in repo.rglob("pom.xml"))
    pom_index_path = str(Path(artifact_output_dir) / "pom-index.json")
    Path(pom_index_path).parent.mkdir(parents=True, exist_ok=True)
    Path(pom_index_path).write_text(json.dumps({"pomFiles": pom_files}, indent=2) + "\n", encoding="utf-8")
    artifact = common_artifact(
        artifact_id="project-analyzer-001",
        workflow_id=workflow_id,
        created_by=TOOL,
        status="SUCCESS",
        reportType="PROJECT_ANALYZER",
        projectFacts={"projectType": "MAVEN", "isMultiModule": len(pom_files) > 1, "rootPom": "pom.xml", "pomFiles": pom_files},
        dependencyResolutionEvidence=[],
        pomEvidence=[],
        artifactReferences={"pomIndex": pom_index_path},
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult.success(TOOL, "collect_maven_facts", output_path, pomFilesFound=len(pom_files)).to_dict()
