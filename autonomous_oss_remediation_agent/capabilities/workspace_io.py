from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from ..workspace import RunWorkspace, TraceStore


class WorkspaceIO:
    def __init__(
        self,
        workspace: RunWorkspace,
        trace: TraceStore,
        max_file_bytes: int = 2_000_000,
        max_active_listing_cursors: int = 8,
    ):
        self.workspace = workspace
        self.trace = trace
        self.max_file_bytes = max_file_bytes
        self.max_active_listing_cursors = max(1, min(max_active_listing_cursors, 100))
        self._listing_cursors: dict[str, _ListingCursor] = {}

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
        cursor: str | int | None = None,
        file_glob: str | None = None,
        max_scanned_entries: int = 5_000,
    ) -> dict[str, Any]:
        limit = max(1, min(max_entries, 2_000))
        scan_limit = max(1, min(max_scanned_entries, 20_000))
        if cursor in {None, 0, ""}:
            directory = self.workspace.repository_directory(path)
            while len(self._listing_cursors) >= self.max_active_listing_cursors:
                oldest_cursor = next(iter(self._listing_cursors))
                self._close_listing_cursor(oldest_cursor)
            cursor_id = uuid.uuid4().hex
            state = _ListingCursor(
                iterator=_walk_repository_entries(directory),
                path=directory.relative_to(self.workspace.repository).as_posix() or ".",
                file_glob=file_glob,
            )
            self._listing_cursors[cursor_id] = state
        else:
            cursor_id = str(cursor)
            state = self._listing_cursors.get(cursor_id)
            if state is None:
                raise ValueError(
                    "Expired, evicted, unknown, or completed listing cursor; start a new listing"
                )

        entries: list[str] = []
        scanned_entries = 0
        exhausted = False
        while scanned_entries < scan_limit and len(entries) < limit:
            try:
                candidate, is_file = next(state.iterator)
            except StopIteration:
                exhausted = True
                break
            except Exception:
                self._close_listing_cursor(cursor_id)
                raise
            scanned_entries += 1
            state.scanned_entries += 1
            if not is_file:
                continue
            relative = candidate.relative_to(self.workspace.repository).as_posix()
            if state.file_glob and not Path(relative).match(state.file_glob):
                continue
            entries.append(relative)
            state.matched_entries += 1

        if exhausted:
            self._close_listing_cursor(cursor_id)
            next_cursor = None
            truncation_reason = None
        else:
            next_cursor = cursor_id
            truncation_reason = "PAGE_LIMIT" if len(entries) >= limit else "SCAN_LIMIT"
        self.trace.append_event(
            "workspace_list",
            path=state.path,
            count=len(entries),
            cursor=cursor_id,
            nextCursor=next_cursor,
            fileGlob=state.file_glob,
            scannedEntries=scanned_entries,
            truncationReason=truncation_reason,
        )
        return {
            "status": "ok",
            "files": entries,
            "path": state.path,
            "fileGlob": state.file_glob,
            "cursor": cursor_id,
            "nextCursor": next_cursor,
            "totalMatches": state.matched_entries if exhausted else None,
            "totalMatchesExact": exhausted,
            "scannedEntries": scanned_entries,
            "cumulativeScannedEntries": state.scanned_entries,
            "truncated": not exhausted,
            "truncationReason": truncation_reason,
        }

    def _close_listing_cursor(self, cursor_id: str) -> None:
        state = self._listing_cursors.pop(cursor_id, None)
        if state is None:
            return
        close = getattr(state.iterator, "close", None)
        if close is not None:
            close()

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


@dataclass
class _ListingCursor:
    iterator: Iterator[tuple[Path, bool]]
    path: str
    file_glob: str | None
    scanned_entries: int = 0
    matched_entries: int = 0


def _walk_repository_entries(directory: Path) -> Iterator[tuple[Path, bool]]:
    iterators = [os.scandir(directory)]
    try:
        while iterators:
            try:
                entry = next(iterators[-1])
            except StopIteration:
                iterators.pop().close()
                continue
            if entry.name == ".git":
                continue
            candidate = Path(entry.path)
            is_directory = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
            yield candidate, is_file
            if is_directory:
                iterators.append(os.scandir(candidate))
    finally:
        for iterator in iterators:
            iterator.close()
