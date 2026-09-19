from __future__ import annotations

import json
import re

from .config import RemediationRequest
from .models import DecisionRecord, DecisionState, RepositoryBaseline, ValidationReport


_WORKING_STATE_HEADER = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]+)?WORKING_STATE[ \t]*:?[ \t]*$"
)
_WORKING_STATE_FALLBACK_LIMIT = 600
MAX_DECISION_CONTEXT_CHARACTERS = 16_000


AGENT_INSTRUCTION = """
You are the single autonomous OSS remediation engineering agent for one prepared repository.

Investigate the repository and remediate the requested vulnerabilities directly. You may read and patch repository text and use the trusted host-native shell for repository discovery, dependency analysis, builds, tests, local Git inspection, and workspace-local helper scripts.

Requirements:
- Base decisions on repository, dependency, build, and scanner evidence.
- Respect every supplied constraint.
- Choose the engineering approach yourself; no patch-plan JSON is required.
- Treat supplied policies as outcome boundaries, not instructions to use a particular implementation technique.
- Do not use vulnerability-specific recipes from this prompt.
- Do not install, replace, or select vulnerability scanners. Deterministic code owns scanning.
- Do not obtain credentials, push branches, or create pull requests. Deterministic delivery owns those actions.
- Treat shell cwd/path policy as operating context, not proof of hard filesystem containment.
- Inspect command failures and continue adapting within the available turn and budget.
- Do not claim success. Deterministic validation after your turn decides success.
- Treat scanner-provided fixed versions and fixed-version expressions as evidence, not required remediation targets. Empty fixed-version evidence does not prove remediation is impossible, and ambiguous ranges must not be converted into guessed concrete versions.
- Maintain a concise model-owned working state across turns: current understanding, strategy or hypothesis, assumptions being tested, meaningful progress, and unresolved work. Revise or replace it whenever evidence warrants. This is engineering continuity, not a rigid patch plan or prescribed sequence.
- Do not provide hidden chain-of-thought or detailed private reasoning. Record only concise engineering state that is useful for the next work cycle.

OSS dependency-remediation engineering principles:
- Inspect how affected versions are controlled by the repository, including relevant parent definitions, imported BOMs, properties, existing dependency-management structures, direct versus transitive ownership, and framework-managed versions.
- Use the repository's management structure as engineering evidence. Avoid redundant or unnecessary lower-level overrides, and prefer coherent, maintainable version management over fragmented isolated pins when evidence supports it.
- Retain discretion to use targeted overrides when repository, compatibility, build, or validation evidence supports them. Do not treat parent, BOM, property, dependency-management, or direct-dependency layers as a mandatory remediation order.
- Do not select a solution solely because it produces the fastest passing scan; consider coverage, compatibility, risk, maintainability, and repository ownership evidence.

Material decision protocol:
1. Establish the problem, complete success criteria, scope, and constraints.
2. Gather relevant evidence before selecting a solution.
3. Identify only materially credible candidate approaches; do not invent artificial alternatives.
4. Evaluate credible candidates against requirement coverage, constraints, evidence, compatibility and engineering risk, maintainability, unresolved assumptions, and ability to validate.
5. Select one approach or a justified combination.
6. Before consequential implementation changes, call `record_decision` with action `SELECT` and the concise observable engineering decision.
7. Implement the selected strategy, then compare new evidence against its coverage, assumptions, validation plan, and success criteria.
8. When evidence materially affects the strategy, decide whether to `RETAIN`, `EXTEND`, `REVISE`, `REPLACE`, or `BLOCK`, and call `record_decision` before continuing under that decision.
9. Self-validate the complete solution with available tools. If self-validation finds a resolvable problem, keep investigating and correcting it within the same cycle rather than knowingly submitting incomplete work for the external validator to rediscover.
10. Finish a work cycle only after recording `READY_FOR_INDEPENDENT_VALIDATION` when evidence supports every success criterion, or `BLOCK` when a concrete blocker prevents completion or verification. Independent deterministic validation remains authoritative and is not replaced by self-validation.

A decision is material when choosing differently could change coverage, technical direction, compatibility, risk, maintainability, permitted scope, validation outcome, or the next meaningful action. Do not record routine navigation, searches, ordinary command selection, formatting, repeated observations, or low-level implementation steps that do not change strategy. Candidate approaches may be classified `COMPLETE`, `PARTIAL`, `CONDITIONAL`, or `NOT_VIABLE`; alternatives are not required when they add no value, including final readiness.

Every `record_decision` call is a complete current snapshot after applying the action, never a partial delta. Restate the complete current diagnosis, active strategy, all satisfied/conditional/unresolved requirement coverage, all active material assumptions and their tests, and current planned or observed self-validation. For `EXTEND`, retain previously satisfied coverage that remains applicable and add the new coverage in the same snapshot. Do not rely on deterministic code to infer or merge semantically similar free-form requirement strings.

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
        "Use tools to investigate and modify the repository, record material decisions, maintain your concise WORKING_STATE, then end the turn for deterministic validation.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )


def extract_working_state(turn_text: str) -> str:
    matches = tuple(_WORKING_STATE_HEADER.finditer(turn_text))
    if matches:
        match = matches[-1]
        section = turn_text[match.start():].strip()
        if turn_text[match.end():].strip():
            return section
    visible = " ".join(turn_text.split())
    if not visible:
        return "WORKING_STATE\n- No structured WORKING_STATE was supplied in the previous cycle."
    excerpt = visible[:_WORKING_STATE_FALLBACK_LIMIT].rstrip()
    if len(visible) > _WORKING_STATE_FALLBACK_LIMIT:
        excerpt += "…"
    return (
        "WORKING_STATE\n"
        "- No structured WORKING_STATE was supplied in the previous cycle.\n"
        f"- Visible response excerpt: {excerpt}"
    )


def validation_feedback(
    report: ValidationReport,
    prior_working_state: str,
    decision_state: DecisionState | None = None,
    decision_trail: tuple[DecisionRecord, ...] = (),
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
        "failedChecks": failed_checks,
        "changedFiles": list(report.changed_files),
        "cumulativeDiffPath": report.diff_path,
        "currentStateDigest": report.tree_digest,
        "cycleEvidence": report.cycle_evidence.to_dict() if report.cycle_evidence else None,
        "scan": scan,
    }
    decision_context = serialize_decision_context(decision_state, decision_trail)
    return (
        "Deterministic validation failed. Continue the original remediation objective, constraints, and completion criteria in the same repository and ADK session; this validation is new evidence, not a replacement objective.\n\n"
        "Relate the evidence to your previous strategy and actions; determine what it supports, contradicts, or leaves unresolved; and reconcile any contradiction between your prior decision/self-validation and the authoritative result before making material corrective changes. Determine whether the failure is an implementation defect, incomplete coverage, invalid assumption, strategy deficiency, constraint conflict, or environmental/tooling problem. Decide whether to continue, modify, or replace your strategy. Preserve useful progress, but do not default to extending the prior implementation when revision or replacement is better supported. Record `RETAIN`, `EXTEND`, `REVISE`, `REPLACE`, or `BLOCK` with `record_decision` before continuing under that decision. Do not assume a particular technology, dependency, version, management layer, file, or remediation technique.\n\n"
        "Scanner fixed-version fields are evidence only: they are not required target versions, empty fixedVersions does not mean remediation is impossible, and ambiguous backend expressions must not be guessed into concrete versions.\n\n"
        "Previous model-owned working state:\n"
        + prior_working_state
        + "\n\nCurrent material decision context:\n"
        + decision_context
        + "\n\nNew deterministic validation evidence:\n"
        + json.dumps(evidence, indent=2, sort_keys=True)
    )


def serialize_decision_context(
    decision_state: DecisionState | None,
    decision_trail: tuple[DecisionRecord, ...],
) -> str:
    total_count = len(decision_trail)
    history: list[dict[str, object]] = []
    context = _decision_context_payload(decision_state, history, total_count)
    serialized = _compact_json(context)
    if len(serialized) > MAX_DECISION_CONTEXT_CHARACTERS:
        raise ValueError("Current decision state exceeds the continuation context limit")
    for decision in reversed(decision_trail):
        candidate_history = [_compact_history_entry(decision), *history]
        candidate = _decision_context_payload(decision_state, candidate_history, total_count)
        candidate_serialized = _compact_json(candidate)
        if len(candidate_serialized) > MAX_DECISION_CONTEXT_CHARACTERS:
            break
        history = candidate_history
        serialized = candidate_serialized
    return serialized


def _decision_context_payload(
    decision_state: DecisionState | None,
    history: list[dict[str, object]],
    total_count: int,
) -> dict[str, object]:
    return {
        "currentDecisionState": decision_state.to_dict() if decision_state else None,
        "previousSelfValidationConclusion": (
            {
                "action": decision_state.current_action.value,
                "agentStatus": decision_state.agent_status.value,
                "validation": list(decision_state.current_validation),
            }
            if decision_state
            else None
        ),
        "materialDecisionHistory": history,
        "historyTruncated": len(history) < total_count,
        "includedDecisionCount": len(history),
        "totalDecisionCount": total_count,
    }


def _compact_history_entry(decision: DecisionRecord) -> dict[str, object]:
    return {
        "decisionId": decision.decision_id,
        "cycle": decision.cycle,
        "action": decision.action.value,
        "previousDecisionId": decision.previous_decision_id,
        "strategy": _clip(decision.strategy, 320),
        "transitionRationale": _clip(decision.rationale, 320),
        "triggeringEvidence": [_clip(value, 180) for value in decision.evidence[:3]],
        "coverageCounts": {
            name: len(values) for name, values in decision.coverage.items()
        },
    }


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
