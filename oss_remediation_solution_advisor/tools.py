from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = Path(
    os.getenv("OSS_REPO_ROOT", str(_DEFAULT_REPOSITORY_ROOT))
).expanduser().resolve()

_ALLOWED_SUFFIXES = {
    ".py",
    ".java",
    ".kt",
    ".kts",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".xml",
    ".properties",
    ".gradle",
    ".cfg",
    ".ini",
}
_ALLOWED_FILENAMES = {"Dockerfile", "Jenkinsfile", "Makefile", "pom.xml"}
_BLOCKED_NAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    "service-account.json",
    "service_account.json",
    "id_rsa",
    "id_ed25519",
}
_BLOCKED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "secrets",
    "workspace",
    "target",
    "build",
}
_BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
_MAX_FILE_BYTES = 512_000
_MAX_READ_LINES = 200
_MAX_LIST_RESULTS = 200
_MAX_SEARCH_RESULTS = 50
_MAX_SCANNED_FILES = 1_500


def _resolve_path(relative_path: str = "") -> Path:
    """Resolve a user-supplied path and keep it inside the configured repository."""
    candidate = Path(relative_path or ".")
    if candidate.is_absolute():
        raise ValueError("Use a repository-relative path, not an absolute path.")

    resolved = (_REPOSITORY_ROOT / candidate).resolve()
    try:
        resolved.relative_to(_REPOSITORY_ROOT)
    except ValueError as exc:
        raise ValueError("The requested path is outside the repository.") from exc
    return resolved


def _relative(path: Path) -> str:
    return path.relative_to(_REPOSITORY_ROOT).as_posix()


def _is_blocked(path: Path) -> bool:
    relative = path.relative_to(_REPOSITORY_ROOT)
    parts_lower = {part.lower() for part in relative.parts}
    name_lower = path.name.lower()

    if parts_lower.intersection(_BLOCKED_PARTS):
        return True
    if name_lower in _BLOCKED_NAMES or name_lower.startswith(".env"):
        return True
    if path.suffix.lower() in _BLOCKED_SUFFIXES:
        return True
    return False


def _is_readable_file(path: Path) -> bool:
    if not path.is_file() or _is_blocked(path):
        return False
    if path.name not in _ALLOWED_FILENAMES and path.suffix.lower() not in _ALLOWED_SUFFIXES:
        return False
    try:
        return path.stat().st_size <= _MAX_FILE_BYTES
    except OSError:
        return False


def _iter_readable_files(root: Path):
    scanned = 0
    for path in sorted(root.rglob("*")):
        if scanned >= _MAX_SCANNED_FILES:
            break
        if path.is_file():
            scanned += 1
            if _is_readable_file(path):
                yield path


def list_repository_files(relative_path: str = "", max_results: int = 100) -> dict:
    """List readable source and documentation files under a local repository path."""
    root = _resolve_path(relative_path)
    if not root.exists():
        return {"error": "Path not found.", "path": relative_path}
    if _is_blocked(root):
        return {"error": "Access to this path is blocked.", "path": relative_path}

    limit = max(1, min(int(max_results), _MAX_LIST_RESULTS))
    if root.is_file():
        files = [_relative(root)] if _is_readable_file(root) else []
    else:
        files = [_relative(path) for path in _iter_readable_files(root)][:limit]

    return {
        "path": relative_path or ".",
        "files": files,
        "count": len(files),
        "limited": len(files) == limit,
    }


def read_repository_file(
    path: str,
    start_line: int = 1,
    end_line: int = 200,
) -> dict:
    """Read a bounded line range from an approved local repository text file."""
    resolved = _resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {"error": "File not found.", "path": path}
    if not _is_readable_file(resolved):
        return {"error": "This file type, size, or path is not allowed.", "path": path}

    start = max(1, int(start_line))
    end = max(start, int(end_line))
    end = min(end, start + _MAX_READ_LINES - 1)

    try:
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"error": f"Unable to read file: {exc}", "path": path}

    selected = lines[start - 1 : end]
    numbered = [f"{number}: {line}" for number, line in enumerate(selected, start=start)]
    return {
        "path": _relative(resolved),
        "start_line": start,
        "end_line": start + len(selected) - 1 if selected else start,
        "total_lines": len(lines),
        "content": "\n".join(numbered),
    }


def search_repository_code(
    query: str,
    relative_path: str = "",
    max_results: int = 25,
) -> dict:
    """Search readable local repository files and return short matching line snippets."""
    term = query.strip()
    if len(term) < 2:
        return {"error": "Search query must contain at least two characters."}

    root = _resolve_path(relative_path)
    if not root.exists():
        return {"error": "Path not found.", "path": relative_path}
    if _is_blocked(root):
        return {"error": "Access to this path is blocked.", "path": relative_path}

    limit = max(1, min(int(max_results), _MAX_SEARCH_RESULTS))
    matches: list[dict[str, object]] = []
    files = [root] if root.is_file() else _iter_readable_files(root)
    needle = term.casefold()

    for file_path in files:
        if not _is_readable_file(file_path):
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        for line_number, line in enumerate(lines, start=1):
            if needle in line.casefold():
                snippet = line.strip()
                if len(snippet) > 240:
                    snippet = snippet[:237] + "..."
                matches.append(
                    {
                        "path": _relative(file_path),
                        "line": line_number,
                        "snippet": snippet,
                    }
                )
                if len(matches) >= limit:
                    return {
                        "query": term,
                        "matches": matches,
                        "count": len(matches),
                        "limited": True,
                    }

    return {
        "query": term,
        "matches": matches,
        "count": len(matches),
        "limited": False,
    }
