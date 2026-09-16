from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from autonomous_oss_remediation_agent.capabilities import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import ConstraintSpec, ExecutionBudgetConfig, RuntimePolicy, ScannerConfig
from autonomous_oss_remediation_agent.deterministic.constraints import ConstraintEvaluator
from autonomous_oss_remediation_agent.deterministic.osv import OsvScanner, ScannerPreflightError, normalize_osv_findings
from autonomous_oss_remediation_agent.models import CommandResult, ScannerHandle
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


class AutonomousScannerConstraintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.workspace.repository.mkdir()
        self.trace = TraceStore(self.workspace)
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
