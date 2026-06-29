from pathlib import Path
import json
import tempfile
import unittest

from oss_remediation_agent.agents.remediation_outcome_analysis_agent import create_outcome_analysis_summary


class OutcomeSummaryTests(unittest.TestCase):
    def test_patch_mismatch_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = _plan(root)
            dry_path = root / "dry.json"
            out_path = root / "outcome.json"
            dry_path.write_text(json.dumps({"status": "FAILED", "errors": ["expected occurrence mismatch"], "patchResults": []}), encoding="utf-8")
            summary = create_outcome_analysis_summary(1, str(out_path), "wf", str(plan_path), dry_run_result_path=str(dry_path))
            self.assertEqual(summary["failureCategory"], "PATCH_OCCURRENCE_MISMATCH")
            self.assertEqual(summary["responsibilityArea"], "PLANNER_DECISION")

    def test_change_scope_failure_classification(self):
        summary = _summary_for_validation({"failedStage": "CHANGE_SCOPE_VALIDATION", "failureSummary": "scope"})
        self.assertEqual(summary["failureCategory"], "CHANGE_SCOPE_FAILURE")
        self.assertEqual(summary["responsibilityArea"], "VALIDATION")

    def test_build_failure_classification(self):
        summary = _summary_for_validation({"failedStage": "BUILD_VALIDATION", "failureSummary": "build"})
        self.assertEqual(summary["failureCategory"], "BUILD_FAILURE")
        self.assertEqual(summary["responsibilityArea"], "VALIDATION")

    def test_test_failure_classification(self):
        summary = _summary_for_validation({"failedStage": "TEST_VALIDATION", "failureSummary": "test"})
        self.assertEqual(summary["failureCategory"], "TEST_FAILURE")
        self.assertEqual(summary["responsibilityArea"], "VALIDATION")

    def test_osv_failure_classification(self):
        summary = _summary_for_validation({"failedStage": "OSV_VALIDATION", "failureSummary": "osv"})
        self.assertEqual(summary["failureCategory"], "OSV_VALIDATION_FAILURE")
        self.assertEqual(summary["responsibilityArea"], "VALIDATION")

    def test_patch_tool_limitation_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = _plan(root)
            proof_path = root / "proof.json"
            out_path = root / "outcome.json"
            proof_path.write_text(json.dumps({"status": "FAILED", "errors": ["unexpected patch engine condition"], "patchResults": []}), encoding="utf-8")
            summary = create_outcome_analysis_summary(1, str(out_path), "wf", str(plan_path), patch_application_proof_path=str(proof_path))
            self.assertEqual(summary["failureCategory"], "PATCH_TOOL_LIMITATION")
            self.assertEqual(summary["responsibilityArea"], "PATCH_TOOL")


def _summary_for_validation(validation_summary: dict):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan_path = _plan(root)
        validation_path = root / "validation.json"
        out_path = root / "outcome.json"
        validation_path.write_text(json.dumps({"status": "FAILED", "summary": validation_summary}), encoding="utf-8")
        return create_outcome_analysis_summary(1, str(out_path), "wf", str(plan_path), validation_result_path=str(validation_path))


def _plan(root: Path) -> Path:
    plan_path = root / "plan.json"
    plan_path.write_text(json.dumps({"workflowId": "wf", "vulnerabilityDecisions": [{"decision": "PATCH", "patches": []}]}), encoding="utf-8")
    return plan_path


if __name__ == "__main__":
    unittest.main()
