from pathlib import Path
import json
import tempfile
import unittest

from oss_remediation_agent.tools.validation_tool import validate_attempt


class ValidationToolTests(unittest.TestCase):
    def test_validation_change_scope_rejects_non_pom_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps({"vulnerabilityDecisions": []}), encoding="utf-8")
            proof = {
                "schemaVersion": "1.0",
                "artifactId": "proof",
                "workflowId": "wf",
                "createdBy": "test",
                "status": "SUCCESS",
                "filesChanged": ["README.md"],
                "patchResults": [],
            }
            proof_path = root / "proof.json"
            proof_path.write_text(json.dumps(proof), encoding="utf-8")
            result = validate_attempt(1, str(repo), str(plan_path), str(proof_path), str(root / "validation.json"), str(root), workflow_id="wf")
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["failureCode"], "CHANGE_SCOPE_FAILURE")


if __name__ == "__main__":
    unittest.main()
