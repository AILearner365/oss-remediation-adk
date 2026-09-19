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
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


class AutonomousDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "decision-run")
        self.workspace.repository.mkdir()
        self.repository_file = self.workspace.repository / "pom.xml"
        self.repository_file.write_text("<project/>\n", encoding="utf-8")
        self.trace = TraceStore(self.workspace)
        budget = ExecutionBudget(
            ExecutionBudgetConfig(
                max_cycles=3,
                max_tool_calls=20,
                command_timeout_seconds=10,
                overall_timeout_seconds=30,
            )
        )
        policy = RuntimePolicy(True, True, True)
        runner = ProcessRunner(self.workspace, self.trace, budget, policy)
        self.capabilities = DeveloperCapabilitySet(
            WorkspaceIO(self.workspace, self.trace), runner, budget, self.trace
        )
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

    def test_sequential_actions_preserve_order_relationships_and_projection(self):
        first = self._record("SELECT")
        previous = first["decision"]["decisionId"]
        actions = (
            "RETAIN",
            "EXTEND",
            "REVISE",
            "REPLACE",
            "READY_FOR_INDEPENDENT_VALIDATION",
            "BLOCK",
        )
        for action in actions:
            result = self._record(action, previous_decision_id=previous)
            previous = result["decision"]["decisionId"]

        events = self._decision_events()
        self.assertEqual([f"D{index}" for index in range(1, 8)], [e["decisionId"] for e in events])
        self.assertEqual(list(actions), [e["action"] for e in events[1:]])
        self.assertEqual(
            [f"D{index}" for index in range(1, 7)],
            [e["previousDecisionId"] for e in events[1:]],
        )
        state = self.capabilities.decisions.current_state
        self.assertEqual("D7", state.latest_decision_id)
        self.assertEqual("BLOCKED", state.status)
        self.assertEqual(
            ("compatibility pending validation", "external validation"),
            state.remaining_unresolved_items,
        )
        self.assertEqual(7, self.capabilities.decisions.event_count)

    def test_transition_defaults_to_latest_previous_decision(self):
        self._record("SELECT")

        result = self._record("REVISE")

        self.assertEqual("D1", result["decision"]["previousDecisionId"])

    def _record(self, action: str, previous_decision_id: str | None = None):
        return self.capabilities.record_decision(
            action=action,
            diagnosis="The requested remediation remains incomplete",
            strategy=f"Strategy for {action}",
            rationale="Repository evidence supports this material direction",
            evidence=["inspection evidence", "build evidence"],
            coverage_satisfied=["repository constraints"],
            coverage_conditional=["compatibility pending validation"],
            coverage_unresolved=["external validation"],
            assumptions=[
                {
                    "assumption": "The selected change controls the observed result",
                    "test": "Run the relevant build and inspect its output",
                    "status": "UNRESOLVED",
                }
            ],
            validation=["Run build", "Run focused tests"],
            previous_decision_id=previous_decision_id,
            alternatives=[
                {
                    "approach": "Alternative approach",
                    "classification": "PARTIAL",
                    "coverage": "Covers one success criterion",
                    "gaps": "Leaves compatibility unresolved",
                }
            ],
        )

    def _decision_events(self):
        if not self.trace.events_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.trace.events_path.read_text(encoding="utf-8").splitlines()
            if json.loads(line)["type"] == "decision_recorded"
        ]


if __name__ == "__main__":
    unittest.main()
