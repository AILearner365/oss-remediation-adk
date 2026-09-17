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


if __name__ == "__main__":
    unittest.main()
