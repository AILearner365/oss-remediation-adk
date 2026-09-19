from __future__ import annotations

from typing import Any

from google.adk.tools.function_tool import FunctionTool

from ..workspace import TraceStore
from .decisions import DecisionTracker
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
        self.decisions = DecisionTracker(trace)

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
        return self._invoke(
            "edit_workspace_text",
            self.workspace_io.edit_text,
            action,
            path,
            content,
            old_text,
            new_text,
            expected_occurrences,
        )

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
        """Record one material engineering decision without modifying or executing the repository."""
        return self._invoke(
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

    def adk_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(self.read_workspace_text),
            FunctionTool(self.edit_workspace_text),
            FunctionTool(self.run_workspace_shell),
            FunctionTool(self.record_decision),
        ]

    def _invoke(self, name: str, function: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            self.budget.consume_tool_call()
            return function(*args, **kwargs)
        except BudgetExceeded as exc:
            self.trace.append_event("tool_budget_exceeded", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "EXECUTION_BUDGET_EXCEEDED"}
        except Exception as exc:
            self.trace.append_event("tool_error", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "TOOL_ERROR"}
