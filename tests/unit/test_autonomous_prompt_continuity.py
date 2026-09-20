from __future__ import annotations

import unittest

from autonomous_oss_remediation_agent.config import RemediationRequest
from autonomous_oss_remediation_agent.journal import (
    INTENT_SECTIONS,
    OUTCOME_SECTIONS,
    PRIOR_CYCLE_INTENT_SECTIONS,
)
from autonomous_oss_remediation_agent.models import (
    CommandResult,
    ConstraintBaseline,
    RepositoryBaseline,
    RepositoryCycleEvidence,
    ScanReport,
    ValidationCheck,
    ValidationReport,
    VulnerabilityFinding,
)
from autonomous_oss_remediation_agent.prompt import (
    AGENT_INSTRUCTION,
    canonical_task_to_solve,
    compatibility_working_state,
    initial_message,
    outcome_message,
    validation_feedback,
)


class AutonomousPromptContinuityTests(unittest.TestCase):
    def test_runtime_messages_expose_every_canonical_questionnaire_section(self):
        initial = initial_message(RemediationRequest(repository_url="repo"), _baseline())
        outcome = outcome_message(1, "execution summary", {})

        for section in INTENT_SECTIONS:
            self.assertIn(f"`{section}`", initial)
        for section in OUTCOME_SECTIONS:
            self.assertIn(f"`{section}`", outcome)
        self.assertEqual(4, len(INTENT_SECTIONS))
        self.assertEqual(3, len(OUTCOME_SECTIONS))
        self.assertIn("One concrete evidence-supported candidate is sufficient", initial)
        self.assertIn("never manufacture alternatives", initial)
        self.assertIn("add clearly named, decision-relevant sections", initial.lower())
        self.assertIn("Allowed `status` values", outcome)
        self.assertIn("assumptions", initial)
        self.assertIn("execution-dependent evidence", initial)
        self.assertIn("# Task to Solve", initial)
        self.assertNotIn("Prior-cycle reassessment", initial)

    def test_canonical_task_is_deterministic_and_contains_normalized_run_information(self):
        request = RemediationRequest(
            repository_url="repo",
            vulnerability_ids=("CVE-2026-0001",),
            build_commands=("mvn verify",),
        )
        baseline = _baseline()

        first = canonical_task_to_solve(request, baseline)
        second = canonical_task_to_solve(request, baseline)

        self.assertEqual(first, second)
        self.assertIn("# Task to Solve", first)
        self.assertIn("CVE-2026-0001", first)
        self.assertIn("abc123", first)
        self.assertIn("mvn verify", first)
        self.assertIn("A passing command or partial improvement", first)

    def test_instruction_rejects_model_authored_working_state(self):
        self.assertIn("Do not emit `WORKING_STATE`", AGENT_INSTRUCTION)
        self.assertNotIn("model-owned working state", AGENT_INSTRUCTION)
        self.assertIn("Do not expose hidden chain-of-thought", AGENT_INSTRUCTION)

    def test_compatibility_working_state_is_deterministic_outcome_projection(self):
        state = compatibility_working_state(
            "INCONCLUSIVE",
            {
                "Implementation Result": "The owning property was updated; scanner coverage remains unverified.",
                "Cycle Intent vs. Implementation": "No material change from the selected solution.",
                "Implementation Trail": "Inspected ownership, edited the property, and ran self-validation.",
            },
        )

        self.assertIn("deprecated deterministic compatibility projection", state)
        self.assertIn("Outcome status: INCONCLUSIVE", state)
        self.assertIn("owning property was updated", state)
        self.assertNotIn("Final approach present at cycle end", state)

    def test_failed_validation_feedback_preserves_journal_and_exposes_next_questionnaire(self):
        prior_journal = "# Task to Solve\n\nOriginal task\n\n# Cycle 1 — Problem Analysis and Solution Decision"
        feedback = validation_feedback(_validation_report(), prior_journal, 2)

        self.assertIn("original canonical Task to Solve", feedback)
        self.assertIn("not a replacement objective", feedback)
        self.assertIn("Treat prior model statements as claims", feedback)
        self.assertIn("what cannot be verified and therefore remains uncertain", feedback)
        self.assertIn("Do not automatically continue or discard previous work", feedback)
        self.assertIn(prior_journal, feedback)
        for section in (*INTENT_SECTIONS, *PRIOR_CYCLE_INTENT_SECTIONS):
            self.assertIn(f"`{section}`", feedback)
        self.assertIn('"currentVersion": "1.0"', feedback)
        self.assertIn('"fixedVersions": [', feedback)
        self.assertIn('"2.0"', feedback)
        self.assertIn('"fixedVersionExpressions": [', feedback)
        self.assertIn('"[2.0,3.0)"', feedback)
        self.assertIn("empty fixedVersions does not mean remediation is impossible", feedback)
        self.assertNotIn("scanner-raw-secret", feedback)
        self.assertNotIn("requiredVersion", feedback)
        self.assertEqual(("Prior-cycle reassessment",), PRIOR_CYCLE_INTENT_SECTIONS)
        self.assertLess(
            feedback.index("`Prior-cycle reassessment`"),
            feedback.index("`Concrete candidate solutions`"),
        )

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

        feedback = validation_feedback(report, "# Journal", 2)

        self.assertIn('"fixedVersions": []', feedback)
        self.assertNotIn("NO_SAFE_REMEDIATION", feedback)


def _baseline() -> RepositoryBaseline:
    report = _validation_report()
    return RepositoryBaseline(
        repository_path="repo",
        commit="abc123",
        reference="main",
        remote_url="repo",
        build_results=(CommandResult(["build"], "repo", 0),),
        scan=report.scan,
        constraints=ConstraintBaseline(),
        target_findings=report.scan.findings,
    )


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
