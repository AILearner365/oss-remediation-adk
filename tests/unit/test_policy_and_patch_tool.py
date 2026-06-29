from pathlib import Path
import json
import unittest

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.tools.generic_patch_apply_tool import dry_run, apply


class PolicyAndPatchToolTests(unittest.TestCase):
    def test_policy_defaults_are_safe(self):
        policy = RemediationPolicy()
        self.assertEqual(policy.severity_scope, ["CRITICAL", "HIGH"])
        self.assertIn("**/pom.xml", policy.allowed_file_patterns)
        self.assertIn("JAVA_SOURCE_CHANGE", policy.blocked_change_types)

    def test_patch_tool_dry_run_and_apply(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            pom = repo / "pom.xml"
            pom.write_text("<project><properties><x.version>1.0</x.version></properties></project>", encoding="utf-8")
            plan = {
                "workflowId": "wf-test",
                "planId": "plan-1",
                "vulnerabilityDecisions": [
                    {
                        "decision": "PATCH",
                        "patches": [
                            {
                                "patchId": "patch-1",
                                "file": "pom.xml",
                                "oldText": "<x.version>1.0</x.version>",
                                "newText": "<x.version>1.1</x.version>",
                                "expectedOccurrences": 1
                            }
                        ]
                    }
                ]
            }
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            dry = dry_run(1, str(repo), str(plan_path), str(root / "dry.json"))
            self.assertEqual(dry["status"], "SUCCESS")
            result = apply(1, str(repo), str(plan_path), str(root / "proof.json"), str(root / "patch.diff"))
            self.assertEqual(result["status"], "SUCCESS")
            self.assertIn("<x.version>1.1</x.version>", pom.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
