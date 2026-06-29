from pathlib import Path
import json
import tempfile
import unittest

from oss_remediation_agent.agents.remediation_outcome_analysis_agent import create_outcome_analysis_summary


class OutcomeSummaryTests(unittest.TestCase):
    def test_patch_mismatch_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            dry_path = root / "dry.json"
            out_path = root / "outcome.json"
            plan_path.write_text(json.dumps({"workflowId": "wf", "vulnerabilityDecisions": [{"decision": "PATCH", "patches": []}]}), encoding="utf-8")
            dry_path.write_text(json.dumps({"status": "FAILED", "errors": ["expected occurrence mismatch"], "patchResults": []}), encoding="utf-8")
            summary = create_outcome_analysis_summary(1, str(out_path), "wf", str(plan_path), dry_run_result_path=str(dry_path))
            self.assertEqual(summary["failureCategory"], "PATCH_OCCURRENCE_MISMATCH")
            self.assertEqual(summary["responsibilityArea"], "PLANNER_DECISION")


if __name__ == "__main__":
    unittest.main()
