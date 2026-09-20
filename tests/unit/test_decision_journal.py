from __future__ import annotations

import tempfile
import unittest

from autonomous_oss_remediation_agent.journal import (
    CaptureStatus,
    CycleCapture,
    DeliveryEligibility,
    INTENT_SECTIONS,
    JournalLifecycle,
    JournalPhase,
    JournalStore,
    OUTCOME_SECTIONS,
    OUTCOME_STATUSES,
    RemediationOutcome,
    render_final_resolution,
)
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


class DecisionJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.workspace.repository.mkdir()
        self.trace = TraceStore(self.workspace)
        self.changed = False
        self.lifecycle = JournalLifecycle(
            JournalStore(self.trace),
            self.trace,
            "Stable caller contract",
            lambda: self.changed,
            max_section_chars=3_000,
            max_checkpoint_chars=12_000,
            max_context_chars=500,
        )
        self.lifecycle.begin_cycle(1)

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_intent_accepts_single_credible_diagnostic_direction(self):
        answers = self._intent_answers()

        result = self.lifecycle.submit_intent(1, answers)

        self.assertTrue(result.accepted)
        self.assertEqual(JournalPhase.EXECUTION, self.lifecycle.phase)
        content = self.lifecycle.store.read()
        self.assertIn("# Cycle 1 — Problem Analysis and Solution Decision", content)
        self.assertEqual(1, content.count("#### Candidate Solution"))

    def test_missing_empty_duplicate_placeholder_oversized_and_malformed_are_rejected(self):
        cases = []
        missing = self._intent_answers()[:-1]
        cases.append((missing, "Missing required section"))
        empty = self._intent_answers()
        self._replace(empty, INTENT_SECTIONS[0], "")
        cases.append((empty, "Empty answer"))
        duplicate = self._intent_answers() + [{"section": INTENT_SECTIONS[0], "answer": "duplicate"}]
        cases.append((duplicate, "Duplicate section"))
        placeholder = self._intent_answers()
        self._replace(placeholder, INTENT_SECTIONS[0], "**TODO**")
        cases.append((placeholder, "Placeholder-only"))
        oversized = self._intent_answers()
        self._replace(oversized, INTENT_SECTIONS[0], "x" * 3_001)
        cases.append((oversized, "exceeds 3000"))
        malformed = self._intent_answers()
        self._replace(malformed, INTENT_SECTIONS[0], "```\nunclosed")
        cases.append((malformed, "unclosed ``` fenced"))

        for answers, expected in cases:
            with self.subTest(expected=expected):
                workspace = RunWorkspace.create(self.temp.name)
                workspace.repository.mkdir()
                trace = TraceStore(workspace)
                lifecycle = JournalLifecycle(
                    JournalStore(trace),
                    trace,
                    "contract",
                    lambda: False,
                    max_section_chars=3_000,
                    max_checkpoint_chars=12_000,
                )
                lifecycle.begin_cycle(1)
                result = lifecycle.submit_intent(1, answers)
                self.assertFalse(result.accepted)
                self.assertTrue(any(expected in error for error in result.errors), result.errors)

        self.assertNotIn("# Cycle 1 — Problem Analysis and Solution Decision", self.lifecycle.store.read())

    def test_additional_subsection_is_accepted_and_prior_content_is_immutable(self):
        answers = self._intent_answers() + [
            {"section": "Repository-specific observation", "answer": "The parent owns dependency versions."}
        ]
        accepted = self.lifecycle.submit_intent(1, answers)
        before = self.lifecycle.store.read()
        self.assertTrue(accepted.accepted)
        self.lifecycle.require_outcome()
        outcome = self.lifecycle.submit_outcome(
            1,
            "INCONCLUSIVE",
            "Evidence is incomplete.",
            self._outcome_answers(),
        )
        self.assertTrue(outcome.accepted)
        self.assertTrue(self.lifecycle.store.read().startswith(before))

        self.lifecycle.store.path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.lifecycle.store.append("test", None, "# Test")

    def test_late_intent_and_incomplete_outcome_are_separate_capture_states(self):
        self.changed = True
        self.assertTrue(self.lifecycle.submit_intent(1, self._intent_answers()).accepted)
        self.assertEqual(CaptureStatus.INCOMPLETE, self.lifecycle.capture_status())
        self.lifecycle.require_outcome()
        self.assertTrue(
            self.lifecycle.submit_outcome(
                1,
                "PARTIALLY_REMEDIATED",
                "Safe useful progress remains incomplete.",
                self._outcome_answers(),
            ).accepted
        )
        self.assertEqual(CaptureStatus.LATE, self.lifecycle.capture_status())

    def test_every_outcome_status_is_structurally_accepted(self):
        for status in OUTCOME_STATUSES:
            with self.subTest(status=status):
                workspace = RunWorkspace.create(self.temp.name)
                workspace.repository.mkdir()
                trace = TraceStore(workspace)
                lifecycle = JournalLifecycle(JournalStore(trace), trace, "contract", lambda: False)
                lifecycle.begin_cycle(1)
                self.assertTrue(lifecycle.submit_intent(1, self._intent_answers()).accepted)
                lifecycle.require_outcome()
                self.assertTrue(
                    lifecycle.submit_outcome(
                        1, status, f"Evidence supports {status}.", self._outcome_answers()
                    ).accepted
                )

    def test_three_outcome_answers_represent_material_execution_history(self):
        self.assertTrue(self.lifecycle.submit_intent(1, self._intent_answers()).accepted)
        self.lifecycle.require_outcome()
        answers = [
            {
                "section": "Implementation Result",
                "answer": "The final repository approach updates the owning property. Self-validation passed the build but compatibility, one constraint, and remaining Task coverage are explicitly unverified, so the result is partial.",
            },
            {
                "section": "Cycle Intent vs. Implementation",
                "answer": "The implementation materially changed after an attempted override failed and was reverted. That evidence rejected an assumption and led to selecting the owning property instead.",
            },
            {
                "section": "Implementation Trail",
                "answer": "Inspected ownership, attempted and reverted the override after its observed failure, reassessed the direction, updated the property, and ran the build self-validation.",
            },
        ]

        result = self.lifecycle.submit_outcome(
            1,
            "PARTIALLY_REMEDIATED",
            "Useful work remains but coverage is incomplete.",
            answers,
        )

        self.assertTrue(result.accepted)
        content = self.lifecycle.store.read()
        self.assertIn("attempted override failed and was reverted", content)
        self.assertIn("compatibility, one constraint", content)
        self.assertEqual(3, len(OUTCOME_SECTIONS))

    def test_cycle_two_requires_prior_cycle_reassessment_and_context_is_bounded(self):
        self.assertTrue(self.lifecycle.submit_intent(1, self._intent_answers()).accepted)
        self.lifecycle.require_outcome()
        self.assertTrue(self.lifecycle.submit_outcome(1, "FAILED", "Checks failed.", self._outcome_answers()).accepted)
        self.lifecycle.begin_cycle(2)
        rejected = self.lifecycle.submit_intent(2, self._intent_answers())
        self.assertFalse(rejected.accepted)
        answers = self._intent_answers() + [
            {
                "section": "Prior-cycle reassessment",
                "answer": "Current repository and deterministic validation evidence contradict the earlier assumption; the unverified claim remains uncertain and does not constrain selection.",
            },
        ]
        self.assertTrue(self.lifecycle.submit_intent(2, answers).accepted)
        context = self.lifecycle.context()
        self.assertLessEqual(len(context), 550)
        self.assertIn("bounded for model input", context)
        self.assertIn("Cycle 1", context)
        self.assertIn("Cycle 2", context)

    def test_run_capture_uses_least_trustworthy_cycle(self):
        self.assertTrue(self.lifecycle.submit_intent(1, self._intent_answers()).accepted)
        self.lifecycle.begin_cycle(2)
        answers = self._intent_answers() + [
            {
                "section": "Prior-cycle reassessment",
                "answer": "The prior outcome was not captured, so prior claims remain unverified; current repository evidence governs the new decision.",
            },
        ]
        self.assertTrue(self.lifecycle.submit_intent(2, answers).accepted)
        self.lifecycle.require_outcome()
        self.assertTrue(
            self.lifecycle.submit_outcome(
                2, "READY_FOR_INDEPENDENT_VALIDATION", "Ready for checks.", self._outcome_answers()
            ).accepted
        )

        self.assertEqual(CaptureStatus.INCOMPLETE, self.lifecycle.capture_status(1))
        self.assertEqual(CaptureStatus.COMPLETE, self.lifecycle.capture_status(2))
        self.assertEqual(CaptureStatus.INCOMPLETE, self.lifecycle.run_capture_status)
        self.assertEqual(("Cycle 1 capture is INCOMPLETE",), self.lifecycle.capture_warnings())

    def test_limited_markdown_subset_handles_fences_and_rejects_heading_injection(self):
        accepted = self._intent_answers()
        self._replace(
            accepted,
            INTENT_SECTIONS[0],
            "Observed code:\n\n```text\n# not a heading\n~~~ also not a closer\n```\n\n### Useful detail\nEvidence follows.",
        )
        self.assertTrue(self.lifecycle.submit_intent(1, accepted).accepted)

        for answer, expected in (
            ("# Injected top level", "level 3-6"),
            ("~~~text\nunclosed", "unclosed ~~~ fenced"),
        ):
            workspace = RunWorkspace.create(self.temp.name)
            workspace.repository.mkdir()
            trace = TraceStore(workspace)
            lifecycle = JournalLifecycle(JournalStore(trace), trace, "contract", lambda: False)
            lifecycle.begin_cycle(1)
            answers = self._intent_answers()
            self._replace(answers, INTENT_SECTIONS[0], answer)
            result = lifecycle.submit_intent(1, answers)
            self.assertFalse(result.accepted)
            self.assertTrue(any(expected in error for error in result.errors), result.errors)

    def test_final_resolution_preserves_new_outcome_without_promoting_it_to_fact(self):
        implementation_result = "Self-validation passed locally, but deterministic validation remains pending and one compatibility behavior is unverified."
        cycle = CycleCapture(
            outcome_answers={
                "Implementation Result": implementation_result,
                "Cycle Intent vs. Implementation": "No material change from the selected solution.",
                "Implementation Trail": "Edited the owned configuration and ran the configured self-check.",
            },
            intent_answers={"Selected solution": "Candidate A was selected."},
        )

        rendered = render_final_resolution(
            RemediationOutcome.INCONCLUSIVE,
            "Original problem",
            {1: cycle},
            None,
            CaptureStatus.COMPLETE,
            DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
            "No delivery.",
            "Evidence remains incomplete.",
        )

        self.assertIn(implementation_result, rendered)
        self.assertIn("only explicitly mapped deterministic checks are authoritative", rendered)
        self.assertIn("Cycle 1 implementation trail", rendered)

    def test_preliminary_baseline_and_task_records_preserve_underlying_data(self):
        workspace = RunWorkspace.create(self.temp.name)
        workspace.repository.mkdir()
        trace = TraceStore(workspace)
        lifecycle = JournalLifecycle(
            JournalStore(trace),
            trace,
            '{"initial": true}',
            lambda: False,
            preliminary_contract=True,
        )
        lifecycle.append_baseline_contract('{"baseline": "abc"}')
        lifecycle.append_task_to_solve("# Task to Solve\n\nStable original task")

        content = lifecycle.store.read()
        self.assertIn("# Preliminary Run Contract", content)
        self.assertIn("Initial run configuration captured before repository preparation", content)
        self.assertIn('{"initial": true}', content)
        self.assertIn("# Baseline Contract", content)
        self.assertIn("Authoritative run starting state established after repository preparation", content)
        self.assertIn('{"baseline": "abc"}', content)
        self.assertEqual(1, content.count("# Task to Solve"))
        self.assertEqual("# Task to Solve\n\nStable original task", lifecycle.task_to_solve)

    def test_bounded_context_retains_provenance_from_all_prior_cycles(self):
        workspace = RunWorkspace.create(self.temp.name)
        workspace.repository.mkdir()
        trace = TraceStore(workspace)
        lifecycle = JournalLifecycle(
            JournalStore(trace),
            trace,
            "initial contract",
            lambda: False,
            max_context_chars=1_400,
        )
        lifecycle.append_baseline_contract("baseline contract")
        lifecycle.append_task_to_solve("# Task to Solve\n\nORIGINAL-TASK-ANCHOR")
        for cycle in range(1, 4):
            lifecycle.store.append(
                "intent",
                cycle,
                f"# Cycle {cycle} — Problem Analysis and Solution Decision\n\ncycle-{cycle}-decision " + "d" * 500,
            )
            lifecycle.store.append(
                "deterministic_validation",
                cycle,
                f"# Cycle {cycle} — Deterministic Validation\n\ncycle-{cycle}-validation " + "v" * 500,
            )

        context = lifecycle.context()

        self.assertLessEqual(len(context), 1_400)
        self.assertIn("ORIGINAL-TASK-ANCHOR", context)
        for cycle in range(1, 4):
            self.assertIn(f"# Cycle {cycle}", context)

    @staticmethod
    def _replace(answers, section, answer):
        next(item for item in answers if item["section"] == section)["answer"] = answer

    @staticmethod
    def _intent_answers():
        return [
            {
                "section": "Model understanding",
                "answer": "Resolve the complete supplied task within every applicable requirement and constraint.",
            },
            {
                "section": "Information, investigation and remaining uncertainty",
                "answer": """| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| Ownership | Select a coherent change | pom.xml | The property owns the version | Runtime compatibility requires execution |

### Material assumptions that remain necessary

None.""",
            },
            {
                "section": "Concrete candidate solutions",
                "answer": """#### Candidate Solution A — Update the owning property

| Question | Model answer |
|---|---|
| What exact solution is proposed? | Update the owning property to 2.0. |
| Why were these exact changes selected? | Repository evidence identifies this ownership boundary. |
| What evidence supports the expected result? | The effective model resolves through this property. |
| Which parts of the problem will it resolve? | The requested finding. |
| Does it satisfy every applicable requirement? | Yes, subject to execution validation. |
| How will it be implemented? | Edit the property, inspect the diff, and self-validate. |
| How will compatibility be preserved? | Run configured checks. |
| Why is the result coherent and maintainable? | It retains one ownership point. |
| What risks or unknowns remain? | Runtime compatibility remains execution-dependent. |
| How will the result be validated? | Build, tests, and fresh deterministic validation. |
| Is it a COMPLETE or PARTIAL solution? | COMPLETE, subject to validation. |""",
            },
            {
                "section": "Selected solution",
                "answer": """- **Selected solution:** Candidate A — Update the owning property
- **Classification:** COMPLETE
- **Why it is preferred:** It follows observed ownership.
- **Comparative coverage:** It covers all requirements; no other supported candidate exists.
- **Remaining risks:** Runtime compatibility requires execution.
- **Evidence requiring reconsideration:** Effective-model or test evidence contradicting ownership.""",
            },
        ]

    @staticmethod
    def _outcome_answers():
        return [{"section": section, "answer": f"Observed evidence for {section}."} for section in OUTCOME_SECTIONS]


if __name__ == "__main__":
    unittest.main()
