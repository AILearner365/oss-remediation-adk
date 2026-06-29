from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from oss_remediation_agent.contracts import ToolResult, common_artifact
from oss_remediation_agent.utils import run_command

TOOL = "OSVScannerTool"


def generate_vulnerability_assessment(
    repository_path: str,
    output_path: str,
    raw_report_path: str,
    severity_scope: list[str] | None = None,
    workflow_id: str = "unknown",
) -> dict:
    severity_scope = severity_scope or ["CRITICAL", "HIGH"]
    result = run_command(["osv-scanner", "scan", "source", "-r", ".", "--format", "json"], cwd=repository_path)
    raw_text = result.get("stdout") or "{}"
    Path(raw_report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(raw_report_path).write_text(raw_text, encoding="utf-8")
    raw_json = _loads(raw_text)
    vulnerabilities = normalize_osv_findings(raw_json, severity_scope, raw_report_path)
    status = "SUCCESS" if result["exitCode"] in (0, 1) else "FAILED"
    artifact = common_artifact(
        artifact_id="vulnerability-assessment-001",
        workflow_id=workflow_id,
        created_by=TOOL,
        status=status,
        reportType="VULNERABILITY_ASSESSMENT",
        scanner={"name": "OSV", "command": "osv-scanner scan source -r . --format json", "rawReportPath": raw_report_path},
        severityScope=severity_scope,
        vulnerabilities=vulnerabilities,
        summary={
            "criticalCount": sum(1 for item in vulnerabilities if item["severity"] == "CRITICAL"),
            "highCount": sum(1 for item in vulnerabilities if item["severity"] == "HIGH"),
            "totalInScopeCount": len(vulnerabilities),
        },
        artifactReferences={"rawOsvReport": raw_report_path},
        errors=[] if status == "SUCCESS" else [result.get("stderr", "")],
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(
        tool_name=TOOL,
        tool_version="1.0.0",
        operation="generate_vulnerability_assessment",
        status=status,
        artifact_path=output_path,
        failure_code=None if status == "SUCCESS" else "OSV_SCAN_FAILED",
        capabilities=["OSV_SCAN", "SEVERITY_FILTERING", "MAVEN_ECOSYSTEM_NORMALIZATION"],
        payload=artifact["summary"] | {"rawReportPath": raw_report_path},
        errors=[] if status == "SUCCESS" else [result.get("stderr", "")],
    ).to_dict()


def validate_post_remediation(repository_path: str, output_path: str, severity_scope: list[str] | None = None) -> dict:
    severity_scope = severity_scope or ["CRITICAL", "HIGH"]
    result = run_command(["osv-scanner", "scan", "source", "-r", ".", "--format", "json"], cwd=repository_path)
    raw_text = result.get("stdout") or "{}"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(raw_text, encoding="utf-8")
    remaining = normalize_osv_findings(_loads(raw_text), severity_scope, output_path)
    return ToolResult(
        tool_name=TOOL,
        tool_version="1.0.0",
        operation="validate_post_remediation",
        status="SUCCESS" if result["exitCode"] in (0, 1) else "FAILED",
        artifact_path=output_path,
        failure_code=None if result["exitCode"] in (0, 1) else "OSV_SCAN_FAILED",
        capabilities=["POST_REMEDIATION_SCAN"],
        payload={
            "scanResultFile": output_path,
            "remainingCriticalCount": sum(1 for item in remaining if item["severity"] == "CRITICAL"),
            "remainingHighCount": sum(1 for item in remaining if item["severity"] == "HIGH"),
            "remainingVulnerabilities": remaining,
        },
        errors=[] if result["exitCode"] in (0, 1) else [result.get("stderr", "")],
    ).to_dict()


def normalize_osv_findings(raw_json: Any, severity_scope: list[str], raw_path: str | Path) -> list[dict[str, Any]]:
    scope = {value.upper() for value in severity_scope}
    normalized = []
    seen = set()
    for package, vulnerability in _iter_records(raw_json):
        if not _is_maven(package):
            continue
        severity = _severity(vulnerability)
        if severity not in scope:
            continue
        package_name = str(package.get("name") or "")
        group_id, artifact_id = _split_coordinate(package_name)
        ids = [str(vulnerability.get("id"))] + [str(alias) for alias in vulnerability.get("aliases", [])]
        ids = [item for item in ids if item and item != "None"]
        key = (tuple(sorted(ids)), package_name, package.get("version"))
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "vulnerabilityId": ids[0] if ids else "UNKNOWN",
            "aliases": ids[1:],
            "severity": severity,
            "dependency": {
                "groupId": group_id,
                "artifactId": artifact_id,
                "packageName": package_name,
                "ecosystem": "Maven",
                "currentVersion": str(package.get("version") or "UNKNOWN"),
            },
            "fixedVersions": _fixed_versions(vulnerability),
            "scannerEvidence": {"rawFindingPath": str(raw_path), "summary": vulnerability.get("summary") or vulnerability.get("details") or ""},
            "status": "OPEN",
        })
    return normalized


def _iter_records(value: Any):
    if isinstance(value, dict):
        for package_record in value.get("packages", []) if isinstance(value.get("packages"), list) else []:
            if not isinstance(package_record, dict):
                continue
            package = package_record.get("package") or package_record
            for vulnerability in package_record.get("vulnerabilities", []) or []:
                if isinstance(package, dict) and isinstance(vulnerability, dict):
                    yield package, vulnerability
        for child in value.values():
            yield from _iter_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_records(child)


def _is_maven(package: dict[str, Any]) -> bool:
    ecosystem = str(package.get("ecosystem") or "").lower()
    name = str(package.get("name") or "")
    return ecosystem == "maven" or (not ecosystem and ":" in name)


def _severity(vulnerability: dict[str, Any]) -> str:
    candidates = [
        vulnerability.get("severity"),
        (vulnerability.get("database_specific") or {}).get("severity"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.upper() in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            return candidate.upper()
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, dict):
                    score = _score(item.get("score") or item.get("baseScore"))
                    if score is not None:
                        return _score_to_severity(score)
    score = _score((vulnerability.get("database_specific") or {}).get("cvss_score"))
    return _score_to_severity(score or 0)


def _fixed_versions(vulnerability: dict[str, Any]) -> list[str]:
    versions = set()
    for affected in vulnerability.get("affected", []) or []:
        for range_item in affected.get("ranges", []) or []:
            for event in range_item.get("events", []) or []:
                if isinstance(event, dict) and event.get("fixed"):
                    versions.add(str(event["fixed"]))
    return sorted(versions)


def _split_coordinate(name: str) -> tuple[str | None, str | None]:
    if ":" not in name:
        return None, name or None
    group_id, artifact_id = name.split(":", 1)
    return group_id, artifact_id


def _score(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.upper().startswith("CVSS:"):
            return None
        if re.fullmatch(r"\d+(?:\.\d+)?", stripped):
            return float(stripped)
    return None


def _score_to_severity(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


def _loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return {}
