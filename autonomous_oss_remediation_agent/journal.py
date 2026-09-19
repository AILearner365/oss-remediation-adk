from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

from .models import ValidationReport
from .workspace import TraceStore


class JournalPhase(str, Enum):
    DISCOVERY = "DISCOVERY"
    INTENT_REQUIRED = "INTENT_REQUIRED"
    EXECUTION = "EXECUTION"
    OUTCOME_REQUIRED = "OUTCOME_REQUIRED"
    DETERMINISTIC_VALIDATION = "DETERMINISTIC_VALIDATION"
    DELIVERY_OR_CONTINUATION = "DELIVERY_OR_CONTINUATION"
    FINISHED = "FINISHED"


class CaptureStatus(str, Enum):
    COMPLETE = "COMPLETE"
    LATE = "LATE"
    INCOMPLETE = "INCOMPLETE"
    MISSING = "MISSING"


class RemediationOutcome(str, Enum):
    FULLY_VALIDATED = "FULLY_VALIDATED"
    PARTIALLY_REMEDIATED = "PARTIALLY_REMEDIATED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NO_CHANGE_REQUIRED = "NO_CHANGE_REQUIRED"


class ValidationStatus(str, Enum):
    PASSED = "PASSED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"


class DeliveryEligibility(str, Enum):
    FULL_AUTOMATIC_DELIVERY = "FULL_AUTOMATIC_DELIVERY"
    PARTIAL_MANUAL_REVIEW_DELIVERY = "PARTIAL_MANUAL_REVIEW_DELIVERY"
    NOT_DELIVERY_ELIGIBLE = "NOT_DELIVERY_ELIGIBLE"


INTENT_SECTIONS = (
    "Problem as received",
    "Interpreted objective",
    "Relevant context and evidence discovered",
    "Input ambiguities, discrepancies, or missing information",
    "Applicable constraints and success criteria",
    "Materially credible candidate approaches",
    "Selected direction",
    "Selection rationale",
    "Assumptions to test",
    "Intended work",
    "Validation approach",
    "Current uncertainties and risks",
)
PRIOR_CYCLE_INTENT_SECTIONS = (
    "Prior-cycle learning",
    "Relationship to the prior approach",
)
OUTCOME_SECTIONS = (
    "Work actually performed",
    "Evidence actually observed",
    "Intended versus actual",
    "Material deviations and their causes",
    "Approaches attempted, rejected, or abandoned",
    "Final approach present at cycle end",
    "Assumption results",
    "Requirement and problem coverage",
    "Constraints and regression assessment",
    "Self-validation assessment",
    "Remaining work, blockers, or uncertainty",
    "Partial-remediation value",
    "Cycle conclusion",
)
OUTCOME_STATUSES = frozenset(
    {
        "READY_FOR_INDEPENDENT_VALIDATION",
        "PARTIALLY_REMEDIATED",
        "BLOCKED",
        "FAILED",
        "INCONCLUSIVE",
        "NO_CHANGE_REQUIRED",
    }
)
OPTIONAL_SECTION = "Additional decision-relevant information"
PLACEHOLDERS = frozenset({"tbd", "todo", "n/a", "na", "none"})


@dataclass(frozen=True)
class JournalSection:
    kind: str
    cycle: int | None
    content_hash: str
    captured_at: str
    start_offset: int
    end_offset: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "cycle": self.cycle,
            "contentHash": self.content_hash,
            "capturedAt": self.captured_at,
            "startOffset": self.start_offset,
            "endOffset": self.end_offset,
        }


@dataclass(frozen=True)
class CheckpointResult:
    accepted: bool
    errors: tuple[str, ...] = ()
    metadata: JournalSection | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "accepted" if self.accepted else "rejected",
            "errors": list(self.errors),
            "metadata": self.metadata.to_dict() if self.metadata else None,
        }


@dataclass
class CycleCapture:
    intent: JournalSection | None = None
    outcome: JournalSection | None = None
    validation: JournalSection | None = None
    late_intent: bool = False
    rejected_intents: int = 0
    rejected_outcomes: int = 0
    intent_answers: dict[str, str] = field(default_factory=dict)
    outcome_answers: dict[str, str] = field(default_factory=dict)
    outcome_status: str | None = None

    @property
    def status(self) -> CaptureStatus:
        if self.intent and self.outcome:
            return CaptureStatus.LATE if self.late_intent else CaptureStatus.COMPLETE
        if self.intent or self.outcome:
            return CaptureStatus.INCOMPLETE
        return CaptureStatus.MISSING


class JournalStore:
    def __init__(self, trace: TraceStore):
        self.trace = trace
        self.path = trace.workspace.artifacts / "agent" / "decision-journal.md"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._accepted_digest = hashlib.sha256(b"").hexdigest()

    def initialize(self, run_contract: str) -> JournalSection:
        if self.path.exists():
            raise ValueError("Decision journal already exists")
        self.path.write_text("", encoding="utf-8")
        return self.append("run_contract", None, run_contract)

    def append(self, kind: str, cycle: int | None, content: str) -> JournalSection:
        before = self.path.read_bytes()
        if hashlib.sha256(before).hexdigest() != self._accepted_digest:
            raise RuntimeError("Previously accepted decision-journal content changed")
        rendered = content.rstrip() + "\n\n"
        start = len(before)
        with self.path.open("ab") as handle:
            handle.write(rendered.encode("utf-8"))
        after = self.path.read_bytes()
        if after[:start] != before:
            raise RuntimeError("Decision journal append changed prior content")
        self._accepted_digest = hashlib.sha256(after).hexdigest()
        metadata = JournalSection(
            kind=kind,
            cycle=cycle,
            content_hash=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            captured_at=datetime.now(timezone.utc).isoformat(),
            start_offset=start,
            end_offset=len(after),
        )
        if hashlib.sha256(after[start:]).hexdigest() != metadata.content_hash:
            raise RuntimeError("Appended journal content hash mismatch")
        self.trace.append_event(
            "journal_section_appended",
            kind=kind,
            cycle=cycle,
            path=str(self.path),
            contentHash=metadata.content_hash,
        )
        return metadata

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")


class JournalLifecycle:
    def __init__(
        self,
        store: JournalStore,
        trace: TraceStore,
        run_contract: str,
        repository_changed: Callable[[], bool],
        *,
        max_checkpoint_attempts: int = 3,
        max_section_chars: int = 8_000,
        max_checkpoint_chars: int = 48_000,
        max_context_chars: int = 24_000,
    ):
        self.store = store
        self.trace = trace
        self.phase = JournalPhase.DISCOVERY
        self.active_cycle = 0
        self.max_checkpoint_attempts = max_checkpoint_attempts
        self.max_section_chars = max_section_chars
        self.max_checkpoint_chars = max_checkpoint_chars
        self.max_context_chars = max_context_chars
        self.cycles: dict[int, CycleCapture] = {}
        self.store.initialize(render_run_contract(run_contract))
        self._repository_changed = repository_changed

    def set_repository_changed_probe(self, repository_changed: Callable[[], bool]) -> None:
        self._repository_changed = repository_changed

    def begin_cycle(self, cycle: int) -> None:
        self.active_cycle = cycle
        self.cycles.setdefault(cycle, CycleCapture())
        self.phase = JournalPhase.INTENT_REQUIRED
        self.trace.append_event("journal_phase_changed", cycle=cycle, phase=self.phase.value)

    def submit_intent(self, cycle: int, answers: list[dict[str, str]]) -> CheckpointResult:
        capture = self.cycles.setdefault(cycle, CycleCapture())
        errors = self._checkpoint_errors("intent", cycle, answers, capture.intent)
        if cycle > 1:
            errors.extend(self._missing_sections(answers, PRIOR_CYCLE_INTENT_SECTIONS))
        if errors:
            capture.rejected_intents += 1
            return self._reject("intent", cycle, errors, capture.rejected_intents)
        late = self._repository_changed()
        rendered = render_checkpoint(cycle, "Intent", answers)
        errors.extend(validate_rendered_markdown(rendered, f"Cycle {cycle} — Intent"))
        if errors:
            capture.rejected_intents += 1
            return self._reject("intent", cycle, errors, capture.rejected_intents)
        capture.intent = self.store.append("intent", cycle, rendered)
        capture.intent_answers = {
            str(item["section"]).strip(): str(item["answer"]).strip() for item in answers
        }
        capture.late_intent = late
        self.phase = JournalPhase.EXECUTION
        self.trace.append_event(
            "intent_submission_accepted",
            cycle=cycle,
            late=late,
            contentHash=capture.intent.content_hash,
        )
        return CheckpointResult(True, metadata=capture.intent)

    def require_outcome(self) -> None:
        self.phase = JournalPhase.OUTCOME_REQUIRED
        self.trace.append_event("journal_phase_changed", cycle=self.active_cycle, phase=self.phase.value)

    def submit_outcome(
        self,
        cycle: int,
        status: str,
        status_explanation: str,
        answers: list[dict[str, str]],
    ) -> CheckpointResult:
        capture = self.cycles.setdefault(cycle, CycleCapture())
        normalized_status = status.strip().upper()
        errors = self._checkpoint_errors("outcome", cycle, answers, capture.outcome)
        if normalized_status not in OUTCOME_STATUSES:
            errors.append(f"Invalid Cycle Outcome status: {status}")
        errors.extend(_answer_errors("Cycle outcome status", status_explanation, self.max_section_chars))
        if errors:
            capture.rejected_outcomes += 1
            return self._reject("outcome", cycle, errors, capture.rejected_outcomes)
        all_answers = [
            {"section": "Cycle outcome status", "answer": f"`{normalized_status}`\n\n{status_explanation.strip()}"},
            *answers,
        ]
        rendered = render_checkpoint(cycle, "Outcome", all_answers)
        errors.extend(validate_rendered_markdown(rendered, f"Cycle {cycle} — Outcome"))
        if errors:
            capture.rejected_outcomes += 1
            return self._reject("outcome", cycle, errors, capture.rejected_outcomes)
        capture.outcome = self.store.append("outcome", cycle, rendered)
        capture.outcome_answers = {
            str(item["section"]).strip(): str(item["answer"]).strip() for item in answers
        }
        capture.outcome_status = normalized_status
        self.phase = JournalPhase.DETERMINISTIC_VALIDATION
        self.trace.append_event(
            "outcome_submission_accepted",
            cycle=cycle,
            status=normalized_status,
            contentHash=capture.outcome.content_hash,
        )
        return CheckpointResult(True, metadata=capture.outcome)

    def append_validation(
        self,
        report: ValidationReport,
        status: ValidationStatus,
        delivery: DeliveryEligibility,
    ) -> JournalSection:
        rendered = render_validation(report, status, delivery)
        errors = validate_rendered_markdown(rendered, f"Cycle {report.cycle} — Deterministic Validation")
        if errors:
            raise RuntimeError("Invalid deterministic validation journal section: " + "; ".join(errors))
        capture = self.cycles.setdefault(report.cycle, CycleCapture())
        capture.validation = self.store.append("deterministic_validation", report.cycle, rendered)
        self.phase = JournalPhase.DELIVERY_OR_CONTINUATION
        self.trace.append_event(
            "deterministic_validation_appended",
            cycle=report.cycle,
            status=status.value,
            deliveryEligibility=delivery.value,
        )
        return capture.validation

    def finish(self, content: str) -> JournalSection:
        metadata = self.store.append("final_resolution", None, content)
        self.phase = JournalPhase.FINISHED
        return metadata

    def capture_status(self, cycle: int | None = None) -> CaptureStatus:
        selected = self.cycles.get(cycle or self.active_cycle)
        return selected.status if selected else CaptureStatus.MISSING

    def outcome_status(self, cycle: int | None = None) -> str | None:
        selected_cycle = cycle or self.active_cycle
        capture = self.cycles.get(selected_cycle)
        return capture.outcome_status if capture else None

    def context(self) -> str:
        content = self.store.read()
        if len(content) <= self.max_context_chars:
            return content
        marker = "\n\n[Earlier journal content bounded for model input]\n\n"
        head_limit = min(6_000, self.max_context_chars // 3)
        tail_limit = max(0, self.max_context_chars - head_limit - len(marker))
        return content[:head_limit] + marker + content[-tail_limit:]

    def _checkpoint_errors(
        self,
        kind: str,
        cycle: int,
        answers: list[dict[str, str]],
        existing: JournalSection | None,
    ) -> list[str]:
        errors: list[str] = []
        attempts = (
            self.cycles.get(cycle, CycleCapture()).rejected_intents
            if kind == "intent"
            else self.cycles.get(cycle, CycleCapture()).rejected_outcomes
        )
        if attempts >= self.max_checkpoint_attempts:
            errors.append(f"Cycle {cycle} {kind} retry limit is exhausted")
        if cycle != self.active_cycle:
            errors.append(f"Expected active cycle {self.active_cycle}, received {cycle}")
        expected_phase = JournalPhase.INTENT_REQUIRED if kind == "intent" else JournalPhase.OUTCOME_REQUIRED
        if self.phase != expected_phase:
            errors.append(f"Expected phase {expected_phase.value}, current phase is {self.phase.value}")
        if existing:
            errors.append(f"Cycle {cycle} {kind} has already been accepted")
        required = INTENT_SECTIONS if kind == "intent" else OUTCOME_SECTIONS
        errors.extend(self._missing_sections(answers, required))
        seen: set[str] = set()
        total = 0
        for item in answers:
            section = str(item.get("section", "")).strip()
            answer = str(item.get("answer", ""))
            if not section:
                errors.append("A section name is empty")
                continue
            key = section.casefold()
            if key in seen:
                errors.append(f"Duplicate section: {section}")
            seen.add(key)
            total += len(answer)
            errors.extend(_answer_errors(section, answer, self.max_section_chars))
        if total > self.max_checkpoint_chars:
            errors.append(
                f"Checkpoint content exceeds {self.max_checkpoint_chars} characters ({total})"
            )
        return errors

    @staticmethod
    def _missing_sections(answers: list[dict[str, str]], required: Iterable[str]) -> list[str]:
        supplied = {str(item.get("section", "")).strip().casefold() for item in answers}
        return [f"Missing required section: {section}" for section in required if section.casefold() not in supplied]

    def _reject(self, kind: str, cycle: int, errors: list[str], attempt: int) -> CheckpointResult:
        self.trace.append_event(
            f"{kind}_submission_rejected",
            cycle=cycle,
            attempt=attempt,
            retryAllowed=attempt < self.max_checkpoint_attempts,
            errors=errors,
        )
        return CheckpointResult(False, tuple(errors))


def render_run_contract(run_contract: str) -> str:
    return "# Run Contract\n\n" + run_contract.strip()


def render_checkpoint(cycle: int, checkpoint: str, answers: list[dict[str, str]]) -> str:
    lines = [f"# Cycle {cycle} — {checkpoint}", ""]
    for item in answers:
        section = str(item["section"]).strip()
        answer = str(item["answer"]).strip()
        lines.extend((f"## {section}", "", answer, ""))
    return "\n".join(lines).rstrip()


def validate_rendered_markdown(content: str, expected_title: str) -> list[str]:
    errors: list[str] = []
    headings: list[tuple[int, str]] = []
    fenced = False
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if fenced or not stripped.startswith("#"):
            continue
        marker, separator, title = stripped.partition(" ")
        if separator and set(marker) == {"#"} and 1 <= len(marker) <= 6 and title.strip():
            headings.append((len(marker), title.strip()))
    if fenced:
        errors.append("Markdown contains an unclosed fenced code block")
    if not headings or headings[0] != (1, expected_title):
        errors.append(f"Rendered Markdown must begin with '# {expected_title}'")
    if any(level == 1 for level, _ in headings[1:]):
        errors.append("Rendered checkpoint contains an unexpected additional top-level heading")
    return errors


def render_validation(
    report: ValidationReport,
    status: ValidationStatus,
    delivery: DeliveryEligibility,
) -> str:
    failed = [check for check in report.checks if not check.passed]
    passed = [check for check in report.checks if check.passed]
    diagnostics = list(report.diagnostic_artifacts)
    lines = [
        f"# Cycle {report.cycle} — Deterministic Validation",
        "",
        "## Validation result",
        "",
        status.value,
        "",
        "## Checks performed",
        "",
    ]
    for check in report.checks:
        lines.append(f"- **{check.name}:** {'PASSED' if check.passed else 'FAILED'} — {check.message}")
    lines.extend(
        [
            "",
            "## Outcome claims confirmed",
            "",
            *(f"- {check.name}: {check.message}" for check in passed),
            *([] if passed else ["- No outcome claim was independently confirmed."]),
            "",
            "## Outcome claims contradicted",
            "",
            *(f"- {check.name}: {check.message}" for check in failed),
            *([] if failed else ["- None identified by deterministic checks."]),
            "",
            "## Requirements satisfied",
            "",
            *(f"- {check.name}" for check in passed),
            *([] if passed else ["- None established."]),
            "",
            "## Requirements remaining",
            "",
            *(f"- {check.name}" for check in failed),
            *([] if failed else ["- None identified."]),
            "",
            "## Constraint result",
            "",
            "All deterministic constraint checks passed."
            if all(check.passed for check in report.checks if "constraint" in check.name or "policy" in check.name)
            else "One or more deterministic constraint checks failed.",
            "",
            "## Repository or system state",
            "",
            f"- **Changed items:** {', '.join(report.changed_files) or 'None'}",
            f"- **State digest:** `{report.tree_digest}`",
            f"- **Diff or evidence artifact:** `{report.diff_path}`",
            f"- **Investigation-only artifacts detected:** {', '.join(diagnostics) or 'None'}",
            "",
            "## Delivery eligibility",
            "",
            delivery.value,
            "",
            "## Validation conclusion",
            "",
            "All authoritative checks passed." if report.passed else "Authoritative validation did not establish full success.",
            "",
            "## Next-cycle requirement",
            "",
            "Not applicable." if report.passed else "Address failed checks and unresolved requirements without replacing the original run contract.",
        ]
    )
    return "\n".join(lines)


def render_final_resolution(
    outcome: RemediationOutcome,
    original_problem: str,
    implemented_approach: str,
    validation: ValidationReport | None,
    capture_status: CaptureStatus,
    delivery: DeliveryEligibility,
    delivery_result: str,
    limitation: str,
) -> str:
    checks = validation.checks if validation else ()
    satisfied = [check.name for check in checks if check.passed]
    unresolved = [check.name for check in checks if not check.passed]
    evidence = "\n".join(f"- {check.name}: {'passed' if check.passed else 'failed'} — {check.message}" for check in checks)
    partial = (
        f"Preserved changes require manual review. Unresolved: {', '.join(unresolved) or 'not deterministically identified'}."
        if outcome == RemediationOutcome.PARTIALLY_REMEDIATED
        else "Not applicable."
    )
    return f"""# Final Resolution

## Final outcome

{outcome.value}

## Original problem

{original_problem}

## Final interpreted resolution

Deterministic validation status and capture quality are reported separately. Capture status: `{capture_status.value}`.

## Final implemented approach

{implemented_approach or 'No accepted Cycle Outcome described an implemented approach.'}

## How the approach evolved

See the immutable cycle Intent, Outcome, and Deterministic Validation sections above.

## Final requirement coverage

### Satisfied

{_bullets(satisfied)}

### Conditional

- Any model-authored claims not directly established by deterministic checks remain conditional.

### Unresolved

{_bullets(unresolved)}

### Not applicable

- None identified by deterministic orchestration.

## Final evidence

{evidence or '- Deterministic validation did not run.'}

## Constraints and known risks

Capture quality `{capture_status.value}`; delivery eligibility `{delivery.value}`.

## Partial-remediation disclosure

{partial}

## Delivery result

{delivery_result}

## Remaining limitations

{limitation}

## Final conclusion

Final outcome is `{outcome.value}`; this does not override the separate deterministic validation, capture, or delivery states."""


def _answer_errors(section: str, answer: str, max_chars: int) -> list[str]:
    stripped = answer.strip()
    errors: list[str] = []
    if not stripped:
        errors.append(f"Empty answer for section: {section}")
    elif stripped.casefold().rstrip(".!") in PLACEHOLDERS:
        errors.append(f"Placeholder-only answer for section: {section}")
    if len(answer) > max_chars:
        errors.append(f"Section exceeds {max_chars} characters: {section}")
    return errors


def _bullets(values: Iterable[str]) -> str:
    items = list(values)
    return "\n".join(f"- {value}" for value in items) if items else "- None established."
