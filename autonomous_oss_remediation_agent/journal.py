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


class CheckpointCaptureStatus(str, Enum):
    PENDING = "PENDING"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    NOT_REQUESTED = "NOT_REQUESTED"


class ImplementationStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    NOT_EXECUTED = "NOT_EXECUTED"


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
    QuestionnaireSection(
        "Problem understanding in project context",
        "What engineering problem is currently established in the context of this project? Explain the requested result, target scope, materially governing requirements and constraints, project characteristics material to understanding the problem, material relationships among symptoms or components when supported by available evidence, and the complete-resolution standard. Do not require or assert a shared or higher-level root cause before the evidence supports one. Do not propose solutions, enumerate approaches, select mechanisms, or replace, narrow, or expand the Task to Solve.",
    ),
    QuestionnaireSection(
        "Information, investigation and remaining uncertainty",
        """What information was needed to develop an evidence-supported solution, and what did the model find?

Use this table:

| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|

The table must report investigation actually performed and evidence actually obtained. The Sources examined column must name actual sources, tools, or methods. Planned, intended, future, or not-yet-performed investigation is not a finding and is not evidence supporting candidate formation. If decision-relevant information is reasonably obtainable through the available engineering capabilities and could materially affect problem understanding, mechanism discovery or applicability, control structure, viability, constraints, candidate formation, or selection, investigate it before submitting this response. When that information may have changed outside the repository, obtain reasonably available current authoritative evidence before candidate selection and use it to discover the actual available and potentially applicable solution space, not merely to confirm the first preferred solution. Prefer current primary or authoritative technical sources when reasonably available for material externally changing claims; when obtained, that evidence takes precedence over unsupported or potentially stale prior knowledge about the changing fact. Keep investigation proportional: current external research is not required when such information is immaterial, non-material information does not require exhaustive investigation, and genuinely execution-dependent information may remain unknown. Failed, blocked, incomplete, or inconclusive research is not evidence that an option or mechanism does not exist. Uncertainty is not evidence for or against an approach; preserve it honestly.

Then add `### Material assumptions that remain necessary`. Report only assumptions that materially affect the current engineering decision. For each, state what is assumed, why it could not be established, what evidence was checked, which decision or conclusion depends on it, and what uncertainty or risk remains. An assumption must not substitute for reasonably obtainable repository evidence material to candidate formation or selection. Do not introduce an assumption merely to explain unexpected evidence or justify proceeding. If an unresolved interpretation is not necessary to the decision, leave it as uncertainty rather than elevating it into a material assumption. If no material assumptions remain, state `None`.

Before reconciling candidates with hard constraints, establish candidate-relevant facts from the Task to Solve, directly observed repository state, and observed execution evidence. Distinguish those established facts from interpretations, unresolved uncertainty, assumptions, prior knowledge, expectations, conventions, or guesses, including potentially stale expectations about externally changing information. Current external evidence may establish what options exist, what outcome they provide, and documented support, compatibility, migration, or breaking-change properties; repository and execution evidence establish what applies to and happens in this project. Neither unsupported prior knowledge nor general external information may displace stronger task-specific or observed project evidence. If they appear inconsistent, investigate the discrepancy rather than declaring the observed project state invalid. Do not use an unsupported expectation, convention, potentially stale prior, unresolved assumption, or absence of evidence as positive support or as a material reason to eliminate a plausible approach. The established properties of a proposed change govern constraint reconciliation; describing or rationalizing the change differently does not alter those properties.

Distinguish ordinary execution-dependent uncertainty from uncertainty that materially determines hard-requirement or hard-constraint compliance. Ordinary uncertainty such as whether builds, tests, runtime checks, or authoritative validation succeed may remain for implementation and validation; candidate formation requires an evidence-supported basis for trying a mechanism, not pre-execution proof of those outcomes. Investigate hard-constraint-determining uncertainty before candidate selection when reasonably possible using the available investigation capabilities. If it cannot be resolved sufficiently for selection, preserve it honestly: the affected candidate is not yet admissible and the uncertainty must not be converted into an assumption that permits selection.

When solution choice materially depends on how relevant state or behavior is produced or controlled, investigate the existing ownership, control, management, inheritance, indirection, configuration, composition, abstraction, relationships, or other repository-evidenced mechanisms to the depth reasonably necessary for the decision. Record the evidence about those boundaries here; the engineering conclusion derived from it belongs in the synthesis section. If candidate viability or selection materially depends on a repository-specific premise that a proposed mechanism controls, changes, resolves, produces, or otherwise affects relevant state or behavior, and the available isolated investigation capabilities can reasonably test that premise, obtain sufficient evidence before treating the premise as established or the candidate as sufficiently supported for selection. General technical knowledge may suggest the mechanism or premise to investigate, but does not by itself establish repository-specific applicability or viability when material repository evidence is reasonably obtainable. If sufficient evidence cannot reasonably be obtained, record the premise and the affected approach as unresolved; that uncertainty neither supports the candidate nor establishes that the mechanism is non-viable. This requires decision-sufficient support, not exhaustive pre-execution proof, experimentally testing every candidate, running every validation, or proving final task success; genuinely execution-dependent outcomes may remain for implementation and validation.""",
    ),
    QuestionnaireSection(
        "Prior-cycle reassessment",
        """Considering all prior cycles and the current repository state, what prior findings, assumptions, decisions, and implemented directions remain valid for solving the unresolved original Task to Solve, and what should be reconsidered or discarded?

Audit all relevant accumulated history as claims against current repository state, repository files and relationships, objective command evidence, deterministic validation evidence, and other permitted authoritative sources. Identify: supported conclusions and their evidence; claims that remain unverified and uncertain; contradicted, insufficiently supported, incomplete, or obsolete reasoning; prior implementation actually present and useful; directions that should no longer constrain selection; material information or solutions prior cycles may have missed; and everything unresolved against the original Task. Do not claim verification not performed, automatically continue a prior direction, or discard useful work merely because validation did not establish complete success.""",
        after_cycle_one=True,
    ),
    QuestionnaireSection(
        "Project-applicable engineering synthesis and high-level solution space",
        """Given the established problem, constraints, evidence, and remaining uncertainty, what engineering synthesis applies to this project, and what high-level solution space follows?

Identify only the engineering principles, established practices, ownership or control boundaries, architectural relationships, support or compatibility boundaries, and other considerations that materially shape this decision. Explain why the rationale behind each consideration matters to this problem and project; do not invoke a generic `best practice` as an unconditional rule. Use project architecture, ownership and control evidence, constraints, current authoritative technical information when material, and repository or experimental evidence to determine whether a generally applicable consideration should be retained as-is, adapted, rejected for this project, or left uncertain. Current external evidence may establish what options and documented properties currently exist, while repository and execution evidence establish what applies to and happens in this project. The newest option is not automatically correct.

From that synthesis, derive the materially distinct high-level solution approaches reasonably supported by the evidence. Q2's evidence record is the evidentiary boundary for this synthesis; do not invent missing support here. Finding one credible or workable mechanism is not sufficient reason to stop exploration when the evidence suggests other materially distinct intervention mechanisms. Distinguish approach viability from preference: do not eliminate an approach merely because another already appears preferable, because relative preference does not establish non-viability. Uncertainty is not evidence. Do not materially eliminate a plausible approach when the deciding reason is an unsupported expectation, convention, potentially stale prior, unresolved assumption, or absence of evidence; preserve its unresolved viability instead. An approach may be eliminated when observed task, repository, or execution evidence, current authoritative information, or a hard task constraint materially establishes that it is unavailable, inapplicable, infeasible, contradicted, constraint-conflicting, or incapable of satisfying the task or providing valid constraint-compliant partial progress. Record evidence-based elimination or unresolved viability when material. Discovering an apparently appropriate control point does not by itself complete exploration.

Keep the synthesis proportional and decision-relevant. A simple isolated problem may require only a short synthesis and one supported high-level approach; a complex project-level problem may retain several. There is no required approach count, and one high-level approach is valid when evidence eliminates the others. Do not manufacture approaches. Do not repeat the investigation log, list generic practices without project-specific rationale, exhaustively catalog theoretical solutions, specify exact file, version, or configuration edits, provide an implementation plan or candidate-level validation, compare concrete candidates, select a solution, or expose private chain-of-thought.""",
    ),
    QuestionnaireSection(
        "Concrete candidate solutions",
        """What concrete solutions translate the surviving high-level approaches into specific implementable changes? Include only evidence-supported, constraint-compliant candidates. Form candidates only from decision-relevant investigation actually performed, evidence actually obtained, and the project-applicable synthesis above. Planned investigation or general technical plausibility alone does not establish repository-specific applicability or viability. Apply the investigation boundary above: do not defer a decision-critical, reasonably testable repository-specific premise until implementation and still treat the candidate as sufficiently supported for selection or COMPLETE classification. If sufficient evidence for such a premise cannot reasonably be obtained, preserve the premise and high-level approach as unresolved; do not promote the premise into candidate support, and do not treat the unresolved premise as evidence that the approach is non-viable.

Candidate count is the result of investigation and synthesis, not a target that determines their breadth. When several materially distinct high-level approaches remain viable, evidence-supported, capable of satisfying the task or providing valid constraint-compliant partial progress, and hard-constraint admissible, preserve them as separate concrete candidates when appropriate, even when another candidate already appears preferable. If only one viable candidate remains after evidence-based approach elimination, one candidate is valid. Do not repeat high-level approach-elimination reasoning here unless it is necessary to explain a candidate-specific admissibility decision. Relative engineering preference alone is not an elimination reason. Never manufacture alternatives merely to satisfy a count.

Hard constraints are mandatory candidate-admissibility conditions, not preferences to balance against engineering benefits. For each proposed mechanism, first establish its constraint-relevant properties from the Task to Solve and available repository, tool, and execution evidence; then reconcile those properties against every applicable hard requirement and constraint. Only candidates with hard-constraint compatibility established sufficiently for selection are admissible for COMPLETE or PARTIAL classification and engineering comparison. An established conflict makes a mechanism ineligible for selection or implementation. Materially unresolved hard-constraint compatibility makes it not yet admissible and requires further investigation before selection. Neither an assumption nor a different description, interpretation, or rationale for the same established operation can waive a hard constraint or make it admissible.

A constraint-conflicting mechanism may still be investigated and recorded as eliminated; investigation is not restricted to admissible solutions. Once the conflict is established, do not promote that mechanism into a selectable candidate. PARTIAL is not a mechanism for bypassing unresolved hard-constraint compliance; it remains valid for safe, evidence-supported, constraint-compliant progress with unresolved completeness, remaining work, or ordinary execution-dependent uncertainty.

For each candidate use `#### Candidate Solution <identifier> — <specific solution name>` followed by this table:

| Question | Model answer |
|---|---|
| What exact solution is proposed? | <answer> |
| Why were these exact changes selected? | <answer> |
| What evidence supports the expected result? | <answer> |
| Which parts of the problem will it resolve? | <answer> |
| Does it satisfy every applicable requirement? | <answer> |
| How will it be implemented? | <ordered directional sequence> |
| How will compatibility be preserved? | <answer> |
| Why is the result coherent and maintainable? | <answer> |
| What risks or unknowns remain? | <answer> |
| How will the result be validated? | <answer> |
| Is it a COMPLETE or PARTIAL solution? | <classification and justification> |

A PARTIAL candidate is valid only when no supported COMPLETE solution is available, it violates no constraint, provides safe measurable progress, preserves a route to completion, and identifies unresolved work.""",
    ),
    QuestionnaireSection(
        "Selected solution",
        """Which solution is selected, and why is it preferred?

Use these fields: `Selected solution:`, `Classification:`, `Why it is preferred:`, `Comparative coverage:`, `Remaining risks:`, and `Evidence requiring reconsideration:`. Reference a submitted candidate and classify it COMPLETE or PARTIAL. Confirm hard-constraint admissibility before applying preference. Compare the surviving admissible candidates using current evidence, complete-problem coverage, compatibility, coherence, maintainability, scope, and risk—not speed, ease, or prior investment. Apply these engineering preferences here, after candidate formation; do not use them to retroactively exclude a viable candidate. These qualities cannot outweigh a hard-constraint conflict. Do not select a candidate with an established hard-requirement or hard-constraint conflict, or one whose compliance remains materially unresolved or depends on an assumption, regardless of whether it is labeled COMPLETE or PARTIAL. Ordinary execution-dependent results that do not determine hard-constraint compliance may remain for implementation, self-validation, and deterministic validation. Do not repeat the full implementation sequence. The implementation intent is directional and may be materially reassessed during this cycle when new evidence warrants it.""",
    ),
)
OUTCOME_QUESTIONNAIRE = (
    QuestionnaireSection(
        "Implementation Result",
        "What was actually implemented during this cycle, and what did your self-validation establish against the Task to Solve, including its success criteria and constraints? If no solution or only a partial solution was implemented, state that explicitly and identify what remains unresolved or unverified.",
    ),
    QuestionnaireSection(
        "Cycle Intent vs. Implementation",
        "Did the implemented solution materially differ from the selected strategy recorded in the Cycle Intent? If yes, what changed, what evidence or findings discovered during implementation led to the material reassessment, and why was the resulting strategy or solution selected? If there was no material change from the Cycle Intent, state that directly.",
    ),
    QuestionnaireSection(
        "Implementation Trail",
        "What was the actual sequence of material implementation and investigation actions from the Cycle Intent through self-validation?",
    ),
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

PRELIMINARY_CONTRACT_DESCRIPTION = (
    "Initial run configuration captured before repository preparation and baseline discovery are complete. "
    "It records the task inputs, configured constraints, budgets, commands, completion criteria, and other "
    "information known when the run begins. Information that depends on repository preparation or baseline "
    "discovery may still be unavailable or preliminary."
)
BASELINE_CONTRACT_DESCRIPTION = (
    "Authoritative run starting state established after repository preparation and baseline discovery. It "
    "records the prepared source/reference, repository baseline, initial findings, and other resolved run "
    "information used to construct the canonical Task to Solve and evaluate subsequent changes."
)

INTENT_CAPTURE_FAILURE_MESSAGE = (
    "The required Cycle Intent was not successfully captured within the allowed retry attempts."
)
IMPLEMENTATION_NOT_EXECUTED_MESSAGE = (
    "Implementation was not executed because the required Cycle Intent was not successfully captured."
)
OUTCOME_NOT_REQUESTED_MESSAGE = (
    "Cycle Outcome was not requested because implementation was not executed."
)
OUTCOME_CAPTURE_FAILURE_MESSAGE = (
    "The required Cycle Outcome was not successfully captured within the allowed retry attempts."
)


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
    intent_capture_status: CheckpointCaptureStatus = CheckpointCaptureStatus.PENDING
    implementation_status: ImplementationStatus = ImplementationStatus.PENDING
    outcome_capture_status: CheckpointCaptureStatus = CheckpointCaptureStatus.PENDING

    @property
    def status(self) -> CaptureStatus:
        if self.intent and self.outcome:
            return CaptureStatus.LATE if self.late_intent else CaptureStatus.COMPLETE
        if self.intent or self.outcome or self.capture_recovery_required:
            return CaptureStatus.INCOMPLETE
        return CaptureStatus.MISSING

    @property
    def capture_recovery_required(self) -> bool:
        return (
            self.intent_capture_status == CheckpointCaptureStatus.FAILED
            or self.outcome_capture_status == CheckpointCaptureStatus.FAILED
        )

    def lifecycle_state(self, cycle: int) -> dict[str, Any]:
        intent_sections = (*INTENT_SECTIONS, *PRIOR_CYCLE_INTENT_SECTIONS) if cycle > 1 else INTENT_SECTIONS
        intent_reason = (
            "Cycle Intent capture failed."
            if self.intent_capture_status == CheckpointCaptureStatus.FAILED
            else None
        )
        outcome_reason = (
            "Cycle Outcome capture failed."
            if self.outcome_capture_status == CheckpointCaptureStatus.FAILED
            else "Cycle Outcome was not requested."
            if self.outcome_capture_status == CheckpointCaptureStatus.NOT_REQUESTED
            else None
        )
        return {
            "intent": {
                "status": self.intent_capture_status.value,
                "message": INTENT_CAPTURE_FAILURE_MESSAGE if intent_reason else None,
                "answers": _answer_capture_states(intent_sections, self.intent is not None, intent_reason),
            },
            "implementation": {
                "status": self.implementation_status.value,
                "message": (
                    IMPLEMENTATION_NOT_EXECUTED_MESSAGE
                    if self.implementation_status == ImplementationStatus.NOT_EXECUTED
                    else None
                ),
            },
            "outcome": {
                "status": self.outcome_capture_status.value,
                "message": (
                    OUTCOME_CAPTURE_FAILURE_MESSAGE
                    if self.outcome_capture_status == CheckpointCaptureStatus.FAILED
                    else OUTCOME_NOT_REQUESTED_MESSAGE
                    if self.outcome_capture_status == CheckpointCaptureStatus.NOT_REQUESTED
                    else None
                ),
                "answers": _answer_capture_states(OUTCOME_SECTIONS, self.outcome is not None, outcome_reason),
            },
        }


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
        max_checkpoint_attempts: int = 10,
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
        self.task_to_solve = ""
        self.store.initialize(render_run_contract(run_contract, preliminary=preliminary_contract))
        self._repository_changed = repository_changed

    def append_baseline_contract(self, run_contract: str) -> JournalSection:
        if self.cycles:
            raise RuntimeError("Baseline Contract must precede remediation cycles")
        return self.store.append(
            "baseline_contract",
            None,
            "# Baseline Contract\n\n"
            f"> {BASELINE_CONTRACT_DESCRIPTION}\n\n"
            + run_contract.strip(),
        )

    def append_task_to_solve(self, task_to_solve: str) -> JournalSection:
        if self.cycles:
            raise RuntimeError("Task to Solve must precede remediation cycles")
        if self.task_to_solve:
            raise RuntimeError("Task to Solve has already been established")
        self.task_to_solve = task_to_solve.strip()
        return self.store.append("task_to_solve", None, self.task_to_solve)

    def set_repository_changed_probe(self, repository_changed: Callable[[], bool]) -> None:
        self._repository_changed = repository_changed

    @property
    def run_capture_status(self) -> CaptureStatus:
        return self.run_capture_status_for()

    def run_capture_status_for(
        self, final_validation: ValidationReport | None = None
    ) -> CaptureStatus:
        if not self.cycles:
            return CaptureStatus.MISSING
        trust = {
            CaptureStatus.MISSING: 0,
            CaptureStatus.INCOMPLETE: 1,
            CaptureStatus.LATE: 2,
            CaptureStatus.COMPLETE: 3,
        }
        historical_status = min(
            (capture.status for capture in self.cycles.values()), key=trust.__getitem__
        )
        if historical_status == CaptureStatus.COMPLETE:
            return historical_status

        latest_cycle = max(self.cycles)
        latest_capture = self.cycles[latest_cycle]
        validation = final_validation or latest_capture.validation_report
        if (
            latest_capture.status != CaptureStatus.COMPLETE
            or validation is None
            or validation.cycle != latest_cycle
            or not validation.passed
        ):
            return historical_status

        earlier_captures = (
            self.cycles[cycle] for cycle in sorted(self.cycles) if cycle < latest_cycle
        )
        if all(
            capture.capture_recovery_required and capture.validation_report is not None
            for capture in earlier_captures
        ):
            return CaptureStatus.COMPLETE
        return historical_status

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
        capture = self.cycles.get(cycle)
        errors = self._checkpoint_errors("intent", cycle, answers, capture)
        if cycle > 1:
            errors.extend(self._missing_sections(answers, PRIOR_CYCLE_INTENT_SECTIONS))
        if errors:
            return self._reject("intent", cycle, errors, self._rejection_capture(cycle))
        if capture is None:
            raise RuntimeError(f"Cycle {cycle} was not begun")
        late = self._repository_changed()
        errors.extend(_intent_structure_errors(answers))
        rendered = render_checkpoint(cycle, "Problem Analysis and Solution Decision", answers)
        errors.extend(
            validate_rendered_markdown(
                rendered,
                f"Cycle {cycle} — Problem Analysis and Solution Decision",
            )
        )
        if errors:
            return self._reject("intent", cycle, errors, capture)
        capture.intent = self.store.append("intent", cycle, rendered)
        capture.intent_answers = {
            str(item["section"]).strip(): str(item["answer"]).strip() for item in answers
        }
        capture.intent_capture_status = CheckpointCaptureStatus.CAPTURED
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
        capture = self._require_active_capture(self.active_cycle)
        capture.implementation_status = ImplementationStatus.EXECUTED
        self.phase = JournalPhase.OUTCOME_REQUIRED
        self.trace.append_event("journal_phase_changed", cycle=self.active_cycle, phase=self.phase.value)

    def fail_intent_capture(self, cycle: int) -> None:
        capture = self._require_active_capture(cycle)
        if capture.intent is not None:
            raise RuntimeError(f"Cycle {cycle} intent has already been accepted")
        capture.intent_capture_status = CheckpointCaptureStatus.FAILED
        capture.implementation_status = ImplementationStatus.NOT_EXECUTED
        capture.outcome_capture_status = CheckpointCaptureStatus.NOT_REQUESTED
        self.phase = JournalPhase.DETERMINISTIC_VALIDATION
        self.trace.append_event(
            "intent_capture_failed",
            cycle=cycle,
            message=INTENT_CAPTURE_FAILURE_MESSAGE,
        )
        self.trace.append_event(
            "journal_phase_changed", cycle=cycle, phase=self.phase.value
        )

    def fail_outcome_capture(self, cycle: int) -> None:
        capture = self._require_active_capture(cycle)
        if capture.outcome is not None:
            raise RuntimeError(f"Cycle {cycle} outcome has already been accepted")
        capture.outcome_capture_status = CheckpointCaptureStatus.FAILED
        self.phase = JournalPhase.DETERMINISTIC_VALIDATION
        self.trace.append_event(
            "outcome_capture_failed",
            cycle=cycle,
            message=OUTCOME_CAPTURE_FAILURE_MESSAGE,
        )
        self.trace.append_event(
            "journal_phase_changed", cycle=cycle, phase=self.phase.value
        )

    def submit_outcome(
        self,
        cycle: int,
        status: str,
        status_explanation: str,
        answers: list[dict[str, str]],
    ) -> CheckpointResult:
        capture = self.cycles.get(cycle)
        normalized_status = status.strip().upper()
        errors = self._checkpoint_errors("outcome", cycle, answers, capture)
        if normalized_status not in OUTCOME_STATUSES:
            errors.append(f"Invalid Cycle Outcome status: {status}")
        errors.extend(_answer_errors("Cycle outcome status", status_explanation, self.max_section_chars))
        if errors:
            return self._reject("outcome", cycle, errors, self._rejection_capture(cycle))
        if capture is None:
            raise RuntimeError(f"Cycle {cycle} was not begun")
        all_answers = [
            {"section": "Cycle outcome status", "answer": f"`{normalized_status}`\n\n{status_explanation.strip()}"},
            *answers,
        ]
        rendered = render_checkpoint(cycle, "Outcome", all_answers)
        errors.extend(validate_rendered_markdown(rendered, f"Cycle {cycle} — Outcome"))
        if errors:
            return self._reject("outcome", cycle, errors, capture)
        capture.outcome = self.store.append("outcome", cycle, rendered)
        capture.outcome_answers = {
            str(item["section"]).strip(): str(item["answer"]).strip() for item in answers
        }
        capture.outcome_capture_status = CheckpointCaptureStatus.CAPTURED
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
        capture = self._require_active_capture(report.cycle)
        rendered = render_validation(report, status, delivery, capture.outcome_status, capture)
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

    def cycle_state(self, cycle: int) -> dict[str, Any]:
        capture = self.cycles.get(cycle)
        return (capture or CycleCapture()).lifecycle_state(cycle)

    def _require_active_capture(self, cycle: int) -> CycleCapture:
        if cycle != self.active_cycle:
            raise RuntimeError(f"Expected active cycle {self.active_cycle}, received {cycle}")
        capture = self.cycles.get(cycle)
        if capture is None:
            raise RuntimeError(f"Cycle {cycle} was not begun")
        return capture

    def _rejection_capture(self, requested_cycle: int) -> CycleCapture | None:
        if requested_cycle == self.active_cycle:
            return self.cycles.get(requested_cycle)
        return self.cycles.get(self.active_cycle)

    def context(self) -> str:
        content = self.store.read()
        if len(content) <= self.max_context_chars:
            return content
        marker = "\n\n[Earlier journal content bounded for model input]\n\n"
        run_sections = [
            section
            for section in self.store.sections
            if section.kind in {"run_contract", "baseline_contract", "task_to_solve"}
        ]
        cycle_sections = [
            section
            for section in self.store.sections
            if section.kind not in {"run_contract", "baseline_contract", "task_to_solve"}
        ]
        available = max(0, self.max_context_chars - len(marker))
        run_size = sum(len(self._section_text(item)) for item in run_sections)
        run_budget = min(available * 2 // 3, run_size)
        if cycle_sections:
            run_budget = min(run_budget, max(0, available - len(cycle_sections) * 40))
        cycle_budget = max(0, available - run_budget)
        bounded = (
            _bounded_sections(
                [(item.kind, self._section_text(item)) for item in run_sections],
                run_budget,
                preserve_kind="task_to_solve",
            )
            + marker
            + _bounded_sections(
                [(item.kind, self._section_text(item)) for item in cycle_sections],
                cycle_budget,
            )
        )
        return bounded[: self.max_context_chars]

    def _section_text(self, section: JournalSection) -> str:
        data = self.store.path.read_bytes()[section.start_offset : section.end_offset]
        return data.decode("utf-8").rstrip()

    def _checkpoint_errors(
        self,
        kind: str,
        cycle: int,
        answers: list[dict[str, str]],
        capture: CycleCapture | None,
    ) -> list[str]:
        errors: list[str] = []
        attempts = (
            capture.rejected_intents
            if capture is not None and kind == "intent"
            else capture.rejected_outcomes
            if capture is not None
            else 0
        )
        if attempts >= self.max_checkpoint_attempts:
            errors.append(f"Cycle {cycle} {kind} retry limit is exhausted")
        if cycle != self.active_cycle:
            errors.append(f"Expected active cycle {self.active_cycle}, received {cycle}")
        if capture is None:
            errors.append(f"Cycle {cycle} was not begun")
        expected_phase = JournalPhase.INTENT_REQUIRED if kind == "intent" else JournalPhase.OUTCOME_REQUIRED
        if self.phase != expected_phase:
            errors.append(f"Expected phase {expected_phase.value}, current phase is {self.phase.value}")
        existing = capture.intent if capture is not None and kind == "intent" else (
            capture.outcome if capture is not None else None
        )
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

    def _reject(
        self,
        kind: str,
        cycle: int,
        errors: list[str],
        capture: CycleCapture | None,
    ) -> CheckpointResult:
        if capture is not None and kind == "intent":
            capture.rejected_intents += 1
            capture.last_intent_errors = tuple(errors)
            attempt = capture.rejected_intents
        elif capture is not None:
            capture.rejected_outcomes += 1
            capture.last_outcome_errors = tuple(errors)
            attempt = capture.rejected_outcomes
        else:
            attempt = 1
        self.trace.append_event(
            f"{kind}_submission_rejected",
            cycle=cycle,
            activeCycle=self.active_cycle,
            attempt=attempt,
            retryAllowed=attempt < self.max_checkpoint_attempts,
            errors=errors,
        )
        return CheckpointResult(False, tuple(errors))


def render_run_contract(run_contract: str, *, preliminary: bool = False) -> str:
    title = "Preliminary Run Contract" if preliminary else "Run Contract"
    description = f"> {PRELIMINARY_CONTRACT_DESCRIPTION}\n\n" if preliminary else ""
    return f"# {title}\n\n" + description + run_contract.strip()


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
        "Use the isolated cycle experiment for decision-relevant investigation before submission. Treat the original Task to Solve as authoritative; "
        "distinguish established information, assumptions, uncertainty, and execution-dependent evidence. Verify "
        "avoidable decision-critical uncertainty where reasonably feasible. The ordered answers describe the final pre-selection decision state, not a rigid reasoning waterfall; investigation may revise problem understanding, applicable engineering considerations, or the solution space before submission. Candidate count must result from "
        "investigation and synthesis: preserve multiple genuinely supported candidates, while "
        "one candidate remains valid when only one survives; never manufacture alternatives. The selected solution is directional rather "
        "than immutable and may be materially reassessed during implementation. You may add clearly named, "
        "decision-relevant sections after all required sections."
    )
    return _render_questionnaire(
        "Problem Analysis and Solution Decision questionnaire",
        sections,
        rules,
    )


def outcome_questionnaire() -> str:
    statuses = ", ".join(f"`{status}`" for status in sorted(OUTCOME_STATUSES))
    rules = (
        "Use these exact section names as `section` values in `submit_cycle_outcome`. "
        f"Allowed `status` values: {statuses}. Report only what actually occurred; do not invent actions, evidence, "
        "attempts, reassessment, or validation. Distinguish observed facts, self-validation, uncertainty, and "
        "unverified expectations. Scope every self-validation claim to the properties its underlying check actually "
        "evaluated; a successful check does not establish a requirement, success criterion, constraint, or outcome "
        "that it did not evaluate, so keep that coverage unresolved or unverified. Include material unsuccessful or "
        "reverted work only when it actually influenced "
        "the result. Do not manufacture a reassessment merely because implementation differed. Report applicable "
        "Task-to-Solve and constraint coverage as satisfied, not satisfied, unresolved, or unverified. "
        "In Implementation Result, capture the actual final repository approach, requirement coverage, constraints, "
        "compatibility or regression implications, actual self-validation, unresolved or unverified coverage, and "
        "partial, blocked, failed, inconclusive, or no-change state when applicable. In Cycle Intent vs. "
        "Implementation, capture material deviations, causal evidence, materially attempted or reverted approaches, "
        "material assumption changes, the resulting strategy, and why it was selected when those events occurred. "
        "In Implementation Trail, chronologically capture material implementation and investigation actions, observed "
        "evidence, influential unsuccessful attempts, reassessment points, resulting changes, and self-validation. "
        "Self-validation is not authoritative deterministic validation. You may add clearly named, "
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


def _intent_structure_errors(answers: list[dict[str, str]]) -> list[str]:
    by_section = {
        str(item.get("section", "")).strip(): str(item.get("answer", ""))
        for item in answers
    }
    errors: list[str] = []
    investigation = by_section.get("Information, investigation and remaining uncertainty", "")
    required_columns = (
        "Information needed",
        "Why it was needed",
        "Sources examined",
        "Finding",
        "What remains unknown or requires execution",
    )
    if investigation and not all(column in investigation for column in required_columns):
        errors.append(
            "Information, investigation and remaining uncertainty: required evidence table columns are missing"
        )
    if investigation and len([line for line in investigation.splitlines() if line.lstrip().startswith("|")]) < 3:
        errors.append(
            "Information, investigation and remaining uncertainty: required evidence table needs at least one information row"
        )
    if investigation and "Material assumptions that remain necessary" not in investigation:
        errors.append(
            "Information, investigation and remaining uncertainty: required material-assumptions subsection is missing"
        )

    candidates = by_section.get("Concrete candidate solutions", "")
    candidate_pattern = re.compile(
        r"^####\s+Candidate Solution\s+([A-Za-z0-9_-]+)\s+[—-]\s+(.+)$",
        flags=re.MULTILINE,
    )
    candidate_matches = list(candidate_pattern.finditer(candidates))
    candidate_ids = [match.group(1) for match in candidate_matches]
    if candidates and not candidate_ids:
        errors.append(
            "Concrete candidate solutions: at least one '#### Candidate Solution <identifier> — <name>' heading is required"
        )
    candidate_fields = (
        "What exact solution is proposed?",
        "Why were these exact changes selected?",
        "What evidence supports the expected result?",
        "Which parts of the problem will it resolve?",
        "Does it satisfy every applicable requirement?",
        "How will it be implemented?",
        "How will compatibility be preserved?",
        "Why is the result coherent and maintainable?",
        "What risks or unknowns remain?",
        "How will the result be validated?",
        "Is it a COMPLETE or PARTIAL solution?",
    )
    if candidate_matches:
        for index, match in enumerate(candidate_matches):
            end = candidate_matches[index + 1].start() if index + 1 < len(candidate_matches) else len(candidates)
            candidate = candidates[match.end() : end]
            for field_name in candidate_fields:
                if field_name in candidate:
                    continue
                errors.append(
                    f"Concrete candidate solutions: Candidate {match.group(1)} is missing field: {field_name}"
                )
            if not re.search(r"\b(?:COMPLETE|PARTIAL)\b", candidate):
                errors.append(
                    f"Concrete candidate solutions: Candidate {match.group(1)} requires COMPLETE or PARTIAL classification"
                )

    selected = by_section.get("Selected solution", "")
    selected_fields = (
        "Selected solution:",
        "Classification:",
        "Why it is preferred:",
        "Comparative coverage:",
        "Remaining risks:",
        "Evidence requiring reconsideration:",
    )
    if selected:
        for field_name in selected_fields:
            if field_name not in selected:
                errors.append(f"Selected solution: required field is missing: {field_name}")
        if not re.search(r"\b(?:COMPLETE|PARTIAL)\b", selected):
            errors.append("Selected solution: classification must be COMPLETE or PARTIAL")
        selected_line = next(
            (line for line in selected.splitlines() if "Selected solution:" in line),
            "",
        )
        if candidate_ids and not any(
            re.search(rf"\b{re.escape(identifier)}\b", selected_line)
            for identifier in candidate_ids
        ):
            errors.append("Selected solution: selected candidate must reference a submitted candidate identifier")
    return errors


def _bounded_sections(
    sections: list[tuple[str, str]],
    budget: int,
    *,
    preserve_kind: str | None = None,
) -> str:
    if budget <= 0 or not sections:
        return ""
    joined = "\n\n".join(content for _, content in sections)
    if len(joined) <= budget:
        return joined
    separator_cost = 2 * (len(sections) - 1)
    usable = max(0, budget - separator_cost)
    minimum = min(120, usable // len(sections))
    allocations = [minimum for _ in sections]
    remaining = usable - sum(allocations)
    if preserve_kind is not None:
        for index, (kind, content) in enumerate(sections):
            if kind != preserve_kind:
                continue
            needed = max(0, len(content) - allocations[index])
            granted = min(needed, remaining)
            allocations[index] += granted
            remaining -= granted
            break
    index = 0
    while remaining > 0 and sections:
        room = len(sections[index][1]) - allocations[index]
        if room > 0:
            granted = min(room, max(1, remaining // len(sections)))
            allocations[index] += granted
            remaining -= granted
        index = (index + 1) % len(sections)
        if all(len(content) <= allocations[position] for position, (_, content) in enumerate(sections)):
            break
    return "\n\n".join(
        _bounded_excerpt(content, allocation)
        for (_, content), allocation in zip(sections, allocations)
        if allocation > 0
    )


def _bounded_excerpt(content: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    marker = "\n[... section content bounded ...]\n"
    if limit <= len(marker) + 20:
        return content[:limit]
    head = (limit - len(marker)) * 2 // 3
    tail = limit - len(marker) - head
    return content[:head].rstrip() + marker + content[-tail:].lstrip()


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


def _answer_capture_states(
    sections: Iterable[str],
    captured: bool,
    reason: str | None,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for section in sections:
        state = {"status": "CAPTURED" if captured else "NOT_CAPTURED"}
        if not captured and reason:
            state["reason"] = reason
        result[section] = state
    return result


def _render_cycle_lifecycle_state(capture: CycleCapture, cycle: int) -> list[str]:
    state = capture.lifecycle_state(cycle)
    lines: list[str] = []
    for label, key in (
        ("Cycle Intent", "intent"),
        ("Implementation", "implementation"),
        ("Cycle Outcome", "outcome"),
    ):
        item = state[key]
        suffix = f" — {item['message']}" if item.get("message") else ""
        lines.append(f"- **{label}:** `{item['status']}`{suffix}")
    for label, key in (
        ("Cycle Intent questionnaire answers", "intent"),
        ("Cycle Outcome questionnaire answers", "outcome"),
    ):
        if all(item["status"] == "CAPTURED" for item in state[key]["answers"].values()):
            continue
        lines.extend(("", f"### {label}", ""))
        for section, answer_state in state[key]["answers"].items():
            suffix = f" — {answer_state['reason']}" if answer_state.get("reason") else ""
            lines.append(f"- **{section}:** `{answer_state['status']}`{suffix}")
    return lines


def render_validation(
    report: ValidationReport,
    status: ValidationStatus,
    delivery: DeliveryEligibility,
    outcome_status: str | None,
    capture: CycleCapture,
) -> str:
    failed = [check for check in report.checks if not check.passed]
    passed = [check for check in report.checks if check.passed]
    diagnostics = list(report.diagnostic_artifacts)
    lines = [
        f"# Cycle {report.cycle} — Deterministic Validation",
        "",
        "## Cycle lifecycle state",
        "",
        *_render_cycle_lifecycle_state(capture, report.cycle),
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
            (
                "A later cycle may reassess the current validated repository state and complete its own required checkpoints; checkpoint failure alone does not require another repository change."
                if report.passed and capture.capture_recovery_required
                else "Not applicable."
                if report.passed
                else "Address failed checks and unresolved requirements without replacing the original run contract."
            ),
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
    implementation_result = latest_answers.get("Implementation Result", "")
    partial = (
        f"Preserved changes require manual review. Unresolved deterministic checks: {', '.join(unresolved) or 'none identified'}."
        if outcome == RemediationOutcome.PARTIALLY_REMEDIATED
        else "Not applicable."
    )
    original_problem_display = (
        "The canonical Task to Solve recorded earlier in this journal remains the original run-level problem contract."
        if original_problem.lstrip().startswith("# Task to Solve")
        else original_problem
    )
    return f"""# Final Resolution

## Final outcome

{outcome.value}

## Original problem

{original_problem_display}

## Final interpreted resolution

Deterministic validation status and capture quality are reported separately. Run-level capture status: `{capture_status.value}`.

## Final implemented approach

{implementation_result or 'No accepted Cycle Outcome described the implementation result.'}

## How the approach evolved

{_approach_evolution(cycles)}

## Final requirement coverage

### Satisfied

{_bullets(satisfied)}

- Model-reported coverage remains part of the accepted Implementation Result; only explicitly mapped deterministic checks are authoritative.

### Conditional

- Any model-reported conditional or unverified coverage remains non-authoritative pending deterministic evidence.

### Unresolved

{_bullets(unresolved)}

### Not applicable

- None established beyond the accepted model report and deterministic checks.

## Final evidence

{evidence or '- Deterministic validation did not run.'}

## Constraints and known risks

Run-level capture quality `{capture_status.value}`; delivery eligibility `{delivery.value}`.

Model-reported constraint, compatibility, regression, and risk information remains in the accepted Implementation Result above; deterministic checks remain authoritative within their stated scope.

## Partial-remediation disclosure

{partial}

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
        selected = _captured_answer_or_state(capture, cycle, "intent", "Selected solution")
        final = _captured_answer_or_state(capture, cycle, "outcome", "Implementation Result")
        deviations = _captured_answer_or_state(
            capture, cycle, "outcome", "Cycle Intent vs. Implementation"
        )
        trail = _captured_answer_or_state(capture, cycle, "outcome", "Implementation Trail")
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
                f"- **Cycle {cycle} implementation trail:** {_inline(trail)}",
                f"- **Cycle {cycle} validation learning:** {learning}.",
            )
        )
    return "\n".join(lines)


def _captured_answer_or_state(
    capture: CycleCapture,
    cycle: int,
    checkpoint: str,
    section: str,
) -> str:
    answers = capture.intent_answers if checkpoint == "intent" else capture.outcome_answers
    if section in answers:
        return answers[section]
    state = capture.lifecycle_state(cycle)[checkpoint]["answers"][section]
    reason = state.get("reason")
    return f"{state['status']} — {reason}" if reason else state["status"]


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
