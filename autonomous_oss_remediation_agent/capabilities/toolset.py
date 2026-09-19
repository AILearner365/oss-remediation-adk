from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from google.adk.tools.function_tool import FunctionTool

from ..workspace import TraceStore
from .decisions import DecisionRecordingError, DecisionTracker
from .execution import BudgetExceeded, ExecutionBudget, ProcessRunner
from .workspace_io import WorkspaceIO


class DeveloperCapabilitySet:
    def __init__(
        self,
        workspace_io: WorkspaceIO,
        process_runner: ProcessRunner,
        budget: ExecutionBudget,
        trace: TraceStore,
    ):
        self.workspace_io = workspace_io
        self.process_runner = process_runner
        self.budget = budget
        self.trace = trace
        self.decisions = DecisionTracker(
            trace,
            max_decisions=max(4, budget.config.max_cycles * 4),
        )
        self._decision_reconciliation_only = False

    def read_workspace_text(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
        """Read a bounded UTF-8 text range from a repository-relative path."""
        return self._invoke("read_workspace_text", self.workspace_io.read_text, path, start_line, end_line)

    def edit_workspace_text(
        self,
        action: str,
        path: str,
        content: str | None = None,
        old_text: str | None = None,
        new_text: str | None = None,
        expected_occurrences: int = 1,
    ) -> dict[str, Any]:
        """Write, exactly replace text in, or delete a repository-relative text file."""
        result = self._invoke(
            "edit_workspace_text",
            self.workspace_io.edit_text,
            action,
            path,
            content,
            old_text,
            new_text,
            expected_occurrences,
        )
        if (
            isinstance(result, dict)
            and result.get("status") == "ok"
            and result.get("changed")
        ):
            self.decisions.note_workspace_edit(str(result["path"]))
        return result

    def run_workspace_shell(self, command: str, cwd: str = ".", timeout_seconds: int | None = None) -> dict[str, Any]:
        """Run a host-native shell command in the trusted prepared repository and return structured evidence."""
        result = self._invoke(
            "run_workspace_shell",
            self.process_runner.run_agent_shell,
            command,
            cwd,
            timeout_seconds,
        )
        return result.to_dict() if hasattr(result, "to_dict") else result

    def record_decision(
        self,
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
        """Record the complete current material decision snapshot without repository execution.

        Every call describes the complete current diagnosis, active strategy, requirement
        coverage, active assumptions, unresolved items, and self-validation status after
        applying this decision. It must not contain only the newly changed portion. The
        runtime assigns the decision ID and cycle.

        Actions mean: ``SELECT`` chooses the initial strategy; ``RETAIN`` keeps it after
        new evidence; ``EXTEND`` adds material scope while restating the complete updated
        strategy; ``REVISE`` materially changes it; ``REPLACE`` substitutes a different
        strategy; ``READY_FOR_INDEPENDENT_VALIDATION`` records complete self-validation;
        and ``BLOCK`` records a concrete blocker. Every action after ``SELECT`` follows the
        latest decision in one linear chain.

        Args:
            action: One supported action described above.
            diagnosis: Complete current diagnosis or decision subject, not only its delta.
            strategy: Complete active strategy after this decision.
            rationale: Why this strategy/action follows from the evidence; do not repeat
                evidence without explaining the engineering judgment.
            evidence: Concise observed facts supporting the decision. Evidence is what was
                observed; rationale explains why those observations justify the choice.
            coverage_satisfied: Complete set of success criteria currently satisfied,
                including applicable coverage retained from earlier decisions.
            coverage_conditional: Complete set of criteria whose satisfaction remains
                conditional.
            coverage_unresolved: Complete set of criteria still unresolved.
            assumptions: All currently active material assumptions. Each item supplies
                ``assumption``, how it will be tested in ``test``, and current ``status``.
            validation: Current self-validation plans and results. Each entry must say
                whether it is planned or observed evidence.
            previous_decision_id: Latest decision ID when explicitly linking a transition.
                Omit to let the runtime link every non-initial action to the latest decision.
            alternatives: Materially credible alternatives when they aid selection or a
                transition, with approach, classification, coverage, and gaps. Do not invent
                alternatives for final readiness or when none add value.

        Returns:
            Structured decision evidence, current projection, and non-blocking warnings.
        """
        return self._invoke_decision(
            "record_decision",
            self.decisions.record,
            action=action,
            diagnosis=diagnosis,
            strategy=strategy,
            rationale=rationale,
            evidence=evidence,
            coverage_satisfied=coverage_satisfied,
            coverage_conditional=coverage_conditional,
            coverage_unresolved=coverage_unresolved,
            assumptions=assumptions,
            validation=validation,
            previous_decision_id=previous_decision_id,
            alternatives=alternatives,
        )

    def start_cycle(self, cycle: int) -> None:
        self.decisions.start_cycle(cycle)

    @contextmanager
    def decision_reconciliation_only(self):
        previous = self._decision_reconciliation_only
        self._decision_reconciliation_only = True
        try:
            yield
        finally:
            self._decision_reconciliation_only = previous

    def adk_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(self.read_workspace_text),
            FunctionTool(self.edit_workspace_text),
            FunctionTool(self.run_workspace_shell),
            FunctionTool(self.record_decision),
        ]

    def _invoke(self, name: str, function: Any, *args: Any, **kwargs: Any) -> Any:
        if self._decision_reconciliation_only:
            error = (
                "Only record_decision is available during decision-capture reconciliation"
            )
            self.trace.append_event(
                "reconciliation_tool_blocked",
                tool=name,
                error=error,
            )
            return {
                "status": "error",
                "error": error,
                "failureCode": "DECISION_RECONCILIATION_METADATA_ONLY",
            }
        try:
            self.budget.consume_tool_call()
            return function(*args, **kwargs)
        except BudgetExceeded as exc:
            self.trace.append_event("tool_budget_exceeded", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "EXECUTION_BUDGET_EXCEEDED"}
        except Exception as exc:
            self.trace.append_event("tool_error", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "TOOL_ERROR"}

    def _invoke_decision(self, name: str, function: Any, **kwargs: Any) -> Any:
        try:
            self.budget.ensure_time_remaining()
            return function(**kwargs)
        except BudgetExceeded as exc:
            self.trace.append_event("decision_recording_rejected", tool=name, error=str(exc))
            return {
                "status": "error",
                "error": str(exc),
                "failureCode": "EXECUTION_BUDGET_EXCEEDED",
            }
        except DecisionRecordingError as exc:
            self.trace.append_event(
                "decision_recording_rejected",
                tool=name,
                error=str(exc),
                failureCode=exc.failure_code,
            )
            return {"status": "error", "error": str(exc), "failureCode": exc.failure_code}
        except Exception as exc:
            self.trace.append_event("tool_error", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "TOOL_ERROR"}
