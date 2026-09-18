from __future__ import annotations

import json

from .config import RemediationRequest
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
- Maintain a concise model-owned working state across turns: current understanding, strategy or hypothesis, assumptions being tested, meaningful progress, and unresolved work. Revise or replace it whenever evidence warrants. This is engineering continuity, not a rigid patch plan or prescribed sequence.
- Do not provide hidden chain-of-thought or detailed private reasoning. Record only concise engineering state that is useful for the next work cycle.

When you have completed a useful work cycle, summarize what you changed and why, followed by a concise `WORKING_STATE` covering understanding, current strategy/hypothesis, assumptions, progress, and unresolved work. If repository evidence shows no safe remediation can satisfy the supplied constraints, respond with `NO_SAFE_REMEDIATION:` followed by the evidence-based reason.
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
        "Begin the first autonomous remediation work cycle in the prepared repository. "
        "The objective, constraints, and completion criteria below are the stable run contract for every turn. "
        "Use tools to investigate and modify the repository, maintain your concise WORKING_STATE, then end the turn for deterministic validation.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )


def validation_feedback(report: ValidationReport, prior_working_state: str) -> str:
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
        "Previous model-owned working state:\n"
        + prior_working_state
        + "\n\nNew deterministic validation evidence:\n"
        + json.dumps(evidence, indent=2, sort_keys=True)
    )
