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
from autonomous_oss_remediation_agent.prompt import AGENT_INSTRUCTION, validation_feedback


class AutonomousPromptContinuityTests(unittest.TestCase):
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
        self.assertNotIn("scanner-raw-secret", feedback)
        self.assertNotIn("requiredVersion", feedback)


def _validation_report() -> ValidationReport:
    finding = VulnerabilityFinding(
        vulnerability_id="CVE-2026-0001",
        aliases=("GHSA-example",),
        severity="HIGH",
        group_id="org.example",
        artifact_id="demo",
        package_name="org.example:demo",
        version="1.0",
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
