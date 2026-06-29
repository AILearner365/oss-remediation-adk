from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.orchestrator import WorkflowOrchestrator


class OrchestratorTests(unittest.TestCase):
    def test_additional_investigation_limit_is_per_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = RemediationPolicy(max_additional_investigation_requests_per_attempt=1)
            orchestrator = WorkflowOrchestrator(tmp, policy=policy)
            orchestrator.initialize("https://example.com/repo.git", "main")

            first = orchestrator.handle_planner_result({"decisionType": "REQUEST_ADDITIONAL_EVIDENCE", "tool": "ProjectAnalyzer"}, attempt_number=1)
            self.assertEqual(first["attempts"][0]["status"], "ADDITIONAL_INVESTIGATION_REQUESTED")

            second = orchestrator.handle_planner_result({"decisionType": "REQUEST_ADDITIONAL_EVIDENCE", "tool": "OSV"}, attempt_number=1)
            self.assertEqual(second["attempts"][0]["status"], "ADDITIONAL_INVESTIGATION_LIMIT_REACHED")
            self.assertEqual(second["status"], "ADDITIONAL_INVESTIGATION_LIMIT_REACHED")

            third = orchestrator.handle_planner_result({"decisionType": "REQUEST_ADDITIONAL_EVIDENCE", "tool": "ProjectAnalyzer"}, attempt_number=2)
            attempt_two = [item for item in third["attempts"] if item["attemptNumber"] == 2][0]
            self.assertEqual(attempt_two["status"], "ADDITIONAL_INVESTIGATION_REQUESTED")

    def test_manual_review_planner_result_generates_final_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)
            orchestrator.initialize("https://example.com/repo.git", "main")
            result = orchestrator.handle_planner_result({"decisionType": "MANUAL_REVIEW"}, attempt_number=1)
            self.assertEqual(result["status"], "SUCCESS")
            manifest = json.loads((Path(tmp) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "MANUAL_REVIEW_REQUIRED")
            self.assertEqual(manifest["final"]["prSummary"], "final/pr-summary.json")

    def test_patch_plan_planner_result_routes_to_patch_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)
            orchestrator.initialize("https://example.com/repo.git", "main")
            plan_path = str(Path(tmp) / "plan.json")
            Path(plan_path).write_text("{}", encoding="utf-8")
            with patch.object(orchestrator, "run_patch_validation_attempt", return_value={"status": "SUCCESS"}) as patched:
                result = orchestrator.handle_planner_result({"decisionType": "PATCH_PLAN", "patchPlanPath": plan_path}, attempt_number=3)
            self.assertEqual(result["status"], "SUCCESS")
            patched.assert_called_once_with(3, plan_path)

    def test_accepted_patch_set_preserves_dependency_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)
            orchestrator.initialize("https://example.com/repo.git", "main")
            plan = {
                "vulnerabilityDecisions": [
                    {
                        "vulnerabilityId": "GHSA-1234",
                        "decision": "PATCH",
                        "dependency": {
                            "groupId": "org.yaml",
                            "artifactId": "snakeyaml",
                            "packageName": "org.yaml:snakeyaml",
                            "currentVersion": "1.33",
                        },
                        "patches": [{"patchId": "patch-1", "oldVersion": "1.33", "newVersion": "2.2"}],
                    }
                ]
            }
            proof = {"patchResults": [{"patchId": "patch-1", "status": "APPLIED"}]}
            plan_path = Path(tmp) / "plan.json"
            proof_path = Path(tmp) / "proof.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            proof_path.write_text(json.dumps(proof), encoding="utf-8")

            patch_set = orchestrator._accepted_patch_set(1, str(plan_path), str(proof_path), "attempt-1/validation-result.json")

            self.assertEqual(patch_set["status"], "VALIDATED")
            self.assertEqual(patch_set["remediationSummary"][0]["dependency"], "org.yaml:snakeyaml")
            self.assertEqual(patch_set["remediationSummary"][0]["oldVersion"], "1.33")
            self.assertEqual(patch_set["remediationSummary"][0]["newVersion"], "2.2")


if __name__ == "__main__":
    unittest.main()
