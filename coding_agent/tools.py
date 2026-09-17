from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

from google.adk.tools import FunctionTool


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
MAX_FILE_BYTES = 5_000_000
MAX_RESULTS = 500
MAX_OUTPUT_CHARS = 60_000

_SKIPPED_DIRECTORIES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}

_ALWAYS_BLOCKED_COMMANDS = (
    (re.compile(r"(^|[;&|]\s*)sudo(?:\s|$)", re.IGNORECASE), "privilege elevation is not allowed"),
    (re.compile(r"(^|[;&|]\s*)runas(?:\.exe)?(?:\s|$)", re.IGNORECASE), "privilege elevation is not allowed"),
    (re.compile(r"\b(?:shutdown|reboot|format)(?:\.exe)?(?:\s|$)", re.IGNORECASE), "machine-level destructive commands are not allowed"),
    (re.compile(r"\b(?:winget|choco)(?:\.exe)?\s+install\b", re.IGNORECASE), "global package installation is not allowed"),
    (re.compile(r"\bnpm\s+(?:install|i)\s+(?:--global|-g)\b", re.IGNORECASE), "global package installation is not allowed"),
    (re.compile(r"\bpip(?:3)?\s+install\b[^\r\n]*(?:--user|--prefix|--root)\b", re.IGNORECASE), "non-workspace package installation is not allowed"),
)

_CONFIRMATION_PATTERNS = (
    re.compile(r"\bgit\s+(?:push|reset\s+--hard|clean\s+-[^\s]*[fd]|checkout\s+--|restore\s+--source)\b", re.IGNORECASE),
    re.compile(r"\b(?:rm|rmdir)(?:\.exe)?\b", re.IGNORECASE),
    re.compile(r"\bRemove-Item\b", re.IGNORECASE),
    re.compile(r"\b(?:del|erase)(?:\.exe)?\b", re.IGNORECASE),
    re.compile(r"\b(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod)\b", re.IGNORECASE),
)


def _resolve_workspace_path(path: str, *, must_exist: bool = False) -> Path:
    raw_path = Path(path or ".")
    candidate = raw_path if raw_path.is_absolute() else WORKSPACE_ROOT / raw_path
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise ValueError(f"Path is outside the repository workspace: {path}") from exc
    return resolved


def _relative_path(path: Path) -> str:
    relative = path.relative_to(WORKSPACE_ROOT)
    return "." if not relative.parts else relative.as_posix()


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "error": message}


def list_files(
    path: str = ".",
    pattern: str = "*",
    max_depth: int = 3,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """List repository files and directories below a repository-relative path.

    Args:
        path: Repository-relative directory or file to inspect.
        pattern: Glob matched against each entry name, such as ``*.py``.
        max_depth: Maximum directory depth to traverse, from 0 through 10.
        include_hidden: Include dot-prefixed entries and common generated directories.
    """
    try:
        target = _resolve_workspace_path(path, must_exist=True)
        depth_limit = max(0, min(max_depth, 10))
        if target.is_file():
            return {"status": "ok", "entries": [{"path": _relative_path(target), "type": "file"}], "truncated": False}
        if not target.is_dir():
            return _error(f"Not a file or directory: {path}")

        entries: list[dict[str, str]] = []
        start_depth = len(target.parts)
        for current_root, directory_names, file_names in os.walk(target, followlinks=False):
            current = Path(current_root)
            depth = len(current.parts) - start_depth
            directory_names[:] = sorted(
                name
                for name in directory_names
                if include_hidden or (not name.startswith(".") and name not in _SKIPPED_DIRECTORIES)
            )
            if depth >= depth_limit:
                directory_names[:] = []

            names = [(name, "directory") for name in directory_names]
            names.extend((name, "file") for name in sorted(file_names))
            for name, entry_type in names:
                if not include_hidden and name.startswith("."):
                    continue
                if fnmatch.fnmatch(name, pattern):
                    entries.append({"path": _relative_path(current / name), "type": entry_type})
                    if len(entries) >= MAX_RESULTS:
                        return {"status": "ok", "entries": entries, "truncated": True}
        return {"status": "ok", "entries": entries, "truncated": False}
    except (OSError, ValueError) as exc:
        return _error(str(exc))


def search_files(
    query: str,
    path: str = ".",
    file_pattern: str = "*",
    search_names: bool = False,
    use_regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = 100,
) -> dict[str, Any]:
    """Search repository file contents or paths and return bounded matches.

    Args:
        query: Text or regular expression to find.
        path: Repository-relative file or directory to search.
        file_pattern: Glob limiting files, such as ``*.py``.
        search_names: Search repository-relative paths instead of file contents.
        use_regex: Interpret query as a regular expression.
        case_sensitive: Use case-sensitive matching.
        max_results: Maximum matches to return, from 1 through 500.
    """
    try:
        target = _resolve_workspace_path(path, must_exist=True)
        result_limit = max(1, min(max_results, MAX_RESULTS))
        flags = 0 if case_sensitive else re.IGNORECASE
        expression = re.compile(query if use_regex else re.escape(query), flags)
        matches: list[dict[str, Any]] = []

        candidates = [target] if target.is_file() else (
            candidate
            for candidate in target.rglob("*")
            if candidate.is_file()
            and not any(part in _SKIPPED_DIRECTORIES for part in candidate.relative_to(target).parts)
        )
        for candidate in candidates:
            try:
                candidate = _resolve_workspace_path(str(candidate), must_exist=True)
            except ValueError:
                continue
            relative = _relative_path(candidate)
            if not fnmatch.fnmatch(candidate.name, file_pattern):
                continue
            if search_names:
                if expression.search(relative):
                    matches.append({"path": relative})
            else:
                if candidate.stat().st_size > MAX_FILE_BYTES:
                    continue
                try:
                    content = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                if "\x00" in content:
                    continue
                for line_number, line in enumerate(content.splitlines(), start=1):
                    found = expression.search(line)
                    if found:
                        matches.append(
                            {
                                "path": relative,
                                "line": line_number,
                                "column": found.start() + 1,
                                "text": line[:500],
                            }
                        )
                        if len(matches) >= result_limit:
                            return {"status": "ok", "matches": matches, "truncated": True}
            if len(matches) >= result_limit:
                return {"status": "ok", "matches": matches, "truncated": True}
        return {"status": "ok", "matches": matches, "truncated": False}
    except (OSError, ValueError, re.error) as exc:
        return _error(str(exc))


def read_file(path: str, start_line: int = 1, end_line: int = 0) -> dict[str, Any]:
    """Read a bounded UTF-8 text range from a repository-relative file.

    Args:
        path: Repository-relative file path.
        start_line: First line to return, using one-based numbering.
        end_line: Last line to return inclusively, or 0 for the end of the file.
    """
    try:
        target = _resolve_workspace_path(path, must_exist=True)
        if not target.is_file():
            return _error(f"Not a file: {path}")
        if target.stat().st_size > MAX_FILE_BYTES:
            return _error(f"File exceeds the {MAX_FILE_BYTES}-byte read limit: {path}")
        content = target.read_text(encoding="utf-8")
        if "\x00" in content:
            return _error(f"Binary files are not supported: {path}")
        lines = content.splitlines()
        if not lines:
            return {
                "status": "ok",
                "path": _relative_path(target),
                "start_line": 1,
                "end_line": 0,
                "total_lines": 0,
                "content": "",
            }
        first = max(1, start_line)
        last = len(lines) if end_line <= 0 else min(end_line, len(lines))
        if first > len(lines) or last < first:
            return _error(f"Invalid line range {first}-{last} for a {len(lines)}-line file")
        selected = "\n".join(f"{number:6d}\t{lines[number - 1]}" for number in range(first, last + 1))
        return {
            "status": "ok",
            "path": _relative_path(target),
            "start_line": first,
            "end_line": last,
            "total_lines": len(lines),
            "content": selected,
        }
    except (OSError, UnicodeError, ValueError) as exc:
        return _error(str(exc))


def write_file(path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    """Create a UTF-8 text file inside the repository, optionally overwriting it.

    Args:
        path: Repository-relative destination path.
        content: Complete text to write.
        overwrite: Allow replacing an existing file when true.
    """
    try:
        target = _resolve_workspace_path(path)
        if target.exists() and not overwrite:
            return _error(f"File already exists; set overwrite=true to replace it: {path}")
        if target.exists() and not target.is_file():
            return _error(f"Not a file: {path}")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            return _error(f"Content exceeds the {MAX_FILE_BYTES}-byte write limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        _resolve_workspace_path(str(target.parent), must_exist=True)
        target.write_bytes(encoded)
        return {"status": "ok", "path": _relative_path(target), "bytes_written": len(encoded)}
    except (OSError, UnicodeError, ValueError) as exc:
        return _error(str(exc))


def edit_file(
    path: str,
    old_text: str,
    new_text: str,
    expected_occurrences: int = 1,
) -> dict[str, Any]:
    """Replace exact text in an existing repository file.

    Args:
        path: Repository-relative text file to edit.
        old_text: Exact text to replace; include context when it is not unique.
        new_text: Replacement text.
        expected_occurrences: Required occurrence count before any write occurs.
    """
    try:
        target = _resolve_workspace_path(path, must_exist=True)
        if not target.is_file():
            return _error(f"Not a file: {path}")
        if not old_text:
            return _error("old_text must not be empty")
        if target.stat().st_size > MAX_FILE_BYTES:
            return _error(f"File exceeds the {MAX_FILE_BYTES}-byte edit limit: {path}")
        with target.open("r", encoding="utf-8", newline="") as file:
            content = file.read()
        occurrences = content.count(old_text)
        if occurrences != expected_occurrences:
            return _error(f"Expected {expected_occurrences} occurrences but found {occurrences}; no changes made")
        updated = content.replace(old_text, new_text)
        if len(updated.encode("utf-8")) > MAX_FILE_BYTES:
            return _error(f"Edited content exceeds the {MAX_FILE_BYTES}-byte limit")
        with target.open("w", encoding="utf-8", newline="") as file:
            file.write(updated)
        return {"status": "ok", "path": _relative_path(target), "replacements": occurrences}
    except (OSError, UnicodeError, ValueError) as exc:
        return _error(str(exc))


def _shell_command(command: str) -> list[str]:
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
    shell = shutil.which("bash") or "/bin/sh"
    return [shell, "-lc", command]


def _bounded_output(value: str) -> tuple[str, bool]:
    if len(value) <= MAX_OUTPUT_CHARS:
        return value, False
    half = MAX_OUTPUT_CHARS // 2
    return value[:half] + "\n... output truncated ...\n" + value[-half:], True


def _blocked_command_reason(command: str) -> str | None:
    if not command.strip():
        return "Command must not be empty"
    for pattern, reason in _ALWAYS_BLOCKED_COMMANDS:
        if pattern.search(command):
            return reason
    return None


def shell_requires_confirmation(command: str, cwd: str = ".", timeout_seconds: int = 120) -> bool:
    """Return whether a shell request is destructive or externally mutating."""
    del cwd, timeout_seconds
    return any(pattern.search(command) for pattern in _CONFIRMATION_PATTERNS)


def run_shell(command: str, cwd: str = ".", timeout_seconds: int = 120) -> dict[str, Any]:
    """Run a host-native shell command from a directory inside the repository.

    Use this general tool for Python, tests, builds, Git inspection, and repository-local scripts.
    Common non-destructive commands run without confirmation; destructive or externally mutating
    commands require ADK confirmation, and machine-level dangerous commands are blocked.

    Args:
        command: Command line interpreted by PowerShell on Windows or Bash on Unix.
        cwd: Repository-relative working directory.
        timeout_seconds: Execution timeout from 1 through 900 seconds.
    """
    try:
        reason = _blocked_command_reason(command)
        if reason:
            return _error(f"Command blocked: {reason}")
        working_directory = _resolve_workspace_path(cwd, must_exist=True)
        if not working_directory.is_dir():
            return _error(f"Working directory is not a directory: {cwd}")
        timeout = max(1, min(timeout_seconds, 900))
        started = time.monotonic()
        try:
            completed = subprocess.run(
                _shell_command(command),
                cwd=working_directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            stdout, stdout_truncated = _bounded_output(completed.stdout)
            stderr, stderr_truncated = _bounded_output(completed.stderr)
            return {
                "status": "ok" if completed.returncode == 0 else "error",
                "command": command,
                "cwd": _relative_path(working_directory),
                "exit_code": completed.returncode,
                "duration_seconds": round(time.monotonic() - started, 3),
                "stdout": stdout,
                "stderr": stderr,
                "output_truncated": stdout_truncated or stderr_truncated,
            }
        except subprocess.TimeoutExpired as exc:
            stdout, _ = _bounded_output(exc.stdout or "")
            stderr, _ = _bounded_output(exc.stderr or "")
            return {
                "status": "error",
                "command": command,
                "cwd": _relative_path(working_directory),
                "exit_code": 124,
                "duration_seconds": round(time.monotonic() - started, 3),
                "stdout": stdout,
                "stderr": stderr,
                "error": f"Command timed out after {timeout} seconds",
            }
    except (OSError, ValueError) as exc:
        return _error(str(exc))


REPOSITORY_TOOLS = [
    FunctionTool(list_files),
    FunctionTool(search_files),
    FunctionTool(read_file),
    FunctionTool(write_file),
    FunctionTool(edit_file),
    FunctionTool(run_shell, require_confirmation=shell_requires_confirmation),
]
