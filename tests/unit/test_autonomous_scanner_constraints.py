from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path

from autonomous_oss_remediation_agent.capabilities import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import ConstraintSpec, ExecutionBudgetConfig, RuntimePolicy, ScannerConfig
from autonomous_oss_remediation_agent.deterministic.constraints import ConstraintEvaluator
from autonomous_oss_remediation_agent.deterministic.osv import OsvScanner, ScannerPreflightError, normalize_osv_findings
from autonomous_oss_remediation_agent.models import CommandResult, ScanOutcome, ScannerHandle
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


class _ArtifactScannerRunner:
    def __init__(self, artifact: Path):
        self.artifact = artifact

    def run_argv(self, command, **kwargs):
        return CommandResult(
            list(command),
            str(kwargs.get("cwd")),
            1,
            stdout="[output truncated]",
            stdout_artifact=str(self.artifact),
        )


class _SequenceScannerRunner:
    def __init__(self, results, registry_probe=None):
        self.results = list(results)
        self.commands = []
        self.registry_probe = registry_probe
        self.registry_probe_content = None

    def run_argv(self, command, **kwargs):
        self.commands.append((list(command), kwargs))
        if self.registry_probe:
            registry_argument = next(value for value in command if value.startswith("--maven-registry="))
            registry_url = registry_argument.split("=", 1)[1]
            with urllib.request.urlopen(registry_url + self.registry_probe) as response:
                self.registry_probe_content = response.read().decode("utf-8")
        result = self.results.pop(0)
        return CommandResult(
            list(command),
            str(kwargs.get("cwd")),
            result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            blocked=result.blocked,
        )


class AutonomousScannerConstraintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.workspace.repository.mkdir()
        self.trace = TraceStore(self.workspace)
        self.maven_repository = Path(self.temp.name) / "m2" / "repository"
        self.maven_repository.mkdir(parents=True)
        budget = ExecutionBudget(ExecutionBudgetConfig(overall_timeout_seconds=60, command_timeout_seconds=10))
        policy = RuntimePolicy(trusted_repository=True, dedicated_runner=True, enable_autonomous_shell=True)
        self.runner = ProcessRunner(self.workspace, self.trace, budget, policy)

    def tearDown(self):
        self.temp.cleanup()

    def test_osv_normalization_is_alias_aware_and_filters_scope(self):
        payload = {
            "results": [
                {
                    "packages": [
                        {
                            "package": {"ecosystem": "Maven", "name": "org.example:demo", "version": "1.0"},
                            "vulnerabilities": [
                                {
                                    "id": "GHSA-demo",
                                    "aliases": ["CVE-2024-0001"],
                                    "database_specific": {"severity": "HIGH"},
                                    "affected": [{"ranges": [{"events": [{"fixed": "1.1"}]}]}],
                                },
                                {"id": "LOW-demo", "database_specific": {"severity": "LOW"}},
                            ],
                        }
                    ]
                }
            ]
        }
        findings = normalize_osv_findings(payload, ("HIGH",))
        self.assertEqual(1, len(findings))
        self.assertEqual("org.example:demo", findings[0].coordinate)
        self.assertIn("CVE-2024-0001", findings[0].identifiers)
        self.assertEqual(("1.1",), findings[0].fixed_versions)

    def test_osv_normalization_scores_cvss_vectors(self):
        payload = {
            "results": [{"packages": [{
                "package": {"ecosystem": "Maven", "name": "org.example:demo", "version": "1.0"},
                "vulnerabilities": [{
                    "id": "CVE-2024-9999",
                    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H"}],
                }],
            }]}]
        }
        findings = normalize_osv_findings(payload, ("CRITICAL",))
        self.assertEqual(1, len(findings))
        self.assertEqual("CRITICAL", findings[0].severity)

    def test_configured_scanner_preflight_records_integrity(self):
        scanner = OsvScanner(self.workspace, self.runner, self.trace)
        executable = Path(sys.executable)
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        handle = scanner.preflight(
            ScannerConfig(mode="configured", executable=str(executable), version=str(sys.version_info.major), sha256=digest)
        )
        self.assertEqual(digest, handle.sha256)
        self.assertFalse(handle.provisioned)
        self.assertEqual(handle, scanner.verify())

    def test_configured_scanner_missing_fails_closed(self):
        scanner = OsvScanner(self.workspace, self.runner, self.trace)
        with self.assertRaises(ScannerPreflightError):
            scanner.preflight(ScannerConfig(mode="configured", executable="definitely-not-installed-osv"))

    def test_scan_parses_full_output_artifact_when_return_tail_is_truncated(self):
        executable = self.workspace.tools / "osv-scanner.exe"
        executable.write_bytes(b"scanner")
        report = self.workspace.artifacts / "commands" / "full.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            '{"results":[{"packages":[{"package":{"ecosystem":"Maven","name":"org.example:demo","version":"1.0"},"vulnerabilities":[{"id":"CVE-2024-0001","database_specific":{"severity":"HIGH"}}]}]}]}',
            encoding="utf-8",
        )
        scanner = OsvScanner(self.workspace, _ArtifactScannerRunner(report), self.trace)
        scanner.handle = ScannerHandle(str(executable), "test", hashlib.sha256(b"scanner").hexdigest(), False)
        result = scanner.scan(self.workspace.repository, ("HIGH",), "large")
        self.assertTrue(result.succeeded)
        self.assertEqual(1, len(result.findings))

    def test_transient_429_retries_then_succeeds_clean(self):
        probe = self.maven_repository / "org" / "example" / "demo" / "1.0" / "demo-1.0.pom"
        probe.parent.mkdir(parents=True)
        probe.write_text("<project/>", encoding="utf-8")
        runner = _SequenceScannerRunner(
            [
                CommandResult(["scanner"], ".", 1, stdout='{"results": []}', stderr="HTTP 429 Too Many Requests"),
                CommandResult(["scanner"], ".", 0, stdout='{"results": []}'),
            ],
            registry_probe="org/example/demo/1.0/demo-1.0.pom",
        )
        sleeps = []
        scanner = self._scanner(runner, sleep=sleeps.append)

        report = scanner.scan(self.workspace.repository, ("HIGH",), "rate-limit-recovery")

        self.assertTrue(report.succeeded)
        self.assertEqual(ScanOutcome.COMPLETED_CLEAN, report.effective_outcome)
        self.assertEqual(2, len(report.attempts))
        self.assertEqual("HTTP_429_RATE_LIMIT", report.attempts[0]["failureReason"].split(":", 1)[0])
        self.assertTrue(report.attempts[0]["retryScheduled"])
        self.assertEqual([5.0], sleeps)
        self.assertTrue(Path(report.attempts[0]["stdoutArtifact"]).is_file())
        self.assertTrue(Path(report.attempts[0]["stderrArtifact"]).is_file())
        self.assertEqual('{"results": []}', Path(report.attempts[0]["rawReportPath"]).read_text(encoding="utf-8"))
        self.assertIn("--data-source=native", runner.commands[0][0])
        registry_argument = next(value for value in runner.commands[0][0] if value.startswith("--maven-registry="))
        self.assertTrue(registry_argument.startswith("--maven-registry=http://127.0.0.1:"))
        self.assertEqual("<project/>", runner.registry_probe_content)

    def test_missing_local_maven_repository_uses_deps_dev(self):
        runner = _SequenceScannerRunner([
            CommandResult(["scanner"], ".", 0, stdout='{"results": []}'),
        ])
        scanner = self._scanner(runner, maven_repository=Path(self.temp.name) / "missing-repository")

        report = scanner.scan(self.workspace.repository, ("HIGH",), "deps-dev-fallback")

        self.assertTrue(report.succeeded)
        self.assertIn("--data-source=deps.dev", runner.commands[0][0])
        self.assertFalse(any(value.startswith("--maven-registry=") for value in runner.commands[0][0]))

    def test_repeated_429_exhausts_retries_and_fails_closed(self):
        failure = CommandResult(["scanner"], ".", 1, stdout='{"results": []}', stderr="HTTP status 429")
        runner = _SequenceScannerRunner([failure, failure, failure])
        sleeps = []
        scanner = self._scanner(runner, sleep=sleeps.append)

        report = scanner.scan(self.workspace.repository, ("HIGH",), "rate-limit-exhausted")

        self.assertFalse(report.succeeded)
        self.assertEqual(ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE, report.effective_outcome)
        self.assertEqual(3, len(report.attempts))
        self.assertEqual([5.0, 15.0], sleeps)
        self.assertFalse(report.attempts[-1]["retryScheduled"])

    def test_empty_results_from_non_successful_execution_are_not_clean(self):
        runner = _SequenceScannerRunner([
            CommandResult(["scanner"], ".", 2, stdout='{"results": []}', stderr="invalid scanner configuration"),
        ])
        scanner = self._scanner(runner)

        report = scanner.scan(self.workspace.repository, ("HIGH",), "incomplete-empty")

        self.assertFalse(report.succeeded)
        self.assertEqual(ScanOutcome.INCOMPLETE_FATAL_FAILURE, report.effective_outcome)
        self.assertEqual((), report.findings)

    def test_normal_vulnerability_findings_remain_complete(self):
        payload = '{"results":[{"packages":[{"package":{"ecosystem":"Maven","name":"org.example:demo","version":"1.0"},"vulnerabilities":[{"id":"CVE-2024-0001","database_specific":{"severity":"HIGH"}}]}]}]}'
        runner = _SequenceScannerRunner([
            CommandResult(["scanner"], ".", 1, stdout=payload),
        ])
        scanner = self._scanner(runner)

        report = scanner.scan(self.workspace.repository, ("HIGH",), "findings")

        self.assertTrue(report.succeeded)
        self.assertEqual(ScanOutcome.COMPLETED_WITH_FINDINGS, report.effective_outcome)
        self.assertEqual(1, len(report.findings))
        self.assertEqual(1, len(report.attempts))

    def _scanner(self, runner, sleep=lambda _: None, maven_repository=None):
        executable = self.workspace.tools / "osv-scanner.exe"
        executable.write_bytes(b"scanner")
        scanner = OsvScanner(
            self.workspace,
            runner,
            self.trace,
            retry_backoff_seconds=(5.0, 15.0),
            sleep=sleep,
            maven_repository=maven_repository or self.maven_repository,
        )
        scanner.handle = ScannerHandle(str(executable), "test", hashlib.sha256(b"scanner").hexdigest(), False)
        return scanner

    @unittest.skipUnless(os.name == "nt", "Provisioning fixture uses a Windows cmd executable")
    def test_pinned_project_scoped_scanner_provisioning(self):
        source = Path(self.temp.name) / "scanner.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("release/osv-scanner.cmd", "@echo osv-scanner 9.9.9\r\n")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        scanner = OsvScanner(self.workspace, self.runner, self.trace)
        handle = scanner.preflight(
            ScannerConfig(
                mode="provision",
                download_url=source.as_uri(),
                sha256=digest,
                version="9.9.9",
                archive_member="release/osv-scanner.cmd",
            )
        )
        self.assertTrue(handle.provisioned)
        self.assertTrue(Path(handle.executable).is_file())

    def test_constraint_capture_and_suppression_detection(self):
        pom = self.workspace.repository / "pom.xml"
        pom.write_text(
            """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.2.0</version></parent>
  <properties><java.version>21</java.version></properties>
</project>""",
            encoding="utf-8",
        )
        evaluator = ConstraintEvaluator()
        baseline = evaluator.capture(self.workspace.repository)
        self.assertIn("java.version=21", baseline.java_versions)
        self.assertIn("parent=3.2.0", baseline.spring_boot_versions)
        suppression = self.workspace.repository / ".osv-scanner.toml"
        suppression.write_text("[[IgnoredVulns]]\nid='CVE-1'\n", encoding="utf-8")
        checks = evaluator.validate(
            self.workspace.repository,
            baseline,
            ConstraintSpec(),
            (".osv-scanner.toml",),
            "+ignore vulnerability CVE-1",
        )
        suppression_check = next(check for check in checks if check.name == "suppression_policy")
        self.assertFalse(suppression_check.passed)

    def test_explicit_protected_versions_are_enforced(self):
        (self.workspace.repository / "pom.xml").write_text(
            """<project><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.2.0</version></parent><properties><java.version>21</java.version></properties></project>""",
            encoding="utf-8",
        )
        evaluator = ConstraintEvaluator()
        baseline = evaluator.capture(self.workspace.repository)
        checks = evaluator.validate(
            self.workspace.repository,
            baseline,
            ConstraintSpec(protected_java_version="17", protected_spring_boot_version="3.1.0"),
            (),
            "",
        )
        self.assertFalse(next(check for check in checks if check.name == "protected_java_version").passed)
        self.assertFalse(next(check for check in checks if check.name == "protected_spring_boot_version").passed)


if __name__ == "__main__":
    unittest.main()
