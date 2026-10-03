"""Offline checks for the development evidence-boundary acceptance fixture."""
import asyncio
from copy import deepcopy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autonomous_oss_remediation_agent.journal import INTENT_SECTIONS, JournalLifecycle, JournalPhase, JournalStore
from autonomous_oss_remediation_agent.agent import (
    IntentToolRecoveryExhausted, IrrecoverableAgentSessionError, intent_tool_error_callback,
)
from autonomous_oss_remediation_agent.capabilities.execution import BudgetExceeded
from autonomous_oss_remediation_agent.orchestrator import AutonomousRemediationOrchestrator
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore
from scripts.retained_evidence_acceptance import (
    _accepted_intent_answers, FACT, main, run_until_intent, score_live_trace, verify_offline, verify_partial_read_offline, prepare,
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

    def _scored_intent(self, *, mode="stream", source=True, repair=True, artifact=False,
                       solution=None, candidate_citation=False, unrelated_citation=False, initial_extras=()):
        lifecycle, trace = self._lifecycle()
        retained = trace.write_text("commands/fixture.stdout.log", FACT)
        ref = trace.issue_evidence_reference(retained)
        display = {"stdoutReference": ref}
        budget = SimpleNamespace(config=SimpleNamespace(max_tool_calls=80), tool_calls=2)
        trace.append_event("adk_interaction", cycle=1, interactionType="tool_call", name="retrieve_retained_evidence",
                           arguments={"reference": ref, "query": "ADAPTER_MODE"})
        trace.append_event("adk_interaction", cycle=1, interactionType="tool_response", name="retrieve_retained_evidence",
                           response={"reference": ref, "matches": [{"text": FACT, "offset": 140000}]})
        empty = score_live_trace(trace, lifecycle, display, budget, {"turns": 1, "stopReason": "continuation_turns_exhausted"})
        self.assertTrue(empty["retrievalSuccess"])
        self.assertTrue(empty["noCheckpointSubmission"])
        self.assertFalse(empty["checkpointAccepted"])
        answers = _answers()
        if artifact:
            for item in answers[:3]:
                item["answer"] += " x" * 3000
        by_section = {item["section"]: item for item in answers}
        by_section["Information, investigation and remaining uncertainty"]["evidence"][0].update(
            source=ref if source is True else (source or "uncited source"), finding=FACT)
        by_section["Concrete candidate solutions"]["candidates"][0].update(
            name=f"{mode} adapter", solution=solution or f"Use {mode}",
            evidence=(f"{FACT} ({ref}, offset 140000)" if candidate_citation else
                      "The ADAPTER_MODE diagnostic setting determines this candidate."))
        if unrelated_citation:
            by_section["Concrete candidate solutions"]["candidates"].append({
                "id": "B", "name": "Unselected", "solution": "Use batch",
                "evidence": f"{FACT} ({ref})", "constraints": "Fixture only",
                "validation": "Check setting", "classification": "PARTIAL",
            })
        selection = by_section["Selected solution"]
        if repair:
            selection["selection"]["candidate_id"] = "missing"

        def record_call(items, *, retained_payload=False):
            detail = {"name": "submit_cycle_intent", "arguments": {"cycle_number": 1, "answers": items}}
            if retained_payload:
                encoded = json.dumps(detail, sort_keys=True, default=str).encode("utf-8")
                self.assertGreater(len(encoded), 16_384)
                path = trace.write_json("agent/interactions/fixture-call.json", detail)
                trace.append_event("adk_interaction", cycle=1, interactionType="tool_call",
                                   artifact=str(path), bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest())
            else:
                trace.append_event("adk_interaction", cycle=1, interactionType="tool_call", **detail)

        initial = answers + list(initial_extras)
        record_call(initial, retained_payload=artifact)
        first = lifecycle.submit_intent(1, initial)
        if repair:
            self.assertFalse(first.accepted)
            retry = {**selection, "selection": {**selection["selection"], "candidate_id": "A"}}
            record_call([retry])
            self.assertTrue(lifecycle.submit_intent(1, [retry]).accepted)
        else:
            self.assertTrue(first.accepted)
        scored = score_live_trace(trace, lifecycle, display, budget, {"turns": 2, "stopReason": "accepted"})
        return scored, lifecycle, trace, display, budget, record_call

    def test_section_only_repair_scores_accepted_merged_intent_and_retained_call(self):
        scored, lifecycle, trace, display, budget, _ = self._scored_intent(artifact=True)
        self.assertTrue(scored["acceptedRecordVerified"])
        self.assertEqual(1, scored["rejectedSubmissions"])
        self.assertTrue(scored["evidenceSupportedSelectedDecision"])
        self.assertTrue(scored["selectedEvidenceCitesIssuedReference"])

    def test_accepted_record_replay_skips_malformed_items_before_local_repair(self):
        from scripts.retained_evidence_acceptance import _accepted_intent_answers
        lifecycle, trace = self._lifecycle()
        answers = _answers()
        selected = answers[-1].copy()
        answers[-1].pop("section")
        interactions = [{"type": "adk_interaction", "interactionType": "tool_call",
                         "name": "submit_cycle_intent", "cycle": 1,
                         "arguments": {"cycle_number": 1, "answers": answers}}]
        self.assertFalse(lifecycle.submit_intent(1, answers).accepted)
        interactions.append({**interactions[0], "arguments": {"cycle_number": 1, "answers": [selected]}})
        result = lifecycle.submit_intent(1, [selected])
        self.assertTrue(result.accepted)
        acceptance = {"type": "intent_submission_accepted", "cycle": 1,
                      "contentHash": result.metadata.content_hash}
        interactions.append(acceptance)
        self.assertEqual(answers[:-1] + [selected], _accepted_intent_answers(interactions, lifecycle, acceptance))

    def test_empty_section_duplicates_retain_valid_sections_and_verify_accepted_score(self):
        scored, *_ = self._scored_intent(initial_extras=[
            {"section": "", "answer": "Malformed first item"},
            {"section": "", "answer": "Malformed second item"},
        ])
        self.assertTrue(scored["acceptedRecordVerified"])
        self.assertEqual(1, scored["rejectedSubmissions"])
        self.assertTrue(scored["evidenceSupportedSelectedDecision"])

    def _record_intent(self, lifecycle, trace, answers, *, cycle=1, event_cycle=1):
        trace.append_event("adk_interaction", cycle=event_cycle, interactionType="tool_call",
                           name="submit_cycle_intent", arguments={"cycle_number": cycle, "answers": answers})
        return lifecycle.submit_intent(cycle, answers)

    def _replay_intent(self, lifecycle, trace):
        events = [json.loads(line) for line in trace.events_path.read_text().splitlines()]
        accepted = next(e for e in events if e["type"] == "intent_submission_accepted")
        return _accepted_intent_answers(events, lifecycle, accepted)

    def test_duplicate_gate_matches_production_for_raw_and_invalid_labels(self):
        # Expected retention is asserted independently of replay and the shared helper.
        for labels, retained in [(["", ""], True), ([" ", " "], False),
                                 ([None, None], False), ([7, "7"], False),
                                 ([" ", "\t"], True)]:
            with self.subTest(labels=labels):
                lifecycle, trace = self._lifecycle()
                answers = _answers()
                self.assertFalse(self._record_intent(lifecycle, trace, answers[:-1]).accepted)
                changed = {**answers[0], "answer": "New observed analysis must only survive an allowed merge."}
                malformed = [{"section": label, "answer": "Malformed label"} for label in labels]
                rejected = self._record_intent(lifecycle, trace, [changed] + malformed)
                self.assertFalse(rejected.accepted)
                self.assertTrue(self._record_intent(lifecycle, trace, [answers[-1]]).accepted)
                expected = [changed if retained else answers[0]] + answers[1:]
                self.assertEqual(expected[0]["answer"], lifecycle.cycles[1].intent_answers[answers[0]["section"]])
                self.assertEqual(expected, self._replay_intent(lifecycle, trace))

    def test_genuine_duplicates_cannot_update_replay_draft(self):
        lifecycle, trace = self._lifecycle()
        answers = _answers()
        self.assertFalse(self._record_intent(lifecycle, trace, answers[:-1]).accepted)
        changed = {**answers[0], "answer": "This duplicate submission must not replace the retained answer."}
        rejected = self._record_intent(lifecycle, trace, [changed, changed, answers[-1]])
        self.assertFalse(rejected.accepted)
        self.assertIn(f"Duplicate section: {changed['section']}", rejected.errors)
        self.assertTrue(self._record_intent(lifecycle, trace, [answers[-1]]).accepted)
        self.assertEqual(answers, self._replay_intent(lifecycle, trace))

    def test_missing_invalid_and_malformed_repairs_preserve_valid_draft(self):
        lifecycle, trace = self._lifecycle()
        answers = _answers()
        malformed = [{"answer": "No section"}, {"section": None, "answer": "Invalid section"},
                     {"section": [], "answer": "Invalid list section"}, None]
        self.assertFalse(self._record_intent(lifecycle, trace, answers[:-1] + malformed).accepted)
        for value in [None, "", " ", 42]:
            self.assertFalse(self._record_intent(lifecycle, trace, [
                {"section": answers[0]["section"], "answer": value}]).accepted)
        self.assertFalse(self._record_intent(lifecycle, trace, [{"section": answers[0]["section"]}]).accepted)
        self.assertTrue(self._record_intent(lifecycle, trace, [answers[-1]]).accepted)
        self.assertEqual(answers, self._replay_intent(lifecycle, trace))

    def test_distinct_raw_labels_merge_using_stripped_section_keys(self):
        lifecycle, trace = self._lifecycle()
        answers = _answers()
        changed = {**answers[0], "section": " " + answers[0]["section"] + " ",
                   "answer": "Updated analysis from a distinct raw label that maps to the same draft key."}
        self.assertFalse(self._record_intent(lifecycle, trace, answers[:-1] + [changed]).accepted)
        self.assertTrue(self._record_intent(lifecycle, trace, [answers[-1]]).accepted)
        self.assertEqual([changed] + answers[1:], self._replay_intent(lifecycle, trace))

    def test_replay_ignores_other_cycles_and_rejects_byte_or_hash_mismatch(self):
        lifecycle, trace = self._lifecycle()
        answers = _answers()
        self.assertFalse(self._record_intent(lifecycle, trace, answers[:-1]).accepted)
        other = [{**answers[0], "answer": "Unrelated cycle must not overwrite this draft."}]
        self.assertFalse(self._record_intent(lifecycle, trace, other, cycle=2).accepted)
        trace.append_event("adk_interaction", cycle=2, interactionType="tool_call",
                           name="submit_cycle_intent", arguments={"cycle_number": 1, "answers": other})
        self.assertTrue(self._record_intent(lifecycle, trace, [answers[-1]]).accepted)
        self.assertEqual(answers, self._replay_intent(lifecycle, trace))
        events = [json.loads(line) for line in trace.events_path.read_text().splitlines()]
        accepted = next(e for e in events if e["type"] == "intent_submission_accepted")
        self.assertIsNone(_accepted_intent_answers(events, lifecycle, {**accepted, "contentHash": "wrong"}))
        tampered = deepcopy(events)
        call = next(e for e in tampered if e.get("name") == "submit_cycle_intent")
        call["arguments"]["answers"][0]["answer"] = "Tampered call text"
        self.assertIsNone(_accepted_intent_answers(tampered, lifecycle, accepted))
        original = lifecycle.store.path.read_bytes()
        lifecycle.store.path.write_bytes(original.replace(b"The observed fixture", b"The altered fixture", 1))
        self.assertIsNone(self._replay_intent(lifecycle, trace))

    def test_later_unaccepted_call_cannot_change_accepted_score(self):
        scored, lifecycle, trace, display, budget, record_call = self._scored_intent()
        self.assertTrue(scored["evidenceSupportedSelectedDecision"])
        later = _answers()
        later[3]["candidates"][0]["solution"] = "Use batch"
        record_call(later)
        self.assertFalse(lifecycle.submit_intent(1, later).accepted)
        after = score_live_trace(trace, lifecycle, display, budget, {"turns": 2, "stopReason": "accepted"})
        self.assertTrue(after["acceptedRecordVerified"])
        self.assertTrue(after["evidenceSupportedSelectedDecision"])

    def test_batch_selection_and_missing_provenance_do_not_pass(self):
        batch, *_ = self._scored_intent(mode="batch")
        self.assertTrue(batch["acceptedRecordVerified"])
        self.assertFalse(batch["evidenceSupportedSelectedDecision"])
        self.assertEqual("mechanically_contradicted", batch["decisionScreen"])
        uncited, *_ = self._scored_intent(source=False)
        self.assertTrue(uncited["selectedCandidateConsistentWithFact"])
        self.assertFalse(uncited["evidenceSupportedSelectedDecision"])
        self.assertEqual("missing_evidence", uncited["decisionScreen"])
        wrong, *_ = self._scored_intent(source="evidence:wrong-reference")
        self.assertFalse(wrong["evidenceSupportedSelectedDecision"])

    def test_observed_accepted_wording_and_selected_candidate_citation(self):
        scored, *_ = self._scored_intent(
            source=False, candidate_citation=True,
            solution="The `ADAPTER_MODE` for the fixture service should be set to `stream`.")
        self.assertEqual("mechanically_supported", scored["decisionScreen"])
        self.assertTrue(scored["selectedEvidenceCitesIssuedReference"])

    def test_ambiguous_prose_and_unrelated_citation_require_review(self):
        ambiguous, *_ = self._scored_intent(solution="Use stream or batch")
        self.assertEqual("ambiguous_manual_review", ambiguous["decisionScreen"])
        negated, *_ = self._scored_intent(solution="Stream is not supported")
        self.assertEqual("ambiguous_manual_review", negated["decisionScreen"])
        conditional, *_ = self._scored_intent(solution="Batch might be appropriate")
        self.assertEqual("ambiguous_manual_review", conditional["decisionScreen"])
        unrelated, *_ = self._scored_intent(source=False, unrelated_citation=True)
        self.assertEqual("missing_evidence", unrelated["decisionScreen"])

    def test_production_no_submission_feedback_preserves_unknown_call_state(self):
        workspace, trace, budget, capabilities, display = prepare(Path(self.temp.name))
        lifecycle = JournalLifecycle(JournalStore(trace), trace, "Fixture", lambda: False)
        lifecycle.append_task_to_solve("Select documented setting")
        lifecycle.begin_cycle(1)
        capabilities.journal = lifecycle
        declarations = {tool.name: tool._get_declaration() for tool in capabilities.adk_tools()}
        self.assertIn("submit_cycle_intent", declarations)
        self.assertNotIn("SubmitCycleIntentAnswers", declarations)
        self.assertNotIn("SubmitCycleIntentAnswersEvidence", declarations)
        nested = declarations["submit_cycle_intent"].parameters_json_schema["$defs"]
        self.assertTrue({"IntentAnswer", "EvidenceRecord", "CandidateRecord", "SelectionRecord"}
                        <= set(nested))
        callback = intent_tool_error_callback(capabilities)
        class Session:
            def __init__(self):
                self.messages = []
            async def run_turn(self, message):
                self.messages.append(message)
                if len(self.messages) == 1:
                    for _ in range(3):
                        response = callback(SimpleNamespace(name="SubmitCycleIntentAnswers",
                                                            description="Tool not found"), {}, None,
                                            ValueError("Tool not found"))
                    self.feedback = response
                else:
                    self.result = lifecycle.submit_intent(1, _answers())
        session = Session()
        runner = object.__new__(AutonomousRemediationOrchestrator)
        asyncio.run(runner._run_until_intent(session, lifecycle, 1, "initial task"))
        self.assertEqual(7, session.feedback["remainingAttempts"])
        self.assertIn("3 unregistered tool call(s)", session.messages[1])
        self.assertIn("7 attempt(s) remain", session.messages[1])
        self.assertIn("no submitted answer sections are retained", session.messages[1])
        self.assertIn("`submit_cycle_intent`", session.messages[1])
        self.assertTrue(session.result.accepted)

    def test_terminal_checkpoint_exhaustion_is_not_shared_tool_or_infrastructure_failure(self):
        from scripts.retained_evidence_acceptance import verify_live
        workspace, trace, budget, capabilities, display = prepare(Path(self.temp.name))
        class Session:
            def __init__(self, error):
                self.error = error
            async def run_turn(self, message):
                capabilities.retrieve_retained_evidence(display["stdoutReference"], query="ADAPTER_MODE")
                for _ in range(10):
                    capabilities.journal.reserve_checkpoint_attempt("intent", "unknown_tool")
                raise self.error
            async def close(self):
                pass
        with patch("scripts.retained_evidence_acceptance.create_remediation_agent", return_value=object()), \
             patch("scripts.retained_evidence_acceptance.GoogleAdkAgentSession",
                   return_value=Session(IntentToolRecoveryExhausted("ten unknown calls"))):
            result = asyncio.run(verify_live(trace, budget, capabilities, display, "scripted"))
        self.assertTrue(result["recoveryExhausted"])
        self.assertEqual("checkpoint_recovery_exhausted", result["terminalCategory"])
        self.assertIn("IntentToolRecoveryExhausted: ten unknown calls", result["terminalError"])
        self.assertEqual(10, result["checkpointAttempts"])
        self.assertEqual(78, result["remainingToolCalls"])

        other, trace2, budget2, capabilities2, display2 = prepare(Path(self.temp.name))
        class InfrastructureSession:
            async def run_turn(self, message):
                raise IrrecoverableAgentSessionError("session transport failed")
            async def close(self):
                pass
        with patch("scripts.retained_evidence_acceptance.create_remediation_agent", return_value=object()), \
             patch("scripts.retained_evidence_acceptance.GoogleAdkAgentSession",
                   return_value=InfrastructureSession()):
            infrastructure = asyncio.run(verify_live(trace2, budget2, capabilities2, display2, "scripted"))
        self.assertFalse(infrastructure["recoveryExhausted"])
        self.assertEqual("infrastructure_error", infrastructure["terminalCategory"])

        third, trace3, budget3, capabilities3, display3 = prepare(Path(self.temp.name))
        class BudgetSession:
            async def run_turn(self, message):
                raise BudgetExceeded("ordinary tool budget reached")
            async def close(self):
                pass
        with patch("scripts.retained_evidence_acceptance.create_remediation_agent", return_value=object()), \
             patch("scripts.retained_evidence_acceptance.GoogleAdkAgentSession",
                   return_value=BudgetSession()):
            budget_result = asyncio.run(verify_live(trace3, budget3, capabilities3, display3, "scripted"))
        self.assertFalse(budget_result["recoveryExhausted"])
        self.assertEqual("budget_exceeded", budget_result["terminalCategory"])

    def test_offline_capabilities_retention_and_partial_edit(self):
        workspace, trace, budget, capabilities, display = prepare(Path(self.temp.name))
        self.assertTrue(verify_offline(capabilities, display)["fullArtifactRetained"])
        other = RunWorkspace.create(self.temp.name)
        self.assertTrue(verify_partial_read_offline(other, TraceStore(other))["trailingSentinelPreserved"])

    def _run_cli(self, *arguments):
        output = io.StringIO()
        with patch.object(sys, "argv", ["retained_evidence_acceptance", *arguments]), redirect_stdout(output):
            status = main()
        return status, json.loads(output.getvalue())["trials"]

    def test_explicit_folder_retains_both_scenarios_and_independent_trials(self):
        parent = Path(self.temp.name) / "explicit"
        status, command = self._run_cli("--scenario", "retained-command", "--trials", "2",
                                        "--workspace-parent", str(parent))
        self.assertEqual(0, status)
        self.assertEqual(2, len({item["workspace"] for item in command}))
        status, partial = self._run_cli("--scenario", "partial-read-edit",
                                        "--workspace-parent", str(parent))
        self.assertEqual(0, status)
        for item in [*command, *partial]:
            self.assertTrue(item["artifactsRetained"])
            self.assertTrue(Path(item["trace"]).is_file())
            self.assertTrue(Path(item["resultArtifact"]).is_file())
        self.assertTrue(partial[0]["trailingSentinelPreserved"])

    def test_default_offline_temp_and_failure_report_location(self):
        status, trials = self._run_cli("--scenario", "retained-command", "--trials", "2")
        self.assertEqual(0, status)
        self.assertEqual(2, len({item["workspace"] for item in trials}))
        self.assertTrue(all(not item["artifactsRetained"] for item in trials))
        self.assertTrue(all(not Path(item["workspace"]).exists() for item in trials))
        parent = Path(self.temp.name) / "failed"
        with patch("scripts.retained_evidence_acceptance.verify_offline", side_effect=RuntimeError("fixture failure")):
            status, failed = self._run_cli("--workspace-parent", str(parent))
        self.assertEqual(1, status)
        self.assertIn("fixture failure", failed[0]["terminalError"])
        self.assertTrue(Path(failed[0]["workspace"]).is_dir())
        self.assertTrue(Path(failed[0]["resultArtifact"]).is_file())


if __name__ == "__main__":
    unittest.main()
