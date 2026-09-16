from __future__ import annotations

import fnmatch
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..config import ConstraintSpec
from ..models import ConstraintBaseline, ValidationCheck


_SUPPRESSION_NAMES = {
    ".osv-scanner.toml",
    "osv-scanner.toml",
    "osv-scanner.json",
    ".osv-scanner-ignore",
}


class ConstraintEvaluator:
    def capture(self, repository: Path) -> ConstraintBaseline:
        java_versions: set[str] = set()
        spring_versions: set[str] = set()
        for pom in _pom_files(repository):
            try:
                root = ET.parse(pom).getroot()
            except ET.ParseError:
                continue
            properties = _child(root, "properties")
            if properties is not None:
                for child in list(properties):
                    name = _local_name(child.tag)
                    value = (child.text or "").strip()
                    if name in {"java.version", "maven.compiler.release", "maven.compiler.source", "maven.compiler.target"} and value:
                        java_versions.add(f"{name}={value}")
                    if name in {"spring-boot.version", "spring.boot.version"} and value:
                        spring_versions.add(f"{name}={value}")
            parent = _child(root, "parent")
            if parent is not None and _text(parent, "artifactId") == "spring-boot-starter-parent":
                version = _text(parent, "version")
                if version:
                    spring_versions.add(f"parent={version}")
        suppressions: dict[str, str] = {}
        for path in repository.rglob("*"):
            if path.is_file() and path.name.lower() in _SUPPRESSION_NAMES:
                relative = path.relative_to(repository).as_posix()
                suppressions[relative] = _hash(path.read_bytes())
        return ConstraintBaseline(
            java_versions=tuple(sorted(java_versions)),
            spring_boot_versions=tuple(sorted(spring_versions)),
            suppression_files=suppressions,
        )

    def validate(
        self,
        repository: Path,
        baseline: ConstraintBaseline,
        spec: ConstraintSpec,
        changed_files: tuple[str, ...],
        diff_text: str,
    ) -> tuple[ValidationCheck, ...]:
        current = self.capture(repository)
        checks: list[ValidationCheck] = []
        java_required = bool(spec.protected_java_version or baseline.java_versions)
        if java_required:
            if spec.protected_java_version:
                expected_java: str | list[str] = spec.protected_java_version
                passed = bool(current.java_versions) and all(
                    value.partition("=")[2] == spec.protected_java_version
                    for value in current.java_versions
                )
            else:
                expected_java = list(baseline.java_versions)
                passed = current.java_versions == baseline.java_versions
            checks.append(
                ValidationCheck(
                    "protected_java_version",
                    passed,
                    "Java version configuration matches the protected value" if passed else "Java version configuration violates the protected value",
                    {
                        "baseline": list(baseline.java_versions),
                        "expected": expected_java,
                        "current": list(current.java_versions),
                    },
                )
            )
        spring_required = bool(spec.protected_spring_boot_version or baseline.spring_boot_versions)
        if spring_required:
            if spec.protected_spring_boot_version:
                expected_spring: str | list[str] = spec.protected_spring_boot_version
                passed = bool(current.spring_boot_versions) and all(
                    value.partition("=")[2] == spec.protected_spring_boot_version
                    for value in current.spring_boot_versions
                )
            else:
                expected_spring = list(baseline.spring_boot_versions)
                passed = current.spring_boot_versions == baseline.spring_boot_versions
            checks.append(
                ValidationCheck(
                    "protected_spring_boot_version",
                    passed,
                    "Spring Boot version configuration matches the protected value" if passed else "Spring Boot version configuration violates the protected value",
                    {
                        "baseline": list(baseline.spring_boot_versions),
                        "expected": expected_spring,
                        "current": list(current.spring_boot_versions),
                    },
                )
            )
        if spec.allowed_paths:
            disallowed = [path for path in changed_files if not _matches_any(path, spec.allowed_paths)]
            checks.append(
                ValidationCheck(
                    "allowed_paths",
                    not disallowed,
                    "All changes are within allowed paths" if not disallowed else "Changes exist outside allowed paths",
                    {"disallowed": disallowed},
                )
            )
        if spec.protected_paths:
            protected = [path for path in changed_files if _matches_any(path, spec.protected_paths)]
            checks.append(
                ValidationCheck(
                    "protected_paths",
                    not protected,
                    "Protected paths are unchanged" if not protected else "Protected paths changed",
                    {"changedProtectedPaths": protected},
                )
            )
        if spec.prohibit_suppressions:
            changed_suppression_files = {
                name
                for name in set(baseline.suppression_files) | set(current.suppression_files)
                if baseline.suppression_files.get(name) != current.suppression_files.get(name)
            }
            added_suppression_lines = [
                line
                for line in diff_text.splitlines()
                if line.startswith("+")
                and not line.startswith("+++")
                and re.search(r"(?i)(osv|vulnerab).*(ignore|suppress|exclude)|(ignore|suppress).*(osv|vulnerab)", line)
            ]
            passed = not changed_suppression_files and not added_suppression_lines
            checks.append(
                ValidationCheck(
                    "suppression_policy",
                    passed,
                    "No prohibited suppression change detected" if passed else "Potential vulnerability suppression change detected",
                    {
                        "changedSuppressionFiles": sorted(changed_suppression_files),
                        "addedSuppressionLines": added_suppression_lines,
                    },
                )
            )
        return tuple(checks)


def _pom_files(repository: Path):
    for pom in repository.rglob("pom.xml"):
        if "target" not in pom.parts and ".git" not in pom.parts:
            yield pom


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in list(element) if _local_name(child.tag) == name), None)


def _text(element: ET.Element, name: str) -> str | None:
    child = _child(element, name)
    value = (child.text or "").strip() if child is not None else ""
    return value or None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) or normalized.startswith(pattern.rstrip("/") + "/") for pattern in patterns)
