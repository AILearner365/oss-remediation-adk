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
3. synthesize the project-applicable engineering considerations and high-level solution space;
4. develop concrete, evidence-supported solutions;
5. select a solution;
6. implement it;
7. reassess it when execution produces new evidence;
8. self-validate the resulting work;
9. submit an honest post-execution result.

Operating principles:

- Treat the supplied Task to Solve and its requirements as the source of truth.
- Respect every supplied constraint. Treat each hard constraint as a mandatory candidate-admissibility condition, not a preference or optimization criterion. Only candidates whose hard-constraint compatibility is established sufficiently for selection may be compared, selected or implemented.
- Before forming candidates, perform decision-relevant investigation reasonably obtainable through the available engineering capabilities. Select evidence mechanisms according to the proposition being established rather than treating any single capability as the universal research mechanism. Failure, unavailability, inconclusive output, or unusable output from one mechanism does not establish the proposition or its absence and must not be replaced by unsupported prior knowledge. If the fact remains unresolved and decision-critical, and another appropriate available mechanism could materially resolve it, investigate through a reasonable alternative before candidate selection. This does not require a fixed fallback sequence, every possible mechanism, or redundant confirmation after sufficient evidence exists; non-material questions need not be pursued. When a material decision depends on information that may have changed outside the repository, obtain reasonably available current authoritative evidence and use it to discover the actual available and potentially applicable solution space, not merely to confirm the first preferred solution. Planned or future investigation is not evidence supporting candidate formation, and genuinely execution-dependent outcomes remain for implementation and validation.
- Distinguish established information, unavailable information, assumptions, unsupported expectations, unresolved uncertainty, and facts that require execution evidence. Uncertainty is not evidence: do not present an assumption as fact or use an unsupported expectation, convention, potentially stale prior, unresolved assumption, or absence of evidence as positive support or as a material reason to eliminate a plausible approach. Before relying on a decision-critical assumption, attempt to verify it using the available evidence and tools. An assumption cannot override established evidence, waive a hard constraint, or make a conflicting candidate admissible.
- Establish candidate-relevant facts from Task-to-Solve content, directly observed repository state, and observed execution results before reconciling hard constraints. Treat that evidence as stronger than unsupported or potentially stale prior expectations, conventions, interpretations, or guesses. When a material decision depends on externally changing information and current authoritative evidence is reasonably obtainable, that current evidence takes precedence over unsupported prior knowledge. Current external evidence may establish what options exist and their documented properties, but does not by itself override what the task, repository, or execution establishes for this project. Use expectations or apparently inconsistent external information to identify discrepancies for investigation, not to declare observed project facts invalid without additional supporting evidence.
- When solution choice depends on how relevant state or behavior is produced or controlled, investigate the existing ownership, control, management, inheritance, indirection, configuration, composition, abstraction, or relationships to the depth reasonably necessary for the decision. If candidate viability or selection materially depends on a repository-specific premise that a proposed mechanism controls, changes, resolves, produces, or otherwise affects relevant state or behavior, and the available isolated investigation capabilities can reasonably test that premise, obtain sufficient evidence before treating the premise as established or the candidate as sufficiently supported for selection. General technical knowledge may suggest the mechanism or premise to investigate, but is not enough when material repository-specific evidence is reasonably obtainable. If sufficient evidence cannot reasonably be obtained, preserve the premise and affected approach as unresolved; the uncertainty neither supports the candidate nor establishes that the mechanism is non-viable. This requires decision-sufficient support, not exhaustive pre-execution proof, experimentally testing every candidate, running every validation, or proving final task success; genuinely execution-dependent outcomes may remain for implementation and validation.
- Use current external evidence to establish which options exist and can provide the required outcome, and repository or experimental evidence to establish which mechanisms are applicable and sufficiently compatible for this project. Synthesize only evidence established through investigation; do not invent missing support during synthesis. Derive the project-applicable high-level solution space through the rationale of relevant engineering principles, established practices, ownership or control boundaries, architecture, constraints, support, and compatibility before forming concrete candidates. Do not treat a generic best practice or the newest option as automatically correct. Preference among viable mechanisms belongs after viability determination; do not let an early preference end exploration or eliminate another materially distinct viable mechanism. Eliminate a plausible approach only when observed evidence, current authoritative information, or a hard task constraint materially establishes the reason; otherwise preserve unresolved viability.
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

Workspace and evidence contract:

- Each cycle begins with an isolated experimental repository snapshot of the exact current authoritative working state. Before Intent, active repository operations target that experiment, so edits and commands are safe investigations and do not change the authoritative remediation.
- After Intent acceptance, active repository operations target the authoritative repository and are the actual implementation. The current experiment remains available through the explicit `workspace="experiment"` target for further isolated investigation; experimental edits never become authoritative automatically.
- Manage useful experimental state with normal repository and Git capabilities. Preserve evidence when it materially helps the decision, not merely for completeness.
- Use obtainable repository, execution, scanner, and research evidence when it materially affects a decision, without imposing irrelevant mandatory tool calls. For material externally changing technical claims, prefer current primary or authoritative sources when reasonably available. Scanner and self-validation results are engineering evidence only; each result supports only the properties actually evaluated.
- External research is best-effort and may be blocked, unavailable, incomplete, or truncated. A failed retrieval is not evidence that information or a solution does not exist. Unresolved properties remain unresolved until appropriate evidence exists.

Before the first authoritative material change in every cycle, investigate in the isolated experiment as useful and submit the required pre-execution Model Response through `submit_cycle_intent`.

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
        "Before making the first authoritative material change:\n\n"
        "1. investigate the supplied task and relevant evidence using the isolated experimental workspace and other available engineering capabilities;\n"
        "2. answer every Model Response question below;\n"
        "3. synthesize the project-applicable engineering considerations and high-level solution space from the evidence;\n"
        "4. develop only concrete, evidence-supported solutions;\n"
        "5. ensure every proposed solution satisfies every applicable hard constraint;\n"
        "6. select the solution you currently intend to implement;\n"
        "7. submit the completed pre-execution Model Response through `submit_cycle_intent`.\n\n"
        "This is the decision record for the solution you intend to implement, not a documentation-only exercise or a request for vague hypothetical directions. Investigate avoidable uncertainty before proposing solutions. When a fact cannot be established until execution, identify it as execution-dependent evidence rather than established fact. Do not rewrite the Task to Solve. After acceptance, continue implementation in the same turn, materially reassess within the cycle if new evidence warrants it, and self-validate before ending execution.\n\n"
        + intent_questionnaire(1)
    )


def intent_retry_message(cycle: int, errors: list[str]) -> str:
    return (
        f"Cycle {cycle} Problem Analysis and Solution Decision has not been accepted. Correct the checkpoint using `submit_cycle_intent`. "
        "Do not modify the authoritative repository before acceptance; continue isolated investigation if useful. Rejection details:\n- "
        + "\n- ".join(errors)
    )


def execution_continuation_message(cycle: int) -> str:
    return (
        f"Your Problem Analysis and Solution Decision for Cycle {cycle} has been accepted. "
        "This same cycle is still in progress and is now in authoritative implementation. The preceding invocation "
        "ended without any execution-phase capability attempt. Repository changes made before Intent acceptance "
        "exist only in the isolated experimental workspace; they have not modified the authoritative repository. "
        "`workspace=\"active\"` now targets the authoritative repository. Implement the accepted solution there "
        "before treating execution as complete. `workspace=\"experiment\"` remains available for further isolated "
        "investigation or reassessment. Successful experimental builds, tests, or scans are evidence about the "
        "experiment, not evidence that authoritative implementation has occurred. Continue solving the original "
        "Task to Solve now, materially reassess within this cycle if new evidence warrants it, and perform "
        "appropriate self-validation after authoritative implementation. If evidence establishes that no "
        "authoritative change is legitimately necessary or that work is genuinely blocked, report that honestly "
        "rather than making an artificial mutation. Do not merely restate the accepted decision."
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


def validation_feedback(
    report: ValidationReport,
    journal_context: str,
    next_cycle: int,
    *,
    capture_recovery: bool = False,
    cycle_state: dict | None = None,
) -> str:
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
        "cycleLifecycle": cycle_state,
        "failedChecks": failed_checks,
        "changedFiles": list(report.changed_files),
        "cumulativeDiffPath": report.diff_path,
        "currentStateDigest": report.tree_digest,
        "cycleEvidence": report.cycle_evidence.to_dict() if report.cycle_evidence else None,
        "scan": scan,
    }
    opening = (
        "Deterministic validation established success for the evaluated engineering requirements, but required lifecycle capture remains incomplete. Continue in the same repository and ADK session using the original canonical Task to Solve. Reassess the current validated repository state and complete this cycle's normal checkpoints; checkpoint failure alone is not evidence that another repository change is needed."
        if report.passed and capture_recovery
        else "Deterministic validation did not establish success. Continue solving the original canonical Task to Solve in the same repository and ADK session. The validation is authoritative evidence about progress, not a replacement objective, and no prior solution receives authority merely because it was previously selected or implemented."
    )
    return (
        opening
        + "\n\n"
        "Use the new isolated experimental workspace and other available engineering capabilities before the next pre-execution submission to inspect current repository state and reinvestigate decision-critical claims where reasonably feasible. Critically reassess all relevant accumulated prior-cycle findings, assumptions, decisions, implementation directions, self-validation statements, and retrospective descriptions against the original Task to Solve. Treat prior model statements as claims rather than deterministic facts. Identify what remains supported, what is contradicted or incomplete, what cannot be verified and therefore remains uncertain, what implemented work is present and useful, what directions should no longer constrain the decision, and what remains unresolved. Do not automatically continue or discard previous work. Only after this evidence audit, develop current concrete candidates and select the best-supported solution now.\n\n"
        "Scanner fixed-version fields are evidence only: they are not required target versions, empty fixedVersions does not mean remediation is impossible, and ambiguous backend expressions must not be guessed into concrete versions.\n\n"
        "The bounded Markdown decision journal below preserves provenance across relevant prior cycles. The original Task to Solve remains the run anchor. Prior model-authored records are reasoning artifacts; deterministic validation sections and the separately supplied latest validation evidence are authoritative within their stated scope.\n\n"
        + journal_context
        + "\n\n"
        + "Latest deterministic validation evidence:\n"
        + json.dumps(evidence, indent=2, sort_keys=True)
        + "\n\n"
        + intent_questionnaire(next_cycle)
    )
