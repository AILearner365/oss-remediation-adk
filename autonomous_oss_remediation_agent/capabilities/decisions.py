from __future__ import annotations

import threading
from typing import Any

from ..models import (
    CandidateClassification,
    DecisionAction,
    DecisionRecord,
    DecisionState,
)
from ..workspace import TraceStore


_MAX_TEXT_LENGTH = 2000
_MAX_ITEM_LENGTH = 1000
_MAX_ITEMS = 20
_TRANSITION_ACTIONS = frozenset(
    {
        DecisionAction.RETAIN,
        DecisionAction.EXTEND,
        DecisionAction.REVISE,
        DecisionAction.REPLACE,
    }
)


class DecisionTracker:
    def __init__(self, trace: TraceStore):
        self.trace = trace
        self._cycle: int | None = None
        self._records: list[DecisionRecord] = []
        self._lock = threading.Lock()

    def start_cycle(self, cycle: int) -> None:
        if cycle < 1:
            raise ValueError("Decision cycle must be at least 1")
        self._cycle = cycle

    def record(
        self,
        *,
        action: str,
        diagnosis: str,
        strategy: str,
        rationale: str,
        evidence: list[str],
        coverage_satisfied: list[str],
        coverage_conditional: list[str],
        coverage_unresolved: list[str],
        assumptions: list[dict[str, str]],
        validation: list[str],
        previous_decision_id: str | None = None,
        alternatives: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if self._cycle is None:
            raise ValueError("Decision recording is unavailable outside an active remediation cycle")
        parsed_action = _enum_value(DecisionAction, action, "action")
        diagnosis = _bounded_text(diagnosis, "diagnosis")
        strategy = _bounded_text(strategy, "strategy")
        rationale = _bounded_text(rationale, "rationale")
        normalized_evidence = _bounded_list(evidence, "evidence")
        coverage = {
            "satisfied": _bounded_list(coverage_satisfied, "coverage_satisfied"),
            "conditional": _bounded_list(coverage_conditional, "coverage_conditional"),
            "unresolved": _bounded_list(coverage_unresolved, "coverage_unresolved"),
        }
        normalized_assumptions = _normalize_assumptions(assumptions)
        normalized_validation = _bounded_list(validation, "validation")
        normalized_alternatives = _normalize_alternatives(alternatives or [])

        with self._lock:
            known_ids = {record.decision_id for record in self._records}
            if previous_decision_id and previous_decision_id not in known_ids:
                raise ValueError(f"Unknown previous_decision_id: {previous_decision_id}")
            if parsed_action in _TRANSITION_ACTIONS and self._records and not previous_decision_id:
                previous_decision_id = self._records[-1].decision_id
            if parsed_action == DecisionAction.SELECT and self._records:
                raise ValueError("SELECT is only valid for the initial material decision")
            record = DecisionRecord(
                decision_id=f"D{len(self._records) + 1}",
                cycle=self._cycle,
                action=parsed_action,
                diagnosis=diagnosis,
                strategy=strategy,
                rationale=rationale,
                evidence=normalized_evidence,
                coverage=coverage,
                assumptions=normalized_assumptions,
                validation=normalized_validation,
                previous_decision_id=previous_decision_id,
                alternatives=normalized_alternatives,
            )
            payload = record.to_dict()
            self.trace.append_event(
                "decision_recorded",
                runId=self.trace.workspace.root.name,
                **payload,
            )
            self._records.append(record)
        return {
            "status": "ok",
            "decision": payload,
            "decisionState": DecisionState.from_record(record).to_dict(),
        }

    @property
    def current_state(self) -> DecisionState | None:
        with self._lock:
            return DecisionState.from_record(self._records[-1]) if self._records else None

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._records)

    def records_for_cycle(self, cycle: int) -> tuple[DecisionRecord, ...]:
        with self._lock:
            return tuple(record for record in self._records if record.cycle == cycle)

    def recent_records(self, limit: int = 10) -> tuple[DecisionRecord, ...]:
        with self._lock:
            return tuple(self._records[-limit:])

    def warn(self, cycle: int, warning: str, **context: Any) -> None:
        self.trace.append_event(
            "decision_warning",
            runId=self.trace.workspace.root.name,
            cycle=cycle,
            warning=warning,
            **context,
        )


def _bounded_text(value: str, name: str, *, required: bool = True) -> str:
    normalized = " ".join(str(value).split())
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > _MAX_TEXT_LENGTH:
        raise ValueError(f"{name} exceeds {_MAX_TEXT_LENGTH} characters")
    return normalized


def _bounded_list(values: list[str], name: str) -> tuple[str, ...]:
    if len(values) > _MAX_ITEMS:
        raise ValueError(f"{name} exceeds {_MAX_ITEMS} items")
    normalized = []
    for value in values:
        item = " ".join(str(value).split())
        if not item:
            continue
        if len(item) > _MAX_ITEM_LENGTH:
            raise ValueError(f"{name} item exceeds {_MAX_ITEM_LENGTH} characters")
        normalized.append(item)
    return tuple(normalized)


def _normalize_assumptions(values: list[dict[str, str]]) -> tuple[dict[str, str], ...]:
    if len(values) > _MAX_ITEMS:
        raise ValueError(f"assumptions exceeds {_MAX_ITEMS} items")
    normalized = []
    for value in values:
        assumption = _bounded_text(value.get("assumption", ""), "assumption")
        test = _bounded_text(value.get("test", ""), "assumption test")
        status = _bounded_text(value.get("status", "UNRESOLVED"), "assumption status")
        normalized.append({"assumption": assumption, "test": test, "status": status})
    return tuple(normalized)


def _normalize_alternatives(values: list[dict[str, str]]) -> tuple[dict[str, Any], ...]:
    if len(values) > _MAX_ITEMS:
        raise ValueError(f"alternatives exceeds {_MAX_ITEMS} items")
    normalized = []
    for value in values:
        classification = _enum_value(
            CandidateClassification,
            value.get("classification", ""),
            "alternative classification",
        )
        normalized.append(
            {
                "approach": _bounded_text(value.get("approach", ""), "alternative approach"),
                "classification": classification.value,
                "coverage": _bounded_text(
                    value.get("coverage", ""), "alternative coverage", required=False
                ),
                "gaps": _bounded_text(value.get("gaps", ""), "alternative gaps", required=False),
            }
        )
    return tuple(normalized)


def _enum_value(enum_type, value: str, name: str):
    try:
        return enum_type(str(value).strip().upper())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"Unsupported {name} {value!r}; expected one of: {allowed}") from exc
