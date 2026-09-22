from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Mapping, Sequence

from ..config import ExecutionBudgetConfig, RuntimePolicy
from ..models import CommandResult
from ..workspace import RepositoryWorkspace, RunWorkspace, TraceStore
from .isolation import ExperimentalProcessIsolation
from .policy import CommandPolicy, sanitized_agent_environment


class BudgetExceeded(RuntimeError):
    pass


class ExecutionBudget:
    def __init__(self, config: ExecutionBudgetConfig):
        self.config = config
        self.started_at = time.monotonic()
        self._tool_calls = 0
        self._lock = threading.Lock()

    @property
    def tool_calls(self) -> int:
        with self._lock:
            return self._tool_calls

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.config.overall_timeout_seconds - self.elapsed_seconds)

    def consume_tool_call(self) -> None:
        with self._lock:
            if self._tool_calls >= self.config.max_tool_calls:
                raise BudgetExceeded(f"Maximum tool calls reached: {self.config.max_tool_calls}")
            self._tool_calls += 1
        self.ensure_time_remaining()

    def ensure_time_remaining(self) -> None:
        if self.remaining_seconds <= 0:
            raise BudgetExceeded("Overall remediation execution deadline reached")

    def effective_timeout(self, requested: int | None = None) -> int:
        self.ensure_time_remaining()
        configured = requested or self.config.command_timeout_seconds
        return max(1, int(min(configured, self.config.command_timeout_seconds, self.remaining_seconds)))

    def model_turn_timeout(self) -> float:
        self.ensure_time_remaining()
        return min(float(self.config.model_turn_timeout_seconds), self.remaining_seconds)


class ProcessRunner:
    def __init__(
        self,
        workspace: RunWorkspace,
        trace: TraceStore,
        budget: ExecutionBudget,
        runtime_policy: RuntimePolicy,
    ):
        self.workspace = workspace
        self.trace = trace
        self.budget = budget
        self.runtime_policy = runtime_policy
        self.command_policy = CommandPolicy()
        self.experimental_isolation = ExperimentalProcessIsolation(workspace.root)
        self._experimental_runtime: dict[int, Path] = {}

    def prepare_experimental_workspace(self, target: RepositoryWorkspace) -> None:
        if target.kind != "experimental" or target.cycle is None:
            raise ValueError("Only cycle experimental workspaces can be prepared for isolation")
        historical = tuple(
            path
            for path in self.workspace.investigation.iterdir()
            if path.is_dir() and path != target.repository
        )
        runtime = self.experimental_isolation.prepare(
            target.repository,
            target.cycle,
            historical,
        )
        self._experimental_runtime[target.cycle] = runtime
        self.trace.append_event(
            "experimental_shell_boundary_prepared",
            cycle=target.cycle,
            workspaceKind=target.kind,
            repository=str(target.repository),
            historicalRepositories=[str(path) for path in historical],
            backend=self.experimental_isolation.backend,
        )

    def run_agent_shell(
        self,
        command: str,
        cwd: str = ".",
        timeout_seconds: int | None = None,
        repository_workspace: RepositoryWorkspace | None = None,
    ) -> CommandResult:
        target = repository_workspace or self.workspace.authoritative_repository()
        allowed, reason = self.command_policy.evaluate(command)
        directory = target.repository_directory(cwd)
        if not allowed:
            result = CommandResult(
                command=[command],
                cwd=str(directory),
                exit_code=126,
                stderr=reason or "Command blocked by policy",
                blocked=True,
            )
            self.trace.append_event(
                "agent_command_blocked",
                command=command,
                cwd=str(directory),
                reason=reason,
                workspaceKind=target.kind,
                cycle=target.cycle,
            )
            return result
        shell_command = _host_shell_command(command)
        environment = sanitized_agent_environment(
            self.workspace.root, self.runtime_policy.allow_network
        )
        if target.kind == "experimental":
            if target.cycle is None or target.cycle not in self._experimental_runtime:
                return CommandResult(
                    command=[command],
                    cwd=str(directory),
                    exit_code=126,
                    stderr="Experimental shell boundary is not prepared",
                    blocked=True,
                )
            runtime = self._experimental_runtime[target.cycle]
            environment.update(
                {
                    "HOME": str(runtime / "home"),
                    "USERPROFILE": str(runtime / "home"),
                    "TEMP": str(runtime / "temp"),
                    "TMP": str(runtime / "temp"),
                }
            )
            for path in (runtime / "home", runtime / "temp"):
                path.mkdir(parents=True, exist_ok=True)
            return self._run_isolated_agent_shell(
                shell_command,
                cwd=directory,
                timeout_seconds=self.budget.effective_timeout(timeout_seconds),
                environment=environment,
                display_command=[command],
                target=target,
            )
        return self._run(
            shell_command,
            cwd=directory,
            timeout_seconds=self.budget.effective_timeout(timeout_seconds),
            environment=environment,
            source="agent",
            display_command=[command],
            trace_metadata={"workspaceKind": target.kind, "cycle": target.cycle},
        )

    def _run_isolated_agent_shell(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: int,
        environment: dict[str, str],
        display_command: list[str],
        target: RepositoryWorkspace,
    ) -> CommandResult:
        command_id = f"agent-{uuid.uuid4().hex[:12]}"
        stdout_path = self.workspace.artifacts / "commands" / f"{command_id}.stdout.log"
        stderr_path = self.workspace.artifacts / "commands" / f"{command_id}.stderr.log"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        isolated = self.experimental_isolation.run(
            command,
            cwd=cwd,
            environment=environment,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_seconds=timeout_seconds,
        )
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
        if isolated.error:
            stderr = (stderr + "\n" if stderr else "") + isolated.error
        if isolated.timed_out:
            stderr = (stderr + "\n" if stderr else "") + f"Command timed out after {timeout_seconds}s"
        limit = self.budget.config.max_returned_output_chars
        result = CommandResult(
            command=display_command,
            cwd=str(cwd),
            exit_code=isolated.exit_code,
            stdout=_tail(stdout, limit),
            stderr=_tail(stderr, limit),
            duration_seconds=time.monotonic() - started,
            timed_out=isolated.timed_out,
            stdout_artifact=str(stdout_path),
            stderr_artifact=str(stderr_path),
        )
        self.trace.append_event(
            "command",
            source="agent",
            result=result.to_dict(),
            workspaceKind=target.kind,
            cycle=target.cycle,
            isolationBackend=self.experimental_isolation.backend,
        )
        return result

    def run_deterministic_shell(
        self,
        command: str,
        cwd: str | Path,
        timeout_seconds: int | None = None,
        environment: Mapping[str, str] | None = None,
        source: str = "deterministic",
    ) -> CommandResult:
        return self._run(
            _host_shell_command(command),
            cwd=Path(cwd),
            timeout_seconds=self.budget.effective_timeout(timeout_seconds),
            environment=dict(environment) if environment is not None else _deterministic_environment(),
            source=source,
            display_command=[command],
        )

    def run_argv(
        self,
        command: Sequence[str],
        cwd: str | Path | None = None,
        timeout_seconds: int | None = None,
        environment: Mapping[str, str] | None = None,
        source: str = "deterministic",
        redact_values: Sequence[str] = (),
        display_command: Sequence[str] | None = None,
    ) -> CommandResult:
        return self._run(
            list(command),
            cwd=Path(cwd) if cwd else self.workspace.root,
            timeout_seconds=self.budget.effective_timeout(timeout_seconds),
            environment=dict(environment) if environment is not None else _deterministic_environment(),
            source=source,
            display_command=list(display_command) if display_command is not None else list(command),
            redact_values=redact_values,
        )

    def _run(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: int,
        environment: dict[str, str],
        source: str,
        display_command: list[str],
        redact_values: Sequence[str] = (),
        trace_metadata: Mapping[str, object] | None = None,
    ) -> CommandResult:
        command_id = f"{source}-{uuid.uuid4().hex[:12]}"
        stdout_path = self.workspace.artifacts / "commands" / f"{command_id}.stdout.log"
        stderr_path = self.workspace.artifacts / "commands" / f"{command_id}.stderr.log"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process: subprocess.Popen[str] | None = None
        stdout = ""
        stderr = ""
        exit_code = 127
        timed_out = False
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=environment,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creation_flags,
                start_new_session=os.name != "nt",
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
                exit_code = process.returncode or 0
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                stdout, stderr = process.communicate()
                exit_code = 124
                stderr = (stderr + "\n" if stderr else "") + f"Command timed out after {timeout_seconds}s"
        except FileNotFoundError as exc:
            stderr = str(exc)
        except OSError as exc:
            stderr = str(exc)
        stdout = _redact(stdout, redact_values)
        stderr = _redact(stderr, redact_values)
        duration = time.monotonic() - started
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        limit = self.budget.config.max_returned_output_chars
        result = CommandResult(
            command=display_command,
            cwd=str(cwd),
            exit_code=exit_code,
            stdout=_tail(stdout, limit),
            stderr=_tail(stderr, limit),
            duration_seconds=duration,
            timed_out=timed_out,
            stdout_artifact=str(stdout_path),
            stderr_artifact=str(stderr_path),
        )
        self.trace.append_event(
            "command",
            source=source,
            result=result.to_dict(),
            **dict(trace_metadata or {}),
        )
        return result


def _host_shell_command(command: str) -> list[str]:
    if os.name == "nt":
        return [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]
    return ["/bin/bash", "-lc", command]


def _deterministic_environment() -> dict[str, str]:
    environment = os.environ.copy()
    prohibited = {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "XRAY_ACCESS_TOKEN",
        "XRAY_USERNAME",
        "XRAY_PASSWORD",
    }
    for name in tuple(environment):
        if name.upper() in prohibited:
            environment.pop(name, None)
    return environment


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


def _tail(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"[output truncated; full log retained]\n{value[-limit:]}"


def _redact(value: str, secrets: Sequence[str]) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted
