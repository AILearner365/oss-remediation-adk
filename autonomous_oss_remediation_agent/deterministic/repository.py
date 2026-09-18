from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Mapping

from ..capabilities.execution import ProcessRunner
from ..models import CommandResult
from ..workspace import RunWorkspace, TraceStore
from .git_auth import NonInteractiveGitAuth


class RepositoryPreparationError(RuntimeError):
    def __init__(self, message: str, result: CommandResult | None = None):
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class RepositoryMetadata:
    path: str
    commit: str
    reference: str
    remote_url: str


class RepositoryPreparer:
    def __init__(
        self,
        workspace: RunWorkspace,
        process_runner: ProcessRunner,
        trace: TraceStore,
        environment: Mapping[str, str] | None = None,
    ):
        self.workspace = workspace
        self.process_runner = process_runner
        self.trace = trace
        self.git_auth = NonInteractiveGitAuth(workspace, process_runner, environment)

    def clone(self, repository_url: str, reference: str) -> RepositoryMetadata:
        if self.workspace.repository.exists():
            shutil.rmtree(self.workspace.repository)
        credential = self.git_auth.credential_for(repository_url)
        clone = self.git_auth.run(
            ["clone", "--no-tags", repository_url, str(self.workspace.repository)],
            cwd=self.workspace.root,
            source="repository_clone",
            credential=credential,
            remote_url=repository_url,
        )
        if not clone.succeeded:
            if self.workspace.repository.exists():
                shutil.rmtree(self.workspace.repository)
            if self.git_auth.is_github_https(repository_url) and credential is None:
                message = (
                    "Repository clone failed non-interactively; private GitHub repositories "
                    "require GH_TOKEN or GITHUB_TOKEN"
                )
            elif credential is not None:
                message = "Repository clone failed using non-interactive GitHub authentication"
            else:
                message = "Repository clone failed non-interactively"
            raise RepositoryPreparationError(message, clone)
        clean_origin = self.process_runner.run_argv(
            ["git", "remote", "set-url", "origin", repository_url],
            cwd=self.workspace.repository,
            source="repository_clean_origin",
            redact_values=credential.redaction_values if credential else (),
        )
        if not clean_origin.succeeded:
            shutil.rmtree(self.workspace.repository)
            raise RepositoryPreparationError("Unable to restore the clean repository origin", clean_origin)
        checkout = self.process_runner.run_argv(
            ["git", "checkout", reference],
            cwd=self.workspace.repository,
            source="repository_checkout",
        )
        if not checkout.succeeded:
            fetch = self.git_auth.run(
                ["fetch", repository_url, reference],
                cwd=self.workspace.repository,
                source="repository_fetch_ref",
                credential=credential,
                remote_url=repository_url,
            )
            if not fetch.succeeded:
                raise RepositoryPreparationError("Requested repository reference is unavailable", fetch)
            checkout = self.process_runner.run_argv(
                ["git", "checkout", "--detach", "FETCH_HEAD"],
                cwd=self.workspace.repository,
                source="repository_checkout_fetched_ref",
            )
            if not checkout.succeeded:
                raise RepositoryPreparationError("Requested repository reference could not be checked out", checkout)
        commit_result = self.process_runner.run_argv(
            ["git", "rev-parse", "HEAD"],
            cwd=self.workspace.repository,
            source="repository_metadata",
        )
        remote_result = self.process_runner.run_argv(
            ["git", "remote", "get-url", "origin"],
            cwd=self.workspace.repository,
            source="repository_metadata",
            redact_values=credential.redaction_values if credential else (),
        )
        if not commit_result.succeeded:
            raise RepositoryPreparationError("Unable to resolve baseline commit", commit_result)
        if not remote_result.succeeded or remote_result.stdout.strip() != repository_url:
            raise RepositoryPreparationError("Repository origin is not the clean requested URL", remote_result)
        disable_push = self.process_runner.run_argv(
            ["git", "remote", "set-url", "--push", "origin", "disabled://autonomous-remediation-delivery-only"],
            cwd=self.workspace.repository,
            source="repository_disable_push",
        )
        if not disable_push.succeeded:
            raise RepositoryPreparationError("Unable to disable the remediation clone push URL", disable_push)
        metadata = RepositoryMetadata(
            path=str(self.workspace.repository),
            commit=commit_result.stdout.strip(),
            reference=reference,
            remote_url=remote_result.stdout.strip(),
        )
        self.trace.append_event("repository_prepared", **metadata.__dict__)
        return metadata
