from __future__ import annotations

import json
import threading
from typing import Any

from ..models import CandidateClassification, DecisionAction, DecisionRecord, DecisionState
from ..workspace import TraceStore


MAX_DECISION_RECORD_CHARACTERS = 14_000
_MAX_TEXT_LENGTH = 1600
_MAX_ITEM_LENGTH = 600
_MAX_ITEMS = 12


class DecisionRecordingError(ValueError):
    def __init__(self, message: str, failure_code: str = "DECISION_RECORD_INVALID"):
        super().__init__(message)
        self.failure_code = failure_code


class DecisionTracker:
    def __init__(self, trace: TraceStore, max_decisions: int):
        if max_decisions < 1:
            raise ValueError("max_decisions must be positive")
        self.trace = trace
        self.max_decisions = max_decisions
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
            raise DecisionRecordingError(
                "Decision recording is unavailable outside an active remediation cycle"
            )
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
            if len(self._records) >= self.max_decisions:
                raise DecisionRecordingError(
                    f"Decision event limit reached: {self.max_decisions}",
                    "DECISION_EVENT_LIMIT_REACHED",
                )
            previous_decision_id = self._validate_chain(parsed_action, previous_decision_id)
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
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if len(serialized) > MAX_DECISION_RECORD_CHARACTERS:
                raise DecisionRecordingError(
                    "Normalized decision record exceeds "
                    f"{MAX_DECISION_RECORD_CHARACTERS} characters",
                    "DECISION_RECORD_TOO_LARGE",
                )
            warnings = _record_warnings(record)
            self.trace.append_event(
                "decision_recorded",
                runId=self.trace.workspace.root.name,
                **payload,
            )
            self._records.append(record)
            for warning in warnings:
                self.warn(record.cycle, warning, decisionId=record.decision_id)
        return {
            "status": "ok",
            "decision": payload,
            "decisionState": DecisionState.from_record(record).to_dict(),
            "warnings": list(warnings),
        }

    def _validate_chain(
        self,
        action: DecisionAction,
        previous_decision_id: str | None,
    ) -> str | None:
        if not self._records:
            if action != DecisionAction.SELECT:
                raise DecisionRecordingError(
                    "The first material decision must use action SELECT",
                    "DECISION_CHAIN_INVALID",
                )
            if previous_decision_id:
                raise DecisionRecordingError(
                    "The initial SELECT decision cannot have a previous_decision_id",
                    "DECISION_CHAIN_INVALID",
                )
            return None
        if action == DecisionAction.SELECT:
            raise DecisionRecordingError(
                "SELECT is only valid for the initial material decision",
                "DECISION_CHAIN_INVALID",
            )
        latest_id = self._records[-1].decision_id
        if previous_decision_id is None:
            return latest_id
        known_ids = {record.decision_id for record in self._records}
        if previous_decision_id not in known_ids:
            raise DecisionRecordingError(
                f"Unknown previous_decision_id: {previous_decision_id}",
                "DECISION_CHAIN_INVALID",
            )
        if previous_decision_id != latest_id:
            raise DecisionRecordingError(
                "Branching is not supported; previous_decision_id must reference "
                f"the latest decision {latest_id}",
                "DECISION_CHAIN_INVALID",
            )
        return previous_decision_id

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

    def all_records(self) -> tuple[DecisionRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def warn(self, cycle: int, warning: str, **context: Any) -> None:
        self.trace.append_event(
            "decision_warning",
            runId=self.trace.workspace.root.name,
            cycle=cycle,
            warning=warning,
            **context,
        )


def _record_warnings(record: DecisionRecord) -> tuple[str, ...]:
    remaining = (
        *record.coverage.get("conditional", ()),
        *record.coverage.get("unresolved", ()),
    )
    warnings = []
    if record.action == DecisionAction.READY_FOR_INDEPENDENT_VALIDATION and remaining:
        warnings.append(
            "Readiness was recorded while coverage remains conditional or unresolved"
        )
    blocker_text = f"{record.diagnosis} {record.rationale}".lower()
    describes_blocker = any(
        marker in blocker_text
        for marker in ("block", "cannot", "unable", "unavailable", "prevents", "conflict")
    )
    if record.action == DecisionAction.BLOCK and not remaining and not describes_blocker:
        warnings.append(
            "BLOCK was recorded without conditional/unresolved coverage; "
            "diagnosis or rationale must identify the concrete blocker"
        )
    return tuple(warnings)


def _bounded_text(value: str, name: str, *, required: bool = True) -> str:
    normalized = " ".join(str(value).split())
    if required and not normalized:
        raise DecisionRecordingError(f"{name} must not be empty")
    if len(normalized) > _MAX_TEXT_LENGTH:
        raise DecisionRecordingError(f"{name} exceeds {_MAX_TEXT_LENGTH} characters")
    return normalized


def _bounded_item_text(value: str, name: str, *, required: bool = True) -> str:
    normalized = " ".join(str(value).split())
    if required and not normalized:
        raise DecisionRecordingError(f"{name} must not be empty")
    if len(normalized) > _MAX_ITEM_LENGTH:
        raise DecisionRecordingError(f"{name} exceeds {_MAX_ITEM_LENGTH} characters")
    return normalized


def _bounded_list(values: list[str], name: str) -> tuple[str, ...]:
    if len(values) > _MAX_ITEMS:
        raise DecisionRecordingError(f"{name} exceeds {_MAX_ITEMS} items")
    normalized = []
    for value in values:
        item = _bounded_item_text(value, f"{name} item", required=False)
        if item:
            normalized.append(item)
    return tuple(normalized)


def _normalize_assumptions(values: list[dict[str, str]]) -> tuple[dict[str, str], ...]:
    if len(values) > _MAX_ITEMS:
        raise DecisionRecordingError(f"assumptions exceeds {_MAX_ITEMS} items")
    normalized = []
    for value in values:
        assumption = _bounded_item_text(value.get("assumption", ""), "assumption")
        test = _bounded_item_text(value.get("test", ""), "assumption test")
        status = _bounded_item_text(value.get("status", "UNRESOLVED"), "assumption status")
        normalized.append({"assumption": assumption, "test": test, "status": status})
    return tuple(normalized)


def _normalize_alternatives(values: list[dict[str, str]]) -> tuple[dict[str, Any], ...]:
    if len(values) > _MAX_ITEMS:
        raise DecisionRecordingError(f"alternatives exceeds {_MAX_ITEMS} items")
    normalized = []
    for value in values:
        classification = _enum_value(
            CandidateClassification,
            value.get("classification", ""),
            "alternative classification",
        )
        normalized.append(
            {
                "approach": _bounded_item_text(
                    value.get("approach", ""), "alternative approach"
                ),
                "classification": classification.value,
                "coverage": _bounded_item_text(
                    value.get("coverage", ""), "alternative coverage", required=False
                ),
                "gaps": _bounded_item_text(
                    value.get("gaps", ""), "alternative gaps", required=False
                ),
            }
        )
    return tuple(normalized)


def _enum_value(enum_type, value: str, name: str):
    try:
        return enum_type(str(value).strip().upper())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise DecisionRecordingError(
            f"Unsupported {name} {value!r}; expected one of: {allowed}"
        ) from exc
