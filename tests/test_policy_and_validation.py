import unittest
from pathlib import Path

from oss_remediation_agent.policy import RemediationPolicy
from oss_remediation_agent.schemas import make_remediation_report, validate_remediation_report
from oss_remediation_agent.tools.validation_tools import evaluate_pr_creation


def successful_report():
    report = make_remediation_report(
        {
            "repositoryUrl": "https://github.com/example/repo.git",
            "referenceBranch": "main",
            "featureBranch": "oss-remediation-main-1234-20260101T000000Z",
        },
        workspace_path=Path("/tmp/repo"),
    )
    report.update(
        {
            "remediationStatus": "SUCCESS",
            "buildStatus": "SUCCESS",
            "testStatus": "SUCCESS",
            "modifiedFiles": ["pom.xml"],
            "remediatedVulnerabilities": [{"dependencyName": "g:a", "status": "FIXED"}],
            "postRemediationScan": {
                "criticalRemaining": 0,
                "highRemaining": 0,
                "newCriticalOrHighIntroduced": False,
                "remainingCriticalOrHighItems": [],
            },
        }
    )
    return report


class PolicyAndValidationTests(unittest.TestCase):
    def test_policy_defaults_are_safe(self):
        policy = RemediationPolicy()
        self.assertTrue(policy.allows_severity("CRITICAL"))
        self.assertTrue(policy.allows_severity("HIGH"))
        self.assertFalse(policy.allows_severity("MEDIUM"))
        self.assertTrue(policy.allows_file("module-a/pom.xml"))
        self.assertFalse(policy.allows_file("src/main/java/App.java"))

    def test_remediation_schema_accepts_valid_report(self):
        result = validate_remediation_report(successful_report())
        self.assertTrue(result.valid, result.errors)

    def test_pr_creation_allows_successful_report(self):
        decision = evaluate_pr_creation(successful_report(), RemediationPolicy())
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["code"], "PR_ALLOWED")

    def test_pr_creation_blocks_manual_review(self):
        report = successful_report()
        report["manualReviewItems"] = [{"dependencyName": "g:b", "status": "MANUAL_REVIEW"}]
        decision = evaluate_pr_creation(report, RemediationPolicy())
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["code"], "MANUAL_REVIEW_PRESENT")

    def test_pr_creation_blocks_non_pom_file(self):
        report = successful_report()
        report["modifiedFiles"] = ["pom.xml", "src/main/java/App.java"]
        decision = evaluate_pr_creation(report, RemediationPolicy())
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["code"], "INVALID_MODIFIED_FILES")


if __name__ == "__main__":
    unittest.main()
