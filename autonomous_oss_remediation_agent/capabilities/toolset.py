from __future__ import annotations

from typing import Any

from google.adk.tools.function_tool import FunctionTool

from ..deterministic.scanner import VulnerabilityScanner
from ..journal import JournalLifecycle, JournalPhase
from ..workspace import RepositoryWorkspace, RunWorkspace, TraceStore
from .execution import BudgetExceeded, ExecutionBudget, ProcessRunner
from .research import HttpResearchProvider, ResearchProvider
from .workspace_io import WorkspaceIO


class DeveloperCapabilitySet:
    def __init__(
        self,
        workspace_io: WorkspaceIO,
        process_runner: ProcessRunner,
        budget: ExecutionBudget,
        trace: TraceStore,
        journal: JournalLifecycle | None = None,
        scanner: VulnerabilityScanner | None = None,
        scanner_severity_scope: tuple[str, ...] = (),
        research_provider: ResearchProvider | None = None,
    ):
        self.workspace_io = workspace_io
        self.process_runner = process_runner
        self.budget = budget
        self.trace = trace
        self.journal = journal
        self.scanner = scanner
        self.scanner_severity_scope = scanner_severity_scope
        self.research_provider = research_provider or HttpResearchProvider(
            enabled=process_runner.runtime_policy.allow_network
        )
        self._experimental_io: WorkspaceIO | None = None
        self._experimental_workspace: RepositoryWorkspace | None = None
        self._execution_activity: dict[int, list[str]] = {}
        self._scan_invocations = 0
        self._research_invocations = 0

    def begin_cycle(self, cycle: int) -> RepositoryWorkspace:
        run_workspace = self.workspace_io.workspace
        if not isinstance(run_workspace, RunWorkspace):
            run_workspace = run_workspace.run_workspace
        experimental = run_workspace.fork_repository(cycle)
        self.process_runner.prepare_experimental_workspace(experimental)
        self._experimental_workspace = experimental
        self._experimental_io = WorkspaceIO(
            experimental,
            self.trace,
            max_file_bytes=self.workspace_io.max_file_bytes,
            max_active_listing_cursors=self.workspace_io.max_active_listing_cursors,
        )
        self.trace.append_event(
            "cycle_workspace_created",
            cycle=cycle,
            workspaceKind="experimental",
            repository=str(experimental.repository),
            sourceRepository=str(run_workspace.repository),
        )
        return experimental

    def read_workspace_text(
        self,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
        workspace: str = "active",
    ) -> dict[str, Any]:
        """Read text from the phase-active repository, or the current experiment when explicitly selected."""
        denied = self._require_phase("read_workspace_text", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        selected = self._select_workspace("read_workspace_text", workspace)
        if isinstance(selected, dict):
            return selected
        io, _ = selected
        return self._invoke("read_workspace_text", io.read_text, path, start_line, end_line, workspace_io=io)

    def list_workspace_files(
        self,
        path: str = ".",
        max_entries: int = 500,
        cursor: str | int | None = None,
        file_glob: str | None = None,
        max_scanned_entries: int = 5_000,
        workspace: str = "active",
    ) -> dict[str, Any]:
        """List bounded files in the phase-active repository or current experiment."""
        denied = self._require_phase("list_workspace_files", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        selected = self._select_workspace("list_workspace_files", workspace)
        if isinstance(selected, dict):
            return selected
        io, _ = selected
        return self._invoke(
            "list_workspace_files", io.list_files, path, max_entries, cursor, file_glob,
            max_scanned_entries, workspace_io=io,
        )

    def search_workspace_text(
        self,
        query: str,
        path: str = ".",
        file_glob: str | None = None,
        max_results: int = 100,
        max_files: int = 5_000,
        workspace: str = "active",
    ) -> dict[str, Any]:
        """Search bounded text in the phase-active repository or current experiment."""
        denied = self._require_phase("search_workspace_text", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        selected = self._select_workspace("search_workspace_text", workspace)
        if isinstance(selected, dict):
            return selected
        io, _ = selected
        return self._invoke(
            "search_workspace_text", io.search_text, query, path, file_glob, max_results,
            max_files, workspace_io=io,
        )

    def inspect_git_state(self, max_log_entries: int = 10, workspace: str = "active") -> dict[str, Any]:
        """Inspect bounded Git metadata in the phase-active repository or current experiment."""
        denied = self._require_phase("inspect_git_state", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        selected = self._select_workspace("inspect_git_state", workspace)
        if isinstance(selected, dict):
            return selected
        io, target = selected
        return self._invoke("inspect_git_state", self._inspect_git_state, io, target, max_log_entries, workspace_io=io)

    def edit_workspace_text(
        self,
        action: str,
        path: str,
        content: str | None = None,
        old_text: str | None = None,
        new_text: str | None = None,
        expected_occurrences: int = 1,
        workspace: str = "active",
    ) -> dict[str, Any]:
        """Edit the experiment before Intent; after Intent edit authoritative state unless experiment is explicit."""
        denied = self._require_phase("edit_workspace_text", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        selected = self._select_workspace("edit_workspace_text", workspace)
        if isinstance(selected, dict):
            return selected
        io, _ = selected
        return self._invoke(
            "edit_workspace_text", io.edit_text, action, path, content, old_text, new_text,
            expected_occurrences, workspace_io=io,
        )

    def run_workspace_shell(
        self,
        command: str,
        cwd: str = ".",
        timeout_seconds: int | None = None,
        workspace: str = "active",
    ) -> dict[str, Any]:
        """Run an allowed command in the experiment before Intent or authoritative repository after Intent."""
        denied = self._require_phase("run_workspace_shell", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        selected = self._select_workspace("run_workspace_shell", workspace)
        if isinstance(selected, dict):
            return selected
        io, target = selected
        result = self._invoke(
            "run_workspace_shell", self.process_runner.run_agent_shell, command, cwd,
            timeout_seconds, target, workspace_io=io,
        )
        return result.to_dict() if hasattr(result, "to_dict") else result

    def scan_current_repository(self, workspace: str = "active") -> dict[str, Any]:
        """Run the configured scanner with harness-owned settings as non-authoritative engineering evidence."""
        denied = self._require_phase("scan_current_repository", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        if self.scanner is None:
            return self._unavailable("scan_current_repository", "No engineering scanner is configured")
        selected = self._select_workspace("scan_current_repository", workspace)
        if isinstance(selected, dict):
            return selected
        io, target = selected
        self._scan_invocations += 1
        cycle = self.journal.active_cycle if self.journal else 0
        label = f"engineering-cycle-{cycle}-{target.kind}-{self._scan_invocations}"
        report = self._invoke(
            "scan_current_repository", self.scanner.scan, target.repository,
            self.scanner_severity_scope, label, workspace_io=io,
        )
        if isinstance(report, dict):
            return report
        payload = report.to_dict()
        payload["status"] = "ok" if report.succeeded else "error"
        payload["workspaceKind"] = target.kind
        payload["cycle"] = target.cycle
        self.trace.append_event(
            "engineering_scan_completed",
            cycle=cycle,
            workspaceKind=target.kind,
            outcome=report.effective_outcome.value,
            backend=report.backend,
            resultReference=report.raw_report_path,
        )
        return payload

    def research_search(self, query: str) -> dict[str, Any]:
        """Best-effort public research search; failure or absence of results is not evidence of absence."""
        denied = self._require_phase("research_search", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        result = self._invoke("research_search", self.research_provider.search, query)
        payload = result.to_dict() if hasattr(result, "to_dict") else result
        cycle = self.journal.active_cycle if self.journal else None
        result_reference = self._write_research_result("search", payload, cycle=cycle, query=query)
        self.trace.append_event(
            "research",
            operation="search",
            cycle=cycle,
            query=query,
            status=payload.get("status"),
            source=payload.get("source"),
            truncated=payload.get("truncated", False),
            resultReference=result_reference,
        )
        return payload

    def research_fetch(self, url: str) -> dict[str, Any]:
        """Best-effort bounded public HTTP(S) retrieval with explicit failure and truncation states."""
        denied = self._require_phase("research_fetch", {JournalPhase.INTENT_REQUIRED, JournalPhase.EXECUTION})
        if denied:
            return denied
        result = self._invoke("research_fetch", self.research_provider.fetch, url)
        payload = result.to_dict() if hasattr(result, "to_dict") else result
        cycle = self.journal.active_cycle if self.journal else None
        result_reference = self._write_research_result("fetch", payload, cycle=cycle, url=url)
        self.trace.append_event(
            "research",
            operation="fetch",
            cycle=cycle,
            source=payload.get("source", url),
            status=payload.get("status"),
            truncated=payload.get("truncated", False),
            resultReference=result_reference,
        )
        return payload

    def _write_research_result(self, operation: str, payload: dict[str, Any], **request: Any) -> str:
        self._research_invocations += 1
        path = self.trace.write_json(
            f"research/{self._research_invocations:03d}-{operation}.json",
            {"operation": operation, **request, "result": payload},
        )
        return str(path)

    def submit_cycle_intent(self, cycle_number: int, answers: list[dict[str, str]]) -> dict[str, Any]:
        """Submit the required Problem Analysis and Solution Decision before authoritative mutation."""
        if not self.journal:
            return self._unavailable("submit_cycle_intent", "Journal lifecycle is not configured")
        result = self.journal.submit_intent(cycle_number, answers)
        response = result.to_dict()
        if result.accepted:
            response.update(
                {
                    "phase": JournalPhase.EXECUTION.value,
                    "availableCapabilities": sorted(self.available_tool_names()),
                    "nextAction": (
                        "Continue in this cycle; active workspace operations now target the authoritative "
                        "repository, while workspace='experiment' remains available for isolated investigation."
                    ),
                }
            )
        return response

    def submit_cycle_outcome(
        self, cycle_number: int, status: str, status_explanation: str,
        answers: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Submit the required metadata-only Cycle Outcome after execution."""
        if not self.journal:
            return self._unavailable("submit_cycle_outcome", "Journal lifecycle is not configured")
        return self.journal.submit_outcome(cycle_number, status, status_explanation, answers).to_dict()

    def adk_tools(self) -> list[FunctionTool]:
        return [
            FunctionTool(self.read_workspace_text), FunctionTool(self.list_workspace_files),
            FunctionTool(self.search_workspace_text), FunctionTool(self.inspect_git_state),
            FunctionTool(self.edit_workspace_text), FunctionTool(self.run_workspace_shell),
            FunctionTool(self.scan_current_repository), FunctionTool(self.research_search),
            FunctionTool(self.research_fetch), FunctionTool(self.submit_cycle_intent),
            FunctionTool(self.submit_cycle_outcome),
        ]

    def available_tool_names(self) -> frozenset[str]:
        engineering = {
            "read_workspace_text", "list_workspace_files", "search_workspace_text",
            "inspect_git_state", "edit_workspace_text", "run_workspace_shell",
            "scan_current_repository", "research_search", "research_fetch",
        }
        if not self.journal:
            return frozenset(engineering)
        by_phase = {
            JournalPhase.INTENT_REQUIRED: engineering | {"submit_cycle_intent"},
            JournalPhase.EXECUTION: engineering,
            JournalPhase.OUTCOME_REQUIRED: {"submit_cycle_outcome"},
        }
        return frozenset(by_phase.get(self.journal.phase, set()))

    def execution_activity(self, cycle: int) -> tuple[str, ...]:
        return tuple(self._execution_activity.get(cycle, ()))

    def _select_workspace(
        self, tool: str, requested: str,
    ) -> tuple[WorkspaceIO, RepositoryWorkspace] | dict[str, Any]:
        normalized = requested.strip().lower()
        phase = self.journal.phase if self.journal else JournalPhase.EXECUTION
        if normalized not in {"active", "authoritative", "experiment"}:
            return self._unavailable(tool, "workspace must be active, authoritative, or experiment")
        if phase == JournalPhase.INTENT_REQUIRED:
            if normalized == "authoritative":
                return self._unavailable(tool, "Authoritative repository capabilities are unavailable before Intent acceptance")
            io = self._experimental_io
            target = self._experimental_workspace
        elif normalized == "experiment":
            io = self._experimental_io
            target = self._experimental_workspace
        else:
            io = self.workspace_io
            workspace = io.workspace
            target = workspace.authoritative_repository() if isinstance(workspace, RunWorkspace) else workspace
        if io is None or target is None:
            return self._unavailable(tool, "Current-cycle experimental workspace is not initialized")
        return io, target

    def _require_phase(self, tool: str, phases: set[JournalPhase]) -> dict[str, Any] | None:
        if not self.journal or self.journal.phase in phases:
            return None
        return self._unavailable(tool, f"Capability unavailable during {self.journal.phase.value}; accepted checkpoint transition required")

    def _unavailable(self, tool: str, reason: str) -> dict[str, Any]:
        self.trace.append_event(
            "phase_capability_rejected", tool=tool,
            phase=self.journal.phase.value if self.journal else None, reason=reason,
        )
        return {"status": "error", "error": reason, "failureCode": "PHASE_CAPABILITY_UNAVAILABLE"}

    def _inspect_git_state(
        self, io: WorkspaceIO, target: RepositoryWorkspace, max_log_entries: int,
    ) -> dict[str, Any]:
        limit = max(1, min(max_log_entries, 50))
        commands = {
            "status": ["git", "status", "--short", "--branch"],
            "head": ["git", "rev-parse", "HEAD"],
            "branch": ["git", "branch", "--show-current"],
            "recentCommits": ["git", "log", f"-{limit}", "--oneline", "--decorate=no"],
        }
        evidence: dict[str, Any] = {"status": "ok", "workspaceKind": target.kind, "cycle": target.cycle}
        for name, command in commands.items():
            result = self.process_runner.run_argv(
                command, cwd=target.repository, source=f"agent_readonly_git_{name}",
            )
            if not result.succeeded:
                return {
                    "status": "error", "failureCode": "READ_ONLY_GIT_INSPECTION_FAILED",
                    "operation": name, "exitCode": result.exit_code,
                    "stderrArtifact": result.stderr_artifact, "workspaceKind": target.kind,
                    "cycle": target.cycle,
                }
            evidence[name] = result.stdout.strip()
        return evidence

    def _invoke(
        self, name: str, function: Any, *args: Any,
        workspace_io: WorkspaceIO | None = None,
    ) -> Any:
        if self.journal and self.journal.phase == JournalPhase.EXECUTION:
            cycle = self.journal.active_cycle
            self._execution_activity.setdefault(cycle, []).append(name)
            self.trace.append_event(
                "execution_capability_invoked", cycle=cycle, tool=name,
                workspaceKind=workspace_io.workspace_kind if workspace_io else None,
            )
        try:
            self.budget.consume_tool_call()
            return function(*args)
        except BudgetExceeded as exc:
            self.trace.append_event("tool_budget_exceeded", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "EXECUTION_BUDGET_EXCEEDED"}
        except Exception as exc:
            self.trace.append_event("tool_error", tool=name, error=str(exc))
            return {"status": "error", "error": str(exc), "failureCode": "TOOL_ERROR"}
