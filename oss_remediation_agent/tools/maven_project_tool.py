from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from oss_remediation_agent.contracts import ToolResult, common_artifact
from oss_remediation_agent.utils import run_command

TOOL = "MavenProjectTool"


def collect_maven_facts(repository_path: str, output_path: str, artifact_output_dir: str, workflow_id: str = "unknown") -> dict:
    repo = Path(repository_path)
    output_dir = Path(artifact_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pom_files = sorted(str(path.relative_to(repo)) for path in repo.rglob("pom.xml"))
    pom_index_path = str(output_dir / "pom-index.json")
    dependency_tree_path = str(output_dir / "dependency-tree.txt")
    effective_pom_path = str(output_dir / "effective-pom.xml")

    project_facts = _project_facts(repo, pom_files)
    pom_evidence = _pom_evidence(repo, pom_files)
    dependency_evidence = _dependency_evidence(repo, dependency_tree_path)
    _effective_pom(repo, effective_pom_path)

    Path(pom_index_path).write_text(json.dumps({"pomFiles": pom_files}, indent=2) + "\n", encoding="utf-8")
    artifact = common_artifact(
        artifact_id="project-analyzer-001",
        workflow_id=workflow_id,
        created_by=TOOL,
        status="SUCCESS",
        reportType="PROJECT_ANALYZER",
        projectFacts=project_facts,
        dependencyResolutionEvidence=dependency_evidence,
        pomEvidence=pom_evidence,
        artifactReferences={
            "pomIndex": pom_index_path,
            "dependencyTree": dependency_tree_path,
            "effectivePom": effective_pom_path,
        },
        limitations=["MVP analyzer collects Maven facts and command artifacts; it does not recommend remediation strategy."],
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult.success(
        TOOL,
        "collect_maven_facts",
        output_path,
        pomFilesFound=len(pom_files),
        dependencyTreePath=dependency_tree_path,
        effectivePomPath=effective_pom_path,
    ).to_dict()


def _project_facts(repo: Path, pom_files: list[str]) -> dict:
    root_pom = repo / "pom.xml"
    root = _parse(root_pom)
    modules = []
    java_versions = []
    properties = {}
    dependency_management_present = False
    parent_hierarchy = []
    spring_boot = {"detected": False, "version": None, "source": None}

    if root is not None:
        modules = [{"moduleName": text, "modulePath": text, "pomFile": f"{text}/pom.xml"} for text in _find_texts(root, ".//{*}modules/{*}module")]
        props = root.find("{*}properties")
        if props is not None:
            for child in list(props):
                tag = child.tag.split("}")[-1]
                value = (child.text or "").strip()
                properties[tag] = value
                if tag in {"java.version", "maven.compiler.source", "maven.compiler.target", "maven.compiler.release"} and value:
                    java_versions.append(value)
        dependency_management_present = root.find(".//{*}dependencyManagement") is not None
        parent = root.find("{*}parent")
        if parent is not None:
            group_id = _text(parent.find("{*}groupId"))
            artifact_id = _text(parent.find("{*}artifactId"))
            version = _text(parent.find("{*}version"))
            parent_hierarchy.append({"groupId": group_id, "artifactId": artifact_id, "version": version, "declaredIn": "pom.xml"})
            if group_id == "org.springframework.boot" or "spring-boot" in artifact_id:
                spring_boot = {"detected": True, "version": version, "source": "parent"}

    return {
        "projectType": "MAVEN_SPRING_BOOT" if spring_boot["detected"] else "MAVEN",
        "isMultiModule": bool(modules) or len(pom_files) > 1,
        "rootPom": "pom.xml",
        "pomFiles": pom_files,
        "modules": modules,
        "java": {"detectedVersions": sorted(set(java_versions)), "source": "pom-properties" if java_versions else None},
        "springBoot": spring_boot,
        "parentHierarchy": parent_hierarchy,
        "mavenProperties": properties,
        "dependencyManagementPresent": dependency_management_present,
    }


def _pom_evidence(repo: Path, pom_files: list[str]) -> list[dict]:
    evidence = []
    for rel in pom_files:
        path = repo / rel
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines, start=1):
            if "<version>" in line or ".version>" in line or "<dependencyManagement" in line:
                start = max(1, index - 2)
                end = min(len(lines), index + 2)
                snippet = "\n".join(lines[start - 1:end])
                evidence.append({"file": rel, "lineStart": start, "lineEnd": end, "snippetType": "POM_SNIPPET", "snippet": snippet, "occurrenceCount": 1})
    return evidence[:100]


def _dependency_evidence(repo: Path, dependency_tree_path: str) -> list[dict]:
    result = run_command(["mvn", "dependency:tree", "-DoutputType=text"], cwd=repo, timeout=1800)
    Path(dependency_tree_path).parent.mkdir(parents=True, exist_ok=True)
    Path(dependency_tree_path).write_text((result.get("stdout") or "") + "\n" + (result.get("stderr") or ""), encoding="utf-8")
    return []


def _effective_pom(repo: Path, effective_pom_path: str) -> None:
    result = run_command(["mvn", "help:effective-pom", f"-Doutput={effective_pom_path}"], cwd=repo, timeout=1800)
    path = Path(effective_pom_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((result.get("stdout") or "") + "\n" + (result.get("stderr") or ""), encoding="utf-8")


def _parse(path: Path):
    try:
        return ET.parse(path).getroot()
    except Exception:
        return None


def _text(node) -> str | None:
    return (node.text or "").strip() if node is not None else None


def _find_texts(root, pattern: str) -> list[str]:
    return [(node.text or "").strip() for node in root.findall(pattern) if (node.text or "").strip()]
