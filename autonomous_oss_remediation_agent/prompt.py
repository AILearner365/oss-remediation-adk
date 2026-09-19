from __future__ import annotations

import json
import re

from .config import RemediationRequest
from .models import (
    DecisionCaptureAssessment,
    DecisionRecord,
    DecisionState,
    RepositoryBaseline,
    ValidationReport,
)


_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+")
_WORKING_STATE_SEPARATOR = re.compile(r"[\s_-]+")
_WORKING_STATE_FALLBACK_LIMIT = 600
_RECONCILIATION_SUMMARY_LIMIT = 1_200
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
6. Repository inspection and exploration may precede selection. Before material implementation begins, call `record_decision` with action `SELECT` and the concise observable engineering decision.
7. Implement the selected strategy, then compare new evidence against its coverage, assumptions, validation plan, and success criteria.
8. When evidence materially affects the strategy, update the snapshot before continuing: use `RETAIN` when the strategy remains supported, `EXTEND` when adding material scope, `REVISE` when materially changing it, `REPLACE` when substituting it, or `BLOCK` for a genuine unresolved blocker.
9. Self-validate the complete solution with available tools. If self-validation finds a resolvable problem, keep investigating and correcting it within the same cycle rather than knowingly submitting incomplete work for the external validator to rediscover.
10. Record `READY_FOR_INDEPENDENT_VALIDATION` only after observed self-validation supports readiness, or `BLOCK` when a concrete unresolved blocker prevents completion or verification. Independent deterministic validation remains authoritative and is not replaced by self-validation.

A decision is material when choosing differently could change coverage, technical direction, compatibility, risk, maintainability, permitted scope, validation outcome, or the next meaningful action. Do not record routine navigation, searches, ordinary command selection, formatting, repeated observations, or low-level implementation steps that do not change strategy. Candidate approaches may be classified `COMPLETE`, `PARTIAL`, `CONDITIONAL`, or `NOT_VIABLE`; record credible alternatives actually considered when they inform the choice, but never fabricate alternatives to populate the field. This iterative protocol observes your engineering decisions; it is not a mandatory remediation algorithm and does not choose a technical strategy for you.

Every `record_decision` call is a complete current snapshot after applying the action, never a partial delta. Restate the complete current diagnosis, active strategy, all satisfied/conditional/unresolved requirement coverage, all active material assumptions and their tests, and current planned or observed self-validation. For `EXTEND`, retain previously satisfied coverage that remains applicable and add the new coverage in the same snapshot. Do not rely on deterministic code to infer or merge semantically similar free-form requirement strings.

Prefer captured command output or ignored build directories for investigation evidence. Avoid writing diagnostic reports into tracked source directories. Before readiness, inspect the final repository diff and remove investigation-only files so deterministic validation and delivery see only intended repository changes.

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
    lines = turn_text.splitlines()
    heading_indexes = [
        index for index, line in enumerate(lines) if _is_working_state_heading(line)
    ]
    if heading_indexes:
        start = heading_indexes[-1]
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if _MARKDOWN_HEADING.match(lines[index].strip()):
                end = index
                break
        section = "\n".join(lines[start:end]).strip()
        if any(line.strip() for line in lines[start + 1 : end]):
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


def _is_working_state_heading(line: str) -> bool:
    candidate = line.strip()
    if not candidate:
        return False
    candidate = _MARKDOWN_HEADING.sub("", candidate).strip()
    candidate = candidate.rstrip(":").strip()
    for marker in ("**", "__", "*", "_", "`"):
        if candidate.startswith(marker) and candidate.endswith(marker):
            candidate = candidate[len(marker) : -len(marker)].strip()
            break
    candidate = candidate.rstrip(":").strip()
    normalized = _WORKING_STATE_SEPARATOR.sub(" ", candidate).strip().upper()
    return normalized in {"WORKING STATE", "CURRENT WORKING STATE"}


def decision_reconciliation_message(
    assessment: DecisionCaptureAssessment,
    working_state: str,
    turn_text: str,
    decision_state: DecisionState | None,
    decision_trail: tuple[DecisionRecord, ...],
    changed_files: tuple[str, ...],
    workspace_edit_paths: tuple[str, ...],
) -> str:
    if decision_state is None:
        action_guidance = (
            "No accepted decision exists. Reconstruct the current diagnosis and active "
            "strategy from the same-session history and evidence, then record the first "
            "complete snapshot with `SELECT`. If the work is already ready or blocked, "
            "record the corresponding terminal snapshot after `SELECT`. A retroactive "
            "selection remains classified as late when workspace edits already occurred."
        )
    else:
        action_guidance = (
            "A decision chain exists but its audit capture is deficient. Record the complete "
            "current snapshot using the action that truthfully relates it to the latest "
            "decision: `RETAIN`, `EXTEND`, `REVISE`, `REPLACE`, "
            "`READY_FOR_INDEPENDENT_VALIDATION`, or `BLOCK`. Do not default to readiness; "
            "use it only when observed self-validation supports it."
        )
    payload = {
        "captureAssessment": assessment.to_dict(),
        "repositoryChangeSummary": {
            "changedFiles": list(changed_files),
            "workspaceEditPathsObserved": list(dict.fromkeys(workspace_edit_paths))[-20:],
            "shellMutationDetection": "NOT_AVAILABLE",
        },
        "currentDecisionContext": json.loads(
            serialize_decision_context(decision_state, decision_trail)
        ),
        "workingState": working_state,
        "agentCycleSummaryExcerpt": _clip(
            " ".join(turn_text.split()),
            _RECONCILIATION_SUMMARY_LIMIT,
        ),
    }
    return (
        "Decision-capture reconciliation only. Authoritative validation has not run yet. "
        "You may call only `record_decision`; do not read or modify repository files, run "
        "shell commands, scan, or deliver. This turn records observable engineering metadata "
        "and does not choose a remediation strategy for you. "
        + action_guidance
        + "\n\nReconciliation evidence:\n"
        + json.dumps(payload, indent=2, sort_keys=True)
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
    if decision_state is None:
        decision_instruction = (
            "No current material decision state is recorded. Reconstruct your current "
            "diagnosis and active strategy from repository evidence, the previous "
            "WORKING_STATE, and the authoritative deterministic validation evidence. Relate "
            "that evidence to the prior work and determine what it supports, contradicts, or "
            "leaves unresolved. Reconstruct your strategy, then decide whether to continue, "
            "modify, or replace your strategy. "
            "Then call `record_decision` with action `SELECT` to record the first complete "
            "current snapshot before making material corrective changes. Do not fabricate "
            "a prior decision or strategy."
        )
    else:
        decision_instruction = (
            "Relate the evidence to your previous strategy and actions; determine what it "
            "supports, contradicts, or leaves unresolved; and reconcile any contradiction "
            "between your prior decision/self-validation and the authoritative result before "
            "making material corrective changes. Determine whether the failure is an "
            "implementation defect, incomplete coverage, invalid assumption, strategy "
            "deficiency, constraint conflict, or environmental/tooling problem. Decide "
            "whether to continue, modify, or replace your strategy. Preserve useful progress, "
            "but do not default to extending the prior implementation when revision or "
            "replacement is better supported. Record `RETAIN`, `EXTEND`, `REVISE`, `REPLACE`, "
            "or `BLOCK` with `record_decision` before continuing under that decision. Do not "
            "assume a particular technology, dependency, version, management layer, file, or "
            "remediation technique."
        )
    return (
        "Deterministic validation failed. Continue the original remediation objective, constraints, and completion criteria in the same repository and ADK session; this validation is new evidence, not a replacement objective.\n\n"
        + decision_instruction
        + "\n\n"
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
    state_payload, state_metadata = _bounded_current_state(decision_state, total_count)
    context = _decision_context_payload(
        decision_state,
        state_payload,
        state_metadata,
        history,
        total_count,
    )
    serialized = _compact_json(context)
    for decision in reversed(decision_trail):
        candidate_history = [_compact_history_entry(decision), *history]
        candidate = _decision_context_payload(
            decision_state,
            state_payload,
            state_metadata,
            candidate_history,
            total_count,
        )
        candidate_serialized = _compact_json(candidate)
        if len(candidate_serialized) > MAX_DECISION_CONTEXT_CHARACTERS:
            break
        history = candidate_history
        serialized = candidate_serialized
    return serialized


def _decision_context_payload(
    decision_state: DecisionState | None,
    state_payload: dict[str, object] | None,
    state_metadata: dict[str, object],
    history: list[dict[str, object]],
    total_count: int,
) -> dict[str, object]:
    return {
        "currentDecisionState": state_payload,
        **state_metadata,
        "previousSelfValidationConclusion": (
            {
                "action": decision_state.current_action.value,
                "agentStatus": decision_state.agent_status.value,
                "validationEntryCount": len(decision_state.current_validation),
                "latestValidationEvidence": (
                    _clip(decision_state.current_validation[-1], 320)
                    if decision_state.current_validation
                    else None
                ),
            }
            if decision_state
            else None
        ),
        "materialDecisionHistory": history,
        "historyTruncated": len(history) < total_count,
        "includedDecisionCount": len(history),
        "totalDecisionCount": total_count,
    }


def _bounded_current_state(
    decision_state: DecisionState | None,
    total_count: int,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    if decision_state is None:
        return None, {
            "currentStateTruncated": False,
            "currentStateFieldCounts": None,
        }

    profiles: tuple[dict[str, int] | None, ...] = (
        None,
        {
            "text": 800,
            "coverage_items": 6,
            "coverage_text": 220,
            "assumption_items": 5,
            "assumption_text": 220,
            "unresolved_items": 6,
            "unresolved_text": 220,
            "validation_items": 6,
            "validation_text": 260,
        },
        {
            "text": 400,
            "coverage_items": 4,
            "coverage_text": 120,
            "assumption_items": 3,
            "assumption_text": 120,
            "unresolved_items": 4,
            "unresolved_text": 120,
            "validation_items": 4,
            "validation_text": 160,
        },
    )
    for profile in profiles:
        payload, counts, truncated = _current_state_payload(decision_state, profile)
        metadata = {
            "currentStateTruncated": truncated,
            "currentStateFieldCounts": counts,
        }
        context = _decision_context_payload(
            decision_state,
            payload,
            metadata,
            [],
            total_count,
        )
        if len(_compact_json(context)) <= MAX_DECISION_CONTEXT_CHARACTERS:
            return payload, metadata

    payload, counts, _ = _current_state_payload(
        decision_state,
        {
            "text": 240,
            "coverage_items": 1,
            "coverage_text": 80,
            "assumption_items": 1,
            "assumption_text": 80,
            "unresolved_items": 1,
            "unresolved_text": 80,
            "validation_items": 1,
            "validation_text": 100,
        },
    )
    return payload, {
        "currentStateTruncated": True,
        "currentStateFieldCounts": counts,
    }


def _current_state_payload(
    decision_state: DecisionState,
    profile: dict[str, int] | None,
) -> tuple[dict[str, object], dict[str, object], bool]:
    if profile is None:
        payload = decision_state.to_dict()
    else:
        payload = {
            "latestDecisionId": decision_state.latest_decision_id,
            "currentAction": decision_state.current_action.value,
            "activeStrategy": _clip(decision_state.active_strategy, profile["text"]),
            "currentDiagnosis": _clip(decision_state.current_diagnosis, profile["text"]),
            "currentCoverage": {
                name: [
                    _clip(value, profile["coverage_text"])
                    for value in values[: profile["coverage_items"]]
                ]
                for name, values in decision_state.current_coverage.items()
            },
            "activeAssumptions": [
                {
                    name: _clip(value, profile["assumption_text"])
                    for name, value in assumption.items()
                }
                for assumption in decision_state.active_assumptions[
                    : profile["assumption_items"]
                ]
            ],
            "remainingUnresolvedItems": [
                _clip(value, profile["unresolved_text"])
                for value in decision_state.remaining_unresolved_items[
                    : profile["unresolved_items"]
                ]
            ],
            "currentValidation": [
                _clip(value, profile["validation_text"])
                for value in decision_state.current_validation[
                    : profile["validation_items"]
                ]
            ],
            "agentStatus": decision_state.agent_status.value,
        }

    coverage_counts = {
        name: {
            "included": len(payload["currentCoverage"].get(name, [])),
            "total": len(values),
        }
        for name, values in decision_state.current_coverage.items()
    }
    counts: dict[str, object] = {
        "coverage": coverage_counts,
        "assumptions": {
            "included": len(payload["activeAssumptions"]),
            "total": len(decision_state.active_assumptions),
        },
        "unresolvedItems": {
            "included": len(payload["remainingUnresolvedItems"]),
            "total": len(decision_state.remaining_unresolved_items),
        },
        "validation": {
            "included": len(payload["currentValidation"]),
            "total": len(decision_state.current_validation),
        },
    }
    truncated = payload != decision_state.to_dict()
    return payload, counts, truncated


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
