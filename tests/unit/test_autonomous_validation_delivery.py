from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autonomous_oss_remediation_agent.capabilities import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import (
    DeliveryConfig,
    ExecutionBudgetConfig,
    RemediationRequest,
    RuntimePolicy,
)
from autonomous_oss_remediation_agent.integrations.delivery import (
    CallableCredentialProvider,
    DeliveryContext,
    DeliveryCredential,
    EnvironmentCredentialProvider,
    GitHubRestDeliveryAdapter,
    ManualDeliveryAdapter,
    configured_delivery_adapter,
    digest_changed_paths,
)
from autonomous_oss_remediation_agent.models import (
    CommandResult,
    ConstraintBaseline,
    RepositoryBaseline,
    ScanReport,
    ValidationCheck,
    ValidationReport,
    VulnerabilityFinding,
)
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore
from autonomous_oss_remediation_agent.deterministic.validation import _is_likely_diagnostic_artifact
from autonomous_oss_remediation_agent.journal import CaptureStatus, DeliveryEligibility, ValidationStatus
from autonomous_oss_remediation_agent.orchestrator import (
    _delivery_eligibility,
    _remediation_outcome,
    _validation_status,
)


class _FakeResponse:
    status_code = 201

    def json(self):
        return {"html_url": "https://github.com/example/repo/pull/1", "number": 1, "draft": True}


class _FakeProcessRunner:
    def __init__(self):
        self.commands = []

    def run_argv(self, command, **kwargs):
        self.commands.append(list(command))
        stdout = "abc123\n" if command[:3] == ["git", "rev-parse", "HEAD"] else ""
        return CommandResult(list(command), str(kwargs.get("cwd", ".")), 0, stdout=stdout)


class AutonomousValidationDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.workspace.repository.mkdir()
        self.trace = TraceStore(self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def test_delivery_fails_closed_without_isolated_credentials(self):
        resolver_calls = []
        provider = CallableCredentialProvider(
            lambda: resolver_calls.append(True) or DeliveryCredential("secret"),
            isolated_from_agent=False,
            description="same identity credential store",
        )
        request = self._request()
        adapter = GitHubRestDeliveryAdapter(request.delivery, provider, _FakeProcessRunner(), self.trace)
        preflight = adapter.preflight(request)
        self.assertFalse(preflight.eligible)
        self.assertEqual([], resolver_calls)

    def test_manual_adapter_is_explicitly_ineligible(self):
        preflight = ManualDeliveryAdapter().preflight(self._request())
        self.assertFalse(preflight.eligible)
        self.assertEqual("manual", preflight.adapter)

    def test_environment_provider_prefers_gh_token(self):
        provider = EnvironmentCredentialProvider(
            {"GH_TOKEN": "gh-token", "GITHUB_TOKEN": "github-token"}
        )
        isolated, reason = provider.isolation_status()
        self.assertTrue(isolated)
        self.assertIn("GH_TOKEN", reason)
        self.assertEqual("gh-token", provider.resolve().token)

    def test_environment_provider_fails_closed_without_token(self):
        provider = EnvironmentCredentialProvider({})
        isolated, reason = provider.isolation_status()
        self.assertFalse(isolated)
        self.assertIn("GH_TOKEN", reason)
        with self.assertRaises(RuntimeError):
            provider.resolve()

    def test_configured_adapter_uses_environment_token_for_auto_github(self):
        request = self._request()
        adapter = configured_delivery_adapter(
            request,
            _FakeProcessRunner(),
            self.trace,
            {"GH_TOKEN": "secret"},
        )
        self.assertIsInstance(adapter, GitHubRestDeliveryAdapter)
        self.assertTrue(adapter.preflight(request).eligible)

    def test_configured_adapter_remains_manual_when_requested(self):
        request = RemediationRequest(
            repository_url="https://github.com/example/repo.git",
            delivery=DeliveryConfig(mode="manual", adapter="github-rest"),
        )
        adapter = configured_delivery_adapter(request, _FakeProcessRunner(), self.trace, {})
        self.assertIsInstance(adapter, ManualDeliveryAdapter)

    def test_github_rest_adapter_delivers_only_validated_digest(self):
        changed = self.workspace.repository / "pom.xml"
        changed.write_text("<project/>\n", encoding="utf-8")
        request = self._request()
        finding = _finding()
        command = CommandResult(["scanner"], str(self.workspace.repository), 0, stdout="{}")
        scan = ScanReport(True, (finding,), command, "baseline.json")
        baseline = RepositoryBaseline(
            str(self.workspace.repository),
            "1234567890",
            "main",
            request.repository_url,
            (command,),
            scan,
            ConstraintBaseline(),
            (finding,),
        )
        validation = ValidationReport(
            1,
            True,
            (ValidationCheck("all", True, "passed"),),
            ("pom.xml",),
            "diff.patch",
            digest_changed_paths(self.workspace.repository, ("pom.xml",)),
            scan=ScanReport(True, (), command, "final.json"),
        )
        provider = CallableCredentialProvider(
            lambda: DeliveryCredential("secret"),
            isolated_from_agent=True,
            description="separate delivery broker",
        )
        runner = _FakeProcessRunner()
        adapter = GitHubRestDeliveryAdapter(
            request.delivery,
            provider,
            runner,
            self.trace,
            http_post=lambda *args, **kwargs: _FakeResponse(),
        )
        adapter._push = lambda workspace, remote_url, branch, credential: CommandResult(
            ["git", "push", "origin", branch], str(workspace.repository), 0
        )
        result = adapter.deliver(DeliveryContext(request, self.workspace, baseline, validation, "updated dependency"))
        self.assertTrue(result.succeeded)
        self.assertEqual("https://github.com/example/repo/pull/1", result.pull_request_url)
        self.assertTrue(any(command[:3] == ["git", "reset", "--mixed"] for command in runner.commands))
        self.assertTrue(any(command[:2] == ["git", "commit"] or "commit" in command for command in runner.commands))

    def test_digest_mismatch_stops_before_credentials(self):
        path = self.workspace.repository / "pom.xml"
        path.write_text("one", encoding="utf-8")
        calls = []
        provider = CallableCredentialProvider(
            lambda: calls.append(True) or DeliveryCredential("secret"),
            isolated_from_agent=True,
            description="isolated",
        )
        request = self._request()
        finding = _finding()
        command = CommandResult(["scanner"], str(self.workspace.repository), 0)
        baseline = RepositoryBaseline(
            str(self.workspace.repository), "1234567", "main", request.repository_url, (command,),
            ScanReport(True, (finding,), command, "baseline.json"), ConstraintBaseline(), (finding,)
        )
        validation = ValidationReport(1, True, (), ("pom.xml",), "diff", "wrong")
        adapter = GitHubRestDeliveryAdapter(request.delivery, provider, _FakeProcessRunner(), self.trace)
        result = adapter.deliver(DeliveryContext(request, self.workspace, baseline, validation, ""))
        self.assertFalse(result.succeeded)
        self.assertEqual([], calls)

    def test_failed_validation_stops_before_credentials(self):
        path = self.workspace.repository / "pom.xml"
        path.write_text("one", encoding="utf-8")
        calls = []
        provider = CallableCredentialProvider(
            lambda: calls.append(True) or DeliveryCredential("secret"),
            isolated_from_agent=True,
            description="isolated",
        )
        request = self._request()
        finding = _finding()
        command = CommandResult(["scanner"], str(self.workspace.repository), 0)
        baseline = RepositoryBaseline(
            str(self.workspace.repository), "1234567", "main", request.repository_url, (command,),
            ScanReport(True, (finding,), command, "baseline.json"), ConstraintBaseline(), (finding,)
        )
        validation = ValidationReport(
            1,
            False,
            (ValidationCheck("build", False, "failed"),),
            ("pom.xml",),
            "diff",
            digest_changed_paths(self.workspace.repository, ("pom.xml",)),
        )
        adapter = GitHubRestDeliveryAdapter(request.delivery, provider, _FakeProcessRunner(), self.trace)
        result = adapter.deliver(DeliveryContext(request, self.workspace, baseline, validation, ""))
        self.assertFalse(result.succeeded)
        self.assertEqual([], calls)

    def test_dependency_tree_diagnostic_artifact_is_detected_conservatively(self):
        self.assertTrue(_is_likely_diagnostic_artifact("dependency_tree.txt"))
        self.assertTrue(_is_likely_diagnostic_artifact("tmp/dependency-tree.tgf"))
        self.assertFalse(_is_likely_diagnostic_artifact("src/main/resources/dependencies.txt"))
        self.assertFalse(_is_likely_diagnostic_artifact("dependency-tree-parser.py"))

    def test_passing_validation_requires_ready_outcome_for_automatic_delivery(self):
        report = _policy_report(passed=True, resolved=1, remaining=0)
        expected = {
            "READY_FOR_INDEPENDENT_VALIDATION": DeliveryEligibility.FULL_AUTOMATIC_DELIVERY,
            "PARTIALLY_REMEDIATED": DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
            "BLOCKED": DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
            "FAILED": DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
            "INCONCLUSIVE": DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
            "NO_CHANGE_REQUIRED": DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
        }
        for status, eligibility in expected.items():
            with self.subTest(status=status):
                self.assertEqual(
                    eligibility,
                    _delivery_eligibility(report, CaptureStatus.COMPLETE, status),
                )
        self.assertEqual(
            DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
            _delivery_eligibility(report, CaptureStatus.INCOMPLETE, "READY_FOR_INDEPENDENT_VALIDATION"),
        )

    def test_partial_requires_measurable_target_improvement(self):
        cases = (
            ("some removed and some remain", _policy_report(False, 1, 1), ValidationStatus.PARTIAL),
            ("no findings removed", _policy_report(False, 0, 2), ValidationStatus.FAILED),
            ("only unrelated file changed", _policy_report(False, 0, 1, changed=("README.md",)), ValidationStatus.FAILED),
            ("build passes but coverage unchanged", _policy_report(False, 0, 1), ValidationStatus.FAILED),
            ("all findings removed", _policy_report(True, 2, 0), ValidationStatus.PASSED),
        )
        for label, report, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(expected, _validation_status(report))
        partial = cases[0][1]
        self.assertEqual("PARTIALLY_REMEDIATED", _remediation_outcome(partial, "PARTIALLY_REMEDIATED").value)
        self.assertEqual(
            DeliveryEligibility.PARTIAL_MANUAL_REVIEW_DELIVERY,
            _delivery_eligibility(partial, CaptureStatus.COMPLETE, "PARTIALLY_REMEDIATED"),
        )

    def test_partial_rejects_every_non_resolution_check_failure(self):
        for failed_check in (
            "protected_java_version",
            "allowed_paths",
            "protected_paths",
            "build_test_startup",
        ):
            with self.subTest(failed_check=failed_check):
                report = _policy_report(False, 1, 1, failed_check=failed_check)
                self.assertEqual(ValidationStatus.FAILED, _validation_status(report))
                self.assertEqual(
                    "FAILED",
                    _remediation_outcome(report, "PARTIALLY_REMEDIATED").value,
                )
                self.assertEqual(
                    DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
                    _delivery_eligibility(
                        report,
                        CaptureStatus.COMPLETE,
                        "PARTIALLY_REMEDIATED",
                    ),
                )

    def _request(self):
        return RemediationRequest(
            repository_url="https://github.com/example/repo.git",
            workspace_parent=self.temp.name,
            runtime_policy=RuntimePolicy(True, True, True),
            delivery=DeliveryConfig(mode="auto", adapter="github-rest"),
        )


def _finding():
    return VulnerabilityFinding(
        "CVE-2024-0001", ("GHSA-demo",), "HIGH", "org.example", "demo", "org.example:demo", "1.0"
    )


def _policy_report(passed, resolved, remaining, changed=("pom.xml",), failed_check=None):
    checks = [
        ValidationCheck("baseline_ancestry", True, "passed"),
        ValidationCheck("git_change_evidence", True, "passed"),
        ValidationCheck("build_test_startup", True, "passed"),
        ValidationCheck("fresh_vulnerability_scan", True, "passed"),
        ValidationCheck("target_findings_improved", resolved > 0, "comparison"),
        ValidationCheck("target_findings_resolved", remaining == 0, "comparison"),
        ValidationCheck("no_new_prohibited_findings", True, "passed"),
        ValidationCheck("delivery_diff_hygiene", True, "passed"),
    ]
    if failed_check:
        existing = next((index for index, check in enumerate(checks) if check.name == failed_check), None)
        failed = ValidationCheck(failed_check, False, "failed")
        if existing is None:
            checks.append(failed)
        else:
            checks[existing] = failed
    resolved_findings = tuple({"vulnerabilityId": f"CVE-R-{index}"} for index in range(resolved))
    remaining_findings = tuple({"vulnerabilityId": f"CVE-U-{index}"} for index in range(remaining))
    return ValidationReport(
        cycle=1,
        passed=passed,
        checks=tuple(checks),
        changed_files=changed,
        diff_path="diff",
        tree_digest="digest",
        scan=ScanReport(True, (), CommandResult(["scan"], ".", 0), "scan.json"),
        delivery_eligible=True,
        resolved_target_findings=resolved_findings,
        remaining_target_findings=remaining_findings,
        target_comparison_complete=True,
    )


if __name__ == "__main__":
    unittest.main()
