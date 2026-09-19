from __future__ import annotations

import json

from .config import RemediationRequest
from .journal import intent_questionnaire, outcome_questionnaire
from .models import RepositoryBaseline, ValidationReport


AGENT_INSTRUCTION = """
You are the single autonomous OSS remediation engineering agent for one prepared repository.

Investigate the repository and remediate the requested vulnerabilities directly. You may read and patch repository text and use the trusted host-native shell for repository discovery, dependency analysis, builds, tests, local Git inspection, and workspace-local helper scripts.

Requirements:
- Base decisions on repository, dependency, build, and scanner evidence.
- Respect every supplied constraint.
- Treat supplied version policies solely as remediation boundaries, not instructions to upgrade or select a particular dependency-management layer. An exact required version constrains the outcome but does not prescribe how to achieve it.
- Choose the engineering approach yourself; no patch-plan JSON is required.
- Do not use vulnerability-specific recipes from this prompt. When choosing a remediation, inspect how affected dependency versions are managed by the repository, including relevant parents, imported BOMs, properties, and existing `dependencyManagement`. Use that structure as engineering evidence, avoid redundant or unnecessary lower-level overrides, and retain discretion to use a lower-level override when repository evidence supports it. Do not treat these management layers as a required remediation order or hierarchy.
- When multiple safe remediations are available, prefer the approach that best preserves the repository's existing dependency-management model, minimizes fragmented version control, and avoids unnecessary explicit overrides. Favor maintainable, coherent changes over a larger set of isolated dependency pins, while retaining discretion to use targeted overrides when repository, compatibility, build, or validation evidence supports them.
- Do not choose a remediation solely because it is the fastest path to a passing scan; also consider maintainability, dependency ownership, and consistency with the project's existing version-management approach.
- Do not install, replace, or select vulnerability scanners. Deterministic code owns scanning.
- Do not obtain credentials, push branches, or create pull requests. Deterministic delivery owns those actions.
- Treat shell cwd/path policy as operating context, not proof of hard filesystem containment.
- Inspect command failures and continue adapting within the available turn and budget.
- Do not claim success. Deterministic validation after your turn decides success.
- Treat scanner-provided fixed versions and fixed-version expressions as evidence, not required remediation targets. Empty fixed-version evidence does not prove remediation is impossible, and ambiguous ranges must not be converted into guessed concrete versions.
- Do not provide hidden chain-of-thought or detailed private reasoning. Record only concise engineering state that is useful for the next work cycle.
- Never edit `agent/decision-journal.md`; deterministic orchestration exclusively owns that artifact.
- At the start of each cycle, use only read-only discovery capabilities, then call `submit_cycle_intent` with every required journal section. The checkpoint constrains reporting timing, not your engineering strategy. One credible approach or a reversible diagnostic experiment is valid; never invent alternatives.
- Material edit and shell capabilities become usable only after Cycle Intent is accepted. You may freely adapt or replace the selected direction when execution evidence warrants.
- When execution ends, repository capabilities are removed. Use the metadata-only `submit_cycle_outcome` capability to report actual work, deviations, evidence, unresolved coverage, and the applicable outcome status. Deterministic validation remains authoritative.

When you have completed a useful execution phase, provide a concise ordinary summary. Do not emit `WORKING_STATE` and do not claim success; the orchestrator will request Cycle Outcome in a separate metadata-only turn and will generate any deprecated compatibility projection deterministically.
""".strip()


def initial_message(request: RemediationRequest, baseline: RepositoryBaseline) -> str:
    payload = {
        "objective": {
            "vulnerabilityIds": list(request.vulnerability_ids),
            "severityScope": list(request.severity_scope),
        },
        "constraints": request.to_dict()["constraints"],
        "baseline": baseline.to_dict(),
        "budgets": request.to_dict()["budget"],
        "completionCriteria": [
            "required build/test/startup commands pass",
            "fresh deterministic vulnerability scan succeeds",
            "requested target findings are absent",
            "no new prohibited findings are introduced",
            "typed constraints remain satisfied",
        ],
    }
    return (
        "Begin Cycle 1 read-only discovery in the prepared repository. "
        "The objective, constraints, and completion criteria below are the stable run contract for every turn. "
        "Inspect only with read capabilities, then submit every required Cycle Intent section through `submit_cycle_intent`. "
        "After it is accepted, execution capabilities become available in the same turn; investigate, modify, and self-validate, then end the turn.\n\n"
        + intent_questionnaire(1)
        + "\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )


def intent_retry_message(cycle: int, errors: list[str]) -> str:
    return (
        f"Cycle {cycle} Intent has not been accepted. Correct the checkpoint using `submit_cycle_intent`. "
        "Do not perform material work before acceptance. Rejection details:\n- "
        + "\n- ".join(errors)
    )


def outcome_message(cycle: int, execution_summary: str, evidence: dict) -> str:
    return (
        f"Execution for Cycle {cycle} has ended. Repository read, edit, and shell capabilities are now unavailable. "
        "Submit a metadata-only Cycle Outcome through `submit_cycle_outcome` for any successful, partial, blocked, "
        "failed, inconclusive, or no-change execution. Report intended-versus-actual work and unresolved coverage; "
        "do not claim deterministic success.\n\n"
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


def compatibility_working_state(
    outcome_status: str | None,
    outcome_answers: dict[str, str],
) -> str:
    fields = (
        ("Outcome status", outcome_status or "MISSING"),
        ("Final approach", outcome_answers.get("Final approach present at cycle end", "Not captured")),
        ("Evidence", outcome_answers.get("Evidence actually observed", "Not captured")),
        ("Remaining work", outcome_answers.get("Remaining work, blockers, or uncertainty", "Not captured")),
        ("Conclusion", outcome_answers.get("Cycle conclusion", "Not captured")),
    )
    lines = ["WORKING_STATE (deprecated deterministic compatibility projection)"]
    for label, value in fields:
        normalized = " ".join(value.split())
        if len(normalized) > 500:
            normalized = normalized[:499].rstrip() + "…"
        lines.append(f"- {label}: {normalized}")
    return "\n".join(lines)


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
        "Deterministic validation failed. Continue the original remediation objective, constraints, and completion criteria in the same repository and ADK session; this validation is new evidence, not a replacement objective.\n\n"
        "Relate the evidence to your previous strategy and actions. Determine what it supports, contradicts, or leaves unresolved; preserve useful progress; reconsider unsupported assumptions or unsuccessful approaches when appropriate; decide whether to continue, modify, or replace your strategy; then continue investigation and remediation with the available developer capabilities. Do not restart by default, and do not assume a particular dependency, version, management layer, file, or remediation technique.\n\n"
        "Scanner fixed-version fields are evidence only: they are not required target versions, empty fixedVersions does not mean remediation is impossible, and ambiguous backend expressions must not be guessed into concrete versions.\n\n"
        "The bounded Markdown decision journal below is the authoritative cross-cycle problem-solving state. Legacy WORKING_STATE is compatibility-only and must not override it.\n\n"
        + journal_context
        + "\n\n"
        + intent_questionnaire(next_cycle)
        + "\n\nNew deterministic validation evidence:\n"
        + json.dumps(evidence, indent=2, sort_keys=True)
    )
