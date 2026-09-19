from __future__ import annotations

from typing import Any

from google.adk.tools.function_tool import FunctionTool

from ..journal import JournalLifecycle, JournalPhase
from ..workspace import TraceStore
from .execution import BudgetExceeded, ExecutionBudget, ProcessRunner
from .workspace_io import WorkspaceIO


class DeveloperCapabilitySet:
    def __init__(
        self,
        workspace_io: WorkspaceIO,
        process_runner: ProcessRunner,
        budget: ExecutionBudget,
        trace: TraceStore,
        journal: JournalLifecycle | None = None,
    ):
        self.workspace_io = workspace_io
        self.process_runner = process_runner
        self.budget = budget
        self.trace = trace
        self.journal = journal

    def read_workspace_text(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
        """Read a bounded UTF-8 text range from a repository-relative path."""
        denied = self._require_phase("read_workspace_text", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        return self._invoke("read_workspace_text", self.workspace_io.read_text, path, start_line, end_line)

    def list_workspace_files(self, path: str = ".", max_entries: int = 500) -> dict[str, Any]:
        """List repository-relative files for read-only discovery."""
        denied = self._require_phase("list_workspace_files", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        return self._invoke("list_workspace_files", self.workspace_io.list_files, path, max_entries)

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
        denied = self._require_phase("edit_workspace_text", {JournalPhase.EXECUTION})
        if denied:
            return denied
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
        denied = self._require_phase("run_workspace_shell", {JournalPhase.EXECUTION})
        if denied:
            return denied
        result = self._invoke(
            "run_workspace_shell",
            self.process_runner.run_agent_shell,
            command,
            cwd,
            timeout_seconds,
        )
        return result.to_dict() if hasattr(result, "to_dict") else result

    def submit_cycle_intent(self, cycle_number: int, answers: list[dict[str, str]]) -> dict[str, Any]:
        """Submit the required metadata-only Cycle Intent before material mutation."""
        if not self.journal:
            return self._unavailable("submit_cycle_intent", "Journal lifecycle is not configured")
        return self.journal.submit_intent(cycle_number, answers).to_dict()

    def submit_cycle_outcome(
        self,
        cycle_number: int,
        status: str,
        status_explanation: str,
        answers: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Submit the required metadata-only Cycle Outcome after execution."""
        if not self.journal:
            return self._unavailable("submit_cycle_outcome", "Journal lifecycle is not configured")
        return self.journal.submit_outcome(cycle_number, status, status_explanation, answers).to_dict()

    def adk_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(self.read_workspace_text),
            FunctionTool(self.list_workspace_files),
            FunctionTool(self.edit_workspace_text),
            FunctionTool(self.run_workspace_shell),
            FunctionTool(self.submit_cycle_intent),
            FunctionTool(self.submit_cycle_outcome),
        ]

    def available_tool_names(self) -> frozenset[str]:
        if not self.journal:
            return frozenset({"read_workspace_text", "list_workspace_files", "edit_workspace_text", "run_workspace_shell"})
        by_phase = {
            JournalPhase.INTENT_REQUIRED: {"read_workspace_text", "list_workspace_files", "submit_cycle_intent"},
            JournalPhase.EXECUTION: {"read_workspace_text", "list_workspace_files", "edit_workspace_text", "run_workspace_shell"},
            JournalPhase.OUTCOME_REQUIRED: {"submit_cycle_outcome"},
        }
        return frozenset(by_phase.get(self.journal.phase, set()))

    def _require_phase(self, tool: str, phases: set[JournalPhase]) -> dict[str, Any] | None:
        if not self.journal or self.journal.phase in phases:
            return None
        return self._unavailable(
            tool,
            f"Capability unavailable during {self.journal.phase.value}; accepted checkpoint transition required",
        )

    def _unavailable(self, tool: str, reason: str) -> dict[str, Any]:
        self.trace.append_event(
            "phase_capability_rejected",
            tool=tool,
            phase=self.journal.phase.value if self.journal else None,
            reason=reason,
        )
        return {"status": "error", "error": reason, "failureCode": "PHASE_CAPABILITY_UNAVAILABLE"}

    def _invoke(self, name: str, function: Any, *args: Any) -> Any:
        try:
            self.budget.consume_tool_call()
            return function(*args)
        except BudgetExceeded as exc:
            self.trace.append_event("tool_budget_exceeded", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "EXECUTION_BUDGET_EXCEEDED"}
        except Exception as exc:
            self.trace.append_event("tool_error", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "TOOL_ERROR"}
