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
            max_section_chars=200,
            max_checkpoint_chars=5_000,
            max_context_chars=500,
        )
        self.lifecycle.begin_cycle(1)

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_intent_accepts_single_credible_diagnostic_direction(self):
        answers = self._intent_answers()
        self._replace(answers, "Materially credible candidate approaches", "One credible reversible diagnostic experiment is sufficient; alternatives add no value.")
        self._replace(answers, "Selected direction", "Run the reversible diagnostic experiment before selecting a final change.")

        result = self.lifecycle.submit_intent(1, answers)

        self.assertTrue(result.accepted)
        self.assertEqual(JournalPhase.EXECUTION, self.lifecycle.phase)
        content = self.lifecycle.store.read()
        self.assertIn("# Cycle 1 — Intent", content)
        self.assertIn("reversible diagnostic experiment", content)

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
        self._replace(oversized, INTENT_SECTIONS[0], "x" * 201)
        cases.append((oversized, "exceeds 200"))
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
                    max_section_chars=200,
                    max_checkpoint_chars=5_000,
                )
                lifecycle.begin_cycle(1)
                result = lifecycle.submit_intent(1, answers)
                self.assertFalse(result.accepted)
                self.assertTrue(any(expected in error for error in result.errors), result.errors)

        self.assertNotIn("# Cycle 1 — Intent", self.lifecycle.store.read())

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

    def test_cycle_two_requires_prior_learning_sections_and_context_is_bounded(self):
        self.assertTrue(self.lifecycle.submit_intent(1, self._intent_answers()).accepted)
        self.lifecycle.require_outcome()
        self.assertTrue(self.lifecycle.submit_outcome(1, "FAILED", "Checks failed.", self._outcome_answers()).accepted)
        self.lifecycle.begin_cycle(2)
        rejected = self.lifecycle.submit_intent(2, self._intent_answers())
        self.assertFalse(rejected.accepted)
        answers = self._intent_answers() + [
            {"section": "Prior-cycle learning", "answer": "Validation contradicted the earlier assumption."},
            {"section": "Relationship to the prior approach", "answer": "Replace the unsupported direction."},
        ]
        self.assertTrue(self.lifecycle.submit_intent(2, answers).accepted)
        context = self.lifecycle.context()
        self.assertLessEqual(len(context), 550)
        self.assertIn("bounded for model input", context)

    def test_run_capture_uses_least_trustworthy_cycle(self):
        self.assertTrue(self.lifecycle.submit_intent(1, self._intent_answers()).accepted)
        self.lifecycle.begin_cycle(2)
        answers = self._intent_answers() + [
            {"section": "Prior-cycle learning", "answer": "The prior outcome was not captured."},
            {"section": "Relationship to the prior approach", "answer": "Continue using repository evidence."},
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

    def test_unstructured_coverage_is_preserved_without_reclassification(self):
        coverage = "The first requirement passed; the second still needs external evidence."
        cycle = CycleCapture(
            outcome_answers={
                "Requirement and problem coverage": coverage,
                "Final approach present at cycle end": "Preserved implementation.",
            }
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

        conditional = rendered.split("### Conditional", 1)[1].split("### Unresolved", 1)[0]
        self.assertNotIn(coverage, conditional)
        self.assertIn("### Uncategorized model-reported coverage", rendered)
        self.assertIn(coverage, rendered)

    @staticmethod
    def _replace(answers, section, answer):
        next(item for item in answers if item["section"] == section)["answer"] = answer

    @staticmethod
    def _intent_answers():
        return [{"section": section, "answer": f"Substantive answer for {section}."} for section in INTENT_SECTIONS]

    @staticmethod
    def _outcome_answers():
        return [{"section": section, "answer": f"Observed evidence for {section}."} for section in OUTCOME_SECTIONS]


if __name__ == "__main__":
    unittest.main()
