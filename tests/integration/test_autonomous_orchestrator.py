from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
import hashlib
import re
from dataclasses import replace
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
    ScanFailureKind,
    ScanOutcome,
    ScanReport,
    ScannerHandle,
    VulnerabilityFinding,
)
from autonomous_oss_remediation_agent.deterministic.osv import OsvScanner
from autonomous_oss_remediation_agent.deterministic.scanner import ScannerPreflightError
from autonomous_oss_remediation_agent.journal import JournalPhase
from autonomous_oss_remediation_agent.orchestrator import AutonomousRemediationOrchestrator


class _FixtureScanner:
    def __init__(self, config, workspace, process_runner, trace):
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


class _CleanAfterBaselineScanner(_FixtureScanner):
    def scan(self, repository, severity_scope, label):
        report = super().scan(repository, severity_scope, label)
        if label == "baseline":
            return report
        return ScanReport(True, (), report.command_result, report.raw_report_path)


class _TwoFindingScanner(_FixtureScanner):
    def scan(self, repository, severity_scope, label):
        report = super().scan(repository, severity_scope, label)
        pom = (Path(repository) / "pom.xml").read_text(encoding="utf-8")
        second = VulnerabilityFinding(
            "CVE-2024-0002", ("GHSA-second",), "HIGH", "org.example", "other", "org.example:other", "1.0"
        )
        findings = (_finding(), second) if "<demo.version>1.0</demo.version>" in pom else (second,)
        return ScanReport(True, findings, report.command_result, report.raw_report_path)


class _RetryingFixtureScanner(OsvScanner):
    def __init__(self, config, workspace, process_runner, trace):
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


class _InfrastructureFailingScanner(_FixtureScanner):
    def scan(self, repository, severity_scope, label):
        if label == "baseline":
            return super().scan(repository, severity_scope, label)
        raw = self.workspace.artifacts / "scans" / f"{label}.json"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("{}", encoding="utf-8")
        return ScanReport(
            False,
            (),
            CommandResult(["xray"], str(repository), 0, stdout="{}"),
            str(raw),
            error="TIMEOUT: XRAY_POLL_TIMEOUT",
            outcome=ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE,
            backend="xray",
            failure_kind=ScanFailureKind.TIMEOUT,
        )


class _BaselineInfrastructureFailingScanner(_InfrastructureFailingScanner):
    def scan(self, repository, severity_scope, label):
        if label != "baseline":
            return super().scan(repository, severity_scope, label)
        raw = self.workspace.artifacts / "scans" / f"{label}.json"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("{}", encoding="utf-8")
        return ScanReport(
            False,
            (),
            CommandResult(["xray"], str(repository), 0, stdout="{}"),
            str(raw),
            error="BACKEND: XRAY_BACKEND_UNAVAILABLE",
            outcome=ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE,
            backend="xray",
            failure_kind=ScanFailureKind.BACKEND,
        )


class _ValidationRaisingScanner(_FixtureScanner):
    def scan(self, repository, severity_scope, label):
        if label == "baseline":
            return super().scan(repository, severity_scope, label)
        raise ScannerPreflightError("validation scanner unavailable")


class _ScriptedAgentSession:
    def __init__(self, capabilities, edits, outcome_status="READY_FOR_INDEPENDENT_VALIDATION"):
        self.capabilities = capabilities
        self.edits = edits
        self.outcome_status = outcome_status
        self.messages = []
        self.closed = False

    async def run_turn(self, message):
        if self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED:
            self.capabilities.submit_cycle_outcome(
                self.capabilities.journal.active_cycle,
                self.outcome_status,
                "Execution completed and is ready for deterministic checks.",
                _outcome_answers(),
            )
            return AgentTurnResult("Cycle Outcome submitted")
        self.messages.append(message)
        self.capabilities.submit_cycle_intent(
            self.capabilities.journal.active_cycle,
            _intent_answers(self.capabilities.journal.active_cycle),
        )
        if self.edits:
            old, new = self.edits.pop(0)
            self.capabilities.edit_workspace_text(
                "replace",
                "pom.xml",
                old_text=f"<demo.version>{old}</demo.version>",
                new_text=f"<demo.version>{new}</demo.version>",
            )
        cycle = len(self.messages)
        return AgentTurnResult(
            f"cycle {cycle} complete\n\n"
            "WORKING_STATE\n"
            f"- Understanding: validation cycle {cycle} repository evidence\n"
            f"- Current strategy/hypothesis: strategy-{cycle}\n"
            "- Assumptions: verify through deterministic validation\n"
            f"- Progress: completed work cycle {cycle}\n"
            "- Unresolved: deterministic completion criteria"
        )

    async def close(self):
        self.closed = True


class _DiagnosticArtifactSession(_ScriptedAgentSession):
    async def run_turn(self, message):
        if self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED:
            return await super().run_turn(message)
        result = await super().run_turn(message)
        self.capabilities.edit_workspace_text(
            "write", "dependency_tree.txt", content="investigation-only graph\n"
        )
        return result


class _FailingAgentSession:
    async def run_turn(self, message):
        raise RuntimeError("model service unavailable")

    async def close(self):
        return None


class _ExecutionFailingSession:
    def __init__(self, capabilities):
        self.capabilities = capabilities

    async def run_turn(self, message):
        if self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED:
            self.capabilities.submit_cycle_outcome(
                self.capabilities.journal.active_cycle,
                "FAILED",
                "Execution ended because the model session raised an error.",
                _outcome_answers(),
            )
            return AgentTurnResult("Failure outcome submitted")
        self.capabilities.submit_cycle_intent(
            self.capabilities.journal.active_cycle,
            _intent_answers(self.capabilities.journal.active_cycle),
        )
        raise RuntimeError("model failed during execution")

    async def close(self):
        return None


class _UnstructuredAgentSession:
    def __init__(self, capabilities=None):
        self.capabilities = capabilities
        self.messages = []

    async def run_turn(self, message):
        if self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED:
            self.capabilities.submit_cycle_outcome(
                self.capabilities.journal.active_cycle,
                "INCONCLUSIVE",
                "No conclusive remediation was completed.",
                _outcome_answers(),
            )
            return AgentTurnResult("Outcome submitted")
        self.messages.append(message)
        self.capabilities.submit_cycle_intent(
            self.capabilities.journal.active_cycle,
            _intent_answers(self.capabilities.journal.active_cycle),
        )
        return AgentTurnResult("Investigated without a structured state. " + ("detail " * 300))

    async def close(self):
        return None


class _PromptLearningSession:
    def __init__(self, capabilities, *, reject_first_intent=False, reject_first_outcome=False):
        self.capabilities = capabilities
        self.reject_first_intent = reject_first_intent
        self.reject_first_outcome = reject_first_outcome
        self.intent_attempts = 0
        self.outcome_attempts = 0
        self.messages = []
        self.denied_mutation = None
        self.intent_sections = []
        self.outcome_sections = []

    @staticmethod
    def _questionnaire(message):
        return re.findall(r"^- `([^`]+)`(?: \(required after Cycle 1\))?: ", message, re.MULTILINE)

    async def run_turn(self, message):
        self.messages.append(message)
        cycle = self.capabilities.journal.active_cycle
        sections = self._questionnaire(message)
        if self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED:
            if sections:
                self.outcome_sections = sections
            self.outcome_attempts += 1
            submitted = (
                self.outcome_sections[1:]
                if self.reject_first_outcome and self.outcome_attempts == 1
                else self.outcome_sections
            )
            self.capabilities.submit_cycle_outcome(
                cycle,
                "READY_FOR_INDEPENDENT_VALIDATION",
                "The recorded work is ready for independent validation.",
                [{"section": section, "answer": f"Observed answer for {section}."} for section in submitted],
            )
            return AgentTurnResult("Outcome learned from runtime questionnaire")
        if sections:
            self.intent_sections = sections
        sections = self.intent_sections
        self.intent_attempts += 1
        submitted = sections[1:] if self.reject_first_intent and self.intent_attempts == 1 else sections
        result = self.capabilities.submit_cycle_intent(
            cycle,
            [{"section": section, "answer": f"Evidence-based answer for {section}."} for section in submitted],
        )
        if result["status"] != "accepted":
            self.denied_mutation = self.capabilities.edit_workspace_text("write", "forbidden.txt", content="no")
            return AgentTurnResult("Correcting rejected checkpoint")
        self.capabilities.edit_workspace_text(
            "replace",
            "pom.xml",
            old_text="<demo.version>1.0</demo.version>",
            new_text="<demo.version>2.0</demo.version>",
        )
        return AgentTurnResult("Executed after learning the questionnaire")

    async def close(self):
        return None


class _MissingFirstOutcomeSession(_ScriptedAgentSession):
    async def run_turn(self, message):
        if (
            self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED
            and self.capabilities.journal.active_cycle == 1
        ):
            return AgentTurnResult("Outcome not submitted")
        return await super().run_turn(message)


class _CommittingAgentSession:
    def __init__(self, capabilities):
        self.capabilities = capabilities

    async def run_turn(self, message):
        if self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED:
            self.capabilities.submit_cycle_outcome(
                self.capabilities.journal.active_cycle,
                "READY_FOR_INDEPENDENT_VALIDATION",
                "The local commit contains the completed remediation.",
                _outcome_answers(),
            )
            return AgentTurnResult("Outcome submitted")
        self.capabilities.submit_cycle_intent(
            self.capabilities.journal.active_cycle,
            _intent_answers(self.capabilities.journal.active_cycle),
        )
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
        self.assertIn("original remediation objective", sessions[0].messages[1])
        self.assertIn("supports, contradicts, or leaves unresolved", sessions[0].messages[1])
        self.assertIn("decision journal", sessions[0].messages[1])
        self.assertIn("# Cycle 1 — Intent", sessions[0].messages[1])
        self.assertIn("# Cycle 1 — Outcome", sessions[0].messages[1])
        self.assertIn("# Cycle 1 — Deterministic Validation", sessions[0].messages[1])
        self.assertNotIn("cycle 1 complete", sessions[0].messages[1])
        self.assertTrue(sessions[0].closed)
        workspace_root = Path(result.workspace_root)
        self.assertTrue((workspace_root / "artifacts" / "final-result.json").is_file())
        cycle_one_agent = json.loads(
            (workspace_root / "artifacts" / "agent" / "cycle-1.json").read_text(encoding="utf-8")
        )
        cycle_two_agent = json.loads(
            (workspace_root / "artifacts" / "agent" / "cycle-2.json").read_text(encoding="utf-8")
        )
        self.assertIn("deprecated deterministic compatibility projection", cycle_one_agent["workingState"])
        self.assertIn("Observed result for Final approach", cycle_one_agent["workingState"])
        self.assertNotIn("cycle 1 complete", cycle_one_agent["workingState"])
        self.assertIn("cycle 1 complete", cycle_one_agent["summary"])
        self.assertIn("Observed result for Final approach", cycle_two_agent["workingState"])
        self.assertTrue(cycle_one_agent["workingStateDeprecated"])
        self.assertIn(result.baseline.commit, sessions[0].messages[1])
        self.assertIn("CVE-2024-0001", sessions[0].messages[1])
        journal = Path(result.journal_path).read_text(encoding="utf-8")
        self.assertIn("# Baseline Contract", journal)
        self.assertIn(result.baseline.commit, journal)
        self.assertIn('"targetFindings"', journal)
        self.assertIn("## How the approach evolved", journal)
        self.assertIn("Cycle 1 selected direction", journal)
        self.assertIn("Cycle 2 validation learning", journal)
        self.assertNotIn("See the immutable cycle", journal)
        cycle_one = json.loads(
            (workspace_root / "artifacts" / "validation" / "cycle-1.json").read_text(encoding="utf-8")
        )
        cycle_two = json.loads(
            (workspace_root / "artifacts" / "validation" / "cycle-2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["pom.xml"], cycle_one["cycleEvidence"]["pathsAddedToChangeSet"])
        self.assertEqual(["pom.xml"], cycle_two["cycleEvidence"]["pathsModifiedSinceCycleStart"])
        cumulative_diff = (workspace_root / "artifacts" / "validation" / "cycle-2.diff").read_text(
            encoding="utf-8"
        )
        self.assertIn("<demo.version>1.0</demo.version>", cumulative_diff)
        self.assertIn("<demo.version>2.0</demo.version>", cumulative_diff)
        push_url = _git(workspace_root / "repository", "remote", "get-url", "--push", "origin")
        self.assertEqual("disabled://autonomous-remediation-delivery-only", push_url.strip())
        events = [json.loads(line) for line in (workspace_root / "artifacts" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        command_sources = {event.get("source") for event in events if event.get("type") == "command"}
        self.assertIn("baseline_test_1", command_sources)
        self.assertIn("baseline_startup_1", command_sources)

    def test_working_state_is_generated_without_model_authorship(self):
        sessions = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: sessions.append(_UnstructuredAgentSession(capabilities)) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertEqual(Outcome.EXECUTION_LIMIT_REACHED, result.outcome)
        self.assertEqual("INCONCLUSIVE", result.remediation_outcome)
        cycle = json.loads(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("deprecated deterministic compatibility projection", cycle["workingState"])
        self.assertIn("Outcome status: INCONCLUSIVE", cycle["workingState"])
        self.assertNotIn("Investigated without", cycle["workingState"])
        self.assertTrue(cycle["workingStateDeprecated"])

    def test_model_learns_questionnaires_and_exact_retry_errors_from_runtime_prompt(self):
        sessions = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _PromptLearningSession(capabilities, reject_first_intent=True)
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        session = sessions[0]
        self.assertTrue(result.validation.passed)
        self.assertEqual(2, session.intent_attempts)
        self.assertIn("Missing required section: Problem as received", session.messages[1])
        self.assertEqual("PHASE_CAPABILITY_UNAVAILABLE", session.denied_mutation["failureCode"])
        self.assertFalse((Path(result.baseline.repository_path) / "forbidden.txt").exists())
        self.assertIn("Cycle Outcome questionnaire", session.messages[-1])

    def test_outcome_retry_contains_exact_structural_error(self):
        sessions = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _PromptLearningSession(capabilities, reject_first_outcome=True)
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        session = sessions[0]
        self.assertTrue(result.validation.passed)
        self.assertEqual(2, session.outcome_attempts)
        self.assertIn("Missing required section: Work actually performed", session.messages[-1])

    def test_incomplete_cycle_one_capture_is_not_hidden_by_complete_cycle_two(self):
        adapter = _RecordingDeliveryAdapter()
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=lambda capabilities, model: _MissingFirstOutcomeSession(
                capabilities, [("1.0", "1.5"), ("1.5", "2.0")]
            ),
            scanner_factory=_FixtureScanner,
            delivery_adapter_factory=lambda workspace, process_runner, trace: adapter,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertEqual("INCOMPLETE", result.capture_status)
        self.assertIn("Cycle 1 capture is INCOMPLETE", result.capture_warnings)
        self.assertEqual("NOT_DELIVERY_ELIGIBLE", result.delivery_eligibility)
        self.assertEqual([], adapter.contexts)

    def test_cycle_evidence_identifies_preserved_and_repeated_repository_state(self):
        sessions = []

        def factory(capabilities, model):
            session = _ScriptedAgentSession(capabilities, [("1.0", "1.5")])
            sessions.append(session)
            return session

        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=factory,
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertEqual("FAILED", result.remediation_outcome)
        workspace_root = Path(result.workspace_root)
        cycle_two = json.loads(
            (workspace_root / "artifacts" / "validation" / "cycle-2.json").read_text(encoding="utf-8")
        )
        evidence = cycle_two["cycleEvidence"]
        self.assertFalse(evidence["repositoryStateChanged"])
        self.assertEqual(1, evidence["matchesPriorCycle"])
        self.assertEqual(["pom.xml"], evidence["beforeChangedFiles"])
        self.assertEqual(["pom.xml"], evidence["afterChangedFiles"])
        self.assertEqual([], evidence["pathsAddedToChangeSet"])
        self.assertEqual([], evidence["pathsModifiedSinceCycleStart"])
        self.assertEqual([], evidence["pathsRemovedFromChangeSet"])

    def test_scanner_retry_stays_inside_one_remediation_cycle(self):
        sessions = []
        scanners = []

        def agent_factory(capabilities, model):
            session = _ScriptedAgentSession(capabilities, [("1.0", "2.0")])
            sessions.append(session)
            return session

        def scanner_factory(config, workspace, process_runner, trace):
            scanner = _RetryingFixtureScanner(config, workspace, process_runner, trace)
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
        self.assertEqual(1, len(scanners))
        self.assertEqual(
            [("baseline", 1), ("validation-cycle-1", 1), ("validation-cycle-1", 2)],
            scanners[0].execution_labels,
        )

    def test_exhausted_scanner_failure_does_not_start_another_agent_cycle(self):
        sessions = []

        def agent_factory(capabilities, model):
            session = _ScriptedAgentSession(capabilities, [("1.0", "2.0")])
            sessions.append(session)
            return session

        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=agent_factory,
            scanner_factory=_InfrastructureFailingScanner,
        ).run()

        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertIn("VALIDATION_SCANNER_FAILURE", result.reason)
        self.assertEqual(1, result.cycles_completed)
        self.assertEqual(1, len(sessions[0].messages))
        self.assertTrue(sessions[0].closed)
        self.assertEqual(ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE, result.validation.scan.effective_outcome)
        self._assert_target_comparison_incomplete(result)

    def test_scanner_exception_does_not_infer_target_resolution(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _ScriptedAgentSession(
                capabilities, [("1.0", "2.0")], "PARTIALLY_REMEDIATED"
            ),
            scanner_factory=_ValidationRaisingScanner,
        ).run()

        self.assertIsNone(result.validation.scan)
        self._assert_target_comparison_incomplete(result)

    def test_baseline_scanner_failure_stops_before_agent_creation(self):
        invoked = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=lambda capabilities, model: invoked.append(True),
            scanner_factory=_BaselineInfrastructureFailingScanner,
        ).run()

        self.assertEqual(Outcome.BASELINE_FAILURE, result.outcome)
        self.assertIn("INCOMPLETE_RETRYABLE_FAILURE", result.reason)
        self.assertEqual([], invoked)
        journal = Path(result.journal_path).read_text(encoding="utf-8")
        self.assertIn("# Preliminary Run Contract", journal)
        self.assertNotIn("# Baseline Contract", journal)

    def test_cycle_budget_exhaustion_is_truthful(self):
        request = self._request(max_cycles=1)
        result = AutonomousRemediationOrchestrator(
            request,
            agent_session_factory=lambda capabilities, model: _ScriptedAgentSession(capabilities, []),
            scanner_factory=_FixtureScanner,
        ).run()
        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertEqual("FAILED", result.remediation_outcome)
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

    def test_execution_failure_still_requests_outcome_and_runs_validation(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _ExecutionFailingSession(capabilities),
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertEqual("FAILED", result.remediation_outcome)
        self.assertEqual("COMPLETE", result.capture_status)
        self.assertIsNotNone(result.validation)
        journal = Path(result.journal_path).read_text(encoding="utf-8")
        self.assertIn("# Cycle 1 — Outcome", journal)
        self.assertIn("# Cycle 1 — Deterministic Validation", journal)

    def test_missing_explicit_vulnerability_stops_before_agent(self):
        invoked = []
        request = replace(self._request(max_cycles=2), vulnerability_ids=("CVE-2021-44228",))

        result = AutonomousRemediationOrchestrator(
            request,
            agent_session_factory=lambda capabilities, model: invoked.append(True),
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertEqual(Outcome.REQUESTED_VULNERABILITY_NOT_FOUND, result.outcome)
        self.assertIn("REQUESTED_VULNERABILITY_NOT_FOUND", result.reason)
        self.assertEqual((), result.baseline.target_findings)
        self.assertEqual(0, result.cycles_completed)
        self.assertEqual([], invoked)
        baseline_pom = Path(result.baseline.repository_path) / "pom.xml"
        self.assertIn("<demo.version>1.0</demo.version>", baseline_pom.read_text(encoding="utf-8"))

    def test_empty_vulnerability_ids_target_all_in_scope_findings(self):
        sessions = []
        request = replace(self._request(max_cycles=1), vulnerability_ids=())

        def factory(capabilities, model):
            session = _ScriptedAgentSession(capabilities, [("1.0", "2.0")])
            sessions.append(session)
            return session

        result = AutonomousRemediationOrchestrator(
            request,
            agent_session_factory=factory,
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertEqual(1, len(result.baseline.target_findings))
        self.assertEqual("CVE-2024-0001", result.baseline.target_findings[0].vulnerability_id)
        self.assertEqual(1, len(sessions))
        self.assertEqual(1, result.cycles_completed)

    def test_validation_includes_agent_local_commits_since_baseline(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _CommittingAgentSession(capabilities),
            scanner_factory=_FixtureScanner,
        ).run()
        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertTrue(result.validation.passed)
        self.assertIn("pom.xml", result.validation.changed_files)

    def test_safe_partial_progress_is_separate_from_full_success_and_manual_only(self):
        request = replace(self._request(max_cycles=1), vulnerability_ids=())
        result = AutonomousRemediationOrchestrator(
            request,
            agent_session_factory=lambda capabilities, model: _ScriptedAgentSession(
                capabilities, [("1.0", "1.5")], "PARTIALLY_REMEDIATED"
            ),
            scanner_factory=_TwoFindingScanner,
        ).run()

        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertEqual("PARTIALLY_REMEDIATED", result.remediation_outcome)
        self.assertEqual("PARTIAL", result.validation_status)
        self.assertEqual("PARTIAL_MANUAL_REVIEW_DELIVERY", result.delivery_eligibility)
        self.assertIsNone(result.delivery)

    def test_unchanged_target_coverage_is_not_partial_remediation(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _ScriptedAgentSession(
                capabilities, [("1.0", "1.5")], "PARTIALLY_REMEDIATED"
            ),
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertEqual("FAILED", result.remediation_outcome)
        self.assertEqual("FAILED", result.validation_status)
        self.assertEqual("NOT_DELIVERY_ELIGIBLE", result.delivery_eligibility)

    def test_no_change_outcome_never_invokes_delivery(self):
        adapter = _RecordingDeliveryAdapter()
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _ScriptedAgentSession(
                capabilities, [], "NO_CHANGE_REQUIRED"
            ),
            scanner_factory=_CleanAfterBaselineScanner,
            delivery_adapter_factory=lambda workspace, process_runner, trace: adapter,
        ).run()

        self.assertEqual("NO_CHANGE_REQUIRED", result.remediation_outcome)
        self.assertEqual("NO_CHANGE_REQUIRED", result.delivery.status)
        self.assertEqual([], adapter.contexts)

    def test_diagnostic_artifact_blocks_delivery_and_is_reported(self):
        adapter = _RecordingDeliveryAdapter()
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _DiagnosticArtifactSession(
                capabilities, [("1.0", "2.0")]
            ),
            scanner_factory=_FixtureScanner,
            delivery_adapter_factory=lambda workspace, process_runner, trace: adapter,
        ).run()

        self.assertIn("dependency_tree.txt", result.validation.diagnostic_artifacts)
        self.assertEqual("NOT_DELIVERY_ELIGIBLE", result.delivery_eligibility)
        self.assertEqual([], adapter.contexts)

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

    def _assert_target_comparison_incomplete(self, result):
        self.assertFalse(result.validation.target_comparison_complete)
        self.assertEqual((), result.validation.resolved_target_findings)
        self.assertEqual((), result.validation.remaining_target_findings)
        self.assertEqual("INCOMPLETE", result.validation_status)
        self.assertNotEqual("PARTIALLY_REMEDIATED", result.remediation_outcome)
        payload = result.validation.to_dict()
        self.assertFalse(payload["targetComparisonComplete"])
        self.assertEqual([], payload["resolvedTargetFindings"])
        journal = Path(result.journal_path).read_text(encoding="utf-8")
        validation_section = journal.split("Deterministic Validation", 1)[1]
        self.assertIn("Target comparison unavailable because the fresh scan did not complete", validation_section)
        self.assertIn("Target comparison completed:** No", validation_section)
        self.assertNotIn("original target findings are absent", validation_section)
        self.assertNotIn("Requested target findings are absent", validation_section)


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


def _intent_answers(cycle):
    sections = [
        "Problem as received",
        "Interpreted objective",
        "Relevant context and evidence discovered",
        "Input ambiguities, discrepancies, or missing information",
        "Applicable constraints and success criteria",
        "Materially credible candidate approaches",
        "Selected direction",
        "Selection rationale",
        "Assumptions to test",
        "Intended work",
        "Validation approach",
        "Current uncertainties and risks",
    ]
    if cycle > 1:
        sections[5:5] = ["Prior-cycle learning", "Relationship to the prior approach"]
    return [{"section": section, "answer": f"Evidence-based answer for {section}."} for section in sections]


def _outcome_answers():
    sections = [
        "Work actually performed",
        "Evidence actually observed",
        "Intended versus actual",
        "Material deviations and their causes",
        "Approaches attempted, rejected, or abandoned",
        "Final approach present at cycle end",
        "Assumption results",
        "Requirement and problem coverage",
        "Constraints and regression assessment",
        "Self-validation assessment",
        "Remaining work, blockers, or uncertainty",
        "Partial-remediation value",
        "Cycle conclusion",
    ]
    return [{"section": section, "answer": f"Observed result for {section}."} for section in sections]


def _git(cwd: Path, *args: str):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


if __name__ == "__main__":
    unittest.main()
