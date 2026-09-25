from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import tarfile
import tempfile
import threading
import time
import urllib.request
import urllib.parse
import zipfile
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from ..capabilities.execution import ProcessRunner
from ..config import ScannerConfig
from ..evidence import is_generated_evidence_path, scanner_copy_ignore
from ..models import CommandResult, ScanFailureKind, ScanOutcome, ScanReport, ScannerHandle, VulnerabilityFinding
from ..workspace import RunWorkspace, TraceStore, sha256_file
from .scanner import ScannerPreflightError


class OsvScanner:
    backend = "osv"

    def __init__(
        self,
        workspace: RunWorkspace,
        process_runner: ProcessRunner,
        trace: TraceStore,
        *,
        retry_backoff_seconds: tuple[float, ...] = (5.0, 15.0),
        sleep: Callable[[float], None] = time.sleep,
        maven_repository: Path | None = None,
    ):
        self.workspace = workspace
        self.process_runner = process_runner
        self.trace = trace
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep = sleep
        self.maven_repository = maven_repository or _default_maven_repository()
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
        _verify_maven_scanner_compatibility(handle.version, repository)
        attempts: list[dict[str, Any]] = []
        max_attempts = len(self.retry_backoff_seconds) + 1
        registry_roots = (self.maven_repository,) if self.maven_repository.is_dir() else ()
        for attempt_number in range(1, max_attempts + 1):
            result = self._execute_scan(handle, repository, label, attempt_number, registry_roots)
            raw_stdout = _full_output(result.stdout, result.stdout_artifact)
            raw_stderr = _full_output(result.stderr, result.stderr_artifact)
            raw_path = self.workspace.artifacts / "scans" / f"{label}-attempt-{attempt_number}.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(raw_stdout or "{}", encoding="utf-8")
            stdout_path = self.workspace.artifacts / "scans" / f"{label}-attempt-{attempt_number}.stdout.log"
            stderr_path = self.workspace.artifacts / "scans" / f"{label}-attempt-{attempt_number}.stderr.log"
            stdout_path.write_text(raw_stdout, encoding="utf-8")
            stderr_path.write_text(raw_stderr, encoding="utf-8")
            payload = _parse_payload(raw_stdout)
            recognizable = _is_recognizable_report(payload)
            findings = tuple(normalize_osv_findings(payload or {}, severity_scope)) if recognizable else ()
            outcome, failure_reason = _classify_attempt(result, payload, raw_stdout, raw_stderr)
            retry_scheduled = (
                outcome == ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE
                and attempt_number < max_attempts
            )
            backoff_seconds = self.retry_backoff_seconds[attempt_number - 1] if retry_scheduled else None
            attempt = {
                "attemptNumber": attempt_number,
                "command": result.command,
                "exitCode": result.exit_code,
                "stdoutArtifact": str(stdout_path),
                "stderrArtifact": str(stderr_path),
                "rawReportPath": str(raw_path),
                "outcome": outcome.value,
                "failureReason": failure_reason,
                "retryScheduled": retry_scheduled,
                "backoffSeconds": backoff_seconds,
                "commandResult": result.to_dict(),
            }
            attempts.append(attempt)
            self.trace.write_json(f"scans/{label}-attempt-{attempt_number}.evidence.json", attempt)
            self.trace.append_event("osv_scan_attempt", label=label, **attempt)
            if retry_scheduled:
                self.sleep(backoff_seconds)
                continue
            final_path = self.workspace.artifacts / "scans" / f"{label}.json"
            final_path.write_text(raw_stdout or "{}", encoding="utf-8")
            succeeded = outcome in {
                ScanOutcome.COMPLETED_CLEAN,
                ScanOutcome.COMPLETED_WITH_FINDINGS,
            }
            error = None if succeeded else failure_reason
            report = ScanReport(
                succeeded=succeeded,
                findings=findings if succeeded else (),
                command_result=result,
                raw_report_path=str(final_path),
                error=error,
                outcome=outcome,
                attempts=tuple(attempts),
                backend=self.backend,
                failure_kind=_failure_kind(failure_reason),
            )
            break
        else:
            raise AssertionError("OSV retry loop did not produce a report")
        self.trace.write_json(f"scans/{label}.normalized.json", report.to_dict())
        return report

    def _execute_scan(
        self,
        handle: ScannerHandle,
        repository: Path,
        label: str,
        attempt_number: int,
        registry_roots: tuple[Path, ...],
    ) -> CommandResult:
        with tempfile.TemporaryDirectory(prefix="autonomous-osv-", dir=self.workspace.temp) as temp_dir:
            staged = Path(temp_dir) / "repository"
            shutil.copytree(
                repository,
                staged,
                ignore=scanner_copy_ignore,
            )
            if registry_roots:
                with _serve_maven_repository(registry_roots) as (registry_url, requests):
                    command = _scan_command(handle.executable, staged, "native", registry_url)
                    result = self.process_runner.run_argv(
                        command,
                        cwd=staged,
                        source=f"osv_{label}_attempt_{attempt_number}",
                    )
                self.trace.write_json(
                    f"scans/{label}-attempt-{attempt_number}.maven-requests.json",
                    {"registryUrl": registry_url, "requests": requests},
                )
                return result
            command = _scan_command(handle.executable, staged, "deps.dev")
            return self.process_runner.run_argv(
                command,
                cwd=staged,
                source=f"osv_{label}_attempt_{attempt_number}",
            )

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


_TRANSIENT_FAILURE_PATTERNS = (
    (re.compile(r"(?:http(?: response)?(?: status)?|status(?: code)?)[^\n\r]{0,40}\b429\b|\b429\s+(?:too many requests|rate limit)", re.IGNORECASE), "HTTP_429_RATE_LIMIT"),
    (re.compile(r"(?:http(?: response)?(?: status)?|status(?: code)?)[^\n\r]{0,40}\b5\d\d\b|\b5(?:00|02|03|04)\s+(?:internal server error|bad gateway|service unavailable|gateway timeout)", re.IGNORECASE), "HTTP_5XX_SERVER_ERROR"),
    (re.compile(r"temporary failure in name resolution|name or service not known|no such host|server misbehaving|dns lookup failed", re.IGNORECASE), "TEMPORARY_DNS_FAILURE"),
    (re.compile(r"connection reset|connection aborted|connection refused|broken pipe|unexpected eof|tls handshake timeout|remote host terminated", re.IGNORECASE), "TEMPORARY_CONNECTION_FAILURE"),
    (re.compile(r"connect(?:ion)? timed out|read timed out|i/o timeout|network is unreachable|temporary network|transport.*temporar", re.IGNORECASE), "TEMPORARY_TRANSPORT_FAILURE"),
)


class _QuietMavenRepositoryHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        repositories: tuple[Path, ...],
        requests: list[dict[str, Any]],
        **kwargs: Any,
    ):
        self.repositories = repositories
        self.requests = requests
        super().__init__(*args, directory=str(repositories[0]), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return None

    def translate_path(self, path: str) -> str:
        relative = Path(urllib.parse.unquote(urllib.parse.urlsplit(path).path).lstrip("/"))
        if ".." in relative.parts:
            return str(self.repositories[0] / "__invalid_path__")
        for repository in self.repositories:
            candidate = repository / relative
            if candidate.exists():
                self.requests.append(
                    {"path": f"/{relative.as_posix()}", "resolvedPath": str(candidate), "found": True}
                )
                return str(candidate)
        self.requests.append(
            {
                "path": f"/{relative.as_posix()}",
                "resolvedPath": str(self.repositories[0] / relative),
                "found": False,
            }
        )
        return str(self.repositories[0] / relative)


@contextmanager
def _serve_maven_repository(
    repositories: tuple[Path, ...],
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    requests: list[dict[str, Any]] = []
    handler = partial(_QuietMavenRepositoryHandler, repositories=repositories, requests=requests)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="osv-maven-cache", daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _default_maven_repository() -> Path:
    maven_user_home = os.environ.get("MAVEN_USER_HOME")
    if maven_user_home:
        return Path(maven_user_home).expanduser() / "repository"
    return Path.home() / ".m2" / "repository"


def _verify_maven_scanner_compatibility(version_text: str, repository: Path) -> None:
    project_poms = tuple(
        path
        for path in repository.rglob("pom.xml")
        if not is_generated_evidence_path(path.relative_to(repository))
    )
    if len(project_poms) < 2:
        return
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", version_text)
    if not match:
        return
    version = tuple(int(value) for value in match.groups())
    if version < (2, 4, 0):
        raise ScannerPreflightError(
            "OSV Scanner 2.4.0 or newer is required for deterministic multi-module Maven scans; "
            f"detected {'.'.join(match.groups())}. Earlier releases can fail to resolve local reactor modules."
        )


def _scan_command(
    executable: str,
    staged: Path,
    data_source: str,
    maven_registry: str | None = None,
) -> list[str]:
    command = [
        executable,
        "scan",
        "source",
        "-r",
        str(staged),
        "--format",
        "json",
        f"--data-source={data_source}",
    ]
    if maven_registry:
        command.append(f"--maven-registry={maven_registry}")
    return command


def _classify_attempt(
    result: CommandResult,
    payload: Any,
    raw_stdout: str,
    raw_stderr: str,
) -> tuple[ScanOutcome, str | None]:
    combined_output = "\n".join((raw_stderr, raw_stdout))
    recognizable = _is_recognizable_report(payload)
    has_vulnerabilities = recognizable and any(True for _ in _iter_records(payload))
    if result.timed_out:
        return ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE, "SCANNER_TIMEOUT: OSV Scanner execution timed out"
    transient_output = raw_stderr if has_vulnerabilities else combined_output
    for pattern, reason in _TRANSIENT_FAILURE_PATTERNS:
        if pattern.search(transient_output):
            detail = raw_stderr.strip() or raw_stdout.strip() or "transient scanner infrastructure failure"
            return ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE, f"{reason}: {detail}"
    if result.blocked:
        return ScanOutcome.INCOMPLETE_FATAL_FAILURE, "SCANNER_EXECUTION_BLOCKED"
    if "no package sources found" in combined_output.lower():
        return ScanOutcome.INCOMPLETE_FATAL_FAILURE, "NO_PACKAGE_SOURCES: OSV Scanner found no package sources"
    if re.search(r"failed resolution|error during extraction", raw_stderr, re.IGNORECASE):
        detail = raw_stderr.strip() or "OSV Scanner could not resolve the complete dependency graph"
        return ScanOutcome.INCOMPLETE_FATAL_FAILURE, f"DEPENDENCY_RESOLUTION_FAILURE: {detail}"
    if not recognizable:
        detail = raw_stderr.strip() or "OSV Scanner did not produce a recognizable JSON report"
        return ScanOutcome.INCOMPLETE_FATAL_FAILURE, f"UNRECOGNIZABLE_REPORT: {detail}"
    if result.exit_code == 0:
        outcome = ScanOutcome.COMPLETED_WITH_FINDINGS if has_vulnerabilities else ScanOutcome.COMPLETED_CLEAN
        return outcome, None
    if result.exit_code == 1 and has_vulnerabilities:
        return ScanOutcome.COMPLETED_WITH_FINDINGS, None
    detail = raw_stderr.strip() or f"OSV Scanner exited with code {result.exit_code}"
    return ScanOutcome.INCOMPLETE_FATAL_FAILURE, f"NON_SUCCESSFUL_EXECUTION: {detail}"


def _parse_payload(raw_stdout: str) -> Any:
    try:
        return json.loads(raw_stdout or "{}")
    except json.JSONDecodeError:
        return None


def _failure_kind(reason: str | None) -> ScanFailureKind | None:
    if not reason:
        return None
    prefix = reason.split(":", 1)[0]
    if prefix == "SCANNER_TIMEOUT":
        return ScanFailureKind.TIMEOUT
    if prefix == "DEPENDENCY_RESOLUTION_FAILURE":
        return ScanFailureKind.DEPENDENCY_RESOLUTION
    if prefix in {
        "HTTP_429_RATE_LIMIT",
        "HTTP_5XX_SERVER_ERROR",
        "TEMPORARY_DNS_FAILURE",
        "TEMPORARY_CONNECTION_FAILURE",
        "TEMPORARY_TRANSPORT_FAILURE",
    }:
        return ScanFailureKind.NETWORK
    if prefix in {"UNRECOGNIZABLE_REPORT"}:
        return ScanFailureKind.INVALID_RESPONSE
    if prefix in {"SCANNER_EXECUTION_BLOCKED", "NO_PACKAGE_SOURCES"}:
        return ScanFailureKind.CONFIGURATION
    return ScanFailureKind.BACKEND


def _is_recognizable_report(payload: Any) -> bool:
    return isinstance(payload, dict) and (
        isinstance(payload.get("results"), list) or isinstance(payload.get("packages"), list)
    )


def _full_output(value: str, artifact: str | None) -> str:
    path = Path(artifact) if artifact else None
    if path and path.is_file():
        return path.read_text(encoding="utf-8")
    return value


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
