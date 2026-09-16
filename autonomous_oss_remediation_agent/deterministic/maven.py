from __future__ import annotations

import os
import shlex
from pathlib import Path

from ..capabilities.execution import ProcessRunner
from ..models import CommandResult


class MavenService:
    def __init__(self, repository: Path, process_runner: ProcessRunner):
        self.repository = repository
        self.process_runner = process_runner

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
        if os.name == "nt" and windows_wrapper.is_file():
            return str(windows_wrapper)
        if unix_wrapper.is_file():
            return str(unix_wrapper)
        if windows_wrapper.is_file():
            return str(windows_wrapper)
        return "mvn"


def command_for_display(command: tuple[str, ...]) -> str:
    return " ".join(shlex.quote(part) for part in command)
