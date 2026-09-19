from __future__ import annotations

import hashlib
import re
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




@dataclass(frozen=True)
class QuestionnaireSection:
    name: str
    guidance: str
    after_cycle_one: bool = False


INTENT_QUESTIONNAIRE = (
    QuestionnaireSection("Problem as received", "Restate the supplied problem, requested outcome, and reported findings without changing their meaning."),
    QuestionnaireSection("Interpreted objective", "Describe the engineering outcome currently required and distinguish it from any literal wording when necessary."),
    QuestionnaireSection("Relevant context and evidence discovered", "Record material observed repository, environment, dependency, build, scan, and prior-work evidence; keep observations separate from assumptions."),
    QuestionnaireSection("Input ambiguities, discrepancies, or missing information", "Identify material uncertainty or explicitly explain why current information is sufficient."),
    QuestionnaireSection("Applicable constraints and success criteria", "Apply caller constraints and state evidence needed for full, partial, blocked, and inconclusive outcomes without turning techniques into constraints."),
    QuestionnaireSection("Prior-cycle learning", "Explain what prior authoritative validation supported, contradicted, or left unresolved.", after_cycle_one=True),
    QuestionnaireSection("Relationship to the prior approach", "Explain whether this direction continues, adjusts, replaces, expands, or investigates before committing to the prior approach.", after_cycle_one=True),
    QuestionnaireSection("Materially credible candidate approaches", "Describe only genuine candidates. One credible approach is valid; if more evidence is needed, a reversible diagnostic experiment is valid. Do not invent alternatives."),
    QuestionnaireSection("Selected direction", "State the approach, combination, or diagnostic experiment selected for execution."),
    QuestionnaireSection("Selection rationale", "Explain evidence, coverage, constraints, risks, maintainability, validation, and meaningful tradeoffs."),
    QuestionnaireSection("Assumptions to test", "For each material assumption state why it matters, how it will be tested, and its current status; explain if none remain."),
    QuestionnaireSection("Intended work", "Describe meaningful directional work and any reversible investigation, not a rigid command-by-command plan."),
    QuestionnaireSection("Validation approach", "State required checks, expected evidence, failure signals, and evidence that should trigger adaptation; do not present planned checks as completed."),
    QuestionnaireSection("Current uncertainties and risks", "Record material uncertainty or risk and how execution or validation should reduce it."),
)
OUTCOME_QUESTIONNAIRE = (
    QuestionnaireSection("Work actually performed", "Describe material changes, investigations, experiments, corrective actions, and relevant reverted or abandoned work."),
    QuestionnaireSection("Evidence actually observed", "Record successful, failed, incomplete, and inconclusive evidence separately from conclusions, with stable references when available."),
    QuestionnaireSection("Intended versus actual", "Compare the accepted Intent with completed, omitted, added, and materially changed work."),
    QuestionnaireSection("Material deviations and their causes", "Explain each strategy-level deviation, its evidence, cause, and effect; say explicitly if none occurred."),
    QuestionnaireSection("Approaches attempted, rejected, or abandoned", "Record material approaches not retained, supporting evidence, failure category, and preserved value; say explicitly if none."),
    QuestionnaireSection("Final approach present at cycle end", "Describe only the approach actually represented by repository state."),
    QuestionnaireSection("Assumption results", "Give each material assumption's final status, evidence, and effect on the implementation or conclusion."),
    QuestionnaireSection("Requirement and problem coverage", "Distinguish satisfied, conditional, unresolved, and not-applicable coverage with justification."),
    QuestionnaireSection("Constraints and regression assessment", "Report constraint compliance, compatibility, regressions, unrelated changes, and investigation-only artifacts."),
    QuestionnaireSection("Self-validation assessment", "Distinguish planned-not-run, passed, failed, inconclusive, and environmentally blocked checks; state what independent validation must confirm."),
    QuestionnaireSection("Remaining work, blockers, or uncertainty", "For each remaining item state why it remains, whether another cycle can resolve it, and whether external input is needed."),
    QuestionnaireSection("Partial-remediation value", "When partial, state measurable improvement, remaining requirements, safety, test health, prohibited issues, manual-review value, and disclosures; otherwise state why not applicable."),
    QuestionnaireSection("Cycle conclusion", "Concise evidence-based summary of intent, actual work, deviations, established results, unresolved work, and next step."),
)
INTENT_SECTIONS = tuple(section.name for section in INTENT_QUESTIONNAIRE if not section.after_cycle_one)
PRIOR_CYCLE_INTENT_SECTIONS = tuple(section.name for section in INTENT_QUESTIONNAIRE if section.after_cycle_one)
OUTCOME_SECTIONS = tuple(section.name for section in OUTCOME_QUESTIONNAIRE)
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
    last_intent_errors: tuple[str, ...] = ()
    last_outcome_errors: tuple[str, ...] = ()
    validation_report: ValidationReport | None = None

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
        self.sections: list[JournalSection] = []

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
        self.sections.append(metadata)
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
        preliminary_contract: bool = False,
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
        self.store.initialize(render_run_contract(run_contract, preliminary=preliminary_contract))
        self._repository_changed = repository_changed

    def append_baseline_contract(self, run_contract: str) -> JournalSection:
        if self.cycles:
            raise RuntimeError("Baseline Contract must precede remediation cycles")
        return self.store.append(
            "baseline_contract",
            None,
            "# Baseline Contract\n\n" + run_contract.strip(),
        )

    def set_repository_changed_probe(self, repository_changed: Callable[[], bool]) -> None:
        self._repository_changed = repository_changed

    @property
    def run_capture_status(self) -> CaptureStatus:
        if not self.cycles:
            return CaptureStatus.MISSING
        trust = {
            CaptureStatus.MISSING: 0,
            CaptureStatus.INCOMPLETE: 1,
            CaptureStatus.LATE: 2,
            CaptureStatus.COMPLETE: 3,
        }
        return min((capture.status for capture in self.cycles.values()), key=trust.__getitem__)

    def capture_warnings(self) -> tuple[str, ...]:
        if not self.cycles:
            return ("No remediation-cycle checkpoints were captured",)
        return tuple(
            f"Cycle {cycle} capture is {capture.status.value}"
            for cycle, capture in sorted(self.cycles.items())
            if capture.status != CaptureStatus.COMPLETE
        )

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
        capture.last_intent_errors = ()
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
        capture.last_outcome_errors = ()
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
        capture = self.cycles.setdefault(report.cycle, CycleCapture())
        rendered = render_validation(report, status, delivery, capture.outcome_status)
        errors = validate_rendered_markdown(rendered, f"Cycle {report.cycle} — Deterministic Validation")
        if errors:
            raise RuntimeError("Invalid deterministic validation journal section: " + "; ".join(errors))
        capture.validation = self.store.append("deterministic_validation", report.cycle, rendered)
        capture.validation_report = report
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
        contract_sections = [
            section
            for section in self.store.sections
            if section.kind in {"run_contract", "baseline_contract"}
        ]
        contract_end = max((section.end_offset for section in contract_sections), default=0)
        contract_chars = len(self.store.path.read_bytes()[:contract_end].decode("utf-8"))
        head_limit = min(contract_chars, self.max_context_chars * 2 // 3)
        head_limit = max(head_limit, min(6_000, self.max_context_chars // 3))
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
            errors.extend(validate_answer_markdown(answer, section))
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
        capture = self.cycles.setdefault(cycle, CycleCapture())
        if kind == "intent":
            capture.last_intent_errors = tuple(errors)
        else:
            capture.last_outcome_errors = tuple(errors)
        self.trace.append_event(
            f"{kind}_submission_rejected",
            cycle=cycle,
            attempt=attempt,
            retryAllowed=attempt < self.max_checkpoint_attempts,
            errors=errors,
        )
        return CheckpointResult(False, tuple(errors))


def render_run_contract(run_contract: str, *, preliminary: bool = False) -> str:
    title = "Preliminary Run Contract" if preliminary else "Run Contract"
    return f"# {title}\n\n" + run_contract.strip()


def render_checkpoint(cycle: int, checkpoint: str, answers: list[dict[str, str]]) -> str:
    lines = [f"# Cycle {cycle} — {checkpoint}", ""]
    for item in answers:
        section = str(item["section"]).strip()
        answer = str(item["answer"]).strip()
        lines.extend((f"## {section}", "", answer, ""))
    return "\n".join(lines).rstrip()


def intent_questionnaire(cycle: int) -> str:
    sections = [
        section for section in INTENT_QUESTIONNAIRE
        if cycle > 1 or not section.after_cycle_one
    ]
    rules = (
        "Use these exact section names as `section` values in `submit_cycle_intent`. "
        "Answer observations as observations, assumptions as unproven assumptions, intended work as future work, "
        "and do not present planned validation as completed evidence. One credible approach or a reversible "
        "diagnostic experiment is sufficient; never invent alternatives. You may add clearly named, "
        "decision-relevant sections after all required sections."
    )
    return _render_questionnaire("Cycle Intent questionnaire", sections, rules)


def outcome_questionnaire() -> str:
    statuses = ", ".join(f"`{status}`" for status in sorted(OUTCOME_STATUSES))
    rules = (
        "Use these exact section names as `section` values in `submit_cycle_outcome`. "
        f"Allowed `status` values: {statuses}. Separate observed evidence from conclusions, compare intended with "
        "actual work, and do not treat self-validation as deterministic validation. You may add clearly named, "
        "decision-relevant sections after all required sections."
    )
    return _render_questionnaire("Cycle Outcome questionnaire", OUTCOME_QUESTIONNAIRE, rules)


def _render_questionnaire(
    title: str,
    sections: Iterable[QuestionnaireSection],
    rules: str,
) -> str:
    lines = [title, rules, "Required sections:"]
    for section in sections:
        conditional = " (required after Cycle 1)" if section.after_cycle_one else ""
        lines.append(f"- `{section.name}`{conditional}: {section.guidance}")
    return "\n".join(lines)


def validate_answer_markdown(answer: str, section: str) -> list[str]:
    errors, headings = _markdown_structure(answer)
    result = [f"{section}: {error}" for error in errors]
    for level, title in headings:
        if level < 3:
            result.append(
                f"{section}: answer headings must use level 3-6; top-level and required-section headings are rendered by the system ({title})"
            )
    return result


def validate_rendered_markdown(content: str, expected_title: str) -> list[str]:
    errors, headings = _markdown_structure(content)
    if not headings or headings[0] != (1, expected_title):
        errors.append(f"Rendered Markdown must begin with '# {expected_title}'")
    if any(level == 1 for level, _ in headings[1:]):
        errors.append("Rendered checkpoint contains an unexpected additional top-level heading")
    return errors


def _markdown_structure(content: str) -> tuple[list[str], list[tuple[int, str]]]:
    """Validate the deliberately limited Markdown subset accepted in journal answers."""
    errors: list[str] = []
    headings: list[tuple[int, str]] = []
    fence_char: str | None = None
    fence_length = 0
    previous_nonblank = False
    for line in content.splitlines():
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        marker_char = stripped[:1]
        marker_length = 0
        if indent <= 3 and marker_char in {"`", "~"}:
            marker_length = len(stripped) - len(stripped.lstrip(marker_char))
        if fence_char is not None:
            if marker_char == fence_char and marker_length >= fence_length and not stripped[marker_length:].strip():
                fence_char = None
                fence_length = 0
            continue
        if marker_length >= 3:
            fence_char = marker_char
            fence_length = marker_length
            previous_nonblank = False
            continue
        if indent <= 3 and stripped.startswith("#"):
            marker, separator, title = stripped.partition(" ")
            if separator and set(marker) == {"#"} and 1 <= len(marker) <= 6 and title.strip():
                headings.append((len(marker), title.strip()))
        if previous_nonblank and indent <= 3 and stripped and set(stripped) <= {"="}:
            errors.append("setext headings are not supported; use level 3-6 ATX headings")
        previous_nonblank = bool(stripped)
    if fence_char is not None:
        errors.append(f"Markdown contains an unclosed {fence_char * fence_length} fenced code block")
    return errors, headings


def render_validation(
    report: ValidationReport,
    status: ValidationStatus,
    delivery: DeliveryEligibility,
    outcome_status: str | None,
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
            "## Deterministic checks passed",
            "",
            *(f"- {check.name}: {check.message}" for check in passed),
            *([] if passed else ["- None."]),
            "",
            "## Deterministic checks failed",
            "",
            *(f"- {check.name}: {check.message}" for check in failed),
            *([] if failed else ["- None."]),
            "",
            "## Model claims directly contradicted",
            "",
            *_validation_contradictions(report, outcome_status),
            "",
            "## Model claims not independently evaluated",
            "",
            "- Narrative claims without an explicit deterministic check mapping remain unevaluated; structural capture does not establish semantic correctness.",
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
            _constraint_result(report),
            "",
            "## Repository or system state",
            "",
            f"- **Changed items:** {', '.join(report.changed_files) or 'None'}",
            f"- **State digest:** `{report.tree_digest}`",
            f"- **Diff or evidence artifact:** `{report.diff_path}`",
            f"- **Investigation-only artifacts detected:** {', '.join(diagnostics) or 'None'}",
            f"- **Target comparison completed:** {'Yes' if report.target_comparison_complete else 'No'}",
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
    cycles: dict[int, CycleCapture],
    validation: ValidationReport | None,
    capture_status: CaptureStatus,
    delivery: DeliveryEligibility,
    delivery_result: str,
    limitation: str,
) -> str:
    checks = validation.checks if validation else ()
    satisfied = [check.name for check in checks if check.passed]
    unresolved = [check.name for check in checks if not check.passed]
    evidence = "\n".join(
        f"- {check.name}: {'passed' if check.passed else 'failed'} — {check.message}"
        for check in checks
    )
    latest = cycles[max(cycles)] if cycles else None
    latest_answers = latest.outcome_answers if latest else {}
    implemented_approach = latest_answers.get("Final approach present at cycle end", "")
    coverage = latest_answers.get("Requirement and problem coverage", "")
    coverage_headings = {
        line.strip()[4:].strip().casefold()
        for line in coverage.splitlines()
        if line.strip().startswith("### ")
    }
    coverage_categories = {"satisfied", "conditional", "unresolved", "not applicable"}
    coverage_is_structured = coverage_categories.issubset(coverage_headings)
    structured_coverage = coverage if coverage_is_structured else ""
    constraints = latest_answers.get("Constraints and regression assessment", "")
    partial_value = latest_answers.get("Partial-remediation value", "")
    partial = (
        f"Preserved changes require manual review. Unresolved deterministic checks: {', '.join(unresolved) or 'none identified'}."
        if outcome == RemediationOutcome.PARTIALLY_REMEDIATED
        else "Not applicable."
    )
    return f"""# Final Resolution

## Final outcome

{outcome.value}

## Original problem

{original_problem}

## Final interpreted resolution

Deterministic validation status and capture quality are reported separately. Run-level capture status: `{capture_status.value}`.

## Final implemented approach

{implemented_approach or 'No accepted Cycle Outcome described an implemented approach.'}

## How the approach evolved

{_approach_evolution(cycles)}

## Final requirement coverage

### Satisfied

{_bullets(satisfied)}
{_captured_block('Model-reported satisfied coverage', _coverage_subsection(structured_coverage, 'Satisfied'))}

### Conditional

{_captured_block('Model-reported conditional coverage', _coverage_subsection(structured_coverage, 'Conditional'))}

### Unresolved

{_bullets(unresolved)}
{_captured_block('Model-reported unresolved coverage', _coverage_subsection(structured_coverage, 'Unresolved'))}

### Not applicable

{_captured_block('Model-reported not-applicable coverage', _coverage_subsection(structured_coverage, 'Not applicable'))}

{'### Uncategorized model-reported coverage' if coverage and not coverage_is_structured else ''}

{coverage if coverage and not coverage_is_structured else ''}

## Final evidence

{evidence or '- Deterministic validation did not run.'}

## Constraints and known risks

Run-level capture quality `{capture_status.value}`; delivery eligibility `{delivery.value}`.

{constraints or 'No accepted Cycle Outcome captured a constraints and regression assessment.'}

## Partial-remediation disclosure

{partial}

{partial_value or 'No additional partial-remediation value statement was captured.'}

## Delivery result

{delivery_result}

## Remaining limitations

{limitation}

## Final conclusion

Final outcome is `{outcome.value}`; this does not override the separate deterministic validation, capture, or delivery states."""


def _validation_contradictions(
    report: ValidationReport,
    outcome_status: str | None,
) -> list[str]:
    contradictions: list[str] = []
    resolved = len(report.resolved_target_findings)
    if outcome_status == "NO_CHANGE_REQUIRED" and report.changed_files:
        contradictions.append(
            "- Outcome reported no change required, but authoritative Git evidence contains changed files."
        )
    if outcome_status == "PARTIALLY_REMEDIATED" and not report.target_comparison_complete:
        contradictions.append(
            "- Outcome reported partial remediation, but target comparison was unavailable because the fresh scan did not complete."
        )
    elif outcome_status == "PARTIALLY_REMEDIATED" and resolved == 0:
        contradictions.append(
            "- Outcome reported partial remediation, but deterministic comparison found no original target finding resolved."
        )
    if outcome_status == "PARTIALLY_REMEDIATED" and report.passed:
        contradictions.append(
            "- Outcome reported partial remediation, but deterministic validation found all target requirements satisfied."
        )
    if report.passed and outcome_status in {"BLOCKED", "FAILED", "INCONCLUSIVE"}:
        contradictions.append(
            f"- Outcome status `{outcome_status}` records an unresolved concern despite all deterministic checks passing; automatic delivery requires manual review."
        )
    return contradictions or ["- None established by an explicit model-claim-to-check mapping."]


def _constraint_result(report: ValidationReport) -> str:
    constraint_checks = [
        check for check in report.checks
        if "constraint" in check.name or "policy" in check.name
    ]
    if not constraint_checks:
        return "No dedicated deterministic constraint check was applicable."
    if all(check.passed for check in constraint_checks):
        return "All applicable deterministic constraint checks passed."
    return "One or more applicable deterministic constraint checks failed."


def _approach_evolution(cycles: dict[int, CycleCapture]) -> str:
    if not cycles:
        return "- No remediation cycle was captured."
    lines: list[str] = []
    for cycle, capture in sorted(cycles.items()):
        selected = capture.intent_answers.get("Selected direction", "Not captured")
        final = capture.outcome_answers.get("Final approach present at cycle end", "Not captured")
        deviations = capture.outcome_answers.get("Material deviations and their causes", "Not captured")
        assumptions = capture.outcome_answers.get("Assumption results", "Not captured")
        report = capture.validation_report
        if report:
            failed = [check.name for check in report.checks if not check.passed]
            learning = (
                "all deterministic checks passed"
                if report.passed
                else "failed or unresolved checks: " + ", ".join(failed)
            )
        else:
            learning = "deterministic validation was not completed"
        lines.extend(
            (
                f"- **Cycle {cycle} selected direction:** {_inline(selected)}",
                f"- **Cycle {cycle} final approach:** {_inline(final)}",
                f"- **Cycle {cycle} material deviations:** {_inline(deviations)}",
                f"- **Cycle {cycle} assumption results:** {_inline(assumptions)}",
                f"- **Cycle {cycle} validation learning:** {learning}.",
            )
        )
    return "\n".join(lines)


def _coverage_subsection(content: str, title: str) -> str:
    current: str | None = None
    collected: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            current = stripped[4:].strip().casefold()
            continue
        if current == title.casefold():
            collected.append(line)
    return "\n".join(collected).strip()


def _captured_block(label: str, content: str) -> str:
    if not content:
        return f"- {label}: not separately captured."
    quoted = "\n".join(f"> {line}" if line else ">" for line in content.splitlines())
    return f"- {label}:\n\n{quoted}"


def _inline(content: str, limit: int = 600) -> str:
    normalized = " ".join(content.split())
    if len(normalized) > limit:
        return normalized[: limit - 1].rstrip() + "…"
    return normalized


def _answer_errors(section: str, answer: str, max_chars: int) -> list[str]:
    stripped = answer.strip()
    placeholder_candidate = re.sub(r"^[\s`*_~#>+\-.]+|[\s`*_~.!]+$", "", stripped.casefold())
    errors: list[str] = []
    if not stripped:
        errors.append(f"Empty answer for section: {section}")
    elif placeholder_candidate in PLACEHOLDERS:
        errors.append(f"Placeholder-only answer for section: {section}")
    if len(answer) > max_chars:
        errors.append(f"Section exceeds {max_chars} characters: {section}")
    return errors


def _bullets(values: Iterable[str]) -> str:
    items = list(values)
    return "\n".join(f"- {value}" for value in items) if items else "- None established."
