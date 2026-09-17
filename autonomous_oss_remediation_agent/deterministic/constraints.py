from __future__ import annotations

import fnmatch
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..config import ConstraintSpec, SpringBootVersionPolicy
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
        spring_required = bool(
            spec.protected_spring_boot_version
            or baseline.spring_boot_versions
            or current.spring_boot_versions
        )
        if spring_required:
            checks.append(
                _spring_boot_policy_check(
                    baseline.spring_boot_versions,
                    current.spring_boot_versions,
                    spec.spring_boot_version_policy,
                    spec.protected_spring_boot_version,
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


def _spring_boot_policy_check(
    baseline_values: tuple[str, ...],
    final_values: tuple[str, ...],
    policy: SpringBootVersionPolicy,
    legacy_required_version: str | None,
) -> ValidationCheck:
    evaluations = _evaluate_spring_boot_changes(baseline_values, final_values)
    required_version = legacy_required_version or policy.required_version
    applicable_policy = policy.to_dict()
    if legacy_required_version:
        applicable_policy["required_version"] = legacy_required_version
        applicable_policy["source"] = "protected_spring_boot_version"
    else:
        applicable_policy["source"] = "version_policies.spring_boot"

    if required_version:
        concrete_final_versions = [
            version
            for _, version in map(_split_detected_version, final_values)
            if not _is_property_reference(version)
        ]
        passed = bool(concrete_final_versions) and all(
            version == required_version for version in concrete_final_versions
        )
        reason = (
            f"Spring Boot matches required version {required_version}"
            if passed
            else f"Spring Boot must end at required version {required_version}"
        )
    else:
        rejected = [
            evaluation
            for evaluation in evaluations
            if not _spring_boot_change_allowed(evaluation, policy)
        ]
        passed = bool(evaluations) and not rejected
        reason = (
            "Spring Boot version movement is allowed by policy"
            if passed
            else "Spring Boot version movement is rejected by policy: "
            + ", ".join(sorted({str(item["detected_change_type"]) for item in rejected}))
        )

    change_types = sorted({str(item["detected_change_type"]) for item in evaluations}) or ["unverifiable"]
    evidence = {
        "component": "spring_boot",
        "baseline_version": _evidence_versions(baseline_values),
        "final_version": _evidence_versions(final_values),
        "applicable_policy": applicable_policy,
        "detected_change_type": change_types[0] if len(change_types) == 1 else change_types,
        "passed": passed,
        "reason": reason,
        "evaluations": evaluations,
    }
    return ValidationCheck("spring_boot_version_policy", passed, reason, evidence)


def _evaluate_spring_boot_changes(
    baseline_values: tuple[str, ...],
    final_values: tuple[str, ...],
) -> list[dict[str, str | bool | None]]:
    baseline_by_source = _versions_by_source(baseline_values)
    final_by_source = _versions_by_source(final_values)
    evaluations: list[dict[str, str | bool | None]] = []
    for source in sorted(set(baseline_by_source) | set(final_by_source)):
        baseline_versions = baseline_by_source.get(source, [])
        final_versions = final_by_source.get(source, [])
        if len(baseline_versions) != len(final_versions):
            evaluations.append(
                {
                    "source": source,
                    "baseline_version": ", ".join(baseline_versions) or None,
                    "final_version": ", ".join(final_versions) or None,
                    "detected_change_type": "configuration_changed",
                    "comparable": False,
                }
            )
            continue
        for baseline_version, final_version in zip(sorted(baseline_versions), sorted(final_versions)):
            change_type = _classify_version_change(baseline_version, final_version)
            evaluations.append(
                {
                    "source": source,
                    "baseline_version": baseline_version,
                    "final_version": final_version,
                    "detected_change_type": change_type,
                    "comparable": change_type != "unparseable",
                }
            )
    return evaluations


def _classify_version_change(baseline_version: str, final_version: str) -> str:
    if baseline_version == final_version:
        return "unchanged"
    baseline = _numeric_version(baseline_version)
    final = _numeric_version(final_version)
    if baseline is None or final is None:
        return "unparseable"
    width = max(len(baseline), len(final), 3)
    baseline += (0,) * (width - len(baseline))
    final += (0,) * (width - len(final))
    if final < baseline:
        return "downgrade"
    first_difference = next(
        (index for index, values in enumerate(zip(baseline, final)) if values[0] != values[1]),
        None,
    )
    if first_difference is None:
        return "unchanged"
    if first_difference == 0:
        return "major"
    if first_difference == 1:
        return "minor"
    return "patch"


def _numeric_version(value: str) -> tuple[int, ...] | None:
    normalized = value.strip().lstrip("vV")
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _spring_boot_change_allowed(
    evaluation: dict[str, str | bool | None],
    policy: SpringBootVersionPolicy,
) -> bool:
    change_type = evaluation["detected_change_type"]
    final_version = evaluation["final_version"]
    if change_type == "unchanged":
        return True
    if change_type == "patch":
        return policy.allow_patch
    if change_type == "minor":
        return policy.allow_minor
    if change_type == "major":
        return policy.allow_major or final_version in policy.approved_versions
    if change_type == "downgrade":
        return policy.allow_downgrade
    return False


def _versions_by_source(values: tuple[str, ...]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for value in values:
        source, version = _split_detected_version(value)
        result.setdefault(source, []).append(version)
    return result


def _split_detected_version(value: str) -> tuple[str, str]:
    source, separator, version = value.partition("=")
    return (source, version) if separator else ("detected", value)


def _is_property_reference(value: str) -> bool:
    return value.startswith("${") and value.endswith("}")


def _evidence_versions(values: tuple[str, ...]) -> str | list[str] | None:
    versions = [_split_detected_version(value)[1] for value in values]
    if not versions:
        return None
    return versions[0] if len(versions) == 1 else versions


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
