from __future__ import annotations

import unittest

from autonomous_oss_remediation_agent.config import RemediationRequest
from autonomous_oss_remediation_agent.journal import (
    INTENT_SECTIONS,
    OUTCOME_SECTIONS,
    PRIOR_CYCLE_INTENT_SECTIONS,
    STRATEGY_CHECKPOINT_SECTIONS,
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
        self.assertIn("One credible approach", initial)
        self.assertIn("reversible diagnostic experiment", initial)
        self.assertIn("add clearly named, decision-relevant sections", initial.lower())
        self.assertIn("Allowed `status` values", outcome)
        self.assertIn("observations", initial)
        self.assertIn("assumptions", initial)
        self.assertIn("future work", initial)
        self.assertIn("completed evidence", initial)

    def test_instruction_rejects_model_authored_working_state(self):
        self.assertIn("Do not emit `WORKING_STATE`", AGENT_INSTRUCTION)
        self.assertNotIn("model-owned working state", AGENT_INSTRUCTION)
        self.assertIn("Do not provide hidden chain-of-thought", AGENT_INSTRUCTION)

    def test_instruction_requires_evidence_discipline_without_prescribing_strategy(self):
        for phrase in (
            "according to their evidence, not merely their source",
            "preserve uncertainty",
            "Prior effort is not evidence",
            "partial success establishes only what the evidence supports",
            "invocation failure",
            "configured deterministic validation remains authoritative",
        ):
            self.assertIn(phrase, AGENT_INSTRUCTION)
        for section in STRATEGY_CHECKPOINT_SECTIONS:
            self.assertIn(f"`{section}`", AGENT_INSTRUCTION)
        self.assertNotIn("ELIGIBLE / INELIGIBLE / NEEDS_EVIDENCE", AGENT_INSTRUCTION)
        self.assertNotIn("numeric score", AGENT_INSTRUCTION.lower())

    def test_compatibility_working_state_is_deterministic_outcome_projection(self):
        state = compatibility_working_state(
            "INCONCLUSIVE",
            {
                "Final approach present at cycle end": "Inspected dependency ownership.",
                "Evidence actually observed": "The parent controls the version.",
                "Remaining work, blockers, or uncertainty": "Scanner evidence remains.",
                "Cycle conclusion": "Continue in another cycle.",
            },
        )

        self.assertIn("deprecated deterministic compatibility projection", state)
        self.assertIn("Outcome status: INCONCLUSIVE", state)
        self.assertIn("The parent controls the version", state)

    def test_failed_validation_feedback_preserves_journal_and_exposes_next_questionnaire(self):
        prior_journal = "# Baseline Contract\n\ncommit: abc\n\n# Cycle 1 — Intent"
        feedback = validation_feedback(_validation_report(), prior_journal, 2)

        self.assertIn("original remediation objective, constraints, and completion criteria", feedback)
        self.assertIn("new evidence, not a replacement objective", feedback)
        self.assertIn("supports, contradicts, or leaves unresolved", feedback)
        self.assertIn("retaining, extending, revising, and replacing", feedback)
        self.assertIn("Prior-cycle work is evidence, not an endorsed strategy", feedback)
        self.assertIn("complete original contract", feedback)
        self.assertIn("local invocation failure", feedback)
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
