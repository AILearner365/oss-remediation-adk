from __future__ import annotations

import unittest

from autonomous_oss_remediation_agent.models import (
    CommandResult,
    RepositoryCycleEvidence,
    ScanReport,
    ValidationCheck,
    ValidationReport,
    VulnerabilityFinding,
)
from autonomous_oss_remediation_agent.prompt import (
    AGENT_INSTRUCTION,
    extract_working_state,
    validation_feedback,
)


class AutonomousPromptContinuityTests(unittest.TestCase):
    def test_extracts_only_explicit_working_state_section(self):
        response = (
            "Updated the managed dependency property and verified the effective graph.\n\n"
            "WORKING_STATE\n"
            "- Understanding: dependency ownership is now clear\n"
            "- Current strategy/hypothesis: validate the property change\n"
            "- Unresolved: deterministic scan result"
        )

        working_state = extract_working_state(response)

        self.assertTrue(working_state.startswith("WORKING_STATE\n"))
        self.assertIn("dependency ownership is now clear", working_state)
        self.assertNotIn("Updated the managed dependency", working_state)

    def test_missing_or_malformed_working_state_uses_bounded_fallback(self):
        missing = "Investigated the repository. " + ("detail " * 300) + "TAIL_MARKER"
        malformed = "Investigation complete. WORKING_STATE is still being developed."

        missing_fallback = extract_working_state(missing)
        malformed_fallback = extract_working_state(malformed)

        self.assertIn("No structured WORKING_STATE was supplied", missing_fallback)
        self.assertIn("Visible response excerpt", missing_fallback)
        self.assertLess(len(missing_fallback), 800)
        self.assertNotIn("TAIL_MARKER", missing_fallback)
        self.assertIn("No structured WORKING_STATE was supplied", malformed_fallback)

    def test_instruction_requires_concise_model_owned_working_state(self):
        self.assertIn("model-owned working state", AGENT_INSTRUCTION)
        self.assertIn("current understanding", AGENT_INSTRUCTION)
        self.assertIn("strategy or hypothesis", AGENT_INSTRUCTION)
        self.assertIn("Revise or replace it whenever evidence warrants", AGENT_INSTRUCTION)
        self.assertIn("Do not provide hidden chain-of-thought", AGENT_INSTRUCTION)

    def test_failed_validation_feedback_preserves_objective_and_prior_strategy(self):
        prior_state = (
            "WORKING_STATE\n"
            "- Understanding: managed dependency remains vulnerable\n"
            "- Current strategy/hypothesis: inspect the existing version owner\n"
            "- Assumptions: current declaration controls the graph\n"
            "- Progress: repository structure inspected\n"
            "- Unresolved: validation still reports the target"
        )
        feedback = validation_feedback(_validation_report(), prior_state)

        self.assertIn("original remediation objective, constraints, and completion criteria", feedback)
        self.assertIn("new evidence, not a replacement objective", feedback)
        self.assertIn("supports, contradicts, or leaves unresolved", feedback)
        self.assertIn("continue, modify, or replace your strategy", feedback)
        self.assertIn(prior_state, feedback)
        self.assertIn('"currentVersion": "1.0"', feedback)
        self.assertIn('"fixedVersions": [', feedback)
        self.assertIn('"2.0"', feedback)
        self.assertIn('"fixedVersionExpressions": [', feedback)
        self.assertIn('"[2.0,3.0)"', feedback)
        self.assertIn("empty fixedVersions does not mean remediation is impossible", feedback)
        self.assertNotIn("scanner-raw-secret", feedback)
        self.assertNotIn("requiredVersion", feedback)

    def test_empty_fixed_versions_remain_normalized_evidence(self):
        report = _validation_report()
        finding = report.scan.findings[0]
        report = ValidationReport(
            cycle=report.cycle,
            passed=report.passed,
            checks=report.checks,
            changed_files=report.changed_files,
            diff_path=report.diff_path,
            tree_digest=report.tree_digest,
            scan=ScanReport(
                True,
                (
                    VulnerabilityFinding(
                        vulnerability_id=finding.vulnerability_id,
                        aliases=finding.aliases,
                        severity=finding.severity,
                        group_id=finding.group_id,
                        artifact_id=finding.artifact_id,
                        package_name=finding.package_name,
                        version=finding.version,
                    ),
                ),
                report.scan.command_result,
                report.scan.raw_report_path,
            ),
            cycle_evidence=report.cycle_evidence,
        )

        feedback = validation_feedback(report, "WORKING_STATE\n- Unresolved: target remains")

        self.assertIn('"fixedVersions": []', feedback)
        self.assertNotIn("NO_SAFE_REMEDIATION", feedback)


def _validation_report() -> ValidationReport:
    finding = VulnerabilityFinding(
        vulnerability_id="CVE-2026-0001",
        aliases=("GHSA-example",),
        severity="HIGH",
        group_id="org.example",
        artifact_id="demo",
        package_name="org.example:demo",
        version="1.0",
        fixed_versions=("2.0",),
        backend_evidence={"fixedVersionExpressions": ["[2.0,3.0)"]},
    )
    scan = ScanReport(
        True,
        (finding,),
        CommandResult(["scanner"], ".", 1, stdout="scanner-raw-secret"),
        "scan.json",
    )
    cycle_evidence = RepositoryCycleEvidence(
        before_state_digest="before",
        after_state_digest="after",
        before_changed_files=("pom.xml",),
        after_changed_files=("pom.xml",),
        paths_added_to_change_set=(),
        paths_modified_since_cycle_start=("pom.xml",),
        paths_removed_from_change_set=(),
        repository_state_changed=True,
        matches_prior_cycle=None,
        delta_path="cycle-delta.json",
    )
    return ValidationReport(
        cycle=2,
        passed=False,
        checks=(ValidationCheck("target_findings_resolved", False, "Target remains"),),
        changed_files=("pom.xml",),
        diff_path="cycle-2.diff",
        tree_digest="after",
        scan=scan,
        cycle_evidence=cycle_evidence,
    )


if __name__ == "__main__":
    unittest.main()
