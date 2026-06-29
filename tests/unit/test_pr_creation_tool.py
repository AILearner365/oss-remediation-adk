from pathlib import Path
import json
import tempfile
import unittest

from oss_remediation_agent.tools.pr_creation_tool import create_pr_summary


class PRCreationToolTests(unittest.TestCase):
    def test_pr_summary_uses_accepted_patch_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            validation_path = root / "attempt-1" / "validation-result.json"
            validation_path.parent.mkdir(parents=True)
            validation_path.write_text(json.dumps({
                "osvValidation": {
                    "status": "SUCCESS",
                    "remainingCriticalCount": 0,
                    "remainingHighCount": 0,
                    "newCriticalHighIntroduced": False,
                },
                "changeScopeValidation": {"status": "SUCCESS"},
                "buildValidation": {"status": "SUCCESS"},
                "testValidation": {"status": "SUCCESS"},
            }), encoding="utf-8")
            manifest = {
                "workflowId": "wf",
                "workspaceRoot": str(root),
                "baseline": {"baselineBuildResult": "baseline/baseline-build-result.json"},
                "attempts": [{"attemptNumber": 1, "validationResult": "attempt-1/validation-result.json"}],
                "acceptedPatchSet": {
                    "status": "VALIDATED",
                    "remediationSummary": [
                        {
                            "vulnerabilityId": "GHSA-1234",
                            "dependency": "org.yaml:snakeyaml",
                            "oldVersion": "1.33",
                            "newVersion": "2.2",
                            "status": "REMEDIATED",
                            "statusReason": "Patch set validated successfully.",
                        }
                    ],
                },
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = create_pr_summary(str(manifest_path), str(root / "pr-summary.json"), str(root / "pr-description.md"), workflow_id="wf")

            self.assertEqual(result["status"], "SUCCESS")
            summary = json.loads((root / "pr-summary.json").read_text(encoding="utf-8"))
            row = summary["remediationSummary"][0]
            self.assertEqual(row["dependency"], "org.yaml:snakeyaml")
            self.assertEqual(row["oldVersion"], "1.33")
            self.assertEqual(row["newVersion"], "2.2")
            markdown = (root / "pr-description.md").read_text(encoding="utf-8")
            self.assertIn("org.yaml:snakeyaml", markdown)
            self.assertNotIn("UNKNOWN", markdown)


if __name__ == "__main__":
    unittest.main()
