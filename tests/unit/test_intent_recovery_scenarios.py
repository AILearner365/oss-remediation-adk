"""Deterministic controls for reusable live cases; no paid model calls."""
import asyncio
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.auth.exceptions import DefaultCredentialsError

from autonomous_oss_remediation_agent.agent import IntentToolRecoveryExhausted
from autonomous_oss_remediation_agent.capabilities.execution import BudgetExceeded
from autonomous_oss_remediation_agent.capabilities.isolation import ExperimentalIsolationUnavailable
from autonomous_oss_remediation_agent.workspace import RunWorkspace
from scripts.intent_recovery_scenarios import (
    CASES, prepare_recovery, run_recovery, score_recovery, seed_answers,
)
from scripts.retained_evidence_acceptance import main
from tests.unit.test_intent_tool_recovery import _ScriptedModel


class IntentRecoveryScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def fixture(self, case=CASES[0]):
        return prepare_recovery(RunWorkspace.create(self.temp.name), case)

    def repaired(self, fixture, partial=True):
        reference = fixture.seed["arguments"]["answers"][1]["evidence"][0]["source"]
        answers = seed_answers(reference)
        if partial:
            return answers[4:] if fixture.seed["case"] == CASES[0] else answers[3:]
        return answers

    def run_scripted(self, fixture, steps):
        model = _ScriptedModel(steps)
        with patch("autonomous_oss_remediation_agent.agent.Gemini", return_value=model):
            return asyncio.run(run_recovery(fixture, "scripted-intent-model"))

    def test_seed_cases_have_exact_observed_shapes_feedback_and_retained_state(self):
        for case in CASES:
            with self.subTest(case=case):
                fixture = self.fixture(case)
                self.assertTrue(all(fixture.checks.values()))
                seed = fixture.seed
                answers = seed["arguments"]["answers"]
                if case == CASES[0]:
                    self.assertNotIn("section", answers[4])
                    self.assertTrue(answers[4]["answer"])
                    self.assertTrue(answers[4]["selection"])
                    self.assertIn("answers[4].section: missing required 'section' field", seed["response"]["errors"])
                    self.assertEqual(answers[:4], seed["retainedDraft"])
                else:
                    for index, key in [(3, "candidates"), (4, "selection")]:
                        self.assertNotIn("answer", answers[index])
                        self.assertNotIn("content", answers[index])
                        self.assertTrue(answers[index][key])
                        self.assertTrue(any(e.startswith(f"answers[{index}]") and ".answer:" in e for e in seed["response"]["errors"]))
                    self.assertEqual(answers[:3], seed["retainedDraft"])
                self.assertNotIn("content", seed["continuation"])
                for detail in seed["response"]["errors"] + seed["response"]["repairInstructions"]:
                    self.assertIn(detail, fixture.message)
                self.assertEqual(1, seed["checkpointAttemptsAfterSeed"])
                self.assertEqual(0, seed["toolCallsAfterSeed"])
                self.assertEqual("PHASE_CAPABILITY_UNAVAILABLE", seed["mutationProbe"]["failureCode"])
                self.assertEqual(seed["repositoryDigestBefore"], seed["repositoryDigestAfterProbe"])
                self.assertEqual("NOT_EXERCISED", score_recovery(fixture, live=False)["outcome"])
                events = fixture.trace.events_path.read_text()
                self.assertIn('"type": "controlled_intent_seed"', events)
                self.assertNotIn('"type": "adk_interaction"', events)

    def test_real_adk_partial_and_complete_repairs_pass_both_cases(self):
        for case in CASES:
            for partial in [True, False]:
                with self.subTest(case=case, partial=partial):
                    fixture = self.fixture(case)
                    result = self.run_scripted(fixture, [
                        ("submit_cycle_intent", {"cycle_number": 1, "answers": self.repaired(fixture, partial)}),
                        "Decision recorded",
                    ])
                    self.assertEqual("PASSED", result["outcome"], result)
                    self.assertTrue(all(result["checks"].values()))
                    self.assertEqual(partial, result["sectionOnlyRepairObserved"])
                    self.assertEqual(2, result["checkpointAttempts"])
                    self.assertEqual(1, len(result["sessionIds"]))
                    self.assertEqual(1, result["continuationTurns"])
                    self.assertEqual("NOT_EXERCISED", result["naturalAutonomousRecovery"])
                    self.assertEqual(fixture.lifecycle.cycles[1].intent.content_hash, result["acceptedContentHash"])

    def test_actual_continuation_after_empty_turn_uses_same_session(self):
        fixture = self.fixture()
        result = self.run_scripted(fixture, ["Continue next turn",
            ("submit_cycle_intent", {"cycle_number": 1, "answers": self.repaired(fixture)}), "Done"])
        self.assertEqual("PASSED", result["outcome"])
        self.assertEqual(2, result["continuationTurns"])
        self.assertEqual(1, len(result["sessionIds"]))
        events = [json.loads(line) for line in fixture.trace.events_path.read_text().splitlines()]
        turns = [e for e in events if e.get("interactionType") == "turn_started"]
        self.assertEqual(fixture.seed["continuation"], turns[1]["message"])

    def test_repeated_supported_malformed_calls_exhaust_existing_allowance(self):
        fixture = self.fixture()
        malformed = deepcopy(fixture.seed["arguments"])
        result = self.run_scripted(fixture, [("submit_cycle_intent", malformed)] * 9 + ["Unable to repair"])
        self.assertEqual("FAILED", result["outcome"])
        self.assertTrue(result["recoveryExhausted"])
        self.assertEqual(10, result["checkpointAttempts"])
        self.assertFalse(result["checkpointAccepted"])
        self.assertEqual("checkpoint_attempts_exhausted", result["stopReason"])

    def test_empty_turn_exhaustion_does_not_claim_checkpoint_attempts(self):
        fixture = self.fixture()
        result = self.run_scripted(fixture, ["No submission"] * 10)
        self.assertEqual("FAILED", result["outcome"])
        self.assertTrue(result["recoveryExhausted"])
        self.assertEqual(1, result["checkpointAttempts"])
        self.assertEqual(10, result["continuationTurns"])

    def test_terminal_failure_and_blocked_reporting(self):
        for error, outcome, exhausted in [
            (DefaultCredentialsError("No test credentials"), "BLOCKED", False),
            (RuntimeError("Fixture defect"), "FAILED", False),
            (BudgetExceeded("Deadline"), "FAILED", True),
            (LlmCallsLimitExceededError("Model-call limit"), "FAILED", True),
            (IntentToolRecoveryExhausted("Checkpoint exhausted"), "FAILED", True),
        ]:
            with self.subTest(error=type(error).__name__):
                fixture = self.fixture()
                with patch("scripts.intent_recovery_scenarios.default_agent_session_factory", side_effect=error):
                    result = asyncio.run(run_recovery(fixture, "unused"))
                self.assertEqual(outcome, result["outcome"])
                self.assertEqual(exhausted, result["recoveryExhausted"])
                self.assertIn(str(error), result["terminalError"])
                self.assertFalse(result["passed"])

    def test_seed_failure_prevents_live_session(self):
        fixture = self.fixture()
        fixture.checks["preIntentMutationDenied"] = False
        with patch("scripts.intent_recovery_scenarios.default_agent_session_factory") as factory:
            result = asyncio.run(run_recovery(fixture, "unused"))
        factory.assert_not_called()
        self.assertEqual("FAILED", result["outcome"])

    def test_accepted_bytes_are_required_and_later_calls_cannot_change_replay(self):
        fixture = self.fixture()
        result = self.run_scripted(fixture, [
            ("submit_cycle_intent", {"cycle_number": 1, "answers": self.repaired(fixture)}), "Done"])
        self.assertEqual("PASSED", result["outcome"])
        fixture.trace.append_event("adk_interaction", cycle=1, sessionId=result["sessionIds"][0],
                                   interactionType="tool_call", name="submit_cycle_intent",
                                   arguments={"cycle_number": 1, "answers": []})
        self.assertEqual("PASSED", score_recovery(fixture, live=True)["outcome"])
        journal = fixture.lifecycle.store.path
        journal.write_bytes(journal.read_bytes().replace(b"Select stream mode", b"Select batch mode", 1))
        result = score_recovery(fixture, live=True)
        self.assertEqual("FAILED", result["outcome"])
        self.assertFalse(result["checks"]["acceptedRecordVerified"])

    def cli(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", ["fixture", *args]), redirect_stdout(output):
            status = main()
        return status, json.loads(output.getvalue())["trials"][0]

    def test_offline_cli_retains_both_runnable_cases_without_live_claim(self):
        with patch("scripts.intent_recovery_scenarios.default_agent_session_factory") as factory:
            for case in CASES:
                status, result = self.cli("--scenario", case, "--workspace-parent", self.temp.name)
                self.assertEqual(0, status)
                self.assertEqual("NOT_EXERCISED", result["outcome"])
                self.assertEqual("PASSED", result["offlineMechanics"])
                artifact = Path(result["resultArtifact"])
                self.assertEqual(result, json.loads(artifact.read_text()))
                for name in ["seed.json", "model-input.txt", "diagnostic.txt"]:
                    self.assertTrue((artifact.parent / "fixture" / name).is_file())
            factory.assert_not_called()

    def test_cli_retains_blocked_execution_and_setup_failure(self):
        with patch("scripts.intent_recovery_scenarios.default_agent_session_factory",
                   side_effect=DefaultCredentialsError("No test credentials")):
            status, result = self.cli("--scenario", CASES[0], "--live", "--workspace-parent", self.temp.name)
        self.assertEqual(1, status)
        self.assertEqual("BLOCKED", result["outcome"])
        self.assertTrue(Path(result["resultArtifact"]).is_file())
        with patch("scripts.retained_evidence_acceptance.prepare_recovery",
                   side_effect=ExperimentalIsolationUnavailable("Unsupported runner")):
            status, result = self.cli("--scenario", CASES[1], "--workspace-parent", self.temp.name)
        self.assertEqual(1, status)
        self.assertEqual("BLOCKED", result["outcome"])
        self.assertTrue(Path(result["resultArtifact"]).is_file())

    def test_live_requires_explicit_retention_folder(self):
        with patch.object(sys, "argv", ["fixture", "--scenario", CASES[0], "--live"]):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(2, error.exception.code)


if __name__ == "__main__":
    unittest.main()
