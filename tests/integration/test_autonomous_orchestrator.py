from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
import hashlib
from pathlib import Path

from autonomous_oss_remediation_agent.config import (
    DeliveryConfig,
    ExecutionBudgetConfig,
    RemediationRequest,
    RuntimePolicy,
    ScannerConfig,
)
from autonomous_oss_remediation_agent.models import (
    AgentTurnResult,
    CommandResult,
    DeliveryPreflight,
    DeliveryResult,
    Outcome,
    ScanReport,
    ScannerHandle,
    VulnerabilityFinding,
)
from autonomous_oss_remediation_agent.deterministic.osv import OsvScanner
from autonomous_oss_remediation_agent.orchestrator import AutonomousRemediationOrchestrator


class _FixtureScanner:
    def __init__(self, workspace, process_runner, trace):
        self.workspace = workspace

    def preflight(self, config):
        return ScannerHandle("fake-osv", "fake 1.0", "0" * 64, False)

    def scan(self, repository, severity_scope, label):
        pom = (Path(repository) / "pom.xml").read_text(encoding="utf-8")
        findings = () if "<demo.version>2.0</demo.version>" in pom else (_finding(),)
        raw = self.workspace.artifacts / "scans" / f"{label}.json"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("{}", encoding="utf-8")
        return ScanReport(
            True,
            findings,
            CommandResult(["fake-osv"], str(repository), 0, stdout="{}"),
            str(raw),
        )


class _RetryingFixtureScanner(OsvScanner):
    def __init__(self, workspace, process_runner, trace):
        super().__init__(workspace, process_runner, trace, sleep=lambda _: None)
        self.execution_labels = []

    def preflight(self, config):
        executable = self.workspace.tools / "fake-osv"
        executable.write_bytes(b"scanner")
        self.handle = ScannerHandle(
            str(executable),
            "fake 1.0",
            hashlib.sha256(b"scanner").hexdigest(),
            False,
        )
        return self.handle

    def _execute_scan(self, handle, repository, label, attempt_number, registry_roots):
        self.execution_labels.append((label, attempt_number))
        if label == "baseline":
            payload = {
                "results": [{
                    "packages": [{
                        "package": {"ecosystem": "Maven", "name": "org.example:demo", "version": "1.0"},
                        "vulnerabilities": [{
                            "id": "CVE-2024-0001",
                            "database_specific": {"severity": "HIGH"},
                        }],
                    }],
                }],
            }
            return CommandResult([handle.executable], str(repository), 1, stdout=json.dumps(payload))
        if attempt_number == 1:
            return CommandResult(
                [handle.executable],
                str(repository),
                1,
                stdout='{"results": []}',
                stderr="HTTP 429 Too Many Requests",
            )
        return CommandResult([handle.executable], str(repository), 0, stdout='{"results": []}')


class _ScriptedAgentSession:
    def __init__(self, capabilities, edits):
        self.capabilities = capabilities
        self.edits = edits
        self.messages = []
        self.closed = False

    async def run_turn(self, message):
        self.messages.append(message)
        if self.edits:
            old, new = self.edits.pop(0)
            self.capabilities.edit_workspace_text(
                "replace",
                "pom.xml",
                old_text=f"<demo.version>{old}</demo.version>",
                new_text=f"<demo.version>{new}</demo.version>",
            )
        return AgentTurnResult(f"cycle {len(self.messages)} complete")

    async def close(self):
        self.closed = True


class _FailingAgentSession:
    async def run_turn(self, message):
        raise RuntimeError("model service unavailable")

    async def close(self):
        return None


class _CommittingAgentSession:
    def __init__(self, capabilities):
        self.capabilities = capabilities

    async def run_turn(self, message):
        self.capabilities.edit_workspace_text(
            "replace",
            "pom.xml",
            old_text="<demo.version>1.0</demo.version>",
            new_text="<demo.version>2.0</demo.version>",
        )
        result = self.capabilities.run_workspace_shell(
            "git add pom.xml; git -c user.name=Agent -c user.email=agent@example.test commit -m investigation"
        )
        return AgentTurnResult(f"local investigation commit: {result.get('exitCode')}")

    async def close(self):
        return None


class _RecordingDeliveryAdapter:
    name = "recording"

    def __init__(self):
        self.contexts = []

    def preflight(self, request):
        return DeliveryPreflight(True, self.name, "test adapter eligible")

    def deliver(self, context):
        self.contexts.append(context)
        return DeliveryResult(True, "SUCCESS", branch="test", commit="abc", pull_request_url="https://example.test/pr/1")


class AutonomousOrchestratorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        (self.source / "pom.xml").write_text(
            "<project><properties><demo.version>1.0</demo.version></properties></project>\n",
            encoding="utf-8",
        )
        _git(self.source, "init", "-b", "main")
        _git(self.source, "config", "user.name", "Test")
        _git(self.source, "config", "user.email", "test@example.com")
        _git(self.source, "add", "pom.xml")
        _git(self.source, "commit", "-m", "baseline")

    def tearDown(self):
        self.temp.cleanup()

    def test_same_agent_session_continues_after_validation_failure(self):
        sessions = []

        def factory(capabilities, model):
            session = _ScriptedAgentSession(capabilities, [("1.0", "1.5"), ("1.5", "2.0")])
            sessions.append(session)
            return session

        request = self._request(max_cycles=3)
        result = AutonomousRemediationOrchestrator(
            request,
            agent_session_factory=factory,
            scanner_factory=_FixtureScanner,
        ).run()
        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertEqual("VALIDATED_MANUAL_DELIVERY_REQUIRED", result.delivery.status)
        self.assertTrue(result.validation.passed)
        self.assertEqual(2, result.cycles_completed)
        self.assertEqual(1, len(sessions))
        self.assertEqual(2, len(sessions[0].messages))
        self.assertIn("Deterministic validation failed", sessions[0].messages[1])
        self.assertTrue(sessions[0].closed)
        self.assertTrue((Path(result.workspace_root) / "artifacts" / "final-result.json").is_file())
        push_url = _git(Path(result.workspace_root) / "repository", "remote", "get-url", "--push", "origin")
        self.assertEqual("disabled://autonomous-remediation-delivery-only", push_url.strip())
        events = [json.loads(line) for line in (Path(result.workspace_root) / "artifacts" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        command_sources = {event.get("source") for event in events if event.get("type") == "command"}
        self.assertIn("baseline_test_1", command_sources)
        self.assertIn("baseline_startup_1", command_sources)

    def test_scanner_retry_stays_inside_one_remediation_cycle(self):
        sessions = []
        scanners = []

        def agent_factory(capabilities, model):
            session = _ScriptedAgentSession(capabilities, [("1.0", "2.0")])
            sessions.append(session)
            return session

        def scanner_factory(workspace, process_runner, trace):
            scanner = _RetryingFixtureScanner(workspace, process_runner, trace)
            scanners.append(scanner)
            return scanner

        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=agent_factory,
            scanner_factory=scanner_factory,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertEqual(1, result.cycles_completed)
        self.assertEqual(1, len(sessions[0].messages))
        self.assertEqual(
            [("baseline", 1), ("validation-cycle-1", 1), ("validation-cycle-1", 2)],
            scanners[0].execution_labels,
        )

    def test_cycle_budget_exhaustion_is_truthful(self):
        request = self._request(max_cycles=1)
        result = AutonomousRemediationOrchestrator(
            request,
            agent_session_factory=lambda capabilities, model: _ScriptedAgentSession(capabilities, []),
            scanner_factory=_FixtureScanner,
        ).run()
        self.assertEqual(Outcome.EXECUTION_LIMIT_REACHED, result.outcome)
        self.assertFalse(result.validation.passed)
        self.assertEqual(1, result.cycles_completed)

    def test_delivery_factory_runs_only_after_validation_success(self):
        adapter = _RecordingDeliveryAdapter()
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=3),
            agent_session_factory=lambda capabilities, model: _ScriptedAgentSession(
                capabilities, [("1.0", "1.5"), ("1.5", "2.0")]
            ),
            scanner_factory=_FixtureScanner,
            delivery_adapter_factory=lambda workspace, process_runner, trace: adapter,
        ).run()
        self.assertEqual(Outcome.SUCCESS, result.outcome)
        self.assertEqual(1, len(adapter.contexts))
        self.assertEqual(2, adapter.contexts[0].validation.cycle)

    def test_unapproved_runtime_boundary_stops_before_agent(self):
        invoked = []
        request = RemediationRequest(
            repository_url=str(self.source),
            workspace_parent=str(Path(self.temp.name) / "runs"),
            build_commands=("git status --porcelain",),
            runtime_policy=RuntimePolicy(),
        )
        result = AutonomousRemediationOrchestrator(
            request,
            agent_session_factory=lambda capabilities, model: invoked.append(True),
            scanner_factory=_FixtureScanner,
        ).run()
        self.assertEqual(Outcome.BASELINE_FAILURE, result.outcome)
        self.assertIn("RUNTIME_BOUNDARY_NOT_APPROVED", result.reason)
        self.assertEqual([], invoked)

    def test_agent_runtime_failure_is_not_mislabeled_as_budget_exhaustion(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=lambda capabilities, model: _FailingAgentSession(),
            scanner_factory=_FixtureScanner,
        ).run()
        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertIn("AGENT_RUNTIME_FAILURE", result.reason)

    def test_validation_includes_agent_local_commits_since_baseline(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _CommittingAgentSession(capabilities),
            scanner_factory=_FixtureScanner,
        ).run()
        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertTrue(result.validation.passed)
        self.assertIn("pom.xml", result.validation.changed_files)

    def _request(self, max_cycles):
        return RemediationRequest(
            repository_url=str(self.source),
            reference_branch="main",
            workspace_parent=str(Path(self.temp.name) / "runs"),
            vulnerability_ids=("CVE-2024-0001",),
            severity_scope=("HIGH",),
            build_commands=("git status --porcelain",),
            test_commands=("git status --porcelain",),
            startup_commands=("git status --porcelain",),
            budget=ExecutionBudgetConfig(
                max_cycles=max_cycles,
                max_tool_calls=10,
                command_timeout_seconds=20,
                overall_timeout_seconds=120,
            ),
            runtime_policy=RuntimePolicy(True, True, True),
            scanner=ScannerConfig(executable="fake"),
            delivery=DeliveryConfig(mode="manual"),
        )


def _finding():
    return VulnerabilityFinding(
        "CVE-2024-0001",
        ("GHSA-demo",),
        "HIGH",
        "org.example",
        "demo",
        "org.example:demo",
        "1.0",
        ("2.0",),
    )


def _git(cwd: Path, *args: str):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


if __name__ == "__main__":
    unittest.main()
