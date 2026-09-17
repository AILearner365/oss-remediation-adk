from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path
from typing import Callable

from ..capabilities.execution import ProcessRunner
from ..config import MavenConfig
from ..models import CommandResult


class MavenExecutionPolicyError(RuntimeError):
    pass


class MavenService:
    def __init__(
        self,
        repository: Path,
        process_runner: ProcessRunner,
        config: MavenConfig | None = None,
        *,
        platform_name: str | None = None,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.repository = repository
        self.process_runner = process_runner
        self.config = config or MavenConfig()
        self.platform_name = platform_name or os.name
        self.which = which

    def run_baseline(
        self,
        build_commands: tuple[str, ...],
        test_commands: tuple[str, ...] = (),
        startup_commands: tuple[str, ...] = (),
    ) -> tuple[CommandResult, ...]:
        results = list(self._run_commands(build_commands, phase="baseline_build", default_goals=("clean", "verify")))
        if all(result.succeeded for result in results):
            results.extend(self._run_commands(test_commands, phase="baseline_test", default_goals=()))
        if all(result.succeeded for result in results):
            results.extend(self._run_commands(startup_commands, phase="baseline_startup", default_goals=()))
        return tuple(results)

    def run_validation(
        self,
        build_commands: tuple[str, ...],
        test_commands: tuple[str, ...],
        startup_commands: tuple[str, ...],
    ) -> tuple[CommandResult, ...]:
        results = list(self._run_commands(build_commands, phase="validation_build", default_goals=("clean", "verify")))
        if all(result.succeeded for result in results):
            results.extend(self._run_commands(test_commands, phase="validation_test", default_goals=()))
        if all(result.succeeded for result in results):
            results.extend(self._run_commands(startup_commands, phase="validation_startup", default_goals=()))
        return tuple(results)

    def _run_commands(
        self,
        commands: tuple[str, ...],
        *,
        phase: str,
        default_goals: tuple[str, ...],
    ) -> tuple[CommandResult, ...]:
        if commands:
            results: list[CommandResult] = []
            for index, command in enumerate(commands, start=1):
                result = self.process_runner.run_deterministic_shell(
                    command,
                    cwd=self.repository,
                    source=f"{phase}_{index}",
                )
                results.append(result)
                if not result.succeeded:
                    break
            return tuple(results)
        if not default_goals:
            return ()
        executable = self.maven_executable()
        return (
            self.process_runner.run_argv(
                [executable, *default_goals],
                cwd=self.repository,
                source=phase,
            ),
        )

    def maven_executable(self) -> str:
        windows_wrapper = self.repository / "mvnw.cmd"
        unix_wrapper = self.repository / "mvnw"
        if self.config.mode == "system":
            return self._system_maven_executable()
        if self.config.mode == "wrapper":
            wrapper = windows_wrapper if self.platform_name == "nt" else unix_wrapper
            wrapper_is_usable = wrapper.is_file() and (
                self.platform_name == "nt" or os.access(wrapper, os.X_OK)
            )
            if not wrapper_is_usable:
                raise MavenExecutionPolicyError(
                    f"Maven wrapper mode requires a usable repository wrapper: {wrapper.name}"
                )
            return str(wrapper)
        wrapper = windows_wrapper if self.platform_name == "nt" else unix_wrapper
        if wrapper.is_file():
            return str(wrapper)
        return self._system_maven_executable()

    def _system_maven_executable(self) -> str:
        if self.platform_name == "nt":
            return self.which("mvn.cmd") or self.which("mvn") or "mvn.cmd"
        return "mvn"


def command_for_display(command: tuple[str, ...]) -> str:
    return " ".join(shlex.quote(part) for part in command)
