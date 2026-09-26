from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WorkspaceBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class RunWorkspace:
    root: Path
    repository: Path
    artifacts: Path
    cache: Path
    temp: Path
    tools: Path

    @classmethod
    def create(cls, parent: str | Path, run_id: str | None = None) -> "RunWorkspace":
        identifier = run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        root = Path(parent).expanduser().resolve() / identifier
        root.mkdir(parents=True, exist_ok=False)
        workspace = cls(
            root=root,
            repository=root / "repository",
            artifacts=root / "artifacts",
            cache=root / "cache",
            temp=root / "temp",
            tools=root / "tools",
        )
        for directory in (
            workspace.investigation,
            workspace.artifacts,
            workspace.cache,
            workspace.temp,
            workspace.tools,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return workspace

    @property
    def investigation(self) -> Path:
        return self.root / "investigation"

    def fork_repository(self, cycle: int) -> "RepositoryWorkspace":
        if cycle < 1:
            raise ValueError("cycle must be positive")
        if not self.repository.is_dir():
            raise FileNotFoundError(self.repository)
        cycle_root = self.investigation / f"cycle-{cycle}"
        target = cycle_root / "repository"
        if cycle_root.exists():
            raise FileExistsError(f"Cycle investigation workspace already exists: {cycle_root}")
        cycle_root.mkdir(parents=True)
        shutil.copytree(self.repository, target, symlinks=True, copy_function=shutil.copy2)
        return RepositoryWorkspace(self, target, "experimental", cycle)

    def authoritative_repository(self) -> "RepositoryWorkspace":
        return RepositoryWorkspace(self, self.repository, "authoritative", None)

    def repository_path(self, relative_path: str | Path, *, allow_missing: bool = True) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            raise WorkspaceBoundaryError("Absolute paths are not allowed.")
        if any(part in {"", ".git"} for part in path.parts if part != "."):
            if ".git" in path.parts:
                raise WorkspaceBoundaryError("Direct .git access is not allowed.")
        if "\x00" in str(path):
            raise WorkspaceBoundaryError("NUL bytes are not allowed in paths.")
        candidate = self.repository / path
        resolved = _resolve_with_missing(candidate)
        repository_root = self.repository.resolve(strict=True)
        try:
            common = Path(os.path.commonpath((str(repository_root), str(resolved))))
        except ValueError as exc:
            raise WorkspaceBoundaryError("Path is outside the prepared repository.") from exc
        if common != repository_root:
            raise WorkspaceBoundaryError("Path is outside the prepared repository.")
        if not allow_missing and not candidate.exists():
            raise FileNotFoundError(candidate)
        return resolved

    def repository_directory(self, relative_path: str | Path = ".") -> Path:
        path = self.repository_path(relative_path, allow_missing=False)
        if not path.is_dir():
            raise WorkspaceBoundaryError(f"Working directory is not a directory: {relative_path}")
        return path


@dataclass(frozen=True)
class RepositoryWorkspace:
    run_workspace: RunWorkspace
    repository: Path
    kind: str
    cycle: int | None

    @property
    def root(self) -> Path:
        return self.run_workspace.root

    def repository_path(self, relative_path: str | Path, *, allow_missing: bool = True) -> Path:
        return _repository_path(self.repository, relative_path, allow_missing=allow_missing)

    def repository_directory(self, relative_path: str | Path = ".") -> Path:
        path = self.repository_path(relative_path, allow_missing=False)
        if not path.is_dir():
            raise WorkspaceBoundaryError(f"Working directory is not a directory: {relative_path}")
        return path


class TraceStore:
    def __init__(self, workspace: RunWorkspace):
        self.workspace = workspace
        self.events_path = workspace.artifacts / "events.jsonl"
        self._execution_environments: dict[str, dict[str, Any]] = {}

    def record_execution_environment(
        self, repository: Path, *, workspace_kind: str, cycle: int | None,
        resources: list[dict[str, str]], provenance: str,
    ) -> None:
        evidence = {"repository": str(repository.resolve()), "workspaceKind": workspace_kind,
                    "cycle": cycle, "resources": resources, "provenance": provenance}
        self._execution_environments[str(repository.resolve())] = evidence
        self.append_event("execution_environment_declared", **evidence)

    def execution_environment(self, repository: Path) -> dict[str, Any] | None:
        return self._execution_environments.get(str(repository.resolve()))

    def write_json(self, relative_path: str, value: Any) -> Path:
        path = self.workspace.artifacts / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return path

    def write_text(self, relative_path: str, value: str) -> Path:
        path = self.workspace.artifacts / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def append_event(self, event_type: str, **payload: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **payload,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_with_missing(path: Path) -> Path:
    missing: list[str] = []
    current = path
    while not current.exists():
        missing.append(current.name)
        if current.parent == current:
            break
        current = current.parent
    resolved = current.resolve(strict=True)
    for part in reversed(missing):
        resolved = resolved / part
    return resolved


def _repository_path(repository: Path, relative_path: str | Path, *, allow_missing: bool) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        raise WorkspaceBoundaryError("Absolute paths are not allowed.")
    if ".git" in path.parts:
        raise WorkspaceBoundaryError("Direct .git access is not allowed.")
    if "\x00" in str(path):
        raise WorkspaceBoundaryError("NUL bytes are not allowed in paths.")
    candidate = repository / path
    resolved = _resolve_with_missing(candidate)
    repository_root = repository.resolve(strict=True)
    try:
        common = Path(os.path.commonpath((str(repository_root), str(resolved))))
    except ValueError as exc:
        raise WorkspaceBoundaryError("Path is outside the prepared repository.") from exc
    if common != repository_root:
        raise WorkspaceBoundaryError("Path is outside the prepared repository.")
    if not allow_missing and not candidate.exists():
        raise FileNotFoundError(candidate)
    return resolved
