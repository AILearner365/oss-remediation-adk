from __future__ import annotations

import shutil
from dataclasses import dataclass

from ..capabilities.execution import ProcessRunner
from ..models import CommandResult
from ..workspace import RunWorkspace, TraceStore


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
    def __init__(self, workspace: RunWorkspace, process_runner: ProcessRunner, trace: TraceStore):
        self.workspace = workspace
        self.process_runner = process_runner
        self.trace = trace

    def clone(self, repository_url: str, reference: str) -> RepositoryMetadata:
        if self.workspace.repository.exists():
            shutil.rmtree(self.workspace.repository)
        clone = self.process_runner.run_argv(
            ["git", "clone", "--no-tags", repository_url, str(self.workspace.repository)],
            cwd=self.workspace.root,
            source="repository_clone",
        )
        if not clone.succeeded:
            raise RepositoryPreparationError("Repository clone failed", clone)
        checkout = self.process_runner.run_argv(
            ["git", "checkout", reference],
            cwd=self.workspace.repository,
            source="repository_checkout",
        )
        if not checkout.succeeded:
            fetch = self.process_runner.run_argv(
                ["git", "fetch", "origin", reference],
                cwd=self.workspace.repository,
                source="repository_fetch_ref",
            )
            if not fetch.succeeded:
                raise RepositoryPreparationError("Requested repository reference is unavailable", checkout)
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
        )
        if not commit_result.succeeded:
            raise RepositoryPreparationError("Unable to resolve baseline commit", commit_result)
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
            remote_url=remote_result.stdout.strip() if remote_result.succeeded else repository_url,
        )
        self.trace.append_event("repository_prepared", **metadata.__dict__)
        return metadata
