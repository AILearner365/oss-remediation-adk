from pathlib import Path
import json
import tempfile
import unittest

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.tools.generic_patch_apply_tool import apply, dry_run


class PolicyAndPatchToolTests(unittest.TestCase):
    def test_policy_defaults_are_safe(self):
        policy = RemediationPolicy()
        self.assertEqual(policy.severity_scope, ["CRITICAL", "HIGH"])
        self.assertIn("**/pom.xml", policy.allowed_file_patterns)
        self.assertIn("JAVA_SOURCE_CHANGE", policy.blocked_change_types)
        self.assertIn("SUPPRESSION_OR_IGNORE_WORKAROUND", policy.blocked_change_types)

    def test_patch_tool_dry_run_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            pom = repo / "pom.xml"
            pom.write_text("<project><properties><x.version>1.0</x.version></properties></project>", encoding="utf-8")
            plan_path = _write_plan(root, [
                {
                    "patchId": "patch-1",
                    "file": "pom.xml",
                    "oldText": "<x.version>1.0</x.version>",
                    "newText": "<x.version>1.1</x.version>",
                    "expectedOccurrences": 1,
                }
            ])
            dry = dry_run(1, str(repo), str(plan_path), str(root / "dry.json"))
            self.assertEqual(dry["status"], "SUCCESS")
            self.assertEqual(dry["toolName"], "GenericPatchApplyTool")
            result = apply(1, str(repo), str(plan_path), str(root / "proof.json"), str(root / "patch.diff"))
            self.assertEqual(result["status"], "SUCCESS")
            self.assertIn("<x.version>1.1</x.version>", pom.read_text(encoding="utf-8"))

    def test_patch_apply_is_atomic_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            pom = repo / "pom.xml"
            original = "<project><a.version>1.0</a.version><b.version>1.0</b.version></project>"
            pom.write_text(original, encoding="utf-8")
            plan_path = _write_plan(root, [
                {
                    "patchId": "patch-1",
                    "file": "pom.xml",
                    "oldText": "<a.version>1.0</a.version>",
                    "newText": "<a.version>1.1</a.version>",
                    "expectedOccurrences": 1,
                },
                {
                    "patchId": "patch-2",
                    "file": "pom.xml",
                    "oldText": "<missing.version>1.0</missing.version>",
                    "newText": "<missing.version>1.1</missing.version>",
                    "expectedOccurrences": 1,
                },
            ])
            result = apply(1, str(repo), str(plan_path), str(root / "proof.json"), str(root / "patch.diff"))
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(pom.read_text(encoding="utf-8"), original)


def _write_plan(root: Path, patches: list[dict]) -> Path:
    plan = {
        "schemaVersion": "1.0",
        "artifactId": "plan",
        "workflowId": "wf-test",
        "createdBy": "test",
        "status": "PATCH_AVAILABLE",
        "planId": "plan-1",
        "vulnerabilityDecisions": [{"decision": "PATCH", "vulnerabilityId": "VULN-1", "patches": patches}],
    }
    plan_path = root / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan_path


if __name__ == "__main__":
    unittest.main()
