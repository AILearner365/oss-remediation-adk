from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from ..capabilities.execution import ProcessRunner
from ..models import CommandResult
from ..workspace import RunWorkspace


@dataclass(frozen=True)
class GitCredential:
    token: str
    username: str = "x-access-token"


class EnvironmentGitCredentialProvider:
    def __init__(
        self,
        environment: Mapping[str, str] | None = None,
        variable_names: tuple[str, ...] = ("GH_TOKEN", "GITHUB_TOKEN"),
    ):
        self._environment = environment if environment is not None else os.environ
        self._variable_names = variable_names

    def isolation_status(self) -> tuple[bool, str]:
        variable_name = self._configured_variable_name()
        if variable_name is None:
            expected = " or ".join(self._variable_names)
            return False, f"No GitHub token is configured; set {expected} for the runner process"
        return True, f"{variable_name} is available only to deterministic Git/GitHub infrastructure"

    def resolve(self) -> GitCredential:
        credential = self.resolve_optional()
        if credential is None:
            expected = " or ".join(self._variable_names)
            raise RuntimeError(f"No GitHub token is configured; set {expected}")
        return credential

    def resolve_optional(self) -> GitCredential | None:
        variable_name = self._configured_variable_name()
        if variable_name is None:
            return None
        return GitCredential(self._environment[variable_name].strip())

    def _configured_variable_name(self) -> str | None:
        for variable_name in self._variable_names:
            if self._environment.get(variable_name, "").strip():
                return variable_name
        return None


class NonInteractiveGitAuth:
    def __init__(
        self,
        workspace: RunWorkspace,
        process_runner: ProcessRunner,
        environment: Mapping[str, str] | None = None,
    ):
        self.workspace = workspace
        self.process_runner = process_runner
        self.environment = environment if environment is not None else os.environ
        self.credential_provider = EnvironmentGitCredentialProvider(self.environment)

    def credential_for(self, remote_url: str) -> GitCredential | None:
        if not self.is_github_https(remote_url):
            return None
        return self.credential_provider.resolve_optional()

    @staticmethod
    def is_github_https(remote_url: str) -> bool:
        parsed = urlparse(remote_url.strip())
        return parsed.scheme == "https" and parsed.hostname in {"github.com", "www.github.com"}

    def run(
        self,
        arguments: list[str],
        *,
        cwd: Path,
        source: str,
        credential: GitCredential | None = None,
        disable_hooks: bool = False,
    ) -> CommandResult:
        self.workspace.temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="git-auth-", dir=self.workspace.temp) as directory:
            auth_root = Path(directory)
            askpass = self._write_askpass(auth_root)
            environment = self._environment(askpass, credential)
            command = [
                "git",
                "-c",
                "core.askPass=",
                "-c",
                "credential.helper=",
                "-c",
                "credential.interactive=false",
                "-c",
                "credential.modalPrompt=false",
            ]
            if disable_hooks:
                command.extend(
                    ["-c", f"core.hooksPath={'NUL' if os.name == 'nt' else '/dev/null'}"]
                )
            command.extend(arguments)
            redactions = (credential.token,) if credential and credential.token else ()
            return self.process_runner.run_argv(
                command,
                cwd=cwd,
                environment=environment,
                source=source,
                redact_values=redactions,
            )

    def _environment(
        self,
        askpass: Path,
        credential: GitCredential | None,
    ) -> dict[str, str]:
        environment = dict(self.environment)
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
        environment.update(
            {
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "never",
                "GCM_PROVIDER": "generic",
                "GIT_ASKPASS_USERNAME": credential.username if credential else "x-access-token",
                "GIT_ASKPASS_SECRET": credential.token if credential else "",
            }
        )
        return environment

    @staticmethod
    def _write_askpass(directory: Path) -> Path:
        askpass = directory / ("askpass.cmd" if os.name == "nt" else "askpass.sh")
        if os.name == "nt":
            askpass.write_text(
                "@echo off\r\n"
                "echo %~1 | findstr /I \"Username\" >nul && (echo %GIT_ASKPASS_USERNAME% & exit /b 0)\r\n"
                "echo %GIT_ASKPASS_SECRET%\r\n"
                "exit /b 0\r\n",
                encoding="utf-8",
            )
        else:
            askpass.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in *Username*) printf '%s\\n' \"$GIT_ASKPASS_USERNAME\" ;; "
                "*) printf '%s\\n' \"$GIT_ASKPASS_SECRET\" ;; esac\n",
                encoding="utf-8",
            )
            askpass.chmod(askpass.stat().st_mode | stat.S_IXUSR)
        return askpass
