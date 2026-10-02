from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from autonomous_oss_remediation_agent.agent import (
    GoogleAdkAgentSession,
    IntentToolRecoveryExhausted,
    create_remediation_agent,
)
from autonomous_oss_remediation_agent.capabilities import (
    DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO,
)
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig, RuntimePolicy
from autonomous_oss_remediation_agent.journal import JournalLifecycle, JournalPhase, JournalStore
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore
from tests.unit import test_decision_journal


class _ScriptedModel(BaseLlm):
    _steps: list = PrivateAttr(default_factory=list)
    _requests: list = PrivateAttr(default_factory=list)
    _observed: list = PrivateAttr(default_factory=list)
    _inspect: object = PrivateAttr(default=None)

    def __init__(self, steps, inspect=None):
        super().__init__(model="scripted-intent-model")
        self._steps = list(steps)
        self._inspect = inspect

    async def generate_content_async(self, llm_request, stream=False):
        self._requests.append(llm_request)
        if self._inspect:
            self._observed.append(self._inspect())
        step = self._steps.pop(0)
        if isinstance(step, tuple):
            name, args = step
            content = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))])
        else:
            content = types.Content(role="model", parts=[types.Part(text=step)])
        yield LlmResponse(content=content)


class IntentToolRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.workspace.repository.mkdir()
        self.pom = self.workspace.repository / "pom.xml"
        self.pom.write_text("<demo.version>1.0</demo.version>\n", encoding="utf-8")
        self.trace = TraceStore(self.workspace)
        self.journal = JournalLifecycle(JournalStore(self.trace), self.trace, "contract", lambda: False)
        self.budget = ExecutionBudget(ExecutionBudgetConfig(
            max_cycles=2, max_tool_calls=20, max_llm_calls_per_turn=30,
            overall_timeout_seconds=60, model_turn_timeout_seconds=30,
        ))
        policy = RuntimePolicy(True, True, True)
        runner = ProcessRunner(self.workspace, self.trace, self.budget, policy)
        self.capabilities = DeveloperCapabilitySet(
            WorkspaceIO(self.workspace, self.trace), runner, self.budget, self.trace, self.journal,
        )
        self.capabilities.begin_cycle(1)
        self.journal.begin_cycle(1)
        self.session = None

    async def asyncTearDown(self):
        if self.session:
            await self.session.close()
        self.temp.cleanup()

    def _session(self, steps, inspect=None):
        model = _ScriptedModel(steps, inspect)
        with patch("autonomous_oss_remediation_agent.agent.Gemini", return_value=model):
            agent = create_remediation_agent(self.capabilities, "scripted-intent-model")
        self.session = GoogleAdkAgentSession(
            agent, self.budget, trace=self.trace, cycle_provider=lambda: self.journal.active_cycle,
        )
        return model

    def _interactions(self, kind):
        return [json.loads(line) for line in self.trace.events_path.read_text(encoding="utf-8").splitlines()
                if '"interactionType": "' + kind + '"' in line]

    async def test_unknown_tool_receives_adk_correction_then_valid_intent_allows_edit(self):
        answers = test_decision_journal.DecisionJournalTests._intent_answers()
        model = self._session([
            ("SubmitCycleIntentAnswers", {"section": "Selected solution", "answer": "text"}),
            ("submit_cycle_intent", {"cycle_number": 1, "answers": answers}),
            ("edit_workspace_text", {"action": "replace", "path": "pom.xml",
                                      "old_text": "1.0", "new_text": "2.0"}),
            "Implementation started",
        ], inspect=lambda: self.pom.read_text(encoding="utf-8"))
        await self.session.run_turn("Submit Cycle Intent")
        self.assertEqual(JournalPhase.EXECUTION, self.journal.phase)
        self.assertIn("2.0", self.pom.read_text(encoding="utf-8"))
        responses = self._interactions("tool_response")
        self.assertEqual("SubmitCycleIntentAnswers", responses[0]["name"])
        self.assertIn("`submit_cycle_intent`", responses[0]["response"]["repairInstructions"])
        self.assertEqual("accepted", responses[1]["response"]["status"])
        self.assertEqual(0, self.journal.cycles[1].rejected_intents)
        self.assertEqual(4, len(model._requests))
        self.assertEqual(["<demo.version>1.0</demo.version>\n"] * 3
                         + ["<demo.version>2.0</demo.version>\n"], model._observed)
        calls = self._interactions("tool_call")
        self.assertEqual(["SubmitCycleIntentAnswers", "submit_cycle_intent", "edit_workspace_text"],
                         [call["name"] for call in calls])

    async def test_repeated_unknown_calls_reach_shared_checkpoint_bound(self):
        self._session([("google:python_interpreter", {"code": "pass"})] * 11)
        with self.assertRaises(IntentToolRecoveryExhausted):
            await self.session.run_turn("Submit Cycle Intent")
        self.assertEqual(JournalPhase.INTENT_REQUIRED, self.journal.phase)
        self.assertIsNone(self.journal.cycles[1].intent)
        self.assertEqual("<demo.version>1.0</demo.version>\n", self.pom.read_text(encoding="utf-8"))
        responses = self._interactions("tool_response")
        self.assertEqual(10, len(responses))
        self.assertFalse(responses[-1]["response"]["retryAllowed"])
        self.assertEqual(10, self.journal.cycles[1].intent_attempts)

    @staticmethod
    def _malformed_intent():
        answers = test_decision_journal.DecisionJournalTests._intent_answers()
        next(item for item in answers if item["section"] == "Information, investigation and remaining uncertainty").pop("evidence")
        return answers

    async def _mixed_intent(self, first: str, *, succeeds: bool):
        valid = test_decision_journal.DecisionJournalTests._intent_answers()
        unknown = ("invented_tool", {})
        rejected = ("submit_cycle_intent", {"cycle_number": 1, "answers": self._malformed_intent()})
        valid_call = ("submit_cycle_intent", {"cycle_number": 1, "answers": valid})
        prefix = ([unknown] * 8 + [rejected] if first == "unknown" else
                  [rejected] * 8 + [unknown])
        if not succeeds:
            prefix.insert(8, unknown if first == "unknown" else rejected)
        steps = prefix + [valid_call]
        if succeeds:
            steps.append(("edit_workspace_text", {"action": "replace", "path": "pom.xml",
                                                  "old_text": "1.0", "new_text": "2.0"}))
        steps.append("Done")
        model = self._session(steps, inspect=lambda: self.pom.read_text(encoding="utf-8"))
        await self.session.run_turn("Submit Intent")
        responses = self._interactions("tool_response")
        self.assertEqual(10, self.journal.cycles[1].intent_attempts)
        self.assertEqual(succeeds, self.journal.phase == JournalPhase.EXECUTION)
        self.assertEqual("accepted" if succeeds else "rejected", responses[-2 if succeeds else -1]["response"]["status"])
        self.assertEqual(["<demo.version>1.0</demo.version>\n"] * (len(model._observed) - (1 if succeeds else 0)),
                         model._observed[:-1] if succeeds else model._observed)
        if succeeds:
            self.assertIn("2.0", self.pom.read_text(encoding="utf-8"))
        else:
            self.assertFalse(responses[-2]["response"]["retryAllowed"])
            self.assertFalse(responses[-1]["response"]["retryAllowed"])
            self.assertEqual("<demo.version>1.0</demo.version>\n", self.pom.read_text(encoding="utf-8"))

    async def test_unknown_then_rejected_intent_can_succeed_on_tenth_attempt(self):
        await self._mixed_intent("unknown", succeeds=True)

    async def test_rejected_intent_then_unknown_can_succeed_on_tenth_attempt(self):
        await self._mixed_intent("rejected", succeeds=True)

    async def test_unknown_then_rejected_intent_exhausts_before_valid_submission(self):
        await self._mixed_intent("unknown", succeeds=False)

    async def test_rejected_intent_then_unknown_exhausts_before_valid_submission(self):
        await self._mixed_intent("rejected", succeeds=False)

    async def test_outcome_uses_its_own_shared_checkpoint_allowance(self):
        self.assertTrue(self.journal.submit_intent(1, test_decision_journal.DecisionJournalTests._intent_answers()).accepted)
        self.journal.require_outcome()
        invalid = ("submit_cycle_outcome", {"cycle_number": 1, "status": "FAILED",
                                            "status_explanation": "Incomplete report", "answers": []})
        valid = ("submit_cycle_outcome", {"cycle_number": 1, "status": "FAILED",
                                          "status_explanation": "Execution was incomplete.",
                                          "answers": test_decision_journal.DecisionJournalTests._outcome_answers()[:2]})
        self._session([("invented_outcome_tool", {})] * 8 + [invalid, valid, "Done"])
        await self.session.run_turn("Submit Outcome")
        responses = self._interactions("tool_response")
        self.assertEqual("accepted", responses[-1]["response"]["status"])
        self.assertEqual(10, self.journal.cycles[1].outcome_attempts)
        self.assertEqual(JournalPhase.DETERMINISTIC_VALIDATION, self.journal.phase)

    async def test_outcome_mixed_attempts_block_later_valid_submission(self):
        self.assertTrue(self.journal.submit_intent(1, test_decision_journal.DecisionJournalTests._intent_answers()).accepted)
        self.journal.require_outcome()
        invalid = ("submit_cycle_outcome", {"cycle_number": 1, "status": "FAILED",
                                            "status_explanation": "Incomplete report", "answers": []})
        valid = ("submit_cycle_outcome", {"cycle_number": 1, "status": "FAILED",
                                          "status_explanation": "Execution was incomplete.",
                                          "answers": test_decision_journal.DecisionJournalTests._outcome_answers()[:2]})
        self._session([invalid] * 9 + [("invented_outcome_tool", {}), valid, "Done"])
        await self.session.run_turn("Submit Outcome")
        responses = self._interactions("tool_response")
        self.assertEqual(10, self.journal.cycles[1].outcome_attempts)
        self.assertFalse(responses[-2]["response"]["retryAllowed"])
        self.assertFalse(responses[-1]["response"]["retryAllowed"])
        self.assertEqual("rejected", responses[-1]["response"]["status"])
        self.assertEqual(JournalPhase.OUTCOME_REQUIRED, self.journal.phase)

    async def test_oversized_intent_rejection_can_be_corrected_in_same_adk_turn(self):
        valid = test_decision_journal.DecisionJournalTests._intent_answers()
        oversized = [dict(item) for item in valid]
        oversized[0]["answer"] += "x" * 8000
        self._session([
            ("submit_cycle_intent", {"cycle_number": 1, "answers": oversized}),
            ("submit_cycle_intent", {"cycle_number": 1, "answers": valid}),
            "Intent accepted",
        ])
        await self.session.run_turn("Submit Cycle Intent")
        responses = self._interactions("tool_response")
        self.assertEqual("rejected", responses[0]["response"]["status"])
        self.assertIn("Section exceeds 8000", str(responses[0]["response"]["errors"]))
        self.assertIn("Shorten the named section", str(responses[0]["response"]["repairInstructions"]))
        self.assertEqual("accepted", responses[1]["response"]["status"])
        self.assertEqual("<demo.version>1.0</demo.version>\n", self.pom.read_text(encoding="utf-8"))
        self.assertEqual(1, self.journal.cycles[1].rejected_intents)

    async def test_phase_toolset_and_unknown_call_after_intent(self):
        answers = test_decision_journal.DecisionJournalTests._intent_answers()
        model = self._session([
            ("submit_cycle_outcome", {"cycle_number": 1, "status": "FAILED",
                                       "status_explanation": "premature", "answers": []}),
            ("submit_cycle_intent", {"cycle_number": 1, "answers": answers}),
            ("invented_execution_tool", {}),
            "Continue implementation",
        ])
        visible_before = {tool.name for tool in await self.session.agent.tools[0].get_tools()}
        self.assertIn("submit_cycle_intent", visible_before)
        self.assertNotIn("submit_cycle_outcome", visible_before)
        await self.session.run_turn("Investigate and submit")
        visible_after = {tool.name for tool in await self.session.agent.tools[0].get_tools()}
        self.assertNotIn("submit_cycle_intent", visible_after)
        responses = self._interactions("tool_response")
        self.assertIn("unavailable", responses[0]["response"]["error"])
        self.assertEqual("accepted", responses[1]["response"]["status"])
        self.assertIn("not a registered tool", responses[2]["response"]["error"])
        self.assertEqual(4, len(model._requests))
        self.assertIn("submit_cycle_intent", model._requests[0].tools_dict)
        self.assertNotIn("submit_cycle_outcome", model._requests[0].tools_dict)
        self.journal.require_outcome()
        model._steps.extend([
            ("submit_cycle_outcome", {"cycle_number": 1, "status": "FAILED",
                                       "status_explanation": "No authoritative edit was attempted.",
                                       "answers": test_decision_journal.DecisionJournalTests._outcome_answers()[:2]}),
            "Outcome recorded",
        ])
        await self.session.run_turn("Record Outcome")
        self.assertEqual(JournalPhase.DETERMINISTIC_VALIDATION, self.journal.phase)
        self.assertEqual({"submit_cycle_outcome", "retrieve_retained_evidence"}, set(model._requests[4].tools_dict))

    async def test_malformed_answer_object_recovers_in_same_session(self):
        valid = test_decision_journal.DecisionJournalTests._intent_answers()
        malformed = [dict(item) for item in valid]
        malformed[0].pop("answer")
        malformed[0]["content"] = "Wrong key"
        self._session([
            ("submit_cycle_intent", {"cycle_number": 1, "answers": malformed}),
            ("submit_cycle_intent", {"cycle_number": 1, "answers": valid}),
            "Intent accepted",
        ])
        await self.session.run_turn("Submit Intent")
        responses = self._interactions("tool_response")
        self.assertIn("answer", str(responses[0]["response"]))
        self.assertEqual("accepted", responses[1]["response"]["status"])
        self.assertEqual(JournalPhase.EXECUTION, self.journal.phase)


if __name__ == "__main__":
    unittest.main()
