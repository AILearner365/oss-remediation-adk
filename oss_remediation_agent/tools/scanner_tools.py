"""Discovery and assessment tool for the ADK OSS remediation workflow."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CRITICAL_HIGH = {"CRITICAL", "HIGH"}


def generate_vulnerability_assessment_report(repository_url: str, reference_branch: str = "main", workspace_root: str | None = None) -> dict[str, Any]:
    """Clone, build, scan, and return Agent 1's Vulnerability Assessment Report."""

    workspace = Path(workspace_root or tempfile.mkdtemp(prefix="oss-remediation-"))
    workspace.mkdir(parents=True, exist_ok=True)
    repo_dir = workspace / _safe_repo_name(repository_url)
    report: dict[str, Any] = {
        "repositoryUrl": repository_url,
        "referenceBranch": reference_branch,
        "latestCommitId": None,
        "featureBranch": None,
        "buildStatus": "NOT_RUN",
        "scanTool": "OSV Scanner",
        "projectType": "MAVEN_SPRING_BOOT",
        "isMultiModuleProject": False,
        "criticalCount": 0,
        "highCount": 0,
        "workspacePath": str(repo_dir),
        "vulnerabilities": [],
        "toolExecutionStatus": "RUNNING",
        "errors": [],
    }

    clone = _run(["git", "clone", repository_url, str(repo_dir)], workspace)
    if clone["returncode"] != 0:
        return _failed(report, "CLONE_FAILED", clone)

    checkout = _run(["git", "checkout", reference_branch], repo_dir)
    if checkout["returncode"] != 0:
        return _failed(report, "CHECKOUT_FAILED", checkout)

    _run(["git", "pull", "origin", reference_branch], repo_dir)
    report["isMultiModuleProject"] = _is_multi_module(repo_dir)

    build = _run(["mvn", "-B", "clean", "install"], repo_dir, timeout=1800)
    if build["returncode"] != 0:
        report["buildStatus"] = "FAILED"
        report["toolExecutionStatus"] = "TERMINATED"
        report["errors"].append({"stage": "BUILD", "message": "Reference branch is not able to build successfully. Discovery terminated before scan.", "details": _trim(build)})
        return report

    report["buildStatus"] = "SUCCESS"
    commit = _run(["git", "rev-parse", "HEAD"], repo_dir)
    latest_commit = commit["stdout"].strip() if commit["returncode"] == 0 else "unknown"
    report["latestCommitId"] = latest_commit
    report["featureBranch"] = _feature_branch(reference_branch, latest_commit)

    scan = _run_osv(repo_dir)
    if scan["returncode"] != 0 and not scan.get("json"):
        report["toolExecutionStatus"] = "SCAN_FAILED"
        report["errors"].append({"stage": "SCAN", "details": _trim(scan)})
        return report

    vulns = _extract_vulnerabilities(scan.get("json") or {})
    report["vulnerabilities"] = vulns
    report["criticalCount"] = sum(1 for vuln in vulns if vuln["severity"] == "CRITICAL")
    report["highCount"] = sum(1 for vuln in vulns if vuln["severity"] == "HIGH")
    report["toolExecutionStatus"] = "SUCCESS"
    return report


def scan_repository(repo_url: str, reference_branch: str = "main") -> dict[str, Any]:
    """Backward-compatible alias for the previous sample tool name."""
    return generate_vulnerability_assessment_report(repo_url, reference_branch)


def _run(command: list[str], cwd: Path, timeout: int = 300) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
        return {"command": command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except FileNotFoundError as exc:
        return {"command": command, "returncode": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {"command": command, "returncode": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "Command timed out."}


def _run_osv(repo_dir: Path) -> dict[str, Any]:
    for command in (["osv-scanner", "scan", "source", "-r", ".", "--format", "json"], ["osv-scanner", "-r", ".", "--format", "json"]):
        result = _run(command, repo_dir, timeout=1200)
        result["json"] = _json(result.get("stdout", ""))
        if result["returncode"] == 0 or result["json"]:
            return result
    return result


def _json(output: str) -> Any | None:
    try:
        return json.loads(output)
    except Exception:
        start, end = output.find("{"), output.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(output[start : end + 1])
            except Exception:
                return None
    return None


def _extract_vulnerabilities(osv_json: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for package, vuln, source in _iter_osv(osv_json):
        severity = _severity(vuln)
        if severity not in CRITICAL_HIGH:
            continue
        name = str(package.get("name") or "UNKNOWN")
        version = str(package.get("version") or "UNKNOWN")
        ids = sorted({str(vuln.get("id"))} | {str(alias) for alias in vuln.get("aliases", [])})
        key = (name, version, tuple(ids))
        if key in seen:
            continue
        seen.add(key)
        findings.append({"dependencyName": name, "currentVersion": version, "severity": severity, "vulnerabilityIds": ids, "summary": vuln.get("summary") or vuln.get("details") or "", "suggestedFixVersions": _fixed_versions(vuln), "affectedPomFile": source if str(source).endswith("pom.xml") else "pom.xml", "dependencyScope": package.get("scope") or "UNKNOWN", "isDirectDependency": bool(package.get("direct", False)), "manualReviewRequired": False, "manualReviewReason": None})
    return findings


def _iter_osv(value: Any, source: str | None = None):
    if isinstance(value, dict):
        if isinstance(value.get("source"), dict):
            source = value["source"].get("path") or source
        for package_record in value.get("packages", []) if isinstance(value.get("packages"), list) else []:
            package = package_record.get("package", package_record)
            for vuln in package_record.get("vulnerabilities", []) if isinstance(package_record, dict) else []:
                if isinstance(package, dict) and isinstance(vuln, dict):
                    yield package, vuln, source
        for item in value.values():
            yield from _iter_osv(item, source)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_osv(item, source)


def _severity(vuln: dict[str, Any]) -> str:
    raw = (vuln.get("database_specific") or {}).get("severity") or vuln.get("severity")
    if isinstance(raw, str):
        return raw.upper()
    if isinstance(raw, list):
        for item in raw:
            value = item if isinstance(item, str) else item.get("severity") if isinstance(item, dict) else None
            if str(value).upper() in CRITICAL_HIGH:
                return str(value).upper()
    return "UNKNOWN"


def _fixed_versions(vuln: dict[str, Any]) -> list[str]:
    versions: set[str] = set()
    for affected in vuln.get("affected", []) if isinstance(vuln.get("affected"), list) else []:
        for range_item in affected.get("ranges", []) if isinstance(affected, dict) else []:
            for event in range_item.get("events", []) if isinstance(range_item, dict) else []:
                if isinstance(event, dict) and event.get("fixed"):
                    versions.add(str(event["fixed"]))
    return sorted(versions, key=_version_key)


def _is_multi_module(repo_dir: Path) -> bool:
    pom = repo_dir / "pom.xml"
    if not pom.exists():
        return False
    try:
        return bool(ET.parse(pom).getroot().findall(".//{*}modules/{*}module"))
    except ET.ParseError:
        return False


def _safe_repo_name(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    name = name[:-4] if name.endswith(".git") else name
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name) or "repository"


def _feature_branch(reference_branch: str, commit: str) -> str:
    branch = re.sub(r"[^A-Za-z0-9_.-]", "-", reference_branch)
    return f"oss-remediation-{branch}-{(commit or '0000')[:4]}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _version_key(version: str) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"([0-9]+)", str(version)) if part)


def _trim(result: dict[str, Any], limit: int = 4000) -> dict[str, Any]:
    return {"command": result.get("command"), "returncode": result.get("returncode"), "stdout": str(result.get("stdout", ""))[-limit:], "stderr": str(result.get("stderr", ""))[-limit:]}


def _failed(report: dict[str, Any], status: str, result: dict[str, Any]) -> dict[str, Any]:
    report["toolExecutionStatus"] = status
    report["errors"].append({"stage": status, "details": _trim(result)})
    return report
