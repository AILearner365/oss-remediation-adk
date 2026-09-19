from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..workspace import RunWorkspace, TraceStore


class WorkspaceIO:
    def __init__(self, workspace: RunWorkspace, trace: TraceStore, max_file_bytes: int = 2_000_000):
        self.workspace = workspace
        self.trace = trace
        self.max_file_bytes = max_file_bytes

    def read_text(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
        target = self.workspace.repository_path(path, allow_missing=False)
        if not target.is_file():
            raise ValueError(f"Not a file: {path}")
        size = target.stat().st_size
        if size > self.max_file_bytes:
            raise ValueError(f"File exceeds {self.max_file_bytes} byte read limit: {path}")
        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        start = max(1, start_line)
        end = min(len(lines), end_line if end_line is not None else len(lines))
        selected = "\n".join(lines[start - 1 : end])
        result = {
            "status": "ok",
            "path": path.replace("\\", "/"),
            "startLine": start,
            "endLine": end,
            "totalLines": len(lines),
            "content": selected,
        }
        self.trace.append_event("workspace_read", path=result["path"], startLine=start, endLine=end)
        return result

    def list_files(
        self,
        path: str = ".",
        max_entries: int = 500,
        cursor: int = 0,
        file_glob: str | None = None,
    ) -> dict[str, Any]:
        directory = self.workspace.repository_directory(path)
        limit = max(1, min(max_entries, 2_000))
        offset = max(0, cursor)
        matches: list[str] = []
        for candidate in sorted(directory.rglob("*")):
            if ".git" in candidate.parts or not candidate.is_file():
                continue
            relative = candidate.relative_to(self.workspace.repository).as_posix()
            if file_glob and not candidate.match(file_glob):
                continue
            matches.append(relative)
        entries = matches[offset : offset + limit]
        next_cursor = offset + len(entries) if offset + len(entries) < len(matches) else None
        self.trace.append_event(
            "workspace_list",
            path=str(path),
            count=len(entries),
            cursor=offset,
            nextCursor=next_cursor,
            fileGlob=file_glob,
        )
        return {
            "status": "ok",
            "files": entries,
            "cursor": offset,
            "nextCursor": next_cursor,
            "totalMatches": len(matches),
            "truncated": next_cursor is not None,
        }

    def search_text(
        self,
        query: str,
        path: str = ".",
        file_glob: str | None = None,
        max_results: int = 100,
        max_files: int = 5_000,
    ) -> dict[str, Any]:
        if not query or len(query) > 500:
            raise ValueError("query must contain 1-500 characters")
        directory = self.workspace.repository_directory(path)
        result_limit = max(1, min(max_results, 500))
        file_limit = max(1, min(max_files, 20_000))
        results: list[dict[str, Any]] = []
        searched_files = 0
        truncated = False
        for candidate in sorted(directory.rglob("*")):
            if searched_files >= file_limit:
                truncated = True
                break
            if ".git" in candidate.parts or not candidate.is_file():
                continue
            if file_glob and not candidate.match(file_glob):
                continue
            if candidate.stat().st_size > self.max_file_bytes:
                continue
            searched_files += 1
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(lines, start=1):
                if query.casefold() not in line.casefold():
                    continue
                results.append(
                    {
                        "path": candidate.relative_to(self.workspace.repository).as_posix(),
                        "line": line_number,
                        "text": line[:500],
                    }
                )
                if len(results) >= result_limit:
                    truncated = True
                    break
            if len(results) >= result_limit:
                break
        self.trace.append_event(
            "workspace_search",
            path=str(path),
            query=query,
            fileGlob=file_glob,
            searchedFiles=searched_files,
            resultCount=len(results),
            truncated=truncated,
        )
        return {
            "status": "ok",
            "query": query,
            "results": results,
            "searchedFiles": searched_files,
            "truncated": truncated,
        }

    def edit_text(
        self,
        action: str,
        path: str,
        content: str | None = None,
        old_text: str | None = None,
        new_text: str | None = None,
        expected_occurrences: int = 1,
    ) -> dict[str, Any]:
        normalized_action = action.lower().strip()
        target = self.workspace.repository_path(path, allow_missing=True)
        before = target.read_bytes() if target.exists() and target.is_file() else b""
        if len(before) > self.max_file_bytes:
            raise ValueError(f"File exceeds {self.max_file_bytes} byte edit limit: {path}")
        if normalized_action == "write":
            if content is None:
                raise ValueError("content is required for write")
            encoded = content.encode("utf-8")
            self._write(target, encoded)
        elif normalized_action == "replace":
            if not target.is_file():
                raise ValueError(f"File does not exist: {path}")
            if old_text is None or new_text is None:
                raise ValueError("old_text and new_text are required for replace")
            current = before.decode("utf-8")
            occurrences = current.count(old_text)
            if occurrences != expected_occurrences:
                raise ValueError(f"Expected {expected_occurrences} occurrences, found {occurrences}")
            self._write(target, current.replace(old_text, new_text).encode("utf-8"))
        elif normalized_action == "delete":
            if target.exists():
                if not target.is_file():
                    raise ValueError("Only file deletion is supported")
                target.unlink()
        else:
            raise ValueError("action must be write, replace, or delete")
        after = target.read_bytes() if target.exists() else b""
        result = {
            "status": "ok",
            "action": normalized_action,
            "path": path.replace("\\", "/"),
            "beforeSha256": _sha256(before),
            "afterSha256": _sha256(after) if target.exists() else None,
            "bytes": len(after),
        }
        self.trace.append_event("workspace_edit", **result)
        return result

    def _write(self, target: Path, content: bytes) -> None:
        if len(content) > self.max_file_bytes:
            raise ValueError(f"Content exceeds {self.max_file_bytes} byte edit limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        checked_target = self.workspace.repository_path(target.relative_to(self.workspace.repository), allow_missing=True)
        checked_target.write_bytes(content)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
