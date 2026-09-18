from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

from ..capabilities.execution import ProcessRunner
from ..models import CommandResult
from ..workspace import RunWorkspace


@dataclass(frozen=True)
class GitCredential:
    token: str
    username: str = "x-access-token"

    @property
    def redaction_values(self) -> tuple[str, ...]:
        return self.token, quote(self.token, safe="")


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
        return (
            parsed.scheme == "https"
            and parsed.hostname in {"github.com", "www.github.com"}
            and parsed.username is None
            and parsed.password is None
        )

    def run(
        self,
        arguments: list[str],
        *,
        cwd: Path,
        source: str,
        credential: GitCredential | None = None,
        remote_url: str | None = None,
        disable_hooks: bool = False,
    ) -> CommandResult:
        actual_arguments = list(arguments)
        display_arguments = list(arguments)
        redactions: tuple[str, ...] = ()
        if credential and credential.token:
            if remote_url is None or not self.is_github_https(remote_url):
                raise ValueError("GitHub credentials require a clean GitHub HTTPS remote URL")
            authenticated_url = self._authenticated_url(remote_url, credential)
            redacted_url = self._authenticated_url(remote_url, credential, redact=True)
            try:
                remote_index = actual_arguments.index(remote_url)
            except ValueError as exc:
                raise ValueError("Git command does not contain the supplied remote URL") from exc
            actual_arguments[remote_index] = authenticated_url
            display_arguments[remote_index] = redacted_url
            redactions = credential.redaction_values

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
        display_command = list(command)
        command.extend(actual_arguments)
        display_command.extend(display_arguments)
        return self.process_runner.run_argv(
            command,
            cwd=cwd,
            environment=self._environment(),
            source=source,
            redact_values=redactions,
            display_command=display_command,
        )

    def _environment(self) -> dict[str, str]:
        environment = dict(self.environment)
        prohibited = {
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "GIT_ASKPASS",
            "GIT_ASKPASS_USERNAME",
            "GIT_ASKPASS_SECRET",
            "SSH_ASKPASS",
            "XRAY_ACCESS_TOKEN",
            "XRAY_USERNAME",
            "XRAY_PASSWORD",
        }
        for name in tuple(environment):
            if name.upper() in prohibited:
                environment.pop(name, None)
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "never",
                "GCM_PROVIDER": "generic",
            }
        )
        return environment

    @staticmethod
    def _authenticated_url(
        remote_url: str,
        credential: GitCredential,
        *,
        redact: bool = False,
    ) -> str:
        parsed = urlsplit(remote_url)
        password = "[REDACTED]" if redact else quote(credential.token, safe="")
        username = quote(credential.username, safe="")
        hostname = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit(
            (parsed.scheme, f"{username}:{password}@{hostname}{port}", parsed.path, parsed.query, parsed.fragment)
        )
