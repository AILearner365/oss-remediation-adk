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

    def list_workspace_files(
        self,
        path: str = ".",
        max_entries: int = 500,
        cursor: str | int | None = None,
        file_glob: str | None = None,
        max_scanned_entries: int = 5_000,
    ) -> dict[str, Any]:
        """List files with bounded traversal; pass opaque `nextCursor` to continue the same query.

        `truncationReason` distinguishes an output `PAGE_LIMIT` from a traversal `SCAN_LIMIT`.
        Continuation is stable within one live cursor; cross-run lexical ordering is not guaranteed.
        """
        denied = self._require_phase("list_workspace_files", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        return self._invoke(
            "list_workspace_files",
            self.workspace_io.list_files,
            path,
            max_entries,
            cursor,
            file_glob,
            max_scanned_entries,
        )

    def search_workspace_text(
        self,
        query: str,
        path: str = ".",
        file_glob: str | None = None,
        max_results: int = 100,
        max_files: int = 5_000,
    ) -> dict[str, Any]:
        """Search bounded repository text content without invoking a shell."""
        denied = self._require_phase("search_workspace_text", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        return self._invoke(
            "search_workspace_text",
            self.workspace_io.search_text,
            query,
            path,
            file_glob,
            max_results,
            max_files,
        )

    def inspect_git_state(self, max_log_entries: int = 10) -> dict[str, Any]:
        """Inspect bounded Git status, branch, HEAD, and recent commit metadata read-only."""
        denied = self._require_phase("inspect_git_state", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        return self._invoke("inspect_git_state", self._inspect_git_state, max_log_entries)

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
        material_strategy_revision: bool = False,
    ) -> dict[str, Any]:
        """Submit the required metadata-only Cycle Outcome after execution."""
        if not self.journal:
            return self._unavailable("submit_cycle_outcome", "Journal lifecycle is not configured")
        return self.journal.submit_outcome(
            cycle_number,
            status,
            status_explanation,
            answers,
            material_strategy_revision,
        ).to_dict()

    def record_strategy_checkpoint(
        self,
        cycle_number: int,
        answers: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Record a bounded metadata-only reassessment after material strategy evidence changes."""
        if not self.journal:
            return self._unavailable(
                "record_strategy_checkpoint",
                "Journal lifecycle is not configured",
            )
        denied = self._require_phase(
            "record_strategy_checkpoint",
            {JournalPhase.EXECUTION},
        )
        if denied:
            return denied
        try:
            self.budget.ensure_time_remaining()
            return self.journal.record_strategy_checkpoint(cycle_number, answers).to_dict()
        except BudgetExceeded as exc:
            self.trace.append_event(
                "strategy_checkpoint_deadline_exceeded",
                error=str(exc),
            )
            return {
                "status": "error",
                "error": str(exc),
                "failureCode": "EXECUTION_BUDGET_EXCEEDED",
            }

    def adk_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(self.read_workspace_text),
            FunctionTool(self.list_workspace_files),
            FunctionTool(self.search_workspace_text),
            FunctionTool(self.inspect_git_state),
            FunctionTool(self.edit_workspace_text),
            FunctionTool(self.run_workspace_shell),
            FunctionTool(self.submit_cycle_intent),
            FunctionTool(self.record_strategy_checkpoint),
            FunctionTool(self.submit_cycle_outcome),
        ]

    def available_tool_names(self) -> frozenset[str]:
        if not self.journal:
            return frozenset({"read_workspace_text", "list_workspace_files", "search_workspace_text", "inspect_git_state", "edit_workspace_text", "run_workspace_shell"})
        by_phase = {
            JournalPhase.INTENT_REQUIRED: {"read_workspace_text", "list_workspace_files", "search_workspace_text", "inspect_git_state", "submit_cycle_intent"},
            JournalPhase.EXECUTION: {"read_workspace_text", "list_workspace_files", "search_workspace_text", "inspect_git_state", "edit_workspace_text", "run_workspace_shell", "record_strategy_checkpoint"},
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

    def _inspect_git_state(self, max_log_entries: int) -> dict[str, Any]:
        limit = max(1, min(max_log_entries, 50))
        commands = {
            "status": ["git", "status", "--short", "--branch"],
            "head": ["git", "rev-parse", "HEAD"],
            "branch": ["git", "branch", "--show-current"],
            "recentCommits": ["git", "log", f"-{limit}", "--oneline", "--decorate=no"],
        }
        evidence: dict[str, Any] = {"status": "ok"}
        for name, command in commands.items():
            result = self.process_runner.run_argv(
                command,
                cwd=self.workspace_io.workspace.repository,
                source=f"agent_readonly_git_{name}",
            )
            if not result.succeeded:
                return {
                    "status": "error",
                    "failureCode": "READ_ONLY_GIT_INSPECTION_FAILED",
                    "operation": name,
                    "exitCode": result.exit_code,
                    "stderrArtifact": result.stderr_artifact,
                }
            evidence[name] = result.stdout.strip()
        return evidence

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
