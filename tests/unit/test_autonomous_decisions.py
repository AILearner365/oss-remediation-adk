from __future__ import annotations

import json
import tempfile
import unittest

from autonomous_oss_remediation_agent.capabilities import (
    DeveloperCapabilitySet,
    ExecutionBudget,
    ProcessRunner,
    WorkspaceIO,
)
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig, RuntimePolicy
from autonomous_oss_remediation_agent.models import (
    AgentDecisionStatus,
    CommandResult,
    ScanReport,
    ValidationCheck,
    ValidationReport,
)
from autonomous_oss_remediation_agent.prompt import (
    MAX_DECISION_CONTEXT_CHARACTERS,
    serialize_decision_context,
    validation_feedback,
)
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


class AutonomousDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "decision-run")
        self.workspace.repository.mkdir()
        self.repository_file = self.workspace.repository / "pom.xml"
        self.repository_file.write_text("<project/>\n", encoding="utf-8")
        self.trace = TraceStore(self.workspace)
        self.capabilities, self.budget = self._new_capabilities(max_cycles=3)
        self.capabilities.start_cycle(1)

    def tearDown(self):
        self.temp.cleanup()

    def test_records_initial_select_with_runtime_identity_and_no_repository_mutation(self):
        before = self.repository_file.read_text(encoding="utf-8")

        result = self._record("SELECT")

        self.assertEqual("ok", result["status"])
        self.assertEqual("D1", result["decision"]["decisionId"])
        self.assertEqual(1, result["decision"]["cycle"])
        self.assertEqual("decision-run", self._decision_events()[0]["runId"])
        self.assertEqual(before, self.repository_file.read_text(encoding="utf-8"))
        self.assertEqual(1, len(self._decision_events()))

    def test_complete_extend_snapshot_repeats_retained_and_new_coverage(self):
        self._record(
            "SELECT",
            coverage_satisfied=["constraint A"],
            coverage_unresolved=["criterion B"],
        )

        extended = self._record(
            "EXTEND",
            coverage_satisfied=["constraint A", "criterion B"],
            coverage_conditional=["criterion C"],
            coverage_unresolved=[],
            strategy="Complete expanded strategy including retained and new work",
        )

        self.assertEqual(
            ["constraint A", "criterion B"],
            extended["decisionState"]["currentCoverage"]["satisfied"],
        )
        self.assertEqual(
            ["criterion C"],
            extended["decisionState"]["remainingUnresolvedItems"],
        )

    def test_tool_documentation_defines_complete_snapshot_contract(self):
        documentation = DeveloperCapabilitySet.record_decision.__doc__ or ""

        self.assertIn("complete current", documentation)
        self.assertIn("must not contain only the newly changed portion", documentation)
        self.assertIn("Concise observed facts supporting the decision", documentation)
        self.assertIn("rationale explains why", documentation)
        self.assertIn("Complete set of success criteria currently satisfied", documentation)
        self.assertIn("All currently active material assumptions", documentation)
        self.assertIn("planned or observed evidence", documentation)
        self.assertIn("latest decision in one linear chain", documentation)

    def test_readiness_with_unresolved_coverage_records_warning_without_rejection(self):
        self._record("SELECT")

        result = self._record("READY_FOR_INDEPENDENT_VALIDATION")

        self.assertEqual("ok", result["status"])
        self.assertTrue(any("coverage remains" in warning for warning in result["warnings"]))
        self.assertEqual(2, len(self._decision_events()))
        self.assertTrue(
            any(event["type"] == "decision_warning" for event in self._events())
        )

    def test_block_without_unresolved_coverage_or_concrete_blocker_warns(self):
        self._record("SELECT")

        result = self._record(
            "BLOCK",
            diagnosis="Current work state",
            rationale="Current evidence summary",
            coverage_conditional=[],
            coverage_unresolved=[],
        )

        self.assertEqual("ok", result["status"])
        self.assertTrue(any("concrete blocker" in warning for warning in result["warnings"]))

    def test_all_supported_actions_form_one_ordered_chain(self):
        self._record("SELECT")
        actions = (
            "RETAIN",
            "EXTEND",
            "REVISE",
            "REPLACE",
            "READY_FOR_INDEPENDENT_VALIDATION",
            "BLOCK",
        )
        for action in actions:
            self._record(action)

        events = self._decision_events()
        self.assertEqual([f"D{index}" for index in range(1, 8)], [e["decisionId"] for e in events])
        self.assertEqual(list(actions), [e["action"] for e in events[1:]])
        self.assertEqual(
            [f"D{index}" for index in range(1, 7)],
            [e["previousDecisionId"] for e in events[1:]],
        )
        state = self.capabilities.decisions.current_state
        self.assertEqual("D7", state.latest_decision_id)
        self.assertEqual(AgentDecisionStatus.BLOCKED, state.agent_status)

    def test_every_post_select_action_defaults_to_latest_parent(self):
        for action in ("READY_FOR_INDEPENDENT_VALIDATION", "BLOCK", "REVISE"):
            capabilities, _ = self._new_capabilities(max_cycles=1)
            capabilities.start_cycle(1)
            self._record_with(capabilities, "SELECT")

            result = self._record_with(capabilities, action)

            self.assertEqual("D1", result["decision"]["previousDecisionId"])

    def test_invalid_chain_attempts_do_not_create_events_or_id_gaps(self):
        first_invalid = self._record("REVISE")
        self.assertEqual("DECISION_CHAIN_INVALID", first_invalid["failureCode"])
        self.assertEqual([], self._decision_events())

        selected = self._record("SELECT")
        self.assertEqual("D1", selected["decision"]["decisionId"])
        second_select = self._record("SELECT")
        unknown_parent = self._record("REVISE", previous_decision_id="D99")
        retained = self._record("RETAIN")
        stale_parent = self._record("REVISE", previous_decision_id="D1")
        revised = self._record("REVISE")

        self.assertEqual("DECISION_CHAIN_INVALID", second_select["failureCode"])
        self.assertEqual("DECISION_CHAIN_INVALID", unknown_parent["failureCode"])
        self.assertEqual("D2", retained["decision"]["decisionId"])
        self.assertEqual("DECISION_CHAIN_INVALID", stale_parent["failureCode"])
        self.assertEqual("D3", revised["decision"]["decisionId"])
        self.assertEqual(["D1", "D2", "D3"], [e["decisionId"] for e in self._decision_events()])

    def test_aggregate_record_limit_rejects_without_partial_event(self):
        large_items = [f"item-{index}-" + ("x" * 580) for index in range(12)]

        result = self.capabilities.record_decision(
            action="SELECT",
            diagnosis="large decision",
            strategy="large strategy",
            rationale="large rationale",
            evidence=large_items,
            coverage_satisfied=large_items,
            coverage_conditional=large_items,
            coverage_unresolved=large_items,
            assumptions=[],
            validation=large_items,
            alternatives=[],
        )

        self.assertEqual("DECISION_RECORD_TOO_LARGE", result["failureCode"])
        self.assertEqual([], self._decision_events())

    def test_near_limit_accepted_record_has_bounded_continuation_context(self):
        validation = [f"observed-{index}-" + ("v" * 560) for index in range(12)]
        coverage = [f"criterion-{index}-" + ("c" * 480) for index in range(3)]

        result = self.capabilities.record_decision(
            action="SELECT",
            diagnosis="diagnosis " + ("d" * 1180),
            strategy="strategy " + ("s" * 1180),
            rationale="rationale " + ("r" * 1180),
            evidence=["observed: " + ("e" * 280)],
            coverage_satisfied=coverage,
            coverage_conditional=[],
            coverage_unresolved=[],
            assumptions=[],
            validation=validation,
            alternatives=[],
        )

        self.assertEqual("ok", result["status"])
        record_size = len(
            json.dumps(
                result["decision"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        self.assertGreater(record_size, 12_000)
        state = self.capabilities.decisions.current_state
        trail = self.capabilities.decisions.all_records()

        serialized = serialize_decision_context(state, trail)
        context = json.loads(serialized)
        feedback = validation_feedback(
            _failed_validation_report(),
            "WORKING_STATE\n- Unresolved: deterministic validation",
            state,
            trail,
        )

        self.assertLessEqual(len(serialized), MAX_DECISION_CONTEXT_CHARACTERS)
        self.assertEqual("D1", context["currentDecisionState"]["latestDecisionId"])
        self.assertEqual("SELECT", context["currentDecisionState"]["currentAction"])
        self.assertEqual("IN_PROGRESS", context["currentDecisionState"]["agentStatus"])
        self.assertEqual(
            context["includedDecisionCount"] < context["totalDecisionCount"],
            context["historyTruncated"],
        )
        self.assertEqual(12, context["currentStateFieldCounts"]["validation"]["total"])
        self.assertIn('"latestDecisionId":"D1"', feedback)
        self.assertIn("New deterministic validation evidence", feedback)

    def test_decision_recording_does_not_consume_operational_tool_budget(self):
        self.assertEqual(0, self.budget.tool_calls)

        self._record("SELECT")
        self.assertEqual(0, self.budget.tool_calls)
        self.capabilities.read_workspace_text("pom.xml")

        self.assertEqual(1, self.budget.tool_calls)

    def test_decision_specific_limit_is_enforced_without_id_gap(self):
        capabilities, _ = self._new_capabilities(max_cycles=1)
        capabilities.start_cycle(1)
        for action in ("SELECT", "RETAIN", "EXTEND", "REVISE"):
            result = self._record_with(capabilities, action)
            self.assertEqual("ok", result["status"])

        rejected = self._record_with(capabilities, "REPLACE")

        self.assertEqual("DECISION_EVENT_LIMIT_REACHED", rejected["failureCode"])
        self.assertEqual(4, capabilities.decisions.event_count)
        self.assertTrue(
            any(
                event["type"] == "decision_recording_rejected"
                and event["failureCode"] == "DECISION_EVENT_LIMIT_REACHED"
                for event in self._events()
            )
        )

    def test_decision_recording_still_obeys_overall_deadline(self):
        self.budget.started_at -= self.budget.config.overall_timeout_seconds + 1

        result = self._record("SELECT")

        self.assertEqual("EXECUTION_BUDGET_EXCEEDED", result["failureCode"])
        self.assertEqual([], self._decision_events())

    def _new_capabilities(self, max_cycles: int):
        budget = ExecutionBudget(
            ExecutionBudgetConfig(
                max_cycles=max_cycles,
                max_tool_calls=20,
                command_timeout_seconds=10,
                overall_timeout_seconds=30,
            )
        )
        runner = ProcessRunner(
            self.workspace,
            self.trace,
            budget,
            RuntimePolicy(True, True, True),
        )
        return (
            DeveloperCapabilitySet(
                WorkspaceIO(self.workspace, self.trace), runner, budget, self.trace
            ),
            budget,
        )

    def _record(self, action: str, **overrides):
        return self._record_with(self.capabilities, action, **overrides)

    def _record_with(self, capabilities, action: str, **overrides):
        values = {
            "diagnosis": "The requested remediation remains incomplete",
            "strategy": f"Complete strategy for {action}",
            "rationale": "Repository evidence supports this material direction",
            "evidence": ["observed: inspection evidence", "observed: build evidence"],
            "coverage_satisfied": ["repository constraints"],
            "coverage_conditional": ["compatibility pending validation"],
            "coverage_unresolved": ["external validation"],
            "assumptions": [
                {
                    "assumption": "The selected change controls the observed result",
                    "test": "planned: run the relevant build and inspect its output",
                    "status": "UNRESOLVED",
                }
            ],
            "validation": ["planned: run build", "observed: focused tests passed"],
            "previous_decision_id": None,
            "alternatives": [
                {
                    "approach": "Alternative approach",
                    "classification": "PARTIAL",
                    "coverage": "Covers one success criterion",
                    "gaps": "Leaves compatibility unresolved",
                }
            ],
        }
        values.update(overrides)
        return capabilities.record_decision(action=action, **values)

    def _events(self):
        if not self.trace.events_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.trace.events_path.read_text(encoding="utf-8").splitlines()
        ]

    def _decision_events(self):
        return [event for event in self._events() if event["type"] == "decision_recorded"]


def _failed_validation_report() -> ValidationReport:
    return ValidationReport(
        cycle=1,
        passed=False,
        checks=(ValidationCheck("target_findings_resolved", False, "Target remains"),),
        changed_files=("pom.xml",),
        diff_path="cycle-1.diff",
        tree_digest="after",
        scan=ScanReport(
            True,
            (),
            CommandResult(["scanner"], ".", 0, stdout="{}"),
            "scan.json",
        ),
    )


if __name__ == "__main__":
    unittest.main()
