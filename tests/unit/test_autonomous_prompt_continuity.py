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
    execution_continuation_message,
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

    def test_instruction_has_no_deprecated_working_state_contract(self):
        self.assertNotIn("WORKING_STATE", AGENT_INSTRUCTION)
        self.assertNotIn("model-owned working state", AGENT_INSTRUCTION)
        self.assertIn("Do not expose hidden chain-of-thought", AGENT_INSTRUCTION)

    def test_pre_execution_reasoning_reconciles_constraints_control_and_exploration(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "Reconcile every candidate against every applicable hard requirement and constraint",
            message,
        )
        self.assertIn("A candidate with an established conflict must not be selected", message)
        self.assertIn(
            "A candidate must not be selected as COMPLETE or PARTIAL when its hard-requirement or hard-constraint compliance depends on an unresolved assumption",
            message,
        )
        self.assertIn(
            "investigate the existing mechanism before selecting an intervention",
            message,
        )
        self.assertIn(
            "ownership, indirection, inheritance, configuration, relationships, or management layers",
            message,
        )
        self.assertIn(
            "rather than introducing a new override merely because one is possible",
            message,
        )
        self.assertIn("Do not stop at the first workable mechanism", message)
        self.assertIn("materially different solution mechanisms", message)
        self.assertIn(
            "One candidate is valid when investigation leaves only one concrete evidence-supported solution",
            message,
        )
        self.assertIn("never manufacture alternatives merely to satisfy a count", message)
        self.assertIn("Possibilities eliminated by evidence do not need to become candidates", message)

    def test_pre_execution_reasoning_preserves_evidence_precedence_and_uncertainty_boundaries(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "must not displace stronger task-specific or observed evidence unless additional evidence establishes",
            message,
        )
        self.assertIn(
            "may identify a decision-critical discrepancy to investigate",
            message,
        )
        self.assertIn(
            "Investigate hard-constraint-determining uncertainty before candidate selection when reasonably possible using available read-only evidence",
            message,
        )
        self.assertIn(
            "preserve it honestly rather than converting it into an assumption that permits selection",
            message,
        )
        self.assertIn(
            "Do not select a candidate with an established hard-requirement or hard-constraint conflict, or one whose compliance depends on an unresolved assumption",
            message,
        )
        self.assertIn(
            "PARTIAL is not a mechanism for bypassing unresolved hard-constraint compliance",
            message,
        )
        self.assertIn(
            "PARTIAL is not a mechanism for bypassing unresolved hard-constraint compliance; it remains valid for safe, evidence-supported, constraint-compliant progress",
            message,
        )
        self.assertIn(
            "Ordinary execution-dependent results that do not determine hard-constraint compliance may remain for implementation, self-validation, and deterministic validation",
            message,
        )

    def test_stable_reasoning_instruction_remains_technology_neutral(self):
        self.assertIn(
            "investigate the existing ownership, indirection, inheritance, configuration, relationships, or management layers",
            AGENT_INSTRUCTION,
        )
        for technology_specific_term in (
            "Maven",
            "Spring Boot",
            "Jackson",
            "dependencyManagement",
            "BOM",
        ):
            self.assertNotIn(technology_specific_term, AGENT_INSTRUCTION)

    def test_execution_continuation_keeps_accepted_decision_in_same_cycle(self):
        message = execution_continuation_message(3)

        self.assertIn("accepted", message)
        self.assertIn("same cycle is still in progress", message)
        self.assertIn("Execution capabilities are now available", message)
        self.assertIn("without any execution-phase capability attempt", message)
        self.assertIn("Do not merely restate", message)

    def test_failed_validation_feedback_preserves_journal_and_exposes_next_questionnaire(self):
        prior_journal = "# Task to Solve\n\nOriginal task\n\n# Cycle 1 — Problem Analysis and Solution Decision"
        feedback = validation_feedback(_validation_report(), prior_journal, 2)

        self.assertIn("original canonical Task to Solve", feedback)
        self.assertIn("not a replacement objective", feedback)
        self.assertIn("Treat prior model statements as claims", feedback)
        self.assertIn("what cannot be verified and therefore remains uncertain", feedback)
        self.assertIn("Do not automatically continue or discard previous work", feedback)
        self.assertNotIn("WORKING_STATE", feedback)
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
