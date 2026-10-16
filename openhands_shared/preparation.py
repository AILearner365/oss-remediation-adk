"""Deterministic local Git preparation for registered shared-backend tasks.

This module creates only local refs and worktrees.  It has no push, delivery,
baseline, scanner, model, or agent integration.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence
from urllib.parse import urlsplit

from .contracts import PreparationRecord, TaskRequest, utc_now
from .store import SQLiteTaskStore

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback retains thread safety.
    fcntl = None


class PreparationError(RuntimeError):
    """Base fail-closed preparation error without captured command output."""


class UnsupportedRepositoryError(PreparationError):
    pass


class RepositoryIdentityError(PreparationError):
    pass


class ReferenceMismatchError(PreparationError):
    pass


class WorkspaceConflictError(PreparationError):
    pass


class GitCommandError(PreparationError):
    def __init__(self, operation: str, return_code: int):
        super().__init__(f"Git operation {operation!r} failed with exit code {return_code}")
        self.operation = operation
        self.return_code = return_code


@dataclass(frozen=True)
class TrustedRepository:
    """Approved mapping from a task repository identity to a local Git source."""

    repository_url: str
    source_path: Path
    origin_url: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.repository_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("trusted repository identity must be a credential-free HTTPS URL")
        source = self.source_path.expanduser().resolve()
        if not source.is_absolute():
            raise ValueError("trusted repository source path must be absolute")
        object.__setattr__(self, "source_path", source)
        origin = urlsplit(self.origin_url)
        if origin.username or origin.password:
            raise ValueError("trusted repository origin must not contain credentials")
        if origin.scheme:
            if origin.scheme not in {"https", "file"} or not origin.path:
                raise ValueError("trusted repository origin must use credential-free HTTPS or file transport")
            if origin.query or origin.fragment:
                raise ValueError("trusted repository origin must not contain a query or fragment")
        elif not Path(self.origin_url).is_absolute():
            raise ValueError("local trusted repository origin must be an absolute path")


@dataclass(frozen=True)
class PreparationConfig:
    workspace_root: Path
    repositories: tuple[TrustedRepository, ...]
    git_timeout_seconds: int = 60
    _by_url: dict[str, TrustedRepository] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        root = self.workspace_root.expanduser().resolve()
        object.__setattr__(self, "workspace_root", root)
        if self.git_timeout_seconds < 1 or self.git_timeout_seconds > 600:
            raise ValueError("git timeout must be from 1 through 600 seconds")
        mapping: dict[str, TrustedRepository] = {}
        for repository in self.repositories:
            if repository.repository_url in mapping:
                raise ValueError(f"duplicate trusted repository {repository.repository_url!r}")
            if root == repository.source_path or root.is_relative_to(repository.source_path) or repository.source_path.is_relative_to(root):
                raise ValueError("workspace root and trusted source repository must not overlap")
            mapping[repository.repository_url] = repository
        object.__setattr__(self, "_by_url", mapping)

    def repository_for(self, repository_url: str) -> TrustedRepository:
        try:
            return self._by_url[repository_url]
        except KeyError as exc:
            raise UnsupportedRepositoryError(
                "registered repository is not present in the trusted repository configuration"
            ) from exc


@dataclass(frozen=True)
class GitInvocation:
    operation: str
    argv: tuple[str, ...]


class GitRunner:
    """Run an allowlisted Git command with a minimal, credential-free environment."""

    _ALLOWED_SUBCOMMANDS = frozenset(
        {
            "cat-file",
            "check-ref-format",
            "config",
            "fetch",
            "ls-remote",
            "merge-base",
            "remote",
            "rev-parse",
            "show-ref",
            "status",
            "symbolic-ref",
            "worktree",
        }
    )

    def __init__(self, *, timeout_seconds: int = 60, git_executable: str | None = None):
        executable = git_executable or shutil.which("git", path=os.defpath)
        if executable is None:
            raise PreparationError("Git executable is unavailable")
        self.git_executable = str(Path(executable).resolve())
        self.timeout_seconds = timeout_seconds
        self.history: list[GitInvocation] = []

    def run(
        self,
        source: Path,
        arguments: Sequence[str],
        *,
        operation: str,
        allowed_return_codes: frozenset[int] = frozenset({0}),
    ) -> tuple[int, str]:
        if not arguments or arguments[0] not in self._ALLOWED_SUBCOMMANDS:
            raise PreparationError("Git subcommand is not permitted during preparation")
        if any(not isinstance(argument, str) or "\x00" in argument for argument in arguments):
            raise PreparationError("Git arguments must be NUL-free strings")
        argv = (
            self.git_executable,
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "credential.helper=",
            "-c",
            "credential.interactive=never",
            "-c",
            "http.extraHeader=",
            "-C",
            str(source),
            *arguments,
        )
        self.history.append(GitInvocation(operation=operation, argv=argv))
        environment = {
            "PATH": os.defpath,
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ASKPASS": os.devnull,
            "SSH_ASKPASS": os.devnull,
        }
        for name in ("SYSTEMROOT", "WINDIR", "TMPDIR", "TEMP", "TMP"):
            if name in os.environ:
                environment[name] = os.environ[name]
        try:
            completed = subprocess.run(
                list(argv),
                cwd=source,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PreparationError(f"Git operation {operation!r} could not complete") from exc
        if completed.returncode not in allowed_return_codes:
            raise GitCommandError(operation, completed.returncode)
        return completed.returncode, completed.stdout.strip()


class DeterministicPreparer:
    """Prepare one registered task in an isolated, exact-commit Git worktree."""

    _thread_locks_guard = threading.Lock()
    _thread_locks: dict[str, threading.Lock] = {}

    def __init__(
        self,
        store: SQLiteTaskStore,
        config: PreparationConfig,
        *,
        git: GitRunner | None = None,
    ):
        self.store = store
        self.config = config
        self.git = git or GitRunner(timeout_seconds=config.git_timeout_seconds)

    def prepare(self, task_id: str) -> PreparationRecord:
        request = self.store.get_request(task_id)
        trusted = self.config.repository_for(request.repository.url)
        self.config.workspace_root.mkdir(parents=True, exist_ok=True)
        with self._repository_lock(trusted):
            recorded = self.store.get_preparation(task_id)
            if recorded is not None:
                self._verify_record(request, trusted, recorded)
                return recorded

            self.store.start_preparation(task_id)
            source_common = self._verify_source(trusted)
            self._verify_remote_ref(request, trusted)
            self._ensure_task_ref(request, trusted, task_id)
            workspace = self.workspace_for_task(task_id)
            branch = branch_for_task(task_id)
            self._reconcile_worktree(
                trusted,
                request,
                task_id,
                source_common,
                workspace,
                branch,
            )
            record = PreparationRecord(
                task_id=task_id,
                repository_url=request.repository.url,
                base_ref=request.repository.base_ref,
                expected_commit=request.repository.expected_commit,
                baseline_commit=request.repository.expected_commit,
                source_path=str(trusted.source_path),
                workspace_path=str(workspace),
                local_branch=branch,
                prepared_at=utc_now(),
            )
            self.store.complete_preparation(record)
            return record

    def workspace_for_task(self, task_id: str) -> Path:
        return self.config.workspace_root / task_id / "repository"

    def _verify_record(
        self,
        request: TaskRequest,
        trusted: TrustedRepository,
        record: PreparationRecord,
    ) -> None:
        if (
            record.repository_url != request.repository.url
            or record.base_ref != request.repository.base_ref
            or record.expected_commit != request.repository.expected_commit
            or record.baseline_commit != request.repository.expected_commit
            or record.source_path != str(trusted.source_path)
            or record.workspace_path != str(self.workspace_for_task(record.task_id))
            or record.local_branch != branch_for_task(record.task_id)
        ):
            raise WorkspaceConflictError("recorded preparation does not match current trusted configuration")
        source_common = self._verify_source_identity(trusted)
        self._verify_workspace(
            trusted,
            Path(record.workspace_path),
            record.local_branch,
            record.baseline_commit,
            source_common,
        )

    def _verify_source(self, trusted: TrustedRepository) -> Path:
        source_common = self._verify_source_identity(trusted)
        _, bare = self.git.run(
            trusted.source_path,
            ["rev-parse", "--is-bare-repository"],
            operation="source_repository_kind",
        )
        if bare != "true":
            _, dirty = self.git.run(
                trusted.source_path,
                ["status", "--porcelain=v1", "--untracked-files=all"],
                operation="source_repository_cleanliness",
            )
            if dirty:
                raise RepositoryIdentityError("trusted source checkout is dirty")
        filter_code, filters = self.git.run(
            trusted.source_path,
            ["config", "--local", "--get-regexp", r"^filter\..*\.(smudge|process)$"],
            operation="source_checkout_filters",
            allowed_return_codes=frozenset({0, 1}),
        )
        if filter_code == 0 and filters:
            raise RepositoryIdentityError(
                "trusted source config defines checkout filters that preparation will not execute"
            )
        return source_common

    def _verify_source_identity(self, trusted: TrustedRepository) -> Path:
        if not trusted.source_path.is_dir():
            raise RepositoryIdentityError("trusted source repository is unavailable")
        _, common = self.git.run(
            trusted.source_path,
            ["rev-parse", "--git-common-dir"],
            operation="source_repository_identity",
        )
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = trusted.source_path / common_path
        common_path = common_path.resolve()
        _, origin = self.git.run(
            trusted.source_path,
            ["remote", "get-url", "origin"],
            operation="source_origin_identity",
        )
        if origin != trusted.origin_url:
            raise RepositoryIdentityError("trusted source origin does not match approved configuration")
        return common_path

    def _verify_remote_ref(self, request: TaskRequest, trusted: TrustedRepository) -> None:
        base_ref = request.repository.base_ref
        try:
            _, output = self.git.run(
                trusted.source_path,
                [
                    "ls-remote",
                    "--exit-code",
                    "--upload-pack=git-upload-pack",
                    "origin",
                    base_ref,
                    f"{base_ref}^{{}}",
                ],
                operation="resolve_remote_base_ref",
            )
        except GitCommandError as exc:
            raise ReferenceMismatchError("requested remote base reference is unavailable") from exc
        refs: dict[str, str] = {}
        for line in output.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                refs[parts[1]] = parts[0].lower()
        remote_commit = refs.get(f"{base_ref}^{{}}") or refs.get(base_ref)
        if remote_commit != request.repository.expected_commit:
            raise ReferenceMismatchError(
                "remote base reference does not match the registered expected commit"
            )

    def _ensure_task_ref(
        self,
        request: TaskRequest,
        trusted: TrustedRepository,
        task_id: str,
    ) -> None:
        internal_ref = fetched_ref_for_task(task_id)
        return_code, _ = self.git.run(
            trusted.source_path,
            ["show-ref", "--verify", "--quiet", internal_ref],
            operation="inspect_task_fetch_ref",
            allowed_return_codes=frozenset({0, 1}),
        )
        if return_code == 0:
            resolved = self._resolve_commit(trusted.source_path, internal_ref, "resolve_task_fetch_ref")
            if resolved != request.repository.expected_commit:
                raise ReferenceMismatchError("task-owned fetched ref collides with unexpected state")
            return
        try:
            self.git.run(
                trusted.source_path,
                [
                    "fetch",
                    "--no-tags",
                    "--upload-pack=git-upload-pack",
                    "origin",
                    f"{request.repository.base_ref}:{internal_ref}",
                ],
                operation="fetch_exact_base_ref",
            )
        except GitCommandError as exc:
            raise ReferenceMismatchError("remote base reference changed during fetch") from exc
        resolved = self._resolve_commit(trusted.source_path, internal_ref, "verify_fetched_base_ref")
        if resolved != request.repository.expected_commit:
            raise ReferenceMismatchError("fetched base reference does not match expected commit")

    def _reconcile_worktree(
        self,
        trusted: TrustedRepository,
        request: TaskRequest,
        task_id: str,
        source_common: Path,
        workspace: Path,
        branch: str,
    ) -> None:
        if workspace.is_symlink():
            raise WorkspaceConflictError("task workspace path is a symbolic link")
        branch_ref = f"refs/heads/{branch}"
        self.git.run(
            trusted.source_path,
            ["check-ref-format", branch_ref],
            operation="validate_local_task_branch",
        )
        branch_code, _ = self.git.run(
            trusted.source_path,
            ["show-ref", "--verify", "--quiet", branch_ref],
            operation="inspect_local_task_branch",
            allowed_return_codes=frozenset({0, 1}),
        )
        branch_exists = branch_code == 0
        if branch_exists:
            branch_commit = self._resolve_commit(
                trusted.source_path,
                branch_ref,
                "resolve_local_task_branch",
            )
            if branch_commit != request.repository.expected_commit:
                raise WorkspaceConflictError("local task branch exists at an unexpected commit")

        if os.path.lexists(workspace):
            if not branch_exists:
                raise WorkspaceConflictError("workspace exists without its task-owned branch")
            self._verify_workspace(
                trusted,
                workspace,
                branch,
                request.repository.expected_commit,
                source_common,
            )
            return

        task_directory = workspace.parent
        if task_directory.is_symlink() or (task_directory.exists() and not task_directory.is_dir()):
            raise WorkspaceConflictError("task workspace parent conflicts with unexpected state")
        if task_directory.exists() and any(task_directory.iterdir()):
            raise WorkspaceConflictError("task workspace parent is not empty")
        task_directory.mkdir(parents=True, exist_ok=True)

        if branch_exists:
            checked_out_paths = self._paths_for_branch(trusted.source_path, branch_ref)
            if checked_out_paths:
                raise WorkspaceConflictError("local task branch is already checked out elsewhere")
            arguments = ["worktree", "add", str(workspace), branch]
        else:
            arguments = [
                "worktree",
                "add",
                "-b",
                branch,
                str(workspace),
                request.repository.expected_commit,
            ]
        try:
            self.git.run(
                trusted.source_path,
                arguments,
                operation="create_task_worktree",
            )
        except GitCommandError as exc:
            raise WorkspaceConflictError("Git could not create the isolated task worktree") from exc
        self._verify_workspace(
            trusted,
            workspace,
            branch,
            request.repository.expected_commit,
            source_common,
        )

    def _verify_workspace(
        self,
        trusted: TrustedRepository,
        workspace: Path,
        branch: str,
        expected_commit: str,
        source_common: Path,
    ) -> None:
        if not workspace.is_dir() or workspace.is_symlink():
            raise WorkspaceConflictError("task workspace is missing or is not a normal directory")
        try:
            _, common = self.git.run(
                workspace,
                ["rev-parse", "--git-common-dir"],
                operation="workspace_repository_identity",
            )
            common_path = Path(common)
            if not common_path.is_absolute():
                common_path = workspace / common_path
            if common_path.resolve() != source_common:
                raise WorkspaceConflictError("workspace belongs to a different Git repository")
            head = self._resolve_commit(workspace, "HEAD", "workspace_head_identity")
            if head != expected_commit:
                raise WorkspaceConflictError("workspace HEAD differs from the immutable baseline")
            _, symbolic_ref = self.git.run(
                workspace,
                ["symbolic-ref", "--quiet", "HEAD"],
                operation="workspace_branch_identity",
            )
            if symbolic_ref != f"refs/heads/{branch}":
                raise WorkspaceConflictError("workspace is not on its task-owned branch")
            _, dirty = self.git.run(
                workspace,
                ["status", "--porcelain=v1", "--untracked-files=all"],
                operation="workspace_cleanliness",
            )
            if dirty:
                raise WorkspaceConflictError("task workspace is dirty")
        except GitCommandError as exc:
            raise WorkspaceConflictError("task workspace could not be verified") from exc

    def _paths_for_branch(self, source: Path, branch_ref: str) -> tuple[Path, ...]:
        _, output = self.git.run(
            source,
            ["worktree", "list", "--porcelain"],
            operation="inspect_registered_worktrees",
        )
        paths: list[Path] = []
        current_path: Path | None = None
        for line in output.splitlines():
            if line.startswith("worktree "):
                current_path = Path(line[len("worktree ") :]).resolve()
            elif line == f"branch {branch_ref}" and current_path is not None:
                paths.append(current_path)
        return tuple(paths)

    def _resolve_commit(self, source: Path, ref: str, operation: str) -> str:
        try:
            _, output = self.git.run(
                source,
                ["rev-parse", "--verify", f"{ref}^{{commit}}"],
                operation=operation,
            )
        except GitCommandError as exc:
            raise ReferenceMismatchError("Git reference does not resolve to a commit") from exc
        commit = output.lower()
        if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
            raise ReferenceMismatchError("Git returned an invalid commit identity")
        return commit

    @contextmanager
    def _repository_lock(self, trusted: TrustedRepository) -> Iterator[None]:
        digest = hashlib.sha256(trusted.repository_url.encode("utf-8")).hexdigest()
        lock_directory = self.config.workspace_root / ".locks"
        lock_directory.mkdir(parents=True, exist_ok=True)
        lock_path = lock_directory / f"{digest}.lock"
        key = str(lock_path)
        with self._thread_locks_guard:
            thread_lock = self._thread_locks.setdefault(key, threading.Lock())
        with thread_lock:
            with lock_path.open("a+b") as handle:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def branch_for_task(task_id: str) -> str:
    return f"openhands-shared/{task_id}"


def fetched_ref_for_task(task_id: str) -> str:
    return f"refs/openhands-shared/fetched/{task_id}"
