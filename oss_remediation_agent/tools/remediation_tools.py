"""Automated remediation and validation tool for the ADK OSS workflow."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from oss_remediation_agent.tools.scanner_tools import CRITICAL_HIGH, _extract_vulnerabilities, _run, _run_osv, _trim


def generate_remediation_report(vulnerability_assessment_report: dict[str, Any], workspace_path: str | None = None) -> dict[str, Any]:
    """Update only Maven dependency versions in pom.xml files and validate.

    The input must be Agent 1's Vulnerability Assessment Report. The output is
    Agent 2's Remediation Report, which is the only valid input to Agent 3.
    """

    assessment = vulnerability_assessment_report or {}
    repo_dir = Path(workspace_path or assessment.get("workspacePath") or ".").resolve()
    vulnerabilities = [v for v in assessment.get("vulnerabilities", []) if str(v.get("severity", "")).upper() in CRITICAL_HIGH]
    report: dict[str, Any] = {
        "repositoryUrl": assessment.get("repositoryUrl"),
        "referenceBranch": assessment.get("referenceBranch"),
        "featureBranch": assessment.get("featureBranch"),
        "remediationStatus": "FAILED",
        "buildStatus": "NOT_RUN",
        "testStatus": "NOT_RUN",
        "workspacePath": str(repo_dir),
        "modifiedFiles": [],
        "remediatedVulnerabilities": [],
        "manualReviewItems": [],
        "failedItems": [],
        "postRemediationScan": {"criticalRemaining": 0, "highRemaining": 0, "newCriticalOrHighIntroduced": False, "remainingCriticalOrHighItems": []},
    }

    if assessment.get("buildStatus") != "SUCCESS":
        report["failedItems"].append({"status": "FAILED", "reason": "Agent 1 buildStatus is not SUCCESS."})
        return report
    if not repo_dir.exists():
        report["failedItems"].append({"status": "FAILED", "reason": f"Workspace path not found: {repo_dir}"})
        return report

    if assessment.get("featureBranch"):
        _run(["git", "checkout", "-B", assessment["featureBranch"]], repo_dir)

    pom_backups = {pom: pom.read_text(encoding="utf-8") for pom in repo_dir.rglob("pom.xml")}
    modified_files: set[str] = set()

    for vulnerability in vulnerabilities:
        result = _remediate_one(repo_dir, vulnerability)
        if result["status"] == "FIXED":
            report["remediatedVulnerabilities"].append(result)
            modified_files.update(result.get("modifiedFiles", []))
        elif result["status"] == "MANUAL_REVIEW":
            report["manualReviewItems"].append(result)
        else:
            report["failedItems"].append(result)

    if report["failedItems"]:
        _restore(pom_backups)
        return report

    report["modifiedFiles"] = sorted(modified_files)
    build = _run(["mvn", "-B", "clean", "install"], repo_dir, timeout=1800)
    report["buildStatus"] = "SUCCESS" if build["returncode"] == 0 else "FAILED"
    if build["returncode"] != 0:
        _restore(pom_backups)
        report["modifiedFiles"] = []
        report["failedItems"].append({"status": "FAILED", "reason": "Build failed after remediation.", "details": _trim(build)})
        return report

    tests = _run(["mvn", "-B", "test"], repo_dir, timeout=1800)
    report["testStatus"] = "SUCCESS" if tests["returncode"] == 0 else "FAILED"
    if tests["returncode"] != 0:
        _restore(pom_backups)
        report["modifiedFiles"] = []
        report["failedItems"].append({"status": "FAILED", "reason": "Tests failed after remediation.", "details": _trim(tests)})
        return report

    remaining = _extract_vulnerabilities(_run_osv(repo_dir).get("json") or {})
    original_keys = {_vuln_key(v) for v in vulnerabilities}
    manual_keys = {_vuln_key(v) for v in report["manualReviewItems"]}
    remaining_items = []
    for item in remaining:
        remaining_items.append({
            "dependencyName": item.get("dependencyName"),
            "severity": item.get("severity"),
            "vulnerabilityIds": item.get("vulnerabilityIds", []),
            "status": "MANUAL_REVIEW" if _vuln_key(item) in manual_keys else "UNRESOLVED",
        })

    report["postRemediationScan"] = {
        "criticalRemaining": sum(1 for item in remaining_items if item["severity"] == "CRITICAL"),
        "highRemaining": sum(1 for item in remaining_items if item["severity"] == "HIGH"),
        "newCriticalOrHighIntroduced": any(_vuln_key(item) not in original_keys for item in remaining),
        "remainingCriticalOrHighItems": remaining_items,
    }

    unresolved = [item for item in remaining_items if item["status"] != "MANUAL_REVIEW"]
    if unresolved:
        report["failedItems"].extend(unresolved)
        report["remediationStatus"] = "FAILED"
    elif report["manualReviewItems"]:
        report["remediationStatus"] = "PARTIAL_SUCCESS"
    else:
        report["remediationStatus"] = "SUCCESS"
    return report


def apply_remediation(repo_url: str, dependency: str, recommended_version: str) -> dict[str, Any]:
    """Backward-compatible alias for the previous sample tool name."""
    return {"status": "manual_review", "repo_url": repo_url, "dependency": dependency, "requested_version": recommended_version, "message": "Use generate_remediation_report with Agent 1's Vulnerability Assessment Report."}


def _remediate_one(repo_dir: Path, vuln: dict[str, Any]) -> dict[str, Any]:
    dependency = str(vuln.get("dependencyName") or "")
    parts = dependency.split(":")
    fixes = [str(version) for version in vuln.get("suggestedFixVersions", []) if version]
    if len(parts) < 2:
        return _manual(vuln, f"Dependency is not a Maven groupId:artifactId coordinate: {dependency}")
    if not fixes:
        return _manual(vuln, "OSV Scanner did not provide suggested fixed versions.")
    if "jdk" in json.dumps(vuln, default=str).lower() or "java 21" in json.dumps(vuln, default=str).lower():
        return _manual(vuln, "Suggested remediation appears to require a JDK upgrade, which is out of scope.")

    pom = _find_pom(repo_dir, parts[0], parts[1], str(vuln.get("affectedPomFile") or "pom.xml"))
    if not pom:
        return _manual(vuln, "No existing pom.xml dependency version declaration was found to update safely.")

    selected = fixes[0]
    update = _update_pom_version(pom, parts[0], parts[1], selected)
    if not update["updated"]:
        return _manual(vuln, update["reason"])

    relative_pom = str(pom.relative_to(repo_dir))
    return {
        "dependencyName": dependency,
        "previousVersion": vuln.get("currentVersion"),
        "updatedVersion": selected,
        "severity": str(vuln.get("severity", "")).upper(),
        "vulnerabilityIds": vuln.get("vulnerabilityIds", []),
        "affectedPomFile": relative_pom,
        "suggestedFixVersions": fixes,
        "selectedVersionReason": f"Selected {selected} because it is the lowest suggested fixed version and limits remediation to Maven dependency version changes.",
        "rejectedVersions": [{"version": version, "reason": f"Not selected because {selected} was tried first to reduce compatibility risk."} for version in fixes[1:]],
        "status": "FIXED",
        "modifiedFiles": [relative_pom],
    }


def _find_pom(repo_dir: Path, group_id: str, artifact_id: str, affected: str) -> Path | None:
    candidates = [repo_dir / affected] if affected else []
    candidates.extend(repo_dir.rglob("pom.xml"))
    for pom in candidates:
        if pom.exists() and pom.name == "pom.xml" and _pom_has_dependency(pom, group_id, artifact_id):
            return pom
    return None


def _pom_has_dependency(pom: Path, group_id: str, artifact_id: str) -> bool:
    try:
        root = ET.parse(pom).getroot()
    except ET.ParseError:
        return False
    for dependency in root.findall(".//{*}dependency"):
        if _child_text(dependency, "groupId") == group_id and _child_text(dependency, "artifactId") == artifact_id:
            return True
    return False


def _update_pom_version(pom: Path, group_id: str, artifact_id: str, version: str) -> dict[str, Any]:
    ET.register_namespace("", "http://maven.apache.org/POM/4.0.0")
    try:
        tree = ET.parse(pom)
    except ET.ParseError as exc:
        return {"updated": False, "reason": f"Unable to parse pom.xml: {exc}"}
    root = tree.getroot()
    for dependency in root.findall(".//{*}dependency"):
        if _child_text(dependency, "groupId") == group_id and _child_text(dependency, "artifactId") == artifact_id:
            version_node = _child(dependency, "version")
            if version_node is None or not version_node.text:
                return {"updated": False, "reason": "Dependency is managed without a direct version; manual dependencyManagement review is required."}
            prop = re.fullmatch(r"\$\{([^}]+)\}", version_node.text.strip())
            if prop:
                prop_node = _find_property(root, prop.group(1))
                if prop_node is None:
                    return {"updated": False, "reason": f"Version property {version_node.text} was not found."}
                prop_node.text = version
            else:
                version_node.text = version
            tree.write(pom, encoding="utf-8", xml_declaration=True)
            return {"updated": True, "reason": None}
    return {"updated": False, "reason": "Dependency declaration not found."}


def _manual(vuln: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"dependencyName": vuln.get("dependencyName"), "currentVersion": vuln.get("currentVersion"), "severity": str(vuln.get("severity", "")).upper(), "vulnerabilityIds": vuln.get("vulnerabilityIds", []), "suggestedFixVersions": vuln.get("suggestedFixVersions", []), "affectedPomFile": vuln.get("affectedPomFile"), "status": "MANUAL_REVIEW", "manualReviewRequired": True, "manualReviewReason": reason}


def _child(node: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in list(node) if child.tag.split("}")[-1] == name), None)


def _child_text(node: ET.Element, name: str) -> str | None:
    child = _child(node, name)
    return child.text.strip() if child is not None and child.text else None


def _find_property(root: ET.Element, name: str) -> ET.Element | None:
    props = root.find(".//{*}properties")
    if props is None:
        return None
    return next((child for child in list(props) if child.tag.split("}")[-1] == name), None)


def _restore(backups: dict[Path, str]) -> None:
    for path, content in backups.items():
        path.write_text(content, encoding="utf-8")


def _vuln_key(item: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    return str(item.get("dependencyName") or ""), tuple(sorted(str(v) for v in item.get("vulnerabilityIds", [])))
