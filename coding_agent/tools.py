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


WORKING_DIRECTORY = Path(os.environ.get("CODING_AGENT_WORKSPACE", os.getcwd())).expanduser().resolve()
MAX_FILE_BYTES = 5_000_000
MAX_RESULTS = 500
MAX_OUTPUT_CHARS = 60_000


def _path(path: str, *, must_exist: bool = False) -> Path:
    value = Path(path or ".").expanduser()
    if not value.is_absolute():
        value = WORKING_DIRECTORY / value
    return value.resolve(strict=must_exist)


def _display_path(path: Path) -> str:
    try:
        relative = path.relative_to(WORKING_DIRECTORY)
        return "." if not relative.parts else relative.as_posix()
    except ValueError:
        return str(path)


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "error": message}


def list_files(
    path: str = ".",
    pattern: str = "*",
    max_depth: int = 3,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """List files and directories below a path.

    Relative paths start at the coding agent's working directory. Absolute paths are accepted.
    Results are bounded and may be filtered by a file-name glob.
    """
    try:
        target = _path(path, must_exist=True)
        if target.is_file():
            return {"status": "ok", "entries": [{"path": _display_path(target), "type": "file"}], "truncated": False}
        if not target.is_dir():
            return _error(f"Not a file or directory: {path}")

        entries: list[dict[str, str]] = []
        depth_limit = max(0, min(max_depth, 20))
        start_depth = len(target.parts)
        for current_root, directory_names, file_names in os.walk(target, followlinks=False):
            current = Path(current_root)
            depth = len(current.parts) - start_depth
            if not include_hidden:
                directory_names[:] = sorted(name for name in directory_names if not name.startswith("."))
            else:
                directory_names.sort()
            if depth >= depth_limit:
                directory_names[:] = []

            names = [(name, "directory") for name in directory_names]
            names.extend((name, "file") for name in sorted(file_names))
            for name, entry_type in names:
                if not include_hidden and name.startswith("."):
                    continue
                if fnmatch.fnmatch(name, pattern):
                    entries.append({"path": _display_path(current / name), "type": entry_type})
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
    """Search file contents or paths below a directory.

    The query is literal unless use_regex is true. Relative paths start at the working directory.
    """
    try:
        target = _path(path, must_exist=True)
        expression = re.compile(query if use_regex else re.escape(query), 0 if case_sensitive else re.IGNORECASE)
        result_limit = max(1, min(max_results, MAX_RESULTS))
        matches: list[dict[str, Any]] = []

        if target.is_file():
            candidates = [target]
        else:
            candidates = (
                candidate
                for candidate in target.rglob("*")
                if candidate.is_file() and ".git" not in candidate.parts
            )

        for candidate in candidates:
            if not fnmatch.fnmatch(candidate.name, file_pattern):
                continue
            display_path = _display_path(candidate)
            if search_names:
                if expression.search(display_path):
                    matches.append({"path": display_path})
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
                                "path": display_path,
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
    """Read a UTF-8 text file, optionally selecting a one-based inclusive line range."""
    try:
        target = _path(path, must_exist=True)
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
                "path": _display_path(target),
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
            "path": _display_path(target),
            "start_line": first,
            "end_line": last,
            "total_lines": len(lines),
            "content": selected,
        }
    except (OSError, UnicodeError, ValueError) as exc:
        return _error(str(exc))


def write_file(path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    """Create a UTF-8 text file, optionally overwriting an existing file."""
    try:
        target = _path(path)
        if target.exists() and not overwrite:
            return _error(f"File already exists; set overwrite=true to replace it: {path}")
        if target.exists() and not target.is_file():
            return _error(f"Not a file: {path}")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            return _error(f"Content exceeds the {MAX_FILE_BYTES}-byte write limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        return {"status": "ok", "path": _display_path(target), "bytes_written": len(encoded)}
    except (OSError, UnicodeError, ValueError) as exc:
        return _error(str(exc))


def edit_file(path: str, old_text: str, new_text: str, expected_occurrences: int = 1) -> dict[str, Any]:
    """Replace exact text in an existing UTF-8 file after checking its occurrence count."""
    try:
        target = _path(path, must_exist=True)
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
        return {"status": "ok", "path": _display_path(target), "replacements": occurrences}
    except (OSError, UnicodeError, ValueError) as exc:
        return _error(str(exc))


def _shell_command(command: str) -> list[str]:
    if os.name == "nt":
        return ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    return [shutil.which("bash") or "/bin/sh", "-lc", command]


def _bounded_output(value: str) -> tuple[str, bool]:
    if len(value) <= MAX_OUTPUT_CHARS:
        return value, False
    half = MAX_OUTPUT_CHARS // 2
    return value[:half] + "\n... output truncated ...\n" + value[-half:], True


_CONSEQUENTIAL_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)(?:sudo|runas|shutdown|reboot|format|rm|rmdir|del|erase|Remove-Item)(?:\.exe)?(?:\s|$)"
    r"|\bgit\s+(?:push|reset\s+--hard|clean\s+-[^\s]*f[^\s]*|checkout\s+--|restore\b)"
    r"|\b(?:winget|choco|apt|apt-get|yum|dnf|brew)\s+install\b"
    r"|\bnpm\s+(?:install|i)\b[^\r\n]*(?:--global|-g)\b"
    r"|\bpip(?:3)?\s+install\b[^\r\n]*(?:--user|--prefix|--root)\b",
    re.IGNORECASE | re.MULTILINE,
)


def shell_requires_confirmation(command: str, cwd: str = ".", timeout_seconds: int = 120) -> bool:
    """Require confirmation for destructive, privileged, publishing, or machine-wide commands."""
    del cwd, timeout_seconds
    return bool(_CONSEQUENTIAL_COMMAND.search(command))


def run_shell(command: str, cwd: str = ".", timeout_seconds: int = 120) -> dict[str, Any]:
    """Run a command using PowerShell on Windows or Bash on Unix.

    The process starts in cwd, resolved relative to the coding agent's working directory.
    This is a trusted host shell, not a filesystem sandbox.
    """
    if not command.strip():
        return _error("Command must not be empty")
    try:
        working_directory = _path(cwd, must_exist=True)
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
                "cwd": _display_path(working_directory),
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
                "cwd": _display_path(working_directory),
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
