from __future__ import annotations

import base64
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import requests

from ..capabilities.execution import ProcessRunner
from ..config import ScannerConfig, XrayScannerConfig
from ..models import CommandResult, ScanFailureKind, ScanOutcome, ScanReport, VulnerabilityFinding
from ..workspace import RunWorkspace, TraceStore
from .maven import MavenService
from .scanner import ScannerPreflightError


@dataclass(frozen=True)
class _XrayFailure:
    kind: ScanFailureKind
    code: str
    retryable: bool = False


_SUBMIT_MAX_ATTEMPTS = 2
_MAX_MALFORMED_POLL_RETRIES = 1


class XrayScanner:
    backend = "xray"

    def __init__(
        self,
        workspace: RunWorkspace,
        process_runner: ProcessRunner,
        trace: TraceStore,
        *,
        session: requests.Session | None = None,
        environment: Mapping[str, str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.workspace = workspace
        self.process_runner = process_runner
        self.trace = trace
        self.session = session or requests.Session()
        self.environment = environment if environment is not None else os.environ
        self.sleep = sleep
        self.monotonic = monotonic
        self.config: XrayScannerConfig | None = None

    def preflight(self, config: ScannerConfig) -> dict[str, Any]:
        if config.xray is None:
            raise ScannerPreflightError("scanner.xray is required for the Xray backend")
        if config.xray.ca_bundle and not Path(config.xray.ca_bundle).expanduser().is_file():
            raise ScannerPreflightError("Configured Xray CA bundle is unavailable")
        self.config = config.xray
        self._authorization()
        evidence = {
            "backend": self.backend,
            "url": self.config.url.rstrip("/"),
            "authMethod": self.config.auth_method,
            "verifyTls": self.config.verify_tls,
            "caBundle": self.config.ca_bundle,
        }
        self.trace.write_json("scanner/preflight.json", evidence)
        self.trace.append_event("scanner_preflight", **evidence)
        return evidence

    def scan(self, repository: Path, severity_scope: tuple[str, ...], label: str) -> ScanReport:
        config = self._verified_config()
        scans_dir = self.workspace.artifacts / "scans"
        scans_dir.mkdir(parents=True, exist_ok=True)
        raw_path = scans_dir / f"{label}.json"
        graph, command_result, dependency_path, graph_path, resolution_error = self._resolve_graph(
            repository,
            label,
        )
        base_evidence = {
            "dependencyTreePath": str(dependency_path),
            "componentGraphPath": str(graph_path) if graph_path else None,
        }
        if resolution_error:
            raw_path.write_text("{}\n", encoding="utf-8")
            return self._finish_report(
                label,
                ScanReport(
                    succeeded=False,
                    findings=(),
                    command_result=command_result,
                    raw_report_path=str(raw_path),
                    error=f"DEPENDENCY_RESOLUTION_FAILURE: {resolution_error}",
                    outcome=ScanOutcome.INCOMPLETE_FATAL_FAILURE,
                    backend=self.backend,
                    failure_kind=ScanFailureKind.DEPENDENCY_RESOLUTION,
                    evidence=base_evidence,
                ),
            )
        attempts: list[dict[str, Any]] = []
        headers, secrets = self._authorization()
        submit_response = None
        for submit_attempt in range(1, _SUBMIT_MAX_ATTEMPTS + 1):
            try:
                submit_response = self._request(
                    "POST",
                    f"{config.url.rstrip('/')}/api/v1/scan/graph",
                    headers,
                    graph,
                )
            except requests.ConnectTimeout:
                retry_scheduled = submit_attempt < _SUBMIT_MAX_ATTEMPTS
                attempts.append(
                    {
                        "phase": "submit",
                        "attemptNumber": submit_attempt,
                        "failure": "CONNECT_TIMEOUT",
                        "retryScheduled": retry_scheduled,
                    }
                )
                if retry_scheduled:
                    self.sleep(config.poll_interval_seconds)
                    continue
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    base_evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.TIMEOUT, "XRAY_CONNECT_TIMEOUT", True),
                )
            except requests.Timeout:
                attempts.append(
                    {
                        "phase": "submit",
                        "attemptNumber": submit_attempt,
                        "failure": "TIMEOUT",
                        "retryScheduled": False,
                    }
                )
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    base_evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.TIMEOUT, "XRAY_SUBMISSION_OUTCOME_UNKNOWN"),
                )
            except requests.RequestException:
                attempts.append(
                    {
                        "phase": "submit",
                        "attemptNumber": submit_attempt,
                        "failure": "NETWORK",
                        "retryScheduled": False,
                    }
                )
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    base_evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.NETWORK, "XRAY_SUBMISSION_OUTCOME_UNKNOWN"),
                )
            break
        if submit_response is None:
            raise AssertionError("Xray submission did not produce a response")
        attempts.append(
            {
                "phase": "submit",
                "attemptNumber": submit_attempt,
                "httpStatus": submit_response.status_code,
            }
        )
        submit_failure = _http_failure(submit_response.status_code)
        if submit_failure:
            raw_path.write_text(_redact(_response_text(submit_response), secrets), encoding="utf-8")
            if submit_failure.retryable:
                submit_failure = _XrayFailure(
                    submit_failure.kind,
                    "XRAY_SUBMISSION_OUTCOME_UNKNOWN",
                )
            return self._http_failure(
                label,
                command_result,
                raw_path,
                base_evidence,
                attempts,
                submit_failure,
            )
        if submit_response.status_code not in {200, 201}:
            raw_path.write_text(_redact(_response_text(submit_response), secrets), encoding="utf-8")
            return self._http_failure(
                label,
                command_result,
                raw_path,
                base_evidence,
                attempts,
                _XrayFailure(ScanFailureKind.BACKEND, "XRAY_SUBMIT_FAILURE"),
            )
        submit_payload = _response_json(submit_response)
        scan_id = str(submit_payload.get("scan_id") or "") if isinstance(submit_payload, dict) else ""
        if not scan_id:
            raw_path.write_text(_redact(_response_text(submit_response), secrets), encoding="utf-8")
            return self._http_failure(
                label,
                command_result,
                raw_path,
                base_evidence,
                attempts,
                _XrayFailure(ScanFailureKind.INVALID_RESPONSE, "XRAY_SUBMISSION_OUTCOME_UNKNOWN"),
            )
        evidence = {**base_evidence, "scanId": scan_id}
        deadline = self.monotonic() + config.poll_timeout_seconds
        malformed_poll_retries = 0
        while True:
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.TIMEOUT, "XRAY_POLL_TIMEOUT", True),
                )
            try:
                response = self._request(
                    "GET",
                    f"{config.url.rstrip('/')}/api/v1/scan/graph/{scan_id}?include_vulnerabilities=true",
                    headers,
                    timeout_seconds=remaining,
                )
            except requests.Timeout:
                attempts.append(
                    {
                        "phase": "poll",
                        "failure": "TIMEOUT",
                        "retryScheduled": False,
                    }
                )
                if self._wait_for_poll_retry(deadline):
                    attempts[-1]["retryScheduled"] = True
                    continue
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.TIMEOUT, "XRAY_POLL_TIMEOUT", True),
                )
            except requests.RequestException:
                attempts.append(
                    {
                        "phase": "poll",
                        "failure": "NETWORK",
                        "retryScheduled": False,
                    }
                )
                if self._wait_for_poll_retry(deadline):
                    attempts[-1]["retryScheduled"] = True
                    continue
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.TIMEOUT, "XRAY_POLL_TIMEOUT", True),
                )
            attempts.append({"phase": "poll", "httpStatus": response.status_code})
            poll_failure = _http_failure(response.status_code)
            if poll_failure:
                if poll_failure.retryable:
                    attempts[-1]["failure"] = poll_failure.code
                    attempts[-1]["retryScheduled"] = False
                    if self._wait_for_poll_retry(deadline, response):
                        attempts[-1]["retryScheduled"] = True
                        continue
                    return self._http_failure(
                        label,
                        command_result,
                        raw_path,
                        evidence,
                        attempts,
                        _XrayFailure(ScanFailureKind.TIMEOUT, "XRAY_POLL_TIMEOUT", True),
                    )
                raw_path.write_text(_redact(_response_text(response), secrets), encoding="utf-8")
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    poll_failure,
                )
            payload = _response_json(response) if response.status_code != 202 else None
            status = str(payload.get("status") or "").strip().lower() if isinstance(payload, dict) else ""
            if response.status_code == 202 or status in {"pending", "in_progress", "in progress"}:
                attempts[-1]["retryScheduled"] = False
                if self._wait_for_poll_retry(deadline, response):
                    attempts[-1]["retryScheduled"] = True
                    continue
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.TIMEOUT, "XRAY_POLL_TIMEOUT", True),
                )
            if response.status_code == 200 and payload is None:
                attempts[-1]["failure"] = "INVALID_JSON"
                retry_scheduled = malformed_poll_retries < _MAX_MALFORMED_POLL_RETRIES
                attempts[-1]["retryScheduled"] = retry_scheduled
                if retry_scheduled:
                    malformed_poll_retries += 1
                    if self._wait_for_poll_retry(deadline):
                        continue
                    return self._http_failure(
                        label,
                        command_result,
                        raw_path,
                        evidence,
                        attempts,
                        _XrayFailure(ScanFailureKind.TIMEOUT, "XRAY_POLL_TIMEOUT", True),
                    )
            raw_path.write_text(_redact(_response_text(response), secrets), encoding="utf-8")
            if response.status_code != 200 or not isinstance(payload, dict):
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.INVALID_RESPONSE, "XRAY_INVALID_RESPONSE"),
                )
            if status == "failed":
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.BACKEND, "XRAY_SCAN_FAILED"),
                )
            if status not in {"completed", "complete", "done", "success", "succeeded"}:
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.INVALID_RESPONSE, "XRAY_UNKNOWN_SCAN_STATUS"),
                )
            vulnerabilities = payload.get("vulnerabilities", [])
            if vulnerabilities is not None and not isinstance(vulnerabilities, list):
                return self._http_failure(
                    label,
                    command_result,
                    raw_path,
                    evidence,
                    attempts,
                    _XrayFailure(ScanFailureKind.INVALID_RESPONSE, "XRAY_INVALID_VULNERABILITIES"),
                )
            findings = tuple(normalize_xray_findings(payload, severity_scope))
            outcome = ScanOutcome.COMPLETED_WITH_FINDINGS if findings else ScanOutcome.COMPLETED_CLEAN
            return self._finish_report(
                label,
                ScanReport(
                    succeeded=True,
                    findings=findings,
                    command_result=command_result,
                    raw_report_path=str(raw_path),
                    outcome=outcome,
                    attempts=tuple(attempts),
                    backend=self.backend,
                    evidence=evidence,
                ),
            )

    def _verified_config(self) -> XrayScannerConfig:
        if self.config is None:
            raise ScannerPreflightError("Xray scanner preflight has not completed")
        return self.config

    def _authorization(self) -> tuple[dict[str, str], tuple[str, ...]]:
        config = self._verified_config()
        if config.auth_method == "access-token":
            token = self.environment.get("XRAY_ACCESS_TOKEN", "")
            if not token:
                raise ScannerPreflightError("XRAY_ACCESS_TOKEN is required for Xray access-token authentication")
            return {"Authorization": f"Bearer {token}"}, (token,)
        username = self.environment.get("XRAY_USERNAME", "")
        password = self.environment.get("XRAY_PASSWORD", "")
        if not username or not password:
            raise ScannerPreflightError("XRAY_USERNAME and XRAY_PASSWORD are required for Xray basic authentication")
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}, (username, password, encoded)

    def _request(
        self,
        method: str,
        url: str,
        authorization: dict[str, str],
        payload: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ):
        config = self._verified_config()
        headers = {**authorization, "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        verify: bool | str = str(Path(config.ca_bundle).expanduser()) if config.ca_bundle else config.verify_tls
        connect_timeout = config.connect_timeout_seconds
        read_timeout = config.read_timeout_seconds
        if timeout_seconds is not None:
            connect_timeout = max(0.001, min(connect_timeout, timeout_seconds))
            read_timeout = max(0.001, min(read_timeout, timeout_seconds))
        return self.session.request(
            method,
            url,
            headers=headers,
            json=payload,
            timeout=(connect_timeout, read_timeout),
            verify=verify,
        )

    def _wait_for_poll_retry(self, deadline: float, response: Any | None = None) -> bool:
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            return False
        delay = self._verified_config().poll_interval_seconds
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            delay = max(delay, retry_after)
        self.sleep(min(delay, remaining))
        return True

    def _resolve_graph(
        self,
        repository: Path,
        label: str,
    ) -> tuple[dict[str, Any] | None, CommandResult, Path, Path | None, str | None]:
        temp_path = self.workspace.temp / f"xray-{label}-dependencies.tgf"
        temp_path.unlink(missing_ok=True)
        dependency_path = self.workspace.artifacts / "scans" / f"{label}.dependencies.tgf"
        dependency_path.parent.mkdir(parents=True, exist_ok=True)
        executable = MavenService(repository, self.process_runner).maven_executable()
        command = [
            executable,
            "-q",
            "dependency:tree",
            "-DoutputType=tgf",
            "-DappendOutput=true",
            f"-DoutputFile={temp_path}",
        ]
        result = self.process_runner.run_argv(command, cwd=repository, source=f"xray_{label}_dependency_tree")
        if temp_path.is_file():
            shutil.copyfile(temp_path, dependency_path)
        else:
            dependency_path.write_text("", encoding="utf-8")
        if not result.succeeded:
            return None, result, dependency_path, None, "Maven dependency:tree did not complete successfully"
        if not temp_path.is_file():
            return None, result, dependency_path, None, "Maven dependency:tree did not produce TGF output"
        try:
            graph = build_xray_graph(temp_path.read_text(encoding="utf-8", errors="replace"))
        except ValueError as exc:
            return None, result, dependency_path, None, str(exc)
        graph_path = self.workspace.artifacts / "scans" / f"{label}.graph.json"
        graph_path.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return graph, result, dependency_path, graph_path, None

    def _http_failure(
        self,
        label: str,
        command_result: CommandResult,
        raw_path: Path,
        evidence: dict[str, Any],
        attempts: list[dict[str, Any]],
        failure: _XrayFailure,
    ) -> ScanReport:
        if not raw_path.exists():
            raw_path.write_text("{}\n", encoding="utf-8")
        outcome = (
            ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE
            if failure.retryable
            else ScanOutcome.INCOMPLETE_FATAL_FAILURE
        )
        return self._finish_report(
            label,
            ScanReport(
                succeeded=False,
                findings=(),
                command_result=command_result,
                raw_report_path=str(raw_path),
                error=f"{failure.kind.value}: {failure.code}",
                outcome=outcome,
                attempts=tuple(attempts),
                backend=self.backend,
                failure_kind=failure.kind,
                evidence=evidence,
            ),
        )

    def _finish_report(self, label: str, report: ScanReport) -> ScanReport:
        self.trace.write_json(f"scans/{label}.normalized.json", report.to_dict())
        self.trace.append_event(
            "vulnerability_scan",
            backend=self.backend,
            label=label,
            outcome=report.effective_outcome.value,
            failureKind=report.failure_kind.value if report.failure_kind else None,
        )
        return report


def build_xray_graph(tgf_text: str) -> dict[str, Any]:
    blocks = _parse_tgf_blocks(tgf_text)
    module_roots: list[dict[str, Any]] = []
    for nodes, edges in blocks:
        children: dict[str, list[str]] = {node_id: [] for node_id in nodes}
        targets: set[str] = set()
        for parent, child in edges:
            if parent not in nodes or child not in nodes:
                raise ValueError("Maven dependency tree contains an edge with an unknown node")
            children[parent].append(child)
            targets.add(child)
        roots = [node_id for node_id in nodes if node_id not in targets]
        if not roots:
            raise ValueError("Maven dependency tree contains no root node")
        for root in roots:
            module_roots.append(_graph_node(root, nodes, children, ()))
    if not module_roots:
        raise ValueError("No Maven dependency graph was parsed")
    return {"component_id": "root", "nodes": module_roots}


def normalize_xray_findings(
    raw_json: Any,
    severity_scope: Iterable[str],
) -> list[VulnerabilityFinding]:
    scope = {str(value).upper() for value in severity_scope}
    vulnerabilities = raw_json.get("vulnerabilities", []) if isinstance(raw_json, dict) else []
    if not isinstance(vulnerabilities, list):
        return []
    findings: list[VulnerabilityFinding] = []
    seen: set[tuple[tuple[str, ...], str, str]] = set()
    for vulnerability in vulnerabilities:
        if not isinstance(vulnerability, dict):
            continue
        severity = _xray_severity(vulnerability.get("severity"))
        if severity not in scope:
            continue
        issue_id = str(vulnerability.get("issue_id") or "")
        cves = _xray_cves(vulnerability.get("cves"))
        references = [str(value) for value in vulnerability.get("references", []) or [] if value]
        ghsas = []
        for reference in references:
            ghsas.extend(match.upper() for match in re.findall(r"GHSA-[0-9A-Z-]+", reference, re.IGNORECASE))
        primary = cves[0] if cves else issue_id or (ghsas[0] if ghsas else "UNKNOWN")
        aliases = _unique((*cves[1:], issue_id, *ghsas), exclude=primary)
        components = vulnerability.get("components")
        if not isinstance(components, dict):
            continue
        for component_id, component in components.items():
            group_id, artifact_id, version = _split_gav_component(str(component_id))
            if not group_id or not artifact_id or not version:
                continue
            component_data = component if isinstance(component, dict) else {}
            fixed_versions, expressions = _normalize_fixed_versions(component_data.get("fixed_versions"))
            identifiers = tuple(sorted({primary, *aliases}))
            package_name = f"{group_id}:{artifact_id}"
            key = (identifiers, package_name, version)
            if key in seen:
                continue
            seen.add(key)
            evidence: dict[str, Any] = {
                "componentId": str(component_id),
                "xrayIssueId": issue_id or None,
            }
            if expressions:
                evidence["fixedVersionExpressions"] = list(expressions)
            findings.append(
                VulnerabilityFinding(
                    vulnerability_id=primary,
                    aliases=aliases,
                    severity=severity,
                    group_id=group_id,
                    artifact_id=artifact_id,
                    package_name=package_name,
                    version=version,
                    fixed_versions=fixed_versions,
                    summary=str(vulnerability.get("summary") or ""),
                    backend_evidence=evidence,
                )
            )
    return findings


def _parse_tgf_blocks(tgf_text: str) -> list[tuple[dict[str, str], list[tuple[str, str]]]]:
    blocks: list[tuple[dict[str, str], list[tuple[str, str]]]] = []
    nodes: dict[str, str] = {}
    edges: list[tuple[str, str]] = []
    reading_edges = False

    def finish() -> None:
        nonlocal nodes, edges, reading_edges
        if nodes:
            blocks.append((nodes, edges))
        nodes = {}
        edges = []
        reading_edges = False

    for raw_line in tgf_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "#":
            reading_edges = True
            continue
        parts = line.split()
        is_edge = (
            reading_edges
            and len(parts) >= 2
            and _integer_token(parts[0])
            and _integer_token(parts[1])
        )
        if is_edge:
            edges.append((parts[0], parts[1]))
            continue
        if reading_edges:
            finish()
        node_parts = line.split(maxsplit=1)
        if len(node_parts) != 2 or not _integer_token(node_parts[0]):
            raise ValueError("Maven dependency tree contains malformed TGF node data")
        nodes[node_parts[0]] = _to_gav_component_id(node_parts[1])
    finish()
    return blocks


def _graph_node(
    node_id: str,
    nodes: dict[str, str],
    children: dict[str, list[str]],
    ancestors: tuple[str, ...],
) -> dict[str, Any]:
    if node_id in ancestors:
        raise ValueError("Maven dependency tree contains a cycle")
    return {
        "component_id": nodes[node_id],
        "nodes": [
            _graph_node(child, nodes, children, (*ancestors, node_id))
            for child in children[node_id]
        ],
    }


def _to_gav_component_id(coordinate: str) -> str:
    tokens = coordinate.strip().split(":")
    if len(tokens) < 4:
        raise ValueError(f"Unsupported Maven coordinate in dependency tree: {coordinate}")
    group_id = tokens[0]
    artifact_id = tokens[1]
    version = tokens[3] if len(tokens) <= 5 else tokens[-2]
    if not group_id or not artifact_id or not version:
        raise ValueError(f"Incomplete Maven coordinate in dependency tree: {coordinate}")
    return f"gav://{group_id}:{artifact_id}:{version}"


def _split_gav_component(component_id: str) -> tuple[str | None, str | None, str | None]:
    coordinate = component_id.removeprefix("gav://")
    tokens = coordinate.split(":")
    if len(tokens) != 3:
        return None, None, None
    return tokens[0] or None, tokens[1] or None, tokens[2] or None


def _normalize_fixed_versions(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, list):
        return (), ()
    concrete: set[str] = set()
    expressions: set[str] = set()
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        singleton = re.fullmatch(r"\[([^,\[\]()]+)\]", text)
        if singleton:
            concrete.add(singleton.group(1).strip())
        elif not any(character in text for character in "[](),"):
            concrete.add(text)
        else:
            expressions.add(text)
    return tuple(sorted(concrete)), tuple(sorted(expressions))


def _xray_cves(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return _unique(
        str(item.get("cve") or "").upper()
        for item in value
        if isinstance(item, dict) and item.get("cve")
    )


def _xray_severity(value: Any) -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    if normalized == "MODERATE":
        return "MEDIUM"
    return normalized if normalized in {"CRITICAL", "HIGH", "MEDIUM", "LOW"} else "UNKNOWN"


def _unique(values: Iterable[str], exclude: str = "") -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized.upper() == exclude.upper() or normalized.upper() in seen:
            continue
        seen.add(normalized.upper())
        result.append(normalized)
    return tuple(result)


def _integer_token(value: str) -> bool:
    return value.lstrip("-").isdigit()


def _http_failure(status_code: int) -> _XrayFailure | None:
    if status_code == 401:
        return _XrayFailure(ScanFailureKind.AUTHENTICATION, "XRAY_AUTHENTICATION_FAILED")
    if status_code == 403:
        return _XrayFailure(ScanFailureKind.AUTHORIZATION, "XRAY_AUTHORIZATION_FAILED")
    if status_code == 429:
        return _XrayFailure(ScanFailureKind.NETWORK, "XRAY_RATE_LIMITED", True)
    if status_code >= 500:
        return _XrayFailure(ScanFailureKind.BACKEND, "XRAY_BACKEND_UNAVAILABLE", True)
    if status_code >= 400:
        return _XrayFailure(ScanFailureKind.BACKEND, "XRAY_REQUEST_REJECTED")
    return None


def _retry_after_seconds(response: Any | None) -> float | None:
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("Retry-After")
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def _response_text(response: Any) -> str:
    return str(getattr(response, "text", "") or "")


def _response_json(response: Any) -> Any:
    try:
        return json.loads(_response_text(response))
    except (TypeError, json.JSONDecodeError):
        return None


def _redact(value: str, secrets: Iterable[str]) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted
