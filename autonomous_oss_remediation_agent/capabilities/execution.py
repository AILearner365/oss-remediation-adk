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
from ..workspace import RunWorkspace, TraceStore
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

    def run_agent_shell(self, command: str, cwd: str = ".", timeout_seconds: int | None = None) -> CommandResult:
        allowed, reason = self.command_policy.evaluate(command)
        directory = self.workspace.repository_directory(cwd)
        if not allowed:
            result = CommandResult(
                command=[command],
                cwd=str(directory),
                exit_code=126,
                stderr=reason or "Command blocked by policy",
                blocked=True,
            )
            self.trace.append_event("agent_command_blocked", command=command, cwd=str(directory), reason=reason)
            return result
        shell_command = _host_shell_command(command)
        return self._run(
            shell_command,
            cwd=directory,
            timeout_seconds=self.budget.effective_timeout(timeout_seconds),
            environment=sanitized_agent_environment(self.workspace.root, self.runtime_policy.allow_network),
            source="agent",
            display_command=[command],
        )

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
            environment=dict(environment) if environment is not None else os.environ.copy(),
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
    ) -> CommandResult:
        return self._run(
            list(command),
            cwd=Path(cwd) if cwd else self.workspace.root,
            timeout_seconds=self.budget.effective_timeout(timeout_seconds),
            environment=dict(environment) if environment is not None else os.environ.copy(),
            source=source,
            display_command=list(command),
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
        self.trace.append_event("command", source=source, result=result.to_dict())
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
