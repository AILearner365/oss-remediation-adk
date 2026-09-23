from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
import hashlib
import os
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


class _RecordingFixtureScanner(_FixtureScanner):
    def __init__(self, config, workspace, process_runner, trace):
        super().__init__(config, workspace, process_runner, trace)
        self.calls = []

    def scan(self, repository, severity_scope, label):
        self.calls.append((Path(repository), severity_scope, label))
        return super().scan(repository, severity_scope, label)


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
        return AgentTurnResult(f"cycle {cycle} complete")

    async def close(self):
        self.closed = True


class _CycleWorkspaceSession(_ScriptedAgentSession):
    def __init__(self, capabilities):
        super().__init__(capabilities, [])
        self.pre_intent_versions = []
        self.previous_marker_reads = []
        self.historical_shell_attempts = []

    async def run_turn(self, message):
        phase = self.capabilities.journal.phase
        cycle = self.capabilities.journal.active_cycle
        if phase == JournalPhase.OUTCOME_REQUIRED:
            self.capabilities.submit_cycle_outcome(
                cycle,
                "READY_FOR_INDEPENDENT_VALIDATION",
                "Cycle work is ready for deterministic validation.",
                _outcome_answers(),
            )
            return AgentTurnResult("Outcome submitted")
        read = self.capabilities.read_workspace_text("pom.xml")
        self.pre_intent_versions.append(read["content"])
        if cycle == 1:
            self.capabilities.edit_workspace_text("write", "cycle-one-only.txt", content="historical")
        else:
            self.previous_marker_reads.append(
                self.capabilities.read_workspace_text("cycle-one-only.txt")
            )
            self.historical_shell_attempts.append(
                self.capabilities.run_workspace_shell(
                    "try { Set-Content ../cycle-1/cycle-one-only.txt changed -ErrorAction Stop } "
                    "catch { Set-Content historical-shell-ran.txt caught }"
                    if os.name == "nt"
                    else "(printf changed > ../cycle-1/cycle-one-only.txt) || "
                    "printf caught > historical-shell-ran.txt"
                )
            )
            self.capabilities.edit_workspace_text("write", "cycle-two-only.txt", content="current")
        self.capabilities.submit_cycle_intent(cycle, _intent_answers(cycle))
        old, new = ("1.0", "1.5") if cycle == 1 else ("1.5", "2.0")
        self.capabilities.edit_workspace_text(
            "replace", "pom.xml",
            old_text=f"<demo.version>{old}</demo.version>",
            new_text=f"<demo.version>{new}</demo.version>",
        )
        return AgentTurnResult(f"cycle {cycle} implementation")


class _EngineeringScanSession(_ScriptedAgentSession):
    def __init__(self, capabilities):
        super().__init__(capabilities, [])
        self.scan_results = []

    async def run_turn(self, message):
        if self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED:
            return await super().run_turn(message)
        cycle = self.capabilities.journal.active_cycle
        self.scan_results.append(self.capabilities.scan_current_repository())
        self.capabilities.submit_cycle_intent(cycle, _intent_answers(cycle))
        self.capabilities.edit_workspace_text(
            "replace", "pom.xml",
            old_text="<demo.version>1.0</demo.version>",
            new_text="<demo.version>2.0</demo.version>",
        )
        self.scan_results.append(self.capabilities.scan_current_repository())
        return AgentTurnResult("implemented and obtained engineering scan evidence")


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


class _MissingIntentSession:
    def __init__(self):
        self.messages = []

    async def run_turn(self, message):
        self.messages.append(message)
        return AgentTurnResult("No submission")

    async def close(self):
        return None


class _IntentThenContinuationSession:
    def __init__(self, capabilities):
        self.capabilities = capabilities
        self.messages = []
        self.execution_tools = frozenset()
        self.pre_intent_activity = None
        self.pre_intent_edit = None
        self.pre_intent_shell = None
        self.authoritative_before_execution = None
        self.experiment_during_execution = None

    async def run_turn(self, message):
        self.messages.append(message)
        phase = self.capabilities.journal.phase
        cycle = self.capabilities.journal.active_cycle
        if phase == JournalPhase.OUTCOME_REQUIRED:
            self.capabilities.submit_cycle_outcome(
                cycle,
                "READY_FOR_INDEPENDENT_VALIDATION",
                "The continuation implemented and self-validated the selected solution.",
                _outcome_answers(),
            )
            return AgentTurnResult("Outcome submitted")
        if phase == JournalPhase.INTENT_REQUIRED:
            self.pre_intent_edit = self.capabilities.edit_workspace_text(
                "replace",
                "pom.xml",
                old_text="<demo.version>1.0</demo.version>",
                new_text="<demo.version>1.5</demo.version>",
            )
            self.pre_intent_shell = self.capabilities.run_workspace_shell(
                "Set-Content experimental-build.txt passed"
                if os.name == "nt"
                else "printf passed > experimental-build.txt"
            )
            self.pre_intent_activity = self.capabilities.execution_activity(cycle)
            self.capabilities.submit_cycle_intent(cycle, _intent_answers(cycle))
            return AgentTurnResult("")
        self.execution_tools = self.capabilities.available_tool_names()
        self.authoritative_before_execution = self.capabilities.read_workspace_text("pom.xml")
        self.experiment_during_execution = self.capabilities.read_workspace_text(
            "pom.xml", workspace="experiment"
        )
        self.capabilities.edit_workspace_text(
            "replace",
            "pom.xml",
            old_text="<demo.version>1.0</demo.version>",
            new_text="<demo.version>2.0</demo.version>",
        )
        return AgentTurnResult("Implemented the accepted solution during same-cycle continuation")

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
        self.pre_intent_experiment = None
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
            [{"section": section, "answer": _intent_answer(section)} for section in submitted],
        )
        if result["status"] != "accepted":
            self.pre_intent_experiment = self.capabilities.edit_workspace_text(
                "write", "isolated-probe.txt", content="experiment only"
            )
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
    def __init__(self, capabilities, edits, outcome_status="READY_FOR_INDEPENDENT_VALIDATION"):
        super().__init__(capabilities, edits, outcome_status)
        self.outcome_attempts = {}

    async def run_turn(self, message):
        if (
            self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED
            and self.capabilities.journal.active_cycle == 1
        ):
            self.outcome_attempts[1] = self.outcome_attempts.get(1, 0) + 1
            return AgentTurnResult("Outcome not submitted")
        return await super().run_turn(message)


class _MissingFirstIntentSession(_ScriptedAgentSession):
    async def run_turn(self, message):
        if (
            self.capabilities.journal.phase == JournalPhase.INTENT_REQUIRED
            and self.capabilities.journal.active_cycle == 1
        ):
            self.messages.append(message)
            return AgentTurnResult("Intent not submitted")
        return await super().run_turn(message)


class _MissingInitialIntentsSession(_ScriptedAgentSession):
    def __init__(self, capabilities, edits, failed_cycles):
        super().__init__(capabilities, edits)
        self.failed_cycles = frozenset(failed_cycles)

    async def run_turn(self, message):
        if (
            self.capabilities.journal.phase == JournalPhase.INTENT_REQUIRED
            and self.capabilities.journal.active_cycle in self.failed_cycles
        ):
            self.messages.append(message)
            return AgentTurnResult("Intent not submitted")
        return await super().run_turn(message)


class _FutureOutcomeThenCorrectSession(_ScriptedAgentSession):
    def __init__(self, capabilities, edits):
        super().__init__(capabilities, edits)
        self.invalid_outcome_result = None

    async def run_turn(self, message):
        if (
            self.capabilities.journal.phase == JournalPhase.OUTCOME_REQUIRED
            and self.invalid_outcome_result is None
        ):
            cycle = self.capabilities.journal.active_cycle
            self.invalid_outcome_result = self.capabilities.submit_cycle_outcome(
                cycle + 1,
                "READY_FOR_INDEPENDENT_VALIDATION",
                "Incorrect future-cycle Outcome.",
                _outcome_answers(),
            )
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
        self.assertIn("Deterministic validation did not establish success", sessions[0].messages[1])
        self.assertIn("original canonical Task to Solve", sessions[0].messages[1])
        self.assertIn("Treat prior model statements as claims", sessions[0].messages[1])
        self.assertIn("decision journal", sessions[0].messages[1])
        self.assertIn("# Cycle 1 — Problem Analysis and Solution Decision", sessions[0].messages[1])
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
        self.assertNotIn("workingState", cycle_one_agent)
        self.assertNotIn("workingStateDeprecated", cycle_one_agent)
        self.assertIn("cycle 1 complete", cycle_one_agent["summary"])
        self.assertNotIn("workingState", cycle_two_agent)
        self.assertNotIn("workingStateDeprecated", cycle_two_agent)
        self.assertIn(result.baseline.commit, sessions[0].messages[1])
        self.assertIn("CVE-2024-0001", sessions[0].messages[1])
        journal = Path(result.journal_path).read_text(encoding="utf-8")
        self.assertIn("# Baseline Contract", journal)
        self.assertIn("# Preliminary Run Contract", journal)
        self.assertIn("# Task to Solve", journal)
        self.assertEqual(1, journal.count("# Task to Solve"))
        self.assertIn(result.baseline.commit, journal)
        self.assertIn('"targetFindings"', journal)
        self.assertIn("## How the approach evolved", journal)
        self.assertIn("Cycle 1 selected direction", journal)
        self.assertIn("Cycle 2 validation learning", journal)
        self.assertLess(
            journal.index("# Cycle 1 — Outcome"),
            journal.index("# Cycle 1 — Deterministic Validation"),
        )
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
        self.assertNotIn(
            "execution_continuation_requested",
            {event.get("type") for event in events},
        )

    def test_accepted_decision_without_execution_gets_same_cycle_continuation(self):
        sessions = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _IntentThenContinuationSession(capabilities)
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertEqual(1, result.cycles_completed)
        self.assertEqual(3, len(sessions[0].messages))
        self.assertIn("same cycle is still in progress", sessions[0].messages[1])
        self.assertIn("now in authoritative implementation", sessions[0].messages[1])
        self.assertIn(
            "exist only in the isolated experimental workspace", sessions[0].messages[1]
        )
        self.assertIn(
            "have not modified the authoritative repository", sessions[0].messages[1]
        )
        self.assertIn(
            '`workspace="active"` now targets the authoritative repository',
            sessions[0].messages[1],
        )
        self.assertIn('`workspace="experiment"` remains available', sessions[0].messages[1])
        self.assertIn(
            "not evidence that authoritative implementation has occurred",
            sessions[0].messages[1],
        )
        self.assertEqual((), sessions[0].pre_intent_activity)
        self.assertEqual("experimental", sessions[0].pre_intent_edit["workspaceKind"])
        self.assertEqual(
            Path(result.workspace_root) / "investigation" / "cycle-1",
            Path(sessions[0].pre_intent_shell["cwd"]),
        )
        self.assertIn(
            "<demo.version>1.0</demo.version>",
            sessions[0].authoritative_before_execution["content"],
        )
        self.assertIn(
            "<demo.version>1.5</demo.version>",
            sessions[0].experiment_during_execution["content"],
        )
        self.assertEqual(
            "experimental", sessions[0].experiment_during_execution["workspaceKind"]
        )
        self.assertIn("edit_workspace_text", sessions[0].execution_tools)
        self.assertIn("run_workspace_shell", sessions[0].execution_tools)
        self.assertIn('"executionAttempted": true', sessions[0].messages[2])
        self.assertIn("Implemented the accepted solution", result.agent_summaries[0])
        events = [
            json.loads(line)
            for line in (
                Path(result.workspace_root) / "artifacts" / "events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        event_types = [event["type"] for event in events]
        self.assertLess(
            event_types.index("intent_submission_accepted"),
            event_types.index("execution_continuation_requested"),
        )
        self.assertLess(
            event_types.index("execution_capability_invoked"),
            event_types.index("journal_phase_changed", event_types.index("execution_capability_invoked")),
        )
        completed = next(
            event for event in events if event["type"] == "execution_continuation_completed"
        )
        self.assertTrue(completed["executionAttempted"])
        self.assertEqual(
            ["read_workspace_text", "read_workspace_text", "edit_workspace_text"],
            completed["tools"],
        )

    def test_cycle_one_outcome_status_does_not_terminate_recovery(self):
        statuses = (
            "FAILED",
            "INCONCLUSIVE",
            "BLOCKED",
            "NO_CHANGE_REQUIRED",
            "PARTIALLY_REMEDIATED",
            "READY_FOR_INDEPENDENT_VALIDATION",
        )
        for status in statuses:
            with self.subTest(status=status):
                sessions = []

                def factory(capabilities, model):
                    session = _ScriptedAgentSession(
                        capabilities,
                        [("1.0", "1.5"), ("1.5", "2.0")],
                        status,
                    )
                    sessions.append(session)
                    return session

                result = AutonomousRemediationOrchestrator(
                    self._request(max_cycles=2),
                    agent_session_factory=factory,
                    scanner_factory=_FixtureScanner,
                ).run()

                self.assertTrue(result.validation.passed)
                self.assertEqual(2, result.cycles_completed)
                self.assertEqual(1, len(sessions))
                self.assertEqual(2, len(sessions[0].messages))
                continuation = sessions[0].messages[1]
                self.assertIn("# Cycle 1 — Problem Analysis and Solution Decision", continuation)
                self.assertIn("# Cycle 1 — Outcome", continuation)
                self.assertIn(f"`{status}`", continuation)
                self.assertIn("Execution completed and is ready for deterministic checks.", continuation)
                self.assertIn("# Cycle 1 — Deterministic Validation", continuation)
                self.assertIn("Latest deterministic validation evidence", continuation)
                self.assertIn("original canonical Task to Solve", continuation)
                self.assertIn('"prohibit_suppressions": true', continuation)
                self.assertEqual(
                    Path(result.baseline.repository_path),
                    sessions[0].capabilities.workspace_io.workspace.repository,
                )

    def test_operational_tool_budget_prevents_another_cycle(self):
        sessions = []
        request = self._request(max_cycles=2)
        request = replace(
            request,
            budget=replace(request.budget, max_tool_calls=1),
        )

        result = AutonomousRemediationOrchestrator(
            request,
            agent_session_factory=lambda capabilities, model: sessions.append(
                _ScriptedAgentSession(
                    capabilities,
                    [("1.0", "1.5"), ("1.5", "2.0")],
                    "FAILED",
                )
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertEqual(1, result.cycles_completed)
        self.assertEqual(1, len(sessions[0].messages))
        self.assertEqual("Configured operational budget reached", result.reason)

    def test_cycle_artifact_omits_deprecated_working_state(self):
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
        self.assertNotIn("workingState", cycle)
        self.assertNotIn("workingStateDeprecated", cycle)
        self.assertIn("Investigated without", cycle["summary"])
        events = [
            json.loads(line)
            for line in (
                Path(result.workspace_root) / "artifacts" / "events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        requested = [event for event in events if event["type"] == "execution_continuation_requested"]
        completed = [event for event in events if event["type"] == "execution_continuation_completed"]
        self.assertEqual(1, len(requested))
        self.assertEqual(1, len(completed))
        self.assertFalse(completed[0]["executionAttempted"])

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
        self.assertIn("Missing required section: Model understanding", session.messages[1])
        self.assertEqual("ok", session.pre_intent_experiment["status"])
        self.assertEqual("experimental", session.pre_intent_experiment["workspaceKind"])
        self.assertFalse((Path(result.baseline.repository_path) / "isolated-probe.txt").exists())
        self.assertTrue(
            (Path(result.workspace_root) / "investigation" / "cycle-1" / "isolated-probe.txt").is_file()
        )
        self.assertIn("Cycle Outcome questionnaire", session.messages[-1])
        cycle = json.loads(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("CAPTURED", cycle["lifecycle"]["intent"]["status"])
        self.assertEqual("EXECUTED", cycle["lifecycle"]["implementation"]["status"])
        self.assertEqual("CAPTURED", cycle["lifecycle"]["outcome"]["status"])

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
        self.assertIn("Missing required section: Implementation Result", session.messages[-1])

    def test_complete_later_cycle_recovers_prior_outcome_capture_failure_for_delivery(self):
        sessions = []
        adapter = _RecordingDeliveryAdapter()
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _MissingFirstOutcomeSession(
                    capabilities, [("1.0", "1.5"), ("1.5", "2.0")]
                )
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
            delivery_adapter_factory=lambda workspace, process_runner, trace: adapter,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertEqual(Outcome.SUCCESS, result.outcome)
        self.assertEqual("COMPLETE", result.capture_status)
        self.assertIn("Cycle 1 capture is INCOMPLETE", result.capture_warnings)
        self.assertEqual("FULL_AUTOMATIC_DELIVERY", result.delivery_eligibility)
        self.assertEqual(1, len(adapter.contexts))
        self.assertEqual(10, sessions[0].outcome_attempts[1])
        cycle_one = json.loads(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("CAPTURED", cycle_one["lifecycle"]["intent"]["status"])
        self.assertEqual("EXECUTED", cycle_one["lifecycle"]["implementation"]["status"])
        self.assertEqual("FAILED", cycle_one["lifecycle"]["outcome"]["status"])
        self.assertTrue(
            all(
                item["status"] == "NOT_CAPTURED"
                for item in cycle_one["lifecycle"]["outcome"]["answers"].values()
            )
        )
        self.assertIsNotNone(cycle_one["deterministicValidation"])

    def test_each_cycle_experiment_forks_exact_current_authoritative_state(self):
        sessions = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _CycleWorkspaceSession(capabilities)
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertIn("<demo.version>1.0</demo.version>", sessions[0].pre_intent_versions[0])
        self.assertIn("<demo.version>1.5</demo.version>", sessions[0].pre_intent_versions[1])
        self.assertEqual("TOOL_ERROR", sessions[0].previous_marker_reads[0]["failureCode"])
        root = Path(result.workspace_root)
        self.assertTrue((root / "investigation" / "cycle-1" / "cycle-one-only.txt").is_file())
        self.assertFalse((root / "investigation" / "cycle-1" / "cycle-two-only.txt").exists())
        self.assertEqual(
            "historical",
            (root / "investigation" / "cycle-1" / "cycle-one-only.txt").read_text(
                encoding="utf-8"
            ),
        )
        self.assertFalse((root / "investigation" / "cycle-2" / "cycle-one-only.txt").exists())
        self.assertTrue((root / "investigation" / "cycle-2" / "cycle-two-only.txt").is_file())
        self.assertTrue((root / "investigation" / "cycle-2" / "historical-shell-ran.txt").is_file())
        self.assertFalse(sessions[0].historical_shell_attempts[0]["blocked"])
        self.assertFalse((root / "repository" / "cycle-one-only.txt").exists())
        self.assertFalse((root / "repository" / "cycle-two-only.txt").exists())

    def test_engineering_scans_do_not_replace_deterministic_validation(self):
        sessions = []
        scanners = []

        def scanner_factory(config, workspace, process_runner, trace):
            scanner = _RecordingFixtureScanner(config, workspace, process_runner, trace)
            scanners.append(scanner)
            return scanner

        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _EngineeringScanSession(capabilities)
            ) or sessions[-1],
            scanner_factory=scanner_factory,
        ).run()

        self.assertTrue(result.validation.passed)
        labels = [call[2] for call in scanners[0].calls]
        self.assertEqual("baseline", labels[0])
        self.assertTrue(any("engineering-cycle-1-experimental" in label for label in labels))
        self.assertTrue(any("engineering-cycle-1-authoritative" in label for label in labels))
        self.assertIn("validation-cycle-1", labels)
        self.assertEqual("experimental", sessions[0].scan_results[0]["workspaceKind"])
        self.assertEqual("authoritative", sessions[0].scan_results[1]["workspaceKind"])

    def test_complete_third_cycle_recovers_prior_intent_capture_failures_for_delivery(self):
        sessions = []
        adapter = _RecordingDeliveryAdapter()
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=3),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _MissingInitialIntentsSession(
                    capabilities, [("1.0", "2.0")], failed_cycles={1, 2}
                )
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
            delivery_adapter_factory=lambda workspace, process_runner, trace: adapter,
        ).run()

        self.assertEqual(Outcome.SUCCESS, result.outcome)
        self.assertTrue(result.validation.passed)
        self.assertEqual("FULLY_VALIDATED", result.remediation_outcome)
        self.assertEqual("COMPLETE", result.capture_status)
        self.assertEqual("FULL_AUTOMATIC_DELIVERY", result.delivery_eligibility)
        self.assertEqual(3, result.cycles_completed)
        self.assertEqual(1, len(adapter.contexts))
        self.assertIn("Cycle 1 capture is INCOMPLETE", result.capture_warnings)
        self.assertIn("Cycle 2 capture is INCOMPLETE", result.capture_warnings)

        workspace = Path(result.workspace_root)
        for cycle in (1, 2):
            artifact = json.loads(
                (workspace / "artifacts" / "agent" / f"cycle-{cycle}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("INCOMPLETE", artifact["captureStatus"])
            self.assertEqual("FAILED", artifact["lifecycle"]["intent"]["status"])
            self.assertEqual("NOT_EXECUTED", artifact["lifecycle"]["implementation"]["status"])
            self.assertEqual("NOT_REQUESTED", artifact["lifecycle"]["outcome"]["status"])
            self.assertIsNotNone(artifact["deterministicValidation"])
        cycle_three = json.loads(
            (workspace / "artifacts" / "agent" / "cycle-3.json").read_text(encoding="utf-8")
        )
        self.assertEqual("COMPLETE", cycle_three["captureStatus"])
        journal = Path(result.journal_path).read_text(encoding="utf-8")
        self.assertIn("# Cycle 1", journal)
        self.assertIn("# Cycle 2", journal)
        self.assertIn("# Cycle 3", journal)

    def test_fully_validated_cycle_with_failed_outcome_continues_with_truthful_context(self):
        sessions = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _MissingFirstOutcomeSession(capabilities, [("1.0", "2.0")])
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertEqual(2, result.cycles_completed)
        self.assertEqual(10, sessions[0].outcome_attempts[1])
        continuation = sessions[0].messages[1]
        self.assertIn("Deterministic validation established success", continuation)
        self.assertIn("checkpoint failure alone is not evidence that another repository change is needed", continuation)
        self.assertIn("**Cycle Intent:** `CAPTURED`", continuation)
        self.assertIn("**Implementation:** `EXECUTED`", continuation)
        self.assertIn("**Cycle Outcome:** `FAILED`", continuation)
        self.assertIn("All authoritative checks passed", continuation)
        self.assertIn('"status": "FAILED"', continuation)
        self.assertIn("**Implementation Result:** `NOT_CAPTURED`", continuation)
        cycle_one = json.loads(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(cycle_one["deterministicValidation"])
        self.assertEqual("FAILED", cycle_one["lifecycle"]["outcome"]["status"])
        events = [
            json.loads(line)
            for line in (
                Path(result.workspace_root) / "artifacts" / "events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        cycle_one_execution = [
            event
            for event in events
            if event["type"] == "execution_capability_invoked" and event.get("cycle") == 1
        ]
        self.assertEqual(1, len(cycle_one_execution))

    def test_final_fully_validated_cycle_with_failed_outcome_remains_manual_review(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _MissingFirstOutcomeSession(
                capabilities, [("1.0", "2.0")]
            ),
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertEqual("INCOMPLETE", result.capture_status)
        self.assertEqual("NOT_DELIVERY_ELIGIBLE", result.delivery_eligibility)
        self.assertEqual(1, result.cycles_completed)

    def test_rejected_future_outcome_does_not_create_phantom_cycle_or_block_delivery(self):
        sessions = []
        adapter = _RecordingDeliveryAdapter()
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _FutureOutcomeThenCorrectSession(capabilities, [("1.0", "2.0")])
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
            delivery_adapter_factory=lambda workspace, process_runner, trace: adapter,
        ).run()

        self.assertEqual("rejected", sessions[0].invalid_outcome_result["status"])
        self.assertIn(
            "Expected active cycle 1, received 2",
            sessions[0].invalid_outcome_result["errors"],
        )
        self.assertEqual(Outcome.SUCCESS, result.outcome)
        self.assertTrue(result.validation.passed)
        self.assertEqual("COMPLETE", result.capture_status)
        self.assertEqual("FULL_AUTOMATIC_DELIVERY", result.delivery_eligibility)
        self.assertEqual(1, len(adapter.contexts))
        self.assertEqual(1, result.cycles_completed)
        journal = Path(result.journal_path).read_text(encoding="utf-8")
        self.assertIn("# Cycle 1 — Outcome", journal)
        self.assertNotIn("# Cycle 2 —", journal)
        self.assertNotIn("**Cycle 2", journal)
        self.assertFalse(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-2.json").exists()
        )

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

    def test_missing_pre_execution_submission_uses_current_stage_terminology(self):
        sessions = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _MissingIntentSession()
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertIn("CYCLE_INTENT_CAPTURE_INCOMPLETE", result.reason)
        self.assertIn(
            "No Problem Analysis and Solution Decision submission was received in the previous turn",
            sessions[0].messages[1],
        )
        self.assertNotIn("No Cycle Intent submission", sessions[0].messages[1])
        self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome)
        self.assertEqual("INCOMPLETE", result.capture_status)
        self.assertIsNotNone(result.validation)
        self.assertEqual(1, result.cycles_completed)
        cycle = json.loads(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("FAILED", cycle["lifecycle"]["intent"]["status"])
        self.assertEqual("NOT_EXECUTED", cycle["lifecycle"]["implementation"]["status"])
        self.assertEqual("NOT_REQUESTED", cycle["lifecycle"]["outcome"]["status"])
        self.assertTrue(
            all(
                item["status"] == "NOT_CAPTURED"
                for item in cycle["lifecycle"]["intent"]["answers"].values()
            )
        )
        self.assertTrue(
            all(
                item["status"] == "NOT_CAPTURED"
                for item in cycle["lifecycle"]["outcome"]["answers"].values()
            )
        )
        self.assertIsNone(cycle["intent"])
        self.assertIsNone(cycle["outcome"])
        self.assertIsNotNone(cycle["deterministicValidation"])

    def test_failed_intent_runs_validation_and_allows_next_cycle(self):
        sessions = []
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=2),
            agent_session_factory=lambda capabilities, model: sessions.append(
                _MissingFirstIntentSession(capabilities, [("1.0", "2.0")])
            ) or sessions[-1],
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertEqual(2, result.cycles_completed)
        continuation = sessions[0].messages[10]
        self.assertIn("**Cycle Intent:** `FAILED`", continuation)
        self.assertIn("**Implementation:** `NOT_EXECUTED`", continuation)
        self.assertIn("**Cycle Outcome:** `NOT_REQUESTED`", continuation)
        self.assertIn("**Model understanding:** `NOT_CAPTURED`", continuation)
        self.assertIn("**Implementation Result:** `NOT_CAPTURED`", continuation)
        self.assertIn("# Cycle 1 — Deterministic Validation", continuation)
        cycle_one = json.loads(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("", cycle_one["summary"])
        self.assertEqual("", cycle_one["outcomeCaptureResponse"])
        self.assertEqual("FAILED", cycle_one["lifecycle"]["intent"]["status"])
        self.assertEqual("NOT_EXECUTED", cycle_one["lifecycle"]["implementation"]["status"])
        self.assertEqual("NOT_REQUESTED", cycle_one["lifecycle"]["outcome"]["status"])
        self.assertIsNotNone(cycle_one["deterministicValidation"])
        events = [
            json.loads(line)
            for line in (
                Path(result.workspace_root) / "artifacts" / "events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertFalse(
            any(
                event["type"] == "execution_capability_invoked" and event.get("cycle") == 1
                for event in events
            )
        )

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
        cycle = json.loads(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("workingState", cycle)
        self.assertNotIn("workingStateDeprecated", cycle)

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
        "Model understanding",
        "Information, investigation and remaining uncertainty",
        "Concrete candidate solutions",
        "Selected solution",
    ]
    if cycle > 1:
        sections[2:2] = ["Prior-cycle reassessment"]
    return [{"section": section, "answer": _intent_answer(section)} for section in sections]


def _intent_answer(section):
    if section == "Information, investigation and remaining uncertainty":
        return """| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| Version ownership | Select the change boundary | pom.xml | The property owns the version | Execution validation remains |

### Material assumptions that remain necessary

None."""
    if section == "Concrete candidate solutions":
        return """#### Candidate Solution A — Update the owning property
| Question | Model answer |
|---|---|
| What exact solution is proposed? | Update demo.version to the evidence-supported value. |
| Why were these exact changes selected? | The repository assigns ownership to this property. |
| What evidence supports the expected result? | pom.xml and baseline scanner evidence. |
| Which parts of the problem will it resolve? | The requested target finding. |
| Does it satisfy every applicable requirement? | Yes, subject to validation. |
| How will it be implemented? | Update the property and self-validate. |
| How will compatibility be preserved? | Run configured checks. |
| Why is the result coherent and maintainable? | It preserves the existing owner. |
| What risks or unknowns remain? | Runtime evidence remains execution-dependent. |
| How will the result be validated? | Build, test, startup, and scan checks. |
| Is it a COMPLETE or PARTIAL solution? | COMPLETE, subject to validation. |"""
    if section == "Selected solution":
        return """- **Selected solution:** Candidate A — Update the owning property
- **Classification:** COMPLETE
- **Why it is preferred:** Current evidence supports the ownership boundary.
- **Comparative coverage:** It covers the complete task; no other supported candidate exists.
- **Remaining risks:** Runtime compatibility requires execution evidence.
- **Evidence requiring reconsideration:** Contrary effective-model or test results."""
    if section == "Prior-cycle reassessment":
        return "Current repository state preserves useful prior work, while prior conclusions remain claims checked against deterministic validation; unsupported claims remain uncertain and do not constrain the next solution."
    return f"Evidence-based answer for {section}."


def _outcome_answers():
    sections = [
        "Implementation Result",
        "Cycle Intent vs. Implementation",
        "Implementation Trail",
    ]
    return [{"section": section, "answer": f"Observed result for {section}."} for section in sections]


def _git(cwd: Path, *args: str):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


if __name__ == "__main__":
    unittest.main()
