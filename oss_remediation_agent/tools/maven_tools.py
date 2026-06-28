"""Deterministic Maven project analysis and minimal POM patch helpers."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class MavenProjectMetadata:
    project_type: str
    is_multi_module: bool
    modules: tuple[str, ...]
    packaging: str | None
    java_versions: tuple[str, ...]
    has_dependency_management: bool
    uses_spring_boot: bool
    pom_files: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "projectType": self.project_type,
            "isMultiModuleProject": self.is_multi_module,
            "modules": list(self.modules),
            "packaging": self.packaging,
            "javaVersions": list(self.java_versions),
            "hasDependencyManagement": self.has_dependency_management,
            "usesSpringBoot": self.uses_spring_boot,
            "pomFiles": list(self.pom_files),
        }


@dataclass(frozen=True)
class PomTarget:
    pom_path: Path
    strategy: str
    group_id: str
    artifact_id: str
    property_name: str | None = None
    is_dependency_management: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def label(self, repo_dir: Path | None = None) -> str:
        path = str(self.pom_path.relative_to(repo_dir)) if repo_dir else str(self.pom_path)
        controlled_by = self.property_name or f"{self.group_id}:{self.artifact_id}"
        return f"{path}:{self.strategy}:{controlled_by}"


def analyze_maven_project(repo_dir: Path) -> MavenProjectMetadata:
    root_pom = repo_dir / "pom.xml"
    pom_files = tuple(str(path.relative_to(repo_dir)) for path in sorted(repo_dir.rglob("pom.xml")))
    modules: tuple[str, ...] = ()
    packaging: str | None = None
    java_versions: set[str] = set()
    has_dependency_management = False
    uses_spring_boot = False

    if root_pom.exists():
        root = _parse_root(root_pom)
        text = root_pom.read_text(encoding="utf-8", errors="replace")
        uses_spring_boot = _contains_spring_boot(text)
        if root is not None:
            modules = tuple(_text(node) for node in root.findall(".//{*}modules/{*}module") if _text(node))
            packaging = _text(root.find("{*}packaging")) or None
            has_dependency_management = root.find(".//{*}dependencyManagement") is not None
            for property_name in ("java.version", "maven.compiler.source", "maven.compiler.target", "maven.compiler.release"):
                node = root.find(f".//{{*}}properties/{{*}}{property_name}")
                if node is not None and _text(node):
                    java_versions.add(_text(node))

    project_type = "UNKNOWN" if not root_pom.exists() else "MAVEN_SPRING_BOOT" if uses_spring_boot else "MAVEN"
    return MavenProjectMetadata(
        project_type=project_type,
        is_multi_module=bool(modules),
        modules=modules,
        packaging=packaging,
        java_versions=tuple(sorted(java_versions)),
        has_dependency_management=has_dependency_management,
        uses_spring_boot=uses_spring_boot,
        pom_files=pom_files,
    )


def find_version_targets(repo_dir: Path, group_id: str, artifact_id: str, affected_pom_file: str | None, is_direct_dependency: bool) -> list[PomTarget]:
    targets: list[PomTarget] = []
    for managed in (False, True):
        for pom_path in iter_candidate_poms(repo_dir, affected_pom_file):
            targets.extend(find_existing_targets(pom_path, group_id, artifact_id, managed))
    return dedupe_targets(targets)


def iter_candidate_poms(repo_dir: Path, affected_pom_file: str | None) -> list[Path]:
    candidates: list[Path] = []
    if affected_pom_file:
        candidates.append((repo_dir / affected_pom_file).resolve())
    candidates.append(repo_dir / "pom.xml")
    candidates.extend(sorted(repo_dir.rglob("pom.xml")))
    result: list[Path] = []
    for path in candidates:
        try:
            path.relative_to(repo_dir)
        except ValueError:
            continue
        if path.exists() and path.name == "pom.xml" and path not in result:
            result.append(path)
    return result


def find_existing_targets(pom_path: Path, group_id: str, artifact_id: str, want_dependency_management: bool) -> list[PomTarget]:
    text = read_text(pom_path)
    targets: list[PomTarget] = []
    management_ranges = dependency_management_ranges(text)
    for dependency_match in re.finditer(r"<dependency\b[^>]*>.*?</dependency>", text, re.DOTALL):
        block = dependency_match.group(0)
        is_managed = any(start <= dependency_match.start() <= end for start, end in management_ranges)
        if is_managed != want_dependency_management:
            continue
        if tag_value(block, "groupId") != group_id or tag_value(block, "artifactId") != artifact_id:
            continue
        version = tag_value(block, "version")
        if not version:
            continue
        property_match = re.fullmatch(r"\$\{([^}]+)\}", version.strip())
        if property_match and has_property(text, property_match.group(1)):
            targets.append(PomTarget(pom_path, "propertyVersion", group_id, artifact_id, property_match.group(1), is_managed, {"source": "pom.xml", "versionExpression": version}))
        elif not property_match:
            targets.append(PomTarget(pom_path, "dependencyVersion", group_id, artifact_id, None, is_managed, {"source": "pom.xml", "versionExpression": version}))
    return targets


def insert_dependency_management_target(repo_dir: Path, group_id: str, artifact_id: str, evidence: dict[str, Any]) -> PomTarget | None:
    root_pom = repo_dir / "pom.xml"
    if not root_pom.exists():
        return None
    return PomTarget(root_pom, "dependencyManagementOverride", group_id, artifact_id, None, True, evidence)


def apply_target(target: PomTarget, version: str) -> dict[str, Any]:
    if target.strategy == "propertyVersion" and target.property_name:
        return replace_property(target.pom_path, target.property_name, version)
    if target.strategy == "dependencyVersion":
        return replace_dependency_version(target.pom_path, target.group_id, target.artifact_id, version, target.is_dependency_management)
    if target.strategy == "dependencyManagementOverride":
        return insert_dependency_management_override(target.pom_path, target.group_id, target.artifact_id, version)
    return {"updated": False, "reason": f"Unknown target strategy: {target.strategy}"}


def replace_property(pom_path: Path, property_name: str, version: str) -> dict[str, Any]:
    text = read_text(pom_path)
    pattern = re.compile(rf"(<{re.escape(property_name)}\b[^>]*>)(.*?)(</{re.escape(property_name)}>)", re.DOTALL)
    if not pattern.search(text):
        return {"updated": False, "reason": f"Property {property_name} was not found."}
    write_text(pom_path, pattern.sub(lambda match: f"{match.group(1)}{version}{match.group(3)}", text, 1))
    return {"updated": True, "reason": None}


def replace_dependency_version(pom_path: Path, group_id: str, artifact_id: str, version: str, want_dependency_management: bool) -> dict[str, Any]:
    text = read_text(pom_path)
    management_ranges = dependency_management_ranges(text)
    for dependency_match in re.finditer(r"<dependency\b[^>]*>.*?</dependency>", text, re.DOTALL):
        block = dependency_match.group(0)
        is_managed = any(start <= dependency_match.start() <= end for start, end in management_ranges)
        if is_managed != want_dependency_management:
            continue
        if tag_value(block, "groupId") != group_id or tag_value(block, "artifactId") != artifact_id:
            continue
        if not re.search(r"<version\b[^>]*>.*?</version>", block, re.DOTALL):
            return {"updated": False, "reason": "Dependency declaration has no direct version tag."}
        new_block = re.sub(r"(<version\b[^>]*>)(.*?)(</version>)", lambda match: f"{match.group(1)}{version}{match.group(3)}", block, 1, flags=re.DOTALL)
        write_text(pom_path, text[: dependency_match.start()] + new_block + text[dependency_match.end() :])
        return {"updated": True, "reason": None}
    return {"updated": False, "reason": "Dependency declaration was not found."}


def insert_dependency_management_override(pom_path: Path, group_id: str, artifact_id: str, version: str) -> dict[str, Any]:
    text = read_text(pom_path)
    newline = "\r\n" if "\r\n" in text else "\n"
    indent_match = re.search(r"\n(\s*)<dependencies\b", text)
    indent = indent_match.group(1) if indent_match else "  "
    dependency_block = f"{indent * 3}<dependency>{newline}{indent * 4}<groupId>{group_id}</groupId>{newline}{indent * 4}<artifactId>{artifact_id}</artifactId>{newline}{indent * 4}<version>{version}</version>{newline}{indent * 3}</dependency>{newline}"
    dependency_management_match = re.search(r"<dependencyManagement\b[^>]*>.*?<dependencies\b[^>]*>", text, re.DOTALL)
    if dependency_management_match:
        insertion_point = text.find("</dependencies>", dependency_management_match.end())
        if insertion_point < 0:
            return {"updated": False, "reason": "Malformed dependencyManagement section."}
        write_text(pom_path, text[:insertion_point] + dependency_block + text[insertion_point:])
        return {"updated": True, "reason": None}
    insertion_point = text.find("</project>")
    if insertion_point < 0:
        return {"updated": False, "reason": "No </project> insertion point was found."}
    dependency_management_block = f"{indent}<dependencyManagement>{newline}{indent * 2}<dependencies>{newline}{dependency_block}{indent * 2}</dependencies>{newline}{indent}</dependencyManagement>{newline}"
    write_text(pom_path, text[:insertion_point] + dependency_management_block + text[insertion_point:])
    return {"updated": True, "reason": None}


def snapshot_poms(repo_dir: Path) -> dict[Path, str]:
    return {path: read_text(path) for path in repo_dir.rglob("pom.xml")}


def restore_poms(snapshot: dict[Path, str]) -> None:
    for path, content in snapshot.items():
        write_text(path, content)


def changed_poms(repo_dir: Path, snapshot: dict[Path, str]) -> list[str]:
    return sorted(str(path.relative_to(repo_dir)) for path, content in snapshot.items() if path.exists() and read_text(path) != content)


def dedupe_targets(targets: Iterable[PomTarget]) -> list[PomTarget]:
    seen: set[tuple[Path, str, str | None, bool]] = set()
    result: list[PomTarget] = []
    for target in targets:
        key = (target.pom_path, target.strategy, target.property_name, target.is_dependency_management)
        if key in seen:
            continue
        seen.add(key)
        result.append(target)
    return result


def tag_value(block: str, tag_name: str) -> str | None:
    match = re.search(rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>", block, re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def dependency_management_ranges(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in re.finditer(r"<dependencyManagement\b[^>]*>.*?</dependencyManagement>", text, re.DOTALL)]


def has_property(text: str, property_name: str) -> bool:
    return bool(re.search(rf"<{re.escape(property_name)}\b[^>]*>.*?</{re.escape(property_name)}>", text, re.DOTALL))


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def _parse_root(pom_path: Path) -> ET.Element | None:
    try:
        return ET.parse(pom_path).getroot()
    except ET.ParseError:
        return None


def _text(node: ET.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


def _contains_spring_boot(text: str) -> bool:
    return "spring-boot" in text or "org.springframework.boot" in text
