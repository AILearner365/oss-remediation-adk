from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import requests

from autonomous_oss_remediation_agent.config import (
    RemediationRequest,
    ScannerConfig,
    XrayScannerConfig,
)
from autonomous_oss_remediation_agent.deterministic.osv import OsvScanner
from autonomous_oss_remediation_agent.deterministic.scanner import create_scanner
from autonomous_oss_remediation_agent.deterministic.xray import (
    XrayScanner,
    build_xray_graph,
    normalize_xray_findings,
)
from autonomous_oss_remediation_agent.models import CommandResult, ScanFailureKind, ScanOutcome
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


class _Response:
    def __init__(self, status_code: int, payload=None, text: str | None = None, headers=None):
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(payload if payload is not None else {})
        self.headers = headers or {}


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _TgfRunner:
    def __init__(self, tgf: str, exit_code: int = 0):
        self.tgf = tgf
        self.exit_code = exit_code
        self.commands = []

    def run_argv(self, command, **kwargs):
        self.commands.append((list(command), kwargs))
        output_argument = next(value for value in command if value.startswith("-DoutputFile="))
        output_path = Path(output_argument.split("=", 1)[1])
        if self.exit_code == 0:
            output_path.write_text(self.tgf, encoding="utf-8")
        return CommandResult(
            list(command),
            str(kwargs.get("cwd")),
            self.exit_code,
            stderr="dependency resolution failed" if self.exit_code else "",
        )


class _Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class AutonomousXrayScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.workspace.repository.mkdir()
        (self.workspace.repository / "pom.xml").write_text("<project/>", encoding="utf-8")
        self.trace = TraceStore(self.workspace)
        self.tgf = (
            "1 org.example:app:jar:1.0:\n"
            "2 org.example:library:jar:2.0:compile\n"
            "#\n"
            "1 2 compile\n"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_and_explicit_scanner_configuration(self):
        legacy = RemediationRequest.from_dict(
            {"repositoryUrl": "https://example.test/repo", "scanner": {"executable": "legacy-osv"}}
        )
        self.assertEqual("osv", legacy.scanner.backend)
        self.assertEqual("legacy-osv", legacy.scanner.executable)

        explicit = RemediationRequest.from_dict(
            {
                "repositoryUrl": "https://example.test/repo",
                "scanner": {"backend": "osv", "osv": {"executable": "nested-osv"}},
            }
        )
        self.assertEqual("osv", explicit.scanner.backend)
        self.assertEqual("nested-osv", explicit.scanner.executable)

        xray = RemediationRequest.from_dict(
            {
                "repositoryUrl": "https://example.test/repo",
                "scanner": {
                    "backend": "xray",
                    "xray": {"url": "https://jfrog.example.test/xray"},
                },
            }
        )
        self.assertEqual("xray", xray.scanner.backend)
        self.assertEqual("https://jfrog.example.test/xray", xray.scanner.xray.url)

    def test_invalid_backend_and_request_credentials_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported scanner backend"):
            RemediationRequest.from_dict(
                {"repositoryUrl": "https://example.test/repo", "scanner": {"backend": "other"}}
            )
        with self.assertRaisesRegex(ValueError, "credentials"):
            RemediationRequest.from_dict(
                {
                    "repositoryUrl": "https://example.test/repo",
                    "scanner": {
                        "backend": "xray",
                        "xray": {
                            "url": "https://jfrog.example.test/xray",
                            "accessToken": "must-not-be-stored",
                        },
                    },
                }
            )

    def test_selector_constructs_explicit_backends(self):
        osv = create_scanner(ScannerConfig(), self.workspace, _TgfRunner(self.tgf), self.trace)
        self.assertIsInstance(osv, OsvScanner)
        xray = create_scanner(
            self._config(),
            self.workspace,
            _TgfRunner(self.tgf),
            self.trace,
        )
        self.assertIsInstance(xray, XrayScanner)

    def test_graph_generation_supports_multiple_reactor_modules(self):
        graph = build_xray_graph(
            self.tgf
            + "3 org.example:service:jar:1.0:\n"
            + "4 org.example:classified:jar:tests:3.0:test\n"
            + "#\n"
            + "3 4 test\n"
        )
        self.assertEqual("root", graph["component_id"])
        self.assertEqual(2, len(graph["nodes"]))
        self.assertEqual("gav://org.example:app:1.0", graph["nodes"][0]["component_id"])
        self.assertEqual(
            "gav://org.example:classified:3.0",
            graph["nodes"][1]["nodes"][0]["component_id"],
        )

    def test_xray_normalization_preserves_ambiguous_fixed_range_as_evidence(self):
        findings = normalize_xray_findings(
            {
                "vulnerabilities": [
                    {
                        "severity": "High",
                        "issue_id": "XRAY-123",
                        "summary": "demo",
                        "cves": [{"cve": "CVE-2026-0001"}, {"cve": "CVE-2026-0002"}],
                        "references": ["https://github.com/advisories/GHSA-AAAA-BBBB-CCCC"],
                        "components": {
                            "gav://org.example:library:2.0": {
                                "fixed_versions": ["[2.1.0]", "[2.2.0,3.0.0)"],
                            }
                        },
                    }
                ]
            },
            ("HIGH",),
        )
        self.assertEqual(1, len(findings))
        finding = findings[0]
        self.assertEqual("CVE-2026-0001", finding.vulnerability_id)
        self.assertIn("XRAY-123", finding.aliases)
        self.assertIn("GHSA-AAAA-BBBB-CCCC", finding.aliases)
        self.assertEqual(("2.1.0",), finding.fixed_versions)
        self.assertEqual(
            ["[2.2.0,3.0.0)"],
            finding.backend_evidence["fixedVersionExpressions"],
        )

    def test_clean_and_findings_results_are_successful(self):
        clean = self._scan([_Response(200, {"scan_id": "clean"}), _Response(200, {"status": "completed"})])
        self.assertTrue(clean.succeeded)
        self.assertEqual(ScanOutcome.COMPLETED_CLEAN, clean.effective_outcome)

        payload = {
            "status": "completed",
            "vulnerabilities": [
                {
                    "severity": "High",
                    "issue_id": "XRAY-123",
                    "cves": [{"cve": "CVE-2026-0001"}],
                    "components": {"gav://org.example:library:2.0": {}},
                }
            ],
        }
        findings = self._scan([_Response(201, {"scan_id": "findings"}), _Response(200, payload)], label="findings")
        self.assertTrue(findings.succeeded)
        self.assertEqual(ScanOutcome.COMPLETED_WITH_FINDINGS, findings.effective_outcome)
        self.assertEqual(1, len(findings.findings))
        self.assertEqual((), findings.findings[0].fixed_versions)

    def test_http_failures_are_distinct_and_never_clean(self):
        cases = (
            (401, ScanFailureKind.AUTHENTICATION),
            (403, ScanFailureKind.AUTHORIZATION),
            (429, ScanFailureKind.NETWORK),
            (500, ScanFailureKind.BACKEND),
        )
        for index, (status, kind) in enumerate(cases):
            with self.subTest(status=status):
                report = self._scan([_Response(status, {"error": "failure"})], label=f"http-{index}")
                self.assertFalse(report.succeeded)
                self.assertEqual((), report.findings)
                self.assertEqual(kind, report.failure_kind)
                self.assertNotEqual(ScanOutcome.COMPLETED_CLEAN, report.effective_outcome)

    def test_submission_retries_only_confirmed_connect_timeout(self):
        scanner, session = self._scanner(
            [
                requests.ConnectTimeout("connect failed"),
                _Response(200, {"scan_id": "retry"}),
                _Response(200, {"status": "completed"}),
            ]
        )
        report = scanner.scan(self.workspace.repository, ("HIGH",), "connect-retry")

        self.assertTrue(report.succeeded)
        self.assertEqual(["POST", "POST", "GET"], [request[0] for request in session.requests])
        self.assertTrue(report.attempts[0]["retryScheduled"])

        scanner, session = self._scanner([requests.ReadTimeout("outcome unknown")])
        report = scanner.scan(self.workspace.repository, ("HIGH",), "read-timeout")
        self.assertFalse(report.succeeded)
        self.assertEqual(ScanOutcome.INCOMPLETE_FATAL_FAILURE, report.effective_outcome)
        self.assertIn("XRAY_SUBMISSION_OUTCOME_UNKNOWN", report.error)
        self.assertEqual(["POST"], [request[0] for request in session.requests])

        scanner, session = self._scanner([requests.ConnectionError("outcome unknown")])
        report = scanner.scan(self.workspace.repository, ("HIGH",), "connection-error")
        self.assertFalse(report.succeeded)
        self.assertEqual(ScanOutcome.INCOMPLETE_FATAL_FAILURE, report.effective_outcome)
        self.assertIn("XRAY_SUBMISSION_OUTCOME_UNKNOWN", report.error)
        self.assertEqual(["POST"], [request[0] for request in session.requests])

    def test_submission_does_not_retry_ambiguous_http_failures(self):
        for index, status in enumerate((429, 500, 502, 503)):
            with self.subTest(status=status):
                scanner, session = self._scanner([_Response(status, {"error": "failure"})])
                report = scanner.scan(self.workspace.repository, ("HIGH",), f"submit-{index}")
                self.assertFalse(report.succeeded)
                self.assertEqual(ScanOutcome.INCOMPLETE_FATAL_FAILURE, report.effective_outcome)
                self.assertIn("XRAY_SUBMISSION_OUTCOME_UNKNOWN", report.error)
                self.assertEqual(["POST"], [request[0] for request in session.requests])

    def test_poll_transient_failures_retry_without_resubmission(self):
        transient_responses = (
            _Response(429, {"error": "rate limited"}),
            _Response(500, {"error": "backend"}),
            _Response(502, {"error": "gateway"}),
            _Response(503, {"error": "unavailable"}),
            requests.Timeout("poll timeout"),
            requests.ConnectionError("poll connection failed"),
        )
        for index, transient in enumerate(transient_responses):
            with self.subTest(transient=type(transient).__name__, index=index):
                scanner, session = self._scanner(
                    [
                        _Response(200, {"scan_id": f"poll-{index}"}),
                        transient,
                        _Response(200, {"status": "completed"}),
                    ]
                )
                report = scanner.scan(self.workspace.repository, ("HIGH",), f"poll-{index}")
                self.assertTrue(report.succeeded)
                self.assertEqual(["POST", "GET", "GET"], [request[0] for request in session.requests])

    def test_poll_authentication_and_authorization_failures_are_not_retried(self):
        cases = (
            (401, ScanFailureKind.AUTHENTICATION),
            (403, ScanFailureKind.AUTHORIZATION),
        )
        for status, failure_kind in cases:
            with self.subTest(status=status):
                scanner, session = self._scanner(
                    [
                        _Response(200, {"scan_id": f"auth-{status}"}),
                        _Response(status, {"error": "rejected"}),
                        _Response(200, {"status": "completed"}),
                    ]
                )
                report = scanner.scan(self.workspace.repository, ("HIGH",), f"poll-auth-{status}")
                self.assertEqual(failure_kind, report.failure_kind)
                self.assertEqual(["POST", "GET"], [request[0] for request in session.requests])

    def test_timeout_malformed_json_and_missing_scan_id_fail_closed(self):
        timeout = self._scan([requests.Timeout("secret-free")], label="request-timeout")
        self.assertEqual(ScanFailureKind.TIMEOUT, timeout.failure_kind)

        malformed = self._scan(
            [
                _Response(200, {"scan_id": "bad"}),
                _Response(200, text="not-json"),
                _Response(200, text="still-not-json"),
            ],
            label="malformed",
        )
        self.assertEqual(ScanFailureKind.INVALID_RESPONSE, malformed.failure_kind)

        missing = self._scan([_Response(200, {"unexpected": True})], label="missing-id")
        self.assertEqual(ScanFailureKind.INVALID_RESPONSE, missing.failure_kind)
        self.assertIn("XRAY_SUBMISSION_OUTCOME_UNKNOWN", missing.error)

        network = self._scan([requests.ConnectionError("connection failed")], label="network")
        self.assertEqual(ScanFailureKind.NETWORK, network.failure_kind)

        backend = self._scan(
            [_Response(200, {"scan_id": "failed"}), _Response(200, {"status": "failed"})],
            label="backend-failed",
        )
        self.assertEqual(ScanFailureKind.BACKEND, backend.failure_kind)

    def test_malformed_poll_json_can_recover_without_resubmission(self):
        scanner, session = self._scanner(
            [
                _Response(200, {"scan_id": "malformed"}),
                _Response(200, text="not-json"),
                _Response(200, {"status": "completed"}),
            ]
        )
        report = scanner.scan(self.workspace.repository, ("HIGH",), "malformed-recovery")
        self.assertTrue(report.succeeded)
        self.assertEqual(["POST", "GET", "GET"], [request[0] for request in session.requests])

    def test_basic_auth_is_used_only_when_explicitly_configured(self):
        session = _Session([_Response(401)])
        config = ScannerConfig(
            backend="xray",
            xray=XrayScannerConfig(
                url="https://jfrog.example.test/xray",
                auth_method="basic",
                poll_interval_seconds=0.001,
                poll_timeout_seconds=1,
            ),
        )
        scanner = XrayScanner(
            self.workspace,
            _TgfRunner(self.tgf),
            self.trace,
            session=session,
            environment={"XRAY_USERNAME": "user", "XRAY_PASSWORD": "password"},
        )
        scanner.preflight(config)
        scanner.scan(self.workspace.repository, ("HIGH",), "basic")
        authorization = session.requests[0][2]["headers"]["Authorization"]
        self.assertTrue(authorization.startswith("Basic "))
        self.assertNotIn("user", authorization)
        self.assertNotIn("password", authorization)

    def test_poll_timeout_fails_closed(self):
        values = iter((0.0, 0.0, 2.0))
        report = self._scan(
            [_Response(200, {"scan_id": "pending"}), _Response(202)],
            label="poll-timeout",
            monotonic=lambda: next(values),
        )
        self.assertEqual(ScanFailureKind.TIMEOUT, report.failure_kind)
        self.assertEqual(ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE, report.effective_outcome)

    def test_retry_after_is_capped_by_poll_deadline(self):
        clock = _Clock()
        scanner, session = self._scanner(
            [
                _Response(200, {"scan_id": "rate-limited"}),
                _Response(429, {"error": "slow down"}, headers={"Retry-After": "10"}),
            ],
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        report = scanner.scan(self.workspace.repository, ("HIGH",), "retry-after")
        self.assertEqual(ScanFailureKind.TIMEOUT, report.failure_kind)
        self.assertEqual(ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE, report.effective_outcome)
        self.assertEqual([1], clock.sleeps)
        self.assertEqual((1, 1), session.requests[1][2]["timeout"])

    def test_dependency_resolution_failure_stops_before_http(self):
        session = _Session([])
        scanner = XrayScanner(
            self.workspace,
            _TgfRunner(self.tgf, exit_code=1),
            self.trace,
            session=session,
            environment={"XRAY_ACCESS_TOKEN": "token"},
        )
        scanner.preflight(self._config())
        report = scanner.scan(self.workspace.repository, ("HIGH",), "resolution")
        self.assertFalse(report.succeeded)
        self.assertEqual(ScanFailureKind.DEPENDENCY_RESOLUTION, report.failure_kind)
        self.assertEqual([], session.requests)

    def test_credentials_are_used_only_in_http_and_redacted_from_artifacts(self):
        token = "top-secret-xray-token"
        session = _Session([_Response(401, {"error": token})])
        scanner = XrayScanner(
            self.workspace,
            _TgfRunner(self.tgf),
            self.trace,
            session=session,
            environment={"XRAY_ACCESS_TOKEN": token},
        )
        scanner.preflight(self._config())
        report = scanner.scan(self.workspace.repository, ("HIGH",), "redaction")
        self.assertEqual(f"Bearer {token}", session.requests[0][2]["headers"]["Authorization"])
        self.assertNotIn(token, json.dumps(report.to_dict()))
        for artifact in self.workspace.artifacts.rglob("*"):
            if artifact.is_file():
                self.assertNotIn(token, artifact.read_text(encoding="utf-8", errors="replace"))

    def _config(self) -> ScannerConfig:
        return ScannerConfig(
            backend="xray",
            xray=XrayScannerConfig(
                url="https://jfrog.example.test/xray",
                poll_interval_seconds=0.001,
                poll_timeout_seconds=1,
            ),
        )

    def _scanner(self, responses, *, monotonic=None, sleep=None):
        session = _Session(responses)
        scanner = XrayScanner(
            self.workspace,
            _TgfRunner(self.tgf),
            self.trace,
            session=session,
            environment={"XRAY_ACCESS_TOKEN": "token"},
            sleep=sleep or (lambda _: None),
            monotonic=monotonic or (lambda: 0.0),
        )
        scanner.preflight(self._config())
        return scanner, session

    def _scan(self, responses, *, label="scan", monotonic=None):
        scanner, _ = self._scanner(responses, monotonic=monotonic)
        return scanner.scan(self.workspace.repository, ("HIGH",), label)


if __name__ == "__main__":
    unittest.main()
