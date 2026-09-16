from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
import math
from pathlib import Path
from typing import Any, Iterable

from ..capabilities.execution import ProcessRunner
from ..config import ScannerConfig
from ..models import CommandResult, ScanReport, ScannerHandle, VulnerabilityFinding
from ..workspace import RunWorkspace, TraceStore, sha256_file


class ScannerPreflightError(RuntimeError):
    pass


class OsvScanner:
    def __init__(self, workspace: RunWorkspace, process_runner: ProcessRunner, trace: TraceStore):
        self.workspace = workspace
        self.process_runner = process_runner
        self.trace = trace
        self.handle: ScannerHandle | None = None

    def preflight(self, config: ScannerConfig) -> ScannerHandle:
        if config.mode == "configured":
            executable = _resolve_executable(config.executable)
            if not executable:
                raise ScannerPreflightError(f"Configured OSV Scanner is unavailable: {config.executable}")
            handle = self._inspect(Path(executable), config, provisioned=False)
        elif config.mode == "provision":
            handle = self._provision(config)
        else:
            raise ScannerPreflightError("scanner.mode must be configured or provision")
        self.handle = handle
        self.trace.write_json("scanner/preflight.json", handle.to_dict())
        self.trace.append_event("scanner_preflight", **handle.to_dict())
        return handle

    def verify(self) -> ScannerHandle:
        if not self.handle:
            raise ScannerPreflightError("OSV Scanner preflight has not completed")
        path = Path(self.handle.executable)
        if not path.is_file():
            raise ScannerPreflightError("Resolved OSV Scanner executable disappeared")
        digest = sha256_file(path)
        if digest != self.handle.sha256:
            raise ScannerPreflightError("Resolved OSV Scanner integrity changed after preflight")
        return self.handle

    def scan(self, repository: Path, severity_scope: tuple[str, ...], label: str) -> ScanReport:
        handle = self.verify()
        with tempfile.TemporaryDirectory(prefix="autonomous-osv-", dir=self.workspace.temp) as temp_dir:
            staged = Path(temp_dir) / "repository"
            shutil.copytree(
                repository,
                staged,
                ignore=shutil.ignore_patterns(".git", "target", ".gradle", "node_modules"),
            )
            result = self.process_runner.run_argv(
                [handle.executable, "scan", "source", "-r", str(staged), "--format", "json"],
                cwd=staged,
                source=f"osv_{label}",
            )
        raw_stdout = result.stdout
        if result.stdout_artifact:
            raw_stdout = Path(result.stdout_artifact).read_text(encoding="utf-8")
        raw_path = self.workspace.artifacts / "scans" / f"{label}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_stdout or "{}", encoding="utf-8")
        try:
            payload = json.loads(raw_stdout or "{}")
        except json.JSONDecodeError:
            payload = None
        recognizable = isinstance(payload, dict) and (
            isinstance(payload.get("results"), list) or isinstance(payload.get("packages"), list)
        )
        no_sources = "no package sources found" in result.stderr.lower()
        succeeded = result.exit_code in (0, 1) and recognizable and not result.timed_out and not no_sources
        findings = tuple(normalize_osv_findings(payload or {}, severity_scope)) if recognizable else ()
        error = None
        if not succeeded:
            error = result.stderr.strip() or "OSV Scanner did not produce a recognizable JSON report"
        report = ScanReport(
            succeeded=succeeded,
            findings=findings,
            command_result=result,
            raw_report_path=str(raw_path),
            error=error,
        )
        self.trace.write_json(f"scans/{label}.normalized.json", report.to_dict())
        return report

    def _inspect(self, executable: Path, config: ScannerConfig, provisioned: bool) -> ScannerHandle:
        digest = sha256_file(executable)
        if config.sha256 and digest.lower() != config.sha256.lower():
            raise ScannerPreflightError("OSV Scanner checksum does not match configured sha256")
        version_result = self.process_runner.run_argv(
            [str(executable), "--version"],
            cwd=self.workspace.root,
            timeout_seconds=config.timeout_seconds,
            source="osv_version",
        )
        if not version_result.succeeded:
            raise ScannerPreflightError(f"Unable to execute OSV Scanner: {version_result.stderr}")
        version = (version_result.stdout or version_result.stderr).strip().splitlines()[0]
        if config.version and config.version not in version:
            raise ScannerPreflightError(f"OSV Scanner version mismatch: expected {config.version}, got {version}")
        return ScannerHandle(str(executable.resolve()), version, digest, provisioned)

    def _provision(self, config: ScannerConfig) -> ScannerHandle:
        if not config.download_url or not config.sha256 or not config.version:
            raise ScannerPreflightError("Provision mode requires download_url, sha256, and version")
        download = self.workspace.tools / "osv-scanner-download"
        try:
            with urllib.request.urlopen(config.download_url, timeout=config.timeout_seconds) as response:
                download.write_bytes(response.read())
        except Exception as exc:
            raise ScannerPreflightError(f"OSV Scanner download failed: {exc}") from exc
        if sha256_file(download).lower() != config.sha256.lower():
            download.unlink(missing_ok=True)
            raise ScannerPreflightError("Downloaded OSV Scanner archive checksum mismatch")
        executable_name = Path(config.archive_member).name if config.archive_member else (
            "osv-scanner.exe" if os.name == "nt" else "osv-scanner"
        )
        if executable_name.lower() not in {"osv-scanner", "osv-scanner.exe", "osv-scanner.cmd"}:
            raise ScannerPreflightError("Configured scanner archive member must name an OSV Scanner executable")
        executable = self.workspace.tools / executable_name
        _extract_scanner(download, executable, config.archive_member)
        if os.name != "nt":
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        inspect_config = ScannerConfig(
            mode="configured",
            executable=str(executable),
            version=config.version,
            timeout_seconds=config.timeout_seconds,
        )
        return self._inspect(executable, inspect_config, provisioned=True)


def normalize_osv_findings(raw_json: Any, severity_scope: Iterable[str]) -> list[VulnerabilityFinding]:
    scope = {str(value).upper() for value in severity_scope}
    findings: list[VulnerabilityFinding] = []
    seen: set[tuple[tuple[str, ...], str, str]] = set()
    for package, vulnerability in _iter_records(raw_json):
        if not _is_maven(package):
            continue
        severity = _severity(vulnerability)
        if severity not in scope:
            continue
        package_name = str(package.get("name") or "")
        group_id, artifact_id = _split_coordinate(package_name)
        primary = str(vulnerability.get("id") or "UNKNOWN")
        aliases = tuple(str(value) for value in vulnerability.get("aliases", []) or [] if value)
        identifiers = tuple(sorted({primary, *aliases}))
        version = str(package.get("version") or "UNKNOWN")
        key = (identifiers, package_name, version)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            VulnerabilityFinding(
                vulnerability_id=primary,
                aliases=aliases,
                severity=severity,
                group_id=group_id,
                artifact_id=artifact_id,
                package_name=package_name,
                version=version,
                fixed_versions=tuple(_fixed_versions(vulnerability)),
                summary=str(vulnerability.get("summary") or vulnerability.get("details") or ""),
            )
        )
    return findings


def _iter_records(value: Any):
    if isinstance(value, dict):
        package_records = value.get("packages", []) if isinstance(value.get("packages"), list) else []
        for package_record in package_records:
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
                    score = _numeric_score(item.get("score") or item.get("baseScore"))
                    if score is not None:
                        return _score_to_severity(score)
    score = _numeric_score((vulnerability.get("database_specific") or {}).get("cvss_score"))
    return _score_to_severity(score or 0)


def _numeric_score(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?", value.strip()):
        return float(value)
    if isinstance(value, str) and value.startswith("CVSS:3."):
        return _cvss_v3_score(value)
    return None


def _cvss_v3_score(vector: str) -> float | None:
    try:
        metrics = dict(part.split(":", 1) for part in vector.split("/")[1:])
        scope = metrics["S"]
        attack_vector = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}[metrics["AV"]]
        attack_complexity = {"L": 0.77, "H": 0.44}[metrics["AC"]]
        privileges = {
            "U": {"N": 0.85, "L": 0.62, "H": 0.27},
            "C": {"N": 0.85, "L": 0.68, "H": 0.50},
        }[scope][metrics["PR"]]
        user_interaction = {"N": 0.85, "R": 0.62}[metrics["UI"]]
        confidentiality = {"H": 0.56, "L": 0.22, "N": 0.0}[metrics["C"]]
        integrity = {"H": 0.56, "L": 0.22, "N": 0.0}[metrics["I"]]
        availability = {"H": 0.56, "L": 0.22, "N": 0.0}[metrics["A"]]
    except (KeyError, ValueError):
        return None
    impact_subscore = 1 - ((1 - confidentiality) * (1 - integrity) * (1 - availability))
    if scope == "U":
        impact = 6.42 * impact_subscore
    else:
        impact = 7.52 * (impact_subscore - 0.029) - 3.25 * ((impact_subscore - 0.02) ** 15)
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * attack_vector * attack_complexity * privileges * user_interaction
    raw = min(impact + exploitability, 10) if scope == "U" else min(1.08 * (impact + exploitability), 10)
    return math.ceil(raw * 10) / 10


def _score_to_severity(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


def _fixed_versions(vulnerability: dict[str, Any]) -> list[str]:
    versions: set[str] = set()
    for affected in vulnerability.get("affected", []) or []:
        for range_item in affected.get("ranges", []) or []:
            for event in range_item.get("events", []) or []:
                if isinstance(event, dict) and event.get("fixed"):
                    versions.add(str(event["fixed"]))
    return sorted(versions)


def _split_coordinate(name: str) -> tuple[str | None, str | None]:
    if ":" not in name:
        return None, name or None
    return tuple(name.split(":", 1))  # type: ignore[return-value]


def _resolve_executable(value: str) -> str | None:
    path = Path(value).expanduser()
    if path.is_file():
        return str(path.resolve())
    return shutil.which(value)


def _extract_scanner(download: Path, executable: Path, archive_member: str | None) -> None:
    if zipfile.is_zipfile(download):
        with zipfile.ZipFile(download) as archive:
            member = _select_member(archive.namelist(), archive_member)
            executable.write_bytes(archive.read(member))
        return
    if tarfile.is_tarfile(download):
        with tarfile.open(download) as archive:
            names = [member.name for member in archive.getmembers() if member.isfile()]
            member_name = _select_member(names, archive_member)
            member = archive.getmember(member_name)
            handle = archive.extractfile(member)
            if handle is None:
                raise ScannerPreflightError("Unable to extract OSV Scanner archive member")
            executable.write_bytes(handle.read())
        return
    executable.write_bytes(download.read_bytes())


def _select_member(names: list[str], requested: str | None) -> str:
    if requested:
        if requested not in names:
            raise ScannerPreflightError(f"Configured scanner archive member not found: {requested}")
        return requested
    candidates = [
        name
        for name in names
        if Path(name).name.lower() in {"osv-scanner", "osv-scanner.exe", "osv-scanner.cmd"}
    ]
    if len(candidates) != 1:
        raise ScannerPreflightError("Unable to uniquely identify OSV Scanner in archive")
    return candidates[0]
