from __future__ import annotations

import subprocess
import tempfile
import unittest
import json
import hashlib
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


class _DecisionAwareAgentSession(_ScriptedAgentSession):
    def __init__(self, capabilities, edits, completion_action="READY_FOR_INDEPENDENT_VALIDATION"):
        super().__init__(capabilities, edits)
        self.latest_decision_id = None
        self.completion_action = completion_action

    async def run_turn(self, message):
        cycle = len(self.messages) + 1
        action = "SELECT" if cycle == 1 else "REVISE"
        decision = self._record(action, f"cycle {cycle} strategy")
        self.latest_decision_id = decision["decision"]["decisionId"]
        turn = await super().run_turn(message)
        if self.completion_action:
            completion = self._record(
                self.completion_action,
                f"cycle {cycle} self-validation conclusion",
            )
            self.latest_decision_id = completion["decision"]["decisionId"]
        return turn

    def _record(self, action, strategy):
        return self.capabilities.record_decision(
            action=action,
            diagnosis="The target finding requires a compatible repository change",
            strategy=strategy,
            rationale="Repository and validation evidence support this direction",
            evidence=["fixture repository evidence"],
            coverage_satisfied=["requested repository change", "local self-validation"],
            coverage_conditional=[],
            coverage_unresolved=(
                ["concrete blocker prevents completion"] if action == "BLOCK" else []
            ),
            assumptions=[
                {
                    "assumption": "The edited value controls the fixture result",
                    "test": "observed: deterministic fixture pre-check completed",
                    "status": "TESTED",
                }
            ],
            validation=["observed: fixture self-check complete"],
            previous_decision_id=self.latest_decision_id,
            alternatives=[],
        )


class _LateDecisionAgentSession(_ScriptedAgentSession):
    def __init__(self, capabilities, edits):
        super().__init__(capabilities, edits)
        self.decision_result = None

    async def run_turn(self, message):
        cycle = len(self.messages) + 1
        if cycle == 2:
            self.decision_result = self.capabilities.record_decision(
                action="SELECT",
                diagnosis="The first cycle did not resolve the target finding",
                strategy="Use current repository and validation evidence to complete remediation",
                rationale="The failed validation establishes the remaining work",
                evidence=["observed: cycle-one deterministic validation failed"],
                coverage_satisfied=["repository constraints preserved"],
                coverage_conditional=[],
                coverage_unresolved=["independent validation"],
                assumptions=[
                    {
                        "assumption": "The second edit controls the fixture result",
                        "test": "planned: deterministic validation",
                        "status": "UNRESOLVED",
                    }
                ],
                validation=["planned: deterministic validation"],
                alternatives=[],
            )
        return await super().run_turn(message)


class _DecisionThenFailingAgentSession:
    def __init__(self, capabilities):
        self.capabilities = capabilities

    async def run_turn(self, message):
        self.capabilities.record_decision(
            action="SELECT",
            diagnosis="Runtime work began but did not complete",
            strategy="Inspect and remediate using repository evidence",
            rationale="Initial evidence justified beginning investigation",
            evidence=["observed: baseline finding"],
            coverage_satisfied=[],
            coverage_conditional=[],
            coverage_unresolved=["all completion criteria"],
            assumptions=[],
            validation=["planned: run focused validation"],
            alternatives=[],
        )
        raise RuntimeError("model service unavailable after decision")

    async def close(self):
        return None


class _FailingAgentSession:
    async def run_turn(self, message):
        raise RuntimeError("model service unavailable")

    async def close(self):
        return None


class _UnstructuredAgentSession:
    def __init__(self):
        self.messages = []

    async def run_turn(self, message):
        self.messages.append(message)
        return AgentTurnResult("Investigated without a structured state. " + ("detail " * 300))

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
        self.assertIn("original remediation objective", sessions[0].messages[1])
        self.assertIn("supports, contradicts, or leaves unresolved", sessions[0].messages[1])
        self.assertIn("strategy-1", sessions[0].messages[1])
        self.assertNotIn("strategy-2", sessions[0].messages[1])
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
        self.assertIn("strategy-1", cycle_one_agent["workingState"])
        self.assertNotIn("cycle 1 complete", cycle_one_agent["workingState"])
        self.assertIn("cycle 1 complete", cycle_one_agent["summary"])
        self.assertIn("strategy-2", cycle_two_agent["workingState"])
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

    def test_decision_state_flows_through_cycle_continuation_and_final_artifacts(self):
        sessions = []

        def factory(capabilities, model):
            session = _DecisionAwareAgentSession(
                capabilities, [("1.0", "1.5"), ("1.5", "2.0")]
            )
            sessions.append(session)
            return session

        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=3),
            agent_session_factory=factory,
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertTrue(result.validation.passed)
        self.assertEqual(4, result.decision_event_count)
        self.assertEqual(
            "D4",
            result.final_decision_state.agent_decision_state.latest_decision_id,
        )
        self.assertIn('"latestDecisionId":"D2"', sessions[0].messages[1])
        self.assertIn('"previousSelfValidationConclusion"', sessions[0].messages[1])
        self.assertIn("New deterministic validation evidence", sessions[0].messages[1])
        self.assertLess(len(sessions[0].messages[1]), 25_000)
        workspace_root = Path(result.workspace_root)
        cycle_one = json.loads(
            (workspace_root / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        cycle_two = json.loads(
            (workspace_root / "artifacts" / "agent" / "cycle-2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("cycle 1 complete", cycle_one["summary"])
        self.assertIn("strategy-1", cycle_one["workingState"])
        self.assertEqual("D2", cycle_one["decisionState"]["latestDecisionId"])
        self.assertEqual(["D1", "D2"], [item["decisionId"] for item in cycle_one["decisionTrail"]])
        self.assertEqual(["D3", "D4"], [item["decisionId"] for item in cycle_two["decisionTrail"]])
        self.assertNotIn("timestamp", cycle_one["decisionTrail"][0])
        self.assertNotIn("type", cycle_one["decisionTrail"][0])
        final_result = json.loads(
            (workspace_root / "artifacts" / "final-result.json").read_text(encoding="utf-8")
        )
        self.assertEqual(4, final_result["decisionEventCount"])
        self.assertEqual(
            "D4",
            final_result["finalDecisionState"]["agentDecisionState"]["latestDecisionId"],
        )
        self.assertEqual("READY", final_result["finalDecisionState"]["agentStatus"])
        self.assertEqual(
            "PASSED",
            final_result["finalDecisionState"]["deterministicValidationStatus"],
        )
        self.assertEqual(
            "VALIDATED",
            final_result["finalDecisionState"]["effectiveResolutionStatus"],
        )
        events = [
            json.loads(line)
            for line in (workspace_root / "artifacts" / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        decisions = [event for event in events if event["type"] == "decision_recorded"]
        self.assertEqual(4, len(decisions))
        warnings = [event for event in events if event["type"] == "decision_warning"]
        self.assertTrue(
            any("contradicted deterministic validation" in event["warning"] for event in warnings)
        )

    def test_later_cycle_can_begin_decision_chain_with_select(self):
        sessions = []

        def factory(capabilities, model):
            session = _LateDecisionAgentSession(
                capabilities,
                [("1.0", "1.5"), ("1.5", "2.0")],
            )
            sessions.append(session)
            return session

        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=3),
            agent_session_factory=factory,
            scanner_factory=_FixtureScanner,
        ).run()

        session = sessions[0]
        self.assertTrue(result.validation.passed)
        self.assertEqual("ok", session.decision_result["status"])
        self.assertEqual("D1", session.decision_result["decision"]["decisionId"])
        self.assertIn("No current material decision state is recorded", session.messages[1])
        self.assertIn("action `SELECT`", session.messages[1])
        self.assertNotIn(
            "Record `RETAIN`, `EXTEND`, `REVISE`, `REPLACE`, or `BLOCK`",
            session.messages[1],
        )

        workspace_root = Path(result.workspace_root)
        cycle_one = json.loads(
            (workspace_root / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        cycle_two = json.loads(
            (workspace_root / "artifacts" / "agent" / "cycle-2.json").read_text(
                encoding="utf-8"
            )
        )
        final_result = json.loads(
            (workspace_root / "artifacts" / "final-result.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("decisionState", cycle_one)
        self.assertEqual("D1", cycle_two["decisionState"]["latestDecisionId"])
        self.assertEqual(["D1"], [item["decisionId"] for item in cycle_two["decisionTrail"]])
        self.assertEqual(
            "D1",
            final_result["finalDecisionState"]["agentDecisionState"]["latestDecisionId"],
        )
        events = [
            json.loads(line)
            for line in (workspace_root / "artifacts" / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertFalse(
            any(
                event.get("failureCode") == "DECISION_CHAIN_INVALID"
                for event in events
            )
        )

    def test_ready_then_failed_validation_is_effectively_rejected(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _DecisionAwareAgentSession(
                capabilities, [("1.0", "1.5")]
            ),
            scanner_factory=_FixtureScanner,
        ).run()

        self._assert_final_decision_status(result, "READY", "FAILED", "VALIDATION_REJECTED")

    def test_ready_then_scanner_failure_is_effectively_incomplete(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _DecisionAwareAgentSession(
                capabilities, [("1.0", "2.0")]
            ),
            scanner_factory=_InfrastructureFailingScanner,
        ).run()

        self._assert_final_decision_status(result, "READY", "INCOMPLETE", "INCOMPLETE")

    def test_blocked_agent_belief_does_not_override_successful_validation(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _DecisionAwareAgentSession(
                capabilities,
                [("1.0", "2.0")],
                completion_action="BLOCK",
            ),
            scanner_factory=_FixtureScanner,
        ).run()

        self._assert_final_decision_status(result, "BLOCKED", "PASSED", "VALIDATED")
        self.assertTrue(result.final_decision_state.warnings)

    def test_omitted_readiness_does_not_override_successful_validation(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _DecisionAwareAgentSession(
                capabilities,
                [("1.0", "2.0")],
                completion_action=None,
            ),
            scanner_factory=_FixtureScanner,
        ).run()

        self._assert_final_decision_status(result, "IN_PROGRESS", "PASSED", "VALIDATED")
        self.assertTrue(result.final_decision_state.warnings)

    def test_runtime_failure_before_validation_reports_not_run_and_incomplete(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _DecisionThenFailingAgentSession(
                capabilities
            ),
            scanner_factory=_FixtureScanner,
        ).run()

        self._assert_final_decision_status(result, "IN_PROGRESS", "NOT_RUN", "INCOMPLETE")

    def test_no_decision_events_preserves_legacy_cycle_and_final_shapes(self):
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: _UnstructuredAgentSession(),
            scanner_factory=_FixtureScanner,
        ).run()

        workspace_root = Path(result.workspace_root)
        cycle = json.loads(
            (workspace_root / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        final_result = json.loads(
            (workspace_root / "artifacts" / "final-result.json").read_text(encoding="utf-8")
        )
        self.assertEqual({"summary", "workingState"}, set(cycle))
        self.assertNotIn("finalDecisionState", final_result)
        self.assertNotIn("decisionEventCount", final_result)
        events = [
            json.loads(line)
            for line in (workspace_root / "artifacts" / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertTrue(
            any(
                event["type"] == "decision_warning"
                and "No material decision" in event["warning"]
                for event in events
            )
        )

    def test_missing_working_state_uses_bounded_fallback_without_failing_run(self):
        session = _UnstructuredAgentSession()
        result = AutonomousRemediationOrchestrator(
            self._request(max_cycles=1),
            agent_session_factory=lambda capabilities, model: session,
            scanner_factory=_FixtureScanner,
        ).run()

        self.assertEqual(Outcome.EXECUTION_LIMIT_REACHED, result.outcome)
        cycle = json.loads(
            (Path(result.workspace_root) / "artifacts" / "agent" / "cycle-1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertGreater(len(cycle["summary"]), len(cycle["workingState"]))
        self.assertIn("No structured WORKING_STATE was supplied", cycle["workingState"])
        self.assertLess(len(cycle["workingState"]), 800)

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

        self.assertEqual(Outcome.EXECUTION_LIMIT_REACHED, result.outcome)
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

    def _assert_final_decision_status(
        self,
        result,
        agent_status,
        validation_status,
        effective_status,
    ):
        state = result.final_decision_state
        self.assertIsNotNone(state)
        self.assertEqual(agent_status, state.agent_decision_state.agent_status.value)
        self.assertEqual(validation_status, state.deterministic_validation_status.value)
        self.assertEqual(effective_status, state.effective_resolution_status.value)


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
