"""Offline checks for the development evidence-boundary acceptance fixture."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from autonomous_oss_remediation_agent.journal import INTENT_SECTIONS, JournalLifecycle, JournalPhase, JournalStore
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore
from scripts.retained_evidence_acceptance import (
    FACT, run_until_intent, score_live_trace, verify_offline, verify_partial_read_offline, prepare,
)
from tests.checkpoint_fixtures import typed_intent_answers


def _answers():
    return typed_intent_answers([
        {"section": section, "answer": f"The observed fixture supports this section: {section}."}
        for section in INTENT_SECTIONS
    ])


class EvidenceBoundaryAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def _lifecycle(self):
        workspace = RunWorkspace.create(self.temp.name)
        workspace.repository.mkdir()
        trace = TraceStore(workspace)
        lifecycle = JournalLifecycle(JournalStore(trace), trace, "Fixture", lambda: False)
        lifecycle.append_task_to_solve("Select a documented setting")
        lifecycle.begin_cycle(1)
        return lifecycle, trace

    def test_retrieval_then_empty_turn_continues_same_session_to_accepted_intent(self):
        workspace, trace, budget, capabilities, display = prepare(Path(self.temp.name))
        lifecycle = JournalLifecycle(JournalStore(trace), trace, "Fixture", lambda: False)
        lifecycle.append_task_to_solve("Select a documented setting")
        lifecycle.begin_cycle(1)
        capabilities.journal = lifecycle
        class Session:
            def __init__(self):
                self.messages = []
                self.session_id = "same-session"

            async def run_turn(self, message):
                self.messages.append(message)
                if len(self.messages) == 1:
                    self.retrieval = capabilities.retrieve_retained_evidence(
                        display["stdoutReference"], query="ADAPTER_MODE")
                if len(self.messages) == 2:
                    self.result = lifecycle.submit_intent(1, _answers())

        session = Session()
        result = asyncio.run(run_until_intent(session, lifecycle, "first task"))
        self.assertEqual({"turns": 2, "stopReason": "accepted"}, result)
        self.assertTrue(session.result.accepted)
        self.assertEqual("ok", session.retrieval["status"])
        self.assertIn(FACT, session.retrieval["matches"][0]["text"])
        self.assertEqual("same-session", session.session_id)
        self.assertIn("No Problem Analysis and Solution Decision submission", session.messages[1])
        self.assertEqual(1, lifecycle.cycles[1].intent_attempts)

    def test_acceptance_stops_without_extra_turn(self):
        lifecycle, _ = self._lifecycle()
        class Session:
            calls = 0
            async def run_turn(self, message):
                self.calls += 1
                lifecycle.submit_intent(1, _answers())
        session = Session()
        self.assertEqual("accepted", asyncio.run(run_until_intent(session, lifecycle, "task"))["stopReason"])
        self.assertEqual(1, session.calls)

    def test_rejection_retries_and_exhaustion_stops(self):
        lifecycle, _ = self._lifecycle()
        class Session:
            def __init__(self):
                self.messages = []
            async def run_turn(self, message):
                self.messages.append(message)
                lifecycle.submit_intent(1, [])
        session = Session()
        result = asyncio.run(run_until_intent(session, lifecycle, "task"))
        self.assertEqual("checkpoint_attempts_exhausted", result["stopReason"])
        self.assertEqual(lifecycle.max_checkpoint_attempts, len(session.messages))
        self.assertIn("Rejection details", session.messages[1])
        self.assertEqual(lifecycle.max_checkpoint_attempts, lifecycle.cycles[1].intent_attempts)

    def test_score_distinguishes_retrieval_rejection_and_selected_provenance(self):
        lifecycle, trace = self._lifecycle()
        ref = "evidence:issued"
        display = {"stdoutReference": ref}
        budget = SimpleNamespace(config=SimpleNamespace(max_tool_calls=80), tool_calls=2)
        trace.append_event("adk_interaction", interactionType="tool_call", name="retrieve_retained_evidence",
                           arguments={"reference": ref, "query": "ADAPTER_MODE"})
        trace.append_event("adk_interaction", interactionType="tool_response", name="retrieve_retained_evidence",
                           response={"reference": ref, "matches": [{"text": FACT, "offset": 140000}]})
        empty = score_live_trace(trace, lifecycle, display, budget, {"turns": 1, "stopReason": "continuation_turns_exhausted"})
        self.assertTrue(empty["retrievalSuccess"])
        self.assertTrue(empty["noCheckpointSubmission"])
        self.assertFalse(empty["checkpointAccepted"])
        trace.append_event("intent_submission_rejected", attempt=1)
        rejected = score_live_trace(trace, lifecycle, display, budget, {"turns": 2, "stopReason": "checkpoint_attempts_exhausted"})
        self.assertEqual(1, rejected["rejectedSubmissions"])
        self.assertTrue(rejected["recoveryExhausted"])
        bad = [
            {"section": "Information, investigation and remaining uncertainty", "evidence": [
                {"finding": FACT, "source": ref}]},
            {"section": "Concrete candidate solutions", "candidates": [
                {"id": "A", "name": "batch", "solution": "Use batch"}]},
            {"section": "Selected solution", "selection": {"candidate_id": "A"}, "answer": FACT},
        ]
        trace.append_event("adk_interaction", interactionType="tool_call", name="submit_cycle_intent",
                           arguments={"answers": bad})
        trace.append_event("intent_submission_accepted", cycle=1)
        scored = score_live_trace(trace, lifecycle, display, budget, {"turns": 3, "stopReason": "accepted"})
        self.assertTrue(scored["checkpointAccepted"])
        self.assertFalse(scored["evidenceSupportedSelectedDecision"])
        self.assertFalse(scored["selectedCandidateConsistentWithFact"])
        bad[1]["candidates"][0].update(name="stream", solution="Use stream")
        trace.append_event("adk_interaction", interactionType="tool_call", name="submit_cycle_intent",
                           arguments={"answers": bad})
        selected = score_live_trace(trace, lifecycle, display, budget, {"turns": 3, "stopReason": "accepted"})
        self.assertTrue(selected["evidenceSupportedSelectedDecision"])
        bad[0]["evidence"][0]["source"] = "uncited source"
        trace.append_event("adk_interaction", interactionType="tool_call", name="submit_cycle_intent",
                           arguments={"answers": bad})
        uncited = score_live_trace(trace, lifecycle, display, budget, {"turns": 3, "stopReason": "accepted"})
        self.assertFalse(uncited["evidenceSupportedSelectedDecision"])

    def test_offline_capabilities_retention_and_partial_edit(self):
        workspace, trace, budget, capabilities, display = prepare(Path(self.temp.name))
        self.assertTrue(verify_offline(capabilities, display)["fullArtifactRetained"])
        other = RunWorkspace.create(self.temp.name)
        self.assertTrue(verify_partial_read_offline(other, TraceStore(other))["trailingSentinelPreserved"])


if __name__ == "__main__":
    unittest.main()
