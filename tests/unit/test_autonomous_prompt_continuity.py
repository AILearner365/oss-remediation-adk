from __future__ import annotations

import unittest

from autonomous_oss_remediation_agent.config import RemediationRequest
from autonomous_oss_remediation_agent.journal import (
    INTENT_SECTIONS,
    OUTCOME_SECTIONS,
    PRIOR_CYCLE_INTENT_SECTIONS,
    intent_questionnaire,
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
        self.assertEqual(5, len(INTENT_SECTIONS))
        self.assertEqual(3, len(OUTCOME_SECTIONS))
        self.assertIn("Candidate count must result from investigation and synthesis", initial)
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

    def test_problem_understanding_is_project_contextual_without_premature_root_cause(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn("Problem understanding in project context", INTENT_SECTIONS)
        self.assertIn("What engineering problem is currently established in the context of this project?", message)
        self.assertIn("material relationships among symptoms or components when supported by available evidence", message)
        self.assertIn("Do not require or assert a shared or higher-level root cause before the evidence supports one", message)
        self.assertIn("Do not propose solutions, enumerate approaches, select mechanisms", message)

    def test_instruction_defines_workspace_and_evidence_contract_without_mandatory_sequence(self):
        self.assertIn("isolated experimental repository snapshot", AGENT_INSTRUCTION)
        self.assertIn("exact current authoritative working state", AGENT_INSTRUCTION)
        self.assertIn('workspace="experiment"', AGENT_INSTRUCTION)
        self.assertIn("experimental edits never become authoritative automatically", AGENT_INSTRUCTION)
        self.assertIn("A failed retrieval is not evidence", AGENT_INSTRUCTION)
        self.assertIn("without imposing irrelevant mandatory tool calls", AGENT_INSTRUCTION)
        self.assertNotIn("must run the scanner", AGENT_INSTRUCTION.lower())

    def test_self_validation_claims_remain_within_each_checks_evaluated_scope(self):
        outcome = outcome_message(1, "execution summary", {})

        self.assertIn(
            "Scope every validation claim to the properties the underlying check actually evaluated",
            AGENT_INSTRUCTION,
        )
        self.assertIn("A successful check supports only those properties", AGENT_INSTRUCTION)
        self.assertIn(
            "do not generalize it to requirements, success criteria, constraints or outcomes the check did not evaluate",
            AGENT_INSTRUCTION,
        )
        self.assertIn("Keep unevaluated coverage unresolved or unverified", AGENT_INSTRUCTION)
        self.assertIn(
            "Scope each self-validation claim to what its underlying check actually evaluated",
            outcome,
        )
        self.assertIn(
            "a successful check does not establish a requirement, success criterion, constraint, or outcome that it did not evaluate",
            outcome,
        )
        self.assertIn("keep that coverage unresolved or unverified", outcome)
        self.assertIn("Self-validation is not authoritative deterministic validation", outcome)

    def test_pre_execution_reasoning_reconciles_constraints_control_and_exploration(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "then reconcile those properties against every applicable hard requirement and constraint",
            message,
        )
        self.assertIn(
            "An established conflict makes a mechanism ineligible for selection or implementation",
            message,
        )
        self.assertIn(
            "to the depth reasonably necessary for the decision",
            message,
        )
        self.assertIn(
            "ownership, control, management, inheritance, indirection, configuration, composition, abstraction, relationships",
            message,
        )
        self.assertIn(
            "Discovering an apparently appropriate control point does not by itself complete exploration",
            message,
        )
        self.assertIn("Finding one credible or workable mechanism is not sufficient reason to stop exploration", message)
        self.assertIn("materially distinct intervention mechanisms", message)
        self.assertIn("Candidate count is the result of investigation and synthesis", message)
        self.assertIn(
            "preserve them as separate concrete candidates when appropriate",
            message,
        )
        self.assertIn("If only one viable candidate remains after evidence-based approach elimination, one candidate is valid", message)
        self.assertIn("Never manufacture alternatives merely to satisfy a count", message)
        self.assertIn("Keep the synthesis proportional and decision-relevant", message)

    def test_engineering_synthesis_owns_project_applicability_and_high_level_solution_space(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn("Project-applicable engineering synthesis and high-level solution space", INTENT_SECTIONS)
        self.assertIn("Explain why the rationale behind each consideration matters to this problem and project", message)
        self.assertIn("should be retained as-is, adapted, rejected for this project, or left uncertain", message)
        self.assertIn("derive the materially distinct high-level solution approaches", message)
        self.assertIn("Record evidence-based elimination or unresolved viability", message)
        self.assertIn("There is no required approach count", message)
        self.assertIn("A simple isolated problem may require only a short synthesis", message)
        self.assertIn("Do not manufacture approaches", message)
        self.assertIn("Do not repeat the investigation log", message)
        self.assertIn("specify exact file, version, or configuration edits", message)
        self.assertIn("compare concrete candidates, select a solution", message)

    def test_viability_is_determined_before_preference_and_candidate_comparison(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "do not let an early preference end exploration or eliminate another materially distinct viable mechanism",
            AGENT_INSTRUCTION,
        )
        self.assertIn(
            "do not eliminate an approach merely because another already appears preferable",
            message,
        )
        self.assertIn("relative preference does not establish non-viability", message)
        self.assertIn(
            "even when another candidate already appears preferable",
            message,
        )
        self.assertIn("Relative engineering preference alone is not an elimination reason", message)
        self.assertIn("Uncertainty is not evidence", message)
        self.assertIn(
            "Do not materially eliminate a plausible approach when the deciding reason is an unsupported expectation, convention, potentially stale prior, unresolved assumption, or absence of evidence",
            message,
        )
        self.assertIn("preserve its unresolved viability instead", message)
        self.assertIn(
            "An approach may be eliminated when observed task, repository, or execution evidence, current authoritative information, or a hard task constraint materially establishes",
            message,
        )
        self.assertIn(
            "Apply these engineering preferences here, after candidate formation; do not use them to retroactively exclude a viable candidate",
            message,
        )

    def test_current_information_discovers_project_applicable_solution_space(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn("unsupported or potentially stale prior expectations", AGENT_INSTRUCTION)
        self.assertIn(
            "current evidence takes precedence over unsupported prior knowledge",
            AGENT_INSTRUCTION,
        )
        self.assertIn(
            "When a material decision depends on information that may have changed outside the repository",
            AGENT_INSTRUCTION,
        )
        self.assertIn("obtain reasonably available current authoritative evidence", message)
        self.assertIn(
            "discover the actual available and potentially applicable solution space, not merely to confirm the first preferred solution",
            message,
        )
        self.assertIn("what options exist, what outcome they provide", message)
        self.assertIn("what applies to and happens in this project", message)
        self.assertIn("The newest option is not automatically correct", message)
        self.assertIn("one high-level approach is valid when evidence eliminates the others", message)
        self.assertIn(
            "current external research is not required when such information is immaterial",
            message,
        )
        self.assertIn(
            "Failed, blocked, incomplete, or inconclusive research is not evidence that an option or mechanism does not exist",
            message,
        )
        self.assertIn(
            "Current external evidence may establish what options exist, what outcome they provide",
            message,
        )
        self.assertIn(
            "repository and execution evidence establish what applies to and happens in this project",
            message,
        )
        self.assertIn(
            "investigate the discrepancy rather than declaring the observed project state invalid",
            message,
        )
        self.assertIn("Uncertainty is not evidence for or against an approach", message)
        self.assertIn(
            "repository or experimental evidence to establish which mechanisms are applicable",
            AGENT_INSTRUCTION,
        )
        self.assertIn(
            "candidate viability or selection materially depends on a repository-specific premise",
            AGENT_INSTRUCTION,
        )
        self.assertNotIn("always choose the latest", message.lower())
        self.assertNotIn("must perform external research", message.lower())

    def test_failed_evidence_mechanism_requires_proportional_source_recovery(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "Select evidence mechanisms according to the proposition being established rather than treating any single capability as the universal research mechanism",
            AGENT_INSTRUCTION,
        )
        self.assertIn(
            "Failure, unavailability, inconclusive output, or unusable output from one mechanism does not establish the proposition or its absence",
            AGENT_INSTRUCTION,
        )
        self.assertIn(
            "must not be replaced by unsupported prior knowledge",
            AGENT_INSTRUCTION,
        )
        self.assertIn(
            "Distinguish failure, unavailability, inconclusive results, and unusable output from evidence that establishes the investigated fact or establishes absence",
            message,
        )
        self.assertIn(
            "If the unresolved fact is decision-critical and another appropriate evidence mechanism available through the existing engineering capabilities could materially resolve it",
            message,
        )
        self.assertIn(
            "investigate through a reasonable alternative before candidate selection",
            message,
        )
        self.assertIn(
            "This does not require trying every mechanism, following a fixed fallback sequence, or redundantly confirming a fact after sufficient decision-relevant evidence exists",
            message,
        )
        self.assertIn(
            "If no reasonable available mechanism can obtain sufficient evidence, preserve the uncertainty honestly",
            message,
        )
        self.assertIn(
            "Q2's evidence record is the evidentiary boundary for this synthesis",
            message,
        )
        self.assertNotIn("research_search", message)

    def test_candidate_formation_requires_completed_repository_specific_investigation(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "Before forming candidates, perform decision-relevant investigation reasonably obtainable through the available engineering capabilities",
            AGENT_INSTRUCTION,
        )
        self.assertIn("Planned or future investigation is not evidence supporting candidate formation", AGENT_INSTRUCTION)
        self.assertIn("non-material questions need not be pursued", AGENT_INSTRUCTION)
        self.assertIn("genuinely execution-dependent outcomes remain for implementation and validation", AGENT_INSTRUCTION)
        self.assertIn("The table must report investigation actually performed and evidence actually obtained", message)
        self.assertIn(
            "Planned, intended, future, or not-yet-performed investigation is not a finding and is not evidence supporting candidate formation",
            message,
        )
        self.assertIn(
            "If decision-relevant information is reasonably obtainable through the available engineering capabilities",
            message,
        )
        self.assertIn(
            "Record the evidence about those boundaries here; the engineering conclusion derived from it belongs in the synthesis section",
            message,
        )
        self.assertIn("non-material information does not require exhaustive investigation", message)
        self.assertIn(
            "candidate viability or selection materially depends on a repository-specific premise",
            AGENT_INSTRUCTION,
        )
        self.assertIn(
            "controls, changes, resolves, produces, or otherwise affects relevant state or behavior",
            message,
        )
        self.assertIn(
            "available isolated investigation capabilities can reasonably test that premise",
            message,
        )
        self.assertIn(
            "obtain sufficient evidence before treating the premise as established or the candidate as sufficiently supported for selection",
            message,
        )
        self.assertIn(
            "If sufficient evidence cannot reasonably be obtained, record the premise and the affected approach as unresolved",
            message,
        )
        self.assertIn(
            "that uncertainty neither supports the candidate nor establishes that the mechanism is non-viable",
            message,
        )
        self.assertIn(
            "General technical knowledge may suggest the mechanism or premise to investigate, but does not by itself establish repository-specific applicability or viability",
            message,
        )
        self.assertIn("not exhaustive pre-execution proof", message)
        self.assertIn("experimentally testing every candidate", message)
        self.assertIn("running every validation", message)
        self.assertIn("proving final task success", message)
        self.assertIn(
            "genuinely execution-dependent outcomes may remain for implementation and validation",
            message,
        )
        self.assertIn(
            "candidate formation requires an evidence-supported basis for trying a mechanism, not pre-execution proof of those outcomes",
            message,
        )
        self.assertIn(
            "An assumption must not substitute for reasonably obtainable repository evidence material to candidate formation or selection",
            message,
        )
        self.assertIn(
            "Form candidates only from decision-relevant investigation actually performed, evidence actually obtained, and the project-applicable synthesis above",
            message,
        )
        self.assertIn(
            "Planned investigation or general technical plausibility alone does not establish repository-specific applicability or viability",
            message,
        )
        self.assertIn(
            "do not defer a decision-critical, reasonably testable repository-specific premise until implementation",
            message,
        )
        self.assertIn("or COMPLETE classification", message)
        self.assertIn(
            "do not promote the premise into candidate support, and do not treat the unresolved premise as evidence that the approach is non-viable",
            message,
        )
        self.assertIn(
            "If new evidence weakens or invalidates the selected solution, reassess the complete unresolved task",
            AGENT_INSTRUCTION,
        )
        self.assertIn(
            "implementation intent is directional and may be materially reassessed during this cycle when new evidence warrants it",
            message,
        )

    def test_material_assumptions_expose_decision_dependencies_without_rationalizing(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "Report only assumptions that materially affect the current engineering decision",
            message,
        )
        self.assertIn("which decision or conclusion depends on it", message)
        self.assertIn("what uncertainty or risk remains", message)
        self.assertIn(
            "Do not introduce an assumption merely to explain unexpected evidence or justify proceeding",
            message,
        )
        self.assertIn(
            "If an unresolved interpretation is not necessary to the decision, leave it as uncertainty rather than elevating it into a material assumption",
            message,
        )
        self.assertNotIn("why proceeding is reasonable", message)
        self.assertNotIn("how the selected solution controls the risk", message)

    def test_pre_execution_reasoning_preserves_evidence_precedence_and_uncertainty_boundaries(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "Before reconciling candidates with hard constraints, establish candidate-relevant facts",
            message,
        )
        self.assertIn(
            "Neither unsupported prior knowledge nor general external information may displace stronger task-specific or observed project evidence",
            message,
        )
        self.assertIn(
            "Do not use an unsupported expectation, convention, potentially stale prior, unresolved assumption, or absence of evidence as positive support or as a material reason to eliminate a plausible approach",
            message,
        )
        self.assertIn(
            "Q2's evidence record is the evidentiary boundary for this synthesis; do not invent missing support here",
            message,
        )
        self.assertIn(
            "Investigate hard-constraint-determining uncertainty before candidate selection when reasonably possible using the available investigation capabilities",
            message,
        )
        self.assertIn(
            "the affected candidate is not yet admissible",
            message,
        )
        self.assertIn(
            "the uncertainty must not be converted into an assumption that permits selection",
            message,
        )
        self.assertIn(
            "PARTIAL is not a mechanism for bypassing unresolved hard-constraint compliance",
            message,
        )

    def test_hard_constraints_gate_admissibility_before_engineering_preference(self):
        message = initial_message(RemediationRequest(repository_url="repo"), _baseline())

        self.assertIn(
            "Hard constraints are mandatory candidate-admissibility conditions, not preferences to balance against engineering benefits",
            message,
        )
        self.assertIn(
            "first establish its constraint-relevant properties from the Task to Solve and available repository, tool, and execution evidence; then reconcile those properties",
            message,
        )
        self.assertIn(
            "Only candidates with hard-constraint compatibility established sufficiently for selection are admissible",
            message,
        )
        self.assertIn(
            "An established conflict makes a mechanism ineligible for selection or implementation",
            message,
        )
        self.assertIn(
            "Materially unresolved hard-constraint compatibility makes it not yet admissible and requires further investigation before selection",
            message,
        )
        self.assertIn(
            "Neither an assumption nor a different description, interpretation, or rationale for the same established operation can waive a hard constraint or make it admissible",
            message,
        )
        self.assertIn(
            "A constraint-conflicting mechanism may still be investigated and recorded as eliminated",
            message,
        )
        self.assertIn("Confirm hard-constraint admissibility before applying preference", message)
        self.assertIn("Compare the surviving admissible candidates", message)
        self.assertIn("These qualities cannot outweigh a hard-constraint conflict", message)
        self.assertIn("When several materially distinct high-level approaches remain viable", message)
        self.assertIn("If only one viable candidate remains after evidence-based approach elimination, one candidate is valid", message)
        self.assertIn("Never manufacture alternatives merely to satisfy a count", message)
        self.assertIn(
            "PARTIAL is not a mechanism for bypassing unresolved hard-constraint compliance; it remains valid for safe, evidence-supported, constraint-compliant progress",
            message,
        )
        self.assertIn(
            "Ordinary execution-dependent results that do not determine hard-constraint compliance may remain for implementation, self-validation, and deterministic validation",
            message,
        )

    def test_stable_reasoning_instruction_remains_technology_neutral(self):
        questionnaire = intent_questionnaire(1)
        self.assertIn(
            "investigate the existing ownership, control, management, inheritance, indirection, configuration, composition, abstraction, or relationships",
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
            self.assertNotIn(technology_specific_term, questionnaire)

    def test_execution_continuation_keeps_accepted_decision_in_same_cycle(self):
        message = execution_continuation_message(3)

        self.assertIn("accepted", message)
        self.assertIn("same cycle is still in progress", message)
        self.assertIn("now in authoritative implementation", message)
        self.assertIn("without any execution-phase capability attempt", message)
        self.assertIn("exist only in the isolated experimental workspace", message)
        self.assertIn("have not modified the authoritative repository", message)
        self.assertIn('`workspace="active"` now targets the authoritative repository', message)
        self.assertIn('`workspace="experiment"` remains available', message)
        self.assertIn("not evidence that authoritative implementation has occurred", message)
        self.assertIn("materially reassess within this cycle", message)
        self.assertIn("self-validation after authoritative implementation", message)
        self.assertIn("no authoritative change is legitimately necessary", message)
        self.assertIn("genuinely blocked", message)
        self.assertIn("rather than making an artificial mutation", message)
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
            feedback.index("`Project-applicable engineering synthesis and high-level solution space`"),
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
