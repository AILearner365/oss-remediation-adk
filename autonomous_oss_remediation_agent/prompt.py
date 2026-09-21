from __future__ import annotations

import json

from .config import RemediationRequest
from .journal import intent_questionnaire, outcome_questionnaire
from .models import RepositoryBaseline, ValidationReport


AGENT_INSTRUCTION = """
You are the autonomous software-engineering agent responsible for resolving one supplied task in a prepared working environment.

You own the complete work cycle:

1. understand the supplied task;
2. investigate the relevant context and evidence;
3. develop concrete, evidence-supported solutions;
4. select a solution;
5. implement it;
6. reassess it when execution produces new evidence;
7. self-validate the resulting work;
8. submit an honest post-execution result.

Operating principles:

- Treat the supplied Task to Solve and its requirements as the source of truth.
- Respect every supplied constraint. Treat each hard constraint as a mandatory candidate-admissibility condition, not a preference or optimization criterion. Only candidates whose hard-constraint compatibility is established sufficiently for selection may be compared, selected or implemented.
- Before forming candidates, perform decision-relevant investigation reasonably obtainable through the available read-only capabilities. Planned or future investigation is not evidence supporting candidate formation; non-material questions need not be pursued, and genuinely execution-dependent outcomes remain for implementation and validation.
- Distinguish established information, unavailable information, assumptions and facts that require execution evidence.
- Do not present an assumption as an established fact.
- Establish candidate-relevant facts from Task-to-Solve content, directly observed repository state, and observed execution results before reconciling hard constraints. Treat that evidence as stronger than unsupported prior expectations, conventions, interpretations, or guesses. Use expectations to identify discrepancies for investigation, not to change established properties of a proposed operation without additional supporting evidence.
- Before relying on a decision-critical assumption, attempt to verify it using the available evidence and tools. An assumption cannot override established evidence, waive a hard constraint, or make a conflicting candidate admissible.
- When solution choice depends on how relevant state or behavior is produced or controlled, investigate the existing ownership, control, management, inheritance, indirection, configuration, composition, abstraction, or relationships to the depth reasonably necessary for the decision. General technical knowledge may suggest a mechanism to investigate, but when repository-specific evidence is material and reasonably obtainable, establish that the mechanism applies, participates in controlling the relevant state, and has an evidence-supported basis for the intended effect.
- Use repository evidence to evaluate which control points support focused, coherent and maintainable interventions; do not let an early preference for one control point end investigation or eliminate another materially distinct viable mechanism. Preference among viable mechanisms belongs in candidate comparison, not viability determination.
- Preserve required behavior, compatibility and existing system conventions.
- Do not make unnecessary or unrelated changes.
- Do not select a solution merely because it is the fastest way to produce one passing check.
- Scope every validation claim to the properties the underlying check actually evaluated. A successful check supports only those properties; do not generalize it to requirements, success criteria, constraints or outcomes the check did not evaluate. Keep unevaluated coverage unresolved or unverified, and do not claim complete resolution from a passing check, partial improvement or unverified expectation.
- Inspect failures and continue adapting while time and operational budget remain.
- If new evidence weakens or invalidates the selected solution, reassess the complete unresolved task. Retain, revise, extend, replace or combine solutions according to the evidence.
- Do not continue an invalidated solution merely to preserve work already done.
- Do not abandon the complete task merely because the first solution failed.
- Do not expose hidden chain-of-thought. Record concise, decision-relevant conclusions, evidence, assumptions and rationale.
- Do not directly edit the decision journal. The orchestrator owns that artifact.
- Do not perform delivery actions unless a supplied capability explicitly assigns them to you.
- Independent deterministic validation remains authoritative.

Before the first material change in every cycle, use read-only investigation and submit the required pre-execution Model Response through `submit_cycle_intent`.

After that response is accepted, continue implementation in the same turn when possible. Material reassessment remains within the same cycle when warranted; routine execution adaptation does not require a new cycle. Before ending execution, perform available self-validation. The orchestrator will then request the mandatory post-execution result separately through `submit_cycle_outcome` with repository capabilities unavailable.
""".strip()


def canonical_task_to_solve(
    request: RemediationRequest,
    baseline: RepositoryBaseline,
) -> str:
    requirements: list[tuple[str, str, str]] = []

    def add_requirement(kind: str, result: str, evaluation: str) -> None:
        requirements.append((kind, result, evaluation))

    target_description = (
        "Requested findings " + ", ".join(f"`{value}`" for value in request.vulnerability_ids)
        if request.vulnerability_ids
        else "All baseline findings within the configured severity scope"
    )
    add_requirement(
        "Outcome",
        f"{target_description} are absent from the final repository scan.",
        "Fresh deterministic scan and comparison with the authoritative baseline.",
    )
    if request.constraints.prohibited_new_severities:
        severities = ", ".join(request.constraints.prohibited_new_severities)
        add_requirement(
            "Outcome",
            f"No newly introduced findings at prohibited severities `{severities}`.",
            "Deterministic baseline-to-final finding comparison.",
        )
    for command_kind, commands in (
        ("build", request.build_commands),
        ("test", request.test_commands),
        ("startup", request.startup_commands),
    ):
        for command in commands:
            add_requirement(
                "Validation",
                f"Configured {command_kind} command succeeds: `{_markdown_cell(command)}`.",
                "Deterministic command result.",
            )
    if request.constraints.prohibit_suppressions:
        add_requirement(
            "Constraint",
            "No vulnerability-suppression file or suppression entry is introduced.",
            "Deterministic constraint comparison.",
        )
    policy = request.constraints.spring_boot_version_policy
    add_requirement(
        "Constraint",
        "Spring Boot version movement obeys the configured policy: "
        f"allow patch={policy.allow_patch}, allow minor={policy.allow_minor}, "
        f"allow major={policy.allow_major}, allow downgrade={policy.allow_downgrade}, "
        f"approved versions={list(policy.approved_versions)}, required version={policy.required_version!r}.",
        "Deterministic version-policy evaluation when Spring Boot is present.",
    )
    if request.constraints.protected_java_version:
        add_requirement(
            "Constraint",
            f"Java version remains `{request.constraints.protected_java_version}`.",
            "Deterministic protected-value comparison.",
        )
    if request.constraints.protected_spring_boot_version:
        add_requirement(
            "Constraint",
            f"Spring Boot version remains `{request.constraints.protected_spring_boot_version}`.",
            "Deterministic protected-value comparison.",
        )
    if request.constraints.allowed_paths:
        add_requirement(
            "Constraint",
            "All changes stay within allowed paths: " + ", ".join(f"`{path}`" for path in request.constraints.allowed_paths) + ".",
            "Deterministic changed-path evaluation.",
        )
    if request.constraints.protected_paths:
        add_requirement(
            "Constraint",
            "Protected paths remain unchanged: " + ", ".join(f"`{path}`" for path in request.constraints.protected_paths) + ".",
            "Deterministic protected-path comparison.",
        )
    for constraint in request.constraints.engineering_constraints:
        add_requirement("Constraint", constraint, "Applicable deterministic or evidence-based assessment.")
    for constraint in request.constraints.informational_constraints:
        add_requirement("Constraint", constraint, "Evidence-based assessment; not falsely represented as deterministic.")
    add_requirement(
        "Compatibility",
        "Required behavior and compatibility are preserved.",
        "Configured tests, runtime checks, and available compatibility evidence.",
    )
    add_requirement(
        "Engineering quality",
        "Changes are focused, coherent, maintainable, and use an appropriate ownership or configuration boundary when supported by evidence.",
        "Change evidence and engineering assessment.",
    )
    add_requirement(
        "Scope",
        "No unnecessary or unrelated change is included.",
        "Diff and scope assessment.",
    )
    rows = [
        f"| R{index} | {_markdown_cell(kind)} | {_markdown_cell(result)} | {_markdown_cell(evaluation)} |"
        for index, (kind, result, evaluation) in enumerate(requirements, start=1)
    ]
    target_selection = (
        "explicit vulnerability identifiers: " + ", ".join(request.vulnerability_ids)
        if request.vulnerability_ids
        else "all findings in the configured severity scope"
    )
    target_findings = json.dumps(
        [
            {
                "vulnerabilityId": finding.vulnerability_id,
                "aliases": list(finding.aliases),
                "severity": finding.severity,
                "coordinate": finding.coordinate,
                "currentVersion": finding.version,
                "fixedVersions": list(finding.fixed_versions),
                **(
                    {
                        "backendEvidence": {
                            "fixedVersionExpressions": finding.backend_evidence[
                                "fixedVersionExpressions"
                            ]
                        }
                    }
                    if "fixedVersionExpressions" in finding.backend_evidence
                    else {}
                ),
            }
            for finding in baseline.target_findings
        ],
        indent=2,
        sort_keys=True,
    )
    constraints = json.dumps(
        request.to_dict()["constraints"],
        indent=2,
        sort_keys=True,
    )
    budget = request.budget
    return "\n".join(
        [
            "# Task to Solve",
            "",
            "## What is the task, and what must the final result satisfy?",
            "",
            "Resolve the requested problem in the prepared project using this authoritative run information:",
            "",
            f"- Source: `{request.repository_url}`",
            f"- Prepared source: `{baseline.remote_url}`",
            f"- Requested reference: `{request.reference_branch}`",
            f"- Prepared reference: `{baseline.reference}` at commit `{baseline.commit}`",
            f"- Working location: `{baseline.repository_path}`",
            f"- Target selection: {target_selection}",
            f"- Requested severity scope: {', '.join(request.severity_scope) or 'None'}",
            f"- Baseline scanner: `{baseline.scan.backend}`; target finding count: `{len(baseline.target_findings)}`",
            "- Operational budget: "
            f"cycles={budget.max_cycles}, tool calls={budget.max_tool_calls}, "
            f"model calls per turn={budget.max_llm_calls_per_turn}, overall seconds={budget.overall_timeout_seconds}",
            "",
            "### Authoritative baseline target findings",
            "",
            "```json",
            target_findings,
            "```",
            "",
            "### Configured constraints",
            "",
            "```json",
            constraints,
            "```",
            "",
            "The final result must satisfy every applicable requirement below.",
            "",
            "| ID | Type | Required final result | Evaluation |",
            "|---|---|---|---|",
            *rows,
            "",
            "A passing command or partial improvement does not, by itself, constitute complete resolution.",
        ]
    )


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def initial_message(
    request: RemediationRequest,
    baseline: RepositoryBaseline,
    task_to_solve: str | None = None,
) -> str:
    task = task_to_solve or canonical_task_to_solve(request, baseline)
    return (
        task
        + "\n\nYou are expected to implement and validate a solution for the Task to Solve.\n\n"
        "Before making the first material change:\n\n"
        "1. investigate the supplied task and relevant evidence using read-only capabilities;\n"
        "2. answer every Model Response question below;\n"
        "3. develop only concrete, evidence-supported solutions;\n"
        "4. ensure every proposed solution satisfies every applicable hard constraint;\n"
        "5. select the solution you currently intend to implement;\n"
        "6. submit the completed pre-execution Model Response through `submit_cycle_intent`.\n\n"
        "This is the decision record for the solution you intend to implement, not a documentation-only exercise or a request for vague hypothetical directions. Investigate avoidable uncertainty before proposing solutions. When a fact cannot be established until execution, identify it as execution-dependent evidence rather than established fact. Do not rewrite the Task to Solve. After acceptance, continue implementation in the same turn, materially reassess within the cycle if new evidence warrants it, and self-validate before ending execution.\n\n"
        + intent_questionnaire(1)
    )


def intent_retry_message(cycle: int, errors: list[str]) -> str:
    return (
        f"Cycle {cycle} Problem Analysis and Solution Decision has not been accepted. Correct the checkpoint using `submit_cycle_intent`. "
        "Do not perform material work before acceptance. Rejection details:\n- "
        + "\n- ".join(errors)
    )


def execution_continuation_message(cycle: int) -> str:
    return (
        f"Your Problem Analysis and Solution Decision for Cycle {cycle} has been accepted. "
        "Execution capabilities are now available, and this same cycle is still in progress. "
        "The preceding invocation ended without any execution-phase capability attempt. Continue solving the "
        "original Task to Solve now: implement the selected solution, or perform the material investigation needed "
        "to establish that it should be revised, is unnecessary, or is genuinely blocked. Adapt within this cycle "
        "if new evidence warrants reassessment, and perform appropriate self-validation before ending execution. "
        "Do not merely restate the accepted decision."
    )


def outcome_message(cycle: int, execution_summary: str, evidence: dict) -> str:
    return (
        f"Execution for Cycle {cycle} has ended. Repository read, edit, and shell capabilities are now unavailable. "
        "Submit a metadata-only Cycle Outcome through `submit_cycle_outcome` for any successful, partial, blocked, "
        "failed, inconclusive, or no-change execution. Report what was actually implemented, any material differences "
        "from the selected solution, material implementation evidence and reassessments, self-validation, and unresolved "
        "coverage. Scope each self-validation claim to what its underlying check actually evaluated; keep unevaluated "
        "coverage unresolved or unverified, and do not claim deterministic success.\n\n"
        + outcome_questionnaire()
        + "\n\nExecution response (compatibility evidence):\n"
        + execution_summary
        + "\n\nDeterministic execution evidence available before validation:\n"
        + json.dumps(evidence, indent=2, sort_keys=True, default=str)
    )


def outcome_retry_message(cycle: int, errors: list[str]) -> str:
    return (
        f"Cycle {cycle} Outcome has not been accepted. Correct it using `submit_cycle_outcome`; only that metadata "
        "capability is available. Rejection details:\n- " + "\n- ".join(errors)
    )


def validation_feedback(report: ValidationReport, journal_context: str, next_cycle: int) -> str:
    failed_checks = []
    for check in report.checks:
        if check.passed:
            continue
        item = {"name": check.name, "message": check.message}
        if check.name != "fresh_vulnerability_scan" and check.evidence:
            item["evidence"] = check.evidence
        failed_checks.append(item)
    scan = None
    if report.scan:
        scan = {
            "backend": report.scan.backend,
            "succeeded": report.scan.succeeded,
            "outcome": report.scan.effective_outcome.value,
            "failureKind": report.scan.failure_kind.value if report.scan.failure_kind else None,
            "error": report.scan.error,
            "findings": [
                {
                    "vulnerabilityId": finding.vulnerability_id,
                    "aliases": list(finding.aliases),
                    "severity": finding.severity,
                    "coordinate": finding.coordinate,
                    "currentVersion": finding.version,
                    "fixedVersions": list(finding.fixed_versions),
                    **(
                        {
                            "backendEvidence": {
                                "fixedVersionExpressions": finding.backend_evidence[
                                    "fixedVersionExpressions"
                                ]
                            }
                        }
                        if "fixedVersionExpressions" in finding.backend_evidence
                        else {}
                    ),
                }
                for finding in report.scan.findings
            ],
        }
    evidence = {
        "cycle": report.cycle,
        "failedChecks": failed_checks,
        "changedFiles": list(report.changed_files),
        "cumulativeDiffPath": report.diff_path,
        "currentStateDigest": report.tree_digest,
        "cycleEvidence": report.cycle_evidence.to_dict() if report.cycle_evidence else None,
        "scan": scan,
    }
    return (
        "Deterministic validation did not establish success. Continue solving the original canonical Task to Solve in the same repository and ADK session. The validation is authoritative evidence about progress, not a replacement objective, and no prior solution receives authority merely because it was previously selected or implemented.\n\n"
        "Use read-only capabilities before the next pre-execution submission to inspect current repository state and reinvestigate decision-critical claims where reasonably feasible. Critically reassess all relevant accumulated prior-cycle findings, assumptions, decisions, implementation directions, self-validation statements, and retrospective descriptions against the original Task to Solve. Treat prior model statements as claims rather than deterministic facts. Identify what remains supported, what is contradicted or incomplete, what cannot be verified and therefore remains uncertain, what implemented work is present and useful, what directions should no longer constrain the decision, and what remains unresolved. Do not automatically continue or discard previous work. Only after this evidence audit, develop current concrete candidates and select the best-supported solution now.\n\n"
        "Scanner fixed-version fields are evidence only: they are not required target versions, empty fixedVersions does not mean remediation is impossible, and ambiguous backend expressions must not be guessed into concrete versions.\n\n"
        "The bounded Markdown decision journal below preserves provenance across relevant prior cycles. The original Task to Solve remains the run anchor. Prior model-authored records are reasoning artifacts; deterministic validation sections and the separately supplied latest validation evidence are authoritative within their stated scope.\n\n"
        + journal_context
        + "\n\n"
        + "Latest deterministic validation evidence:\n"
        + json.dumps(evidence, indent=2, sort_keys=True)
        + "\n\n"
        + intent_questionnaire(next_cycle)
    )
