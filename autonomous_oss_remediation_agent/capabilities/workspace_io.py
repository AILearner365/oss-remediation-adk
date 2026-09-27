from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from ..evidence import EVIDENCE_EXCLUDED_DIRECTORIES, is_generated_evidence_path
from ..workspace import RepositoryWorkspace, RunWorkspace, TraceStore


_MODEL_RESULT_BUDGET_CHARS = 8_000


class WorkspaceIO:
    def __init__(
        self,
        workspace: RunWorkspace | RepositoryWorkspace,
        trace: TraceStore,
        max_file_bytes: int = 2_000_000,
        max_active_listing_cursors: int = 8,
    ):
        self.workspace = workspace
        self.trace = trace
        self.max_file_bytes = max_file_bytes
        self.max_active_listing_cursors = max(1, min(max_active_listing_cursors, 100))
        self._listing_cursors: dict[str, _ListingCursor] = {}
        self._search_cursors: dict[str, tuple[str, str, str | None, str, int]] = {}

    @property
    def workspace_kind(self) -> str:
        return getattr(self.workspace, "kind", "authoritative")

    @property
    def cycle(self) -> int | None:
        return getattr(self.workspace, "cycle", None)

    def _trace(self, event_type: str, **payload: Any) -> None:
        payload.setdefault("workspaceKind", self.workspace_kind)
        payload.setdefault("cycle", self.cycle)
        self.trace.append_event(event_type, **payload)

    def read_text(self, path: str, start_line: int = 1, end_line: int | None = None,
                  start_column: int = 1) -> dict[str, Any]:
        target = self.workspace.repository_path(path, allow_missing=False)
        if not target.is_file():
            raise ValueError(f"Not a file: {path}")
        size = target.stat().st_size
        if size > self.max_file_bytes:
            raise ValueError(f"File exceeds {self.max_file_bytes} byte read limit: {path}")
        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        start = max(1, start_line)
        if start_column < 1:
            raise ValueError("start_column must be positive")
        end = min(len(lines), end_line if end_line is not None else len(lines))
        requested_end = end
        selected_lines: list[str] = []
        chars = 0
        line_truncated = False
        for index, line in enumerate(lines[start - 1 : end]):
            if index == 0:
                line = line[start_column - 1:]
            if selected_lines and chars + len(line) + 1 > 8000:
                break
            if len(line) > 8000:
                selected_lines.append(line[:8000])
                chars += 8000
                line_truncated = True
                break
            selected_lines.append(line)
            chars += len(line) + 1
        end = start + len(selected_lines) - 1
        selected = "\n".join(selected_lines)
        result = {
            "status": "ok",
            "path": path.replace("\\", "/"),
            "startLine": start,
            "startColumn": start_column,
            "endLine": end,
            "totalLines": len(lines),
            "content": selected,
            "complete": not line_truncated and end >= (requested_end if requested_end is not None else len(lines)),
            "moreExists": line_truncated or end < len(lines),
            "nextStartLine": end if line_truncated else (end + 1 if end < len(lines) else None),
            "nextStartColumn": start_column + 8000 if line_truncated else 1,
        }
        result["workspaceKind"] = self.workspace_kind
        result["cycle"] = self.cycle
        self._trace("workspace_read", path=result["path"], startLine=start, endLine=end)
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
        oversized_entries: list[dict[str, Any]] = []
        result_chars = 0
        scanned_entries = 0
        exhausted = False
        response_budget_hit = False
        while scanned_entries < scan_limit and len(entries) + len(oversized_entries) < limit:
            try:
                if state.pending is not None:
                    candidate, is_file = state.pending
                    state.pending = None
                else:
                    candidate, is_file = next(state.iterator)
                    scanned_entries += 1
                    state.scanned_entries += 1
            except StopIteration:
                exhausted = True
                break
            except Exception:
                self._close_listing_cursor(cursor_id)
                raise
            if not is_file:
                continue
            relative = candidate.relative_to(self.workspace.repository).as_posix()
            if state.file_glob and not Path(relative).match(state.file_glob):
                continue
            entry_chars = len(json.dumps(relative))
            if entry_chars > _MODEL_RESULT_BUDGET_CHARS:
                display_entry = {
                    "resultIndex": len(entries) + len(oversized_entries),
                    "pathPrefix": relative[:160], "pathSuffix": relative[-80:],
                    "pathChars": len(relative),
                    "pathSha256": hashlib.sha256(relative.encode("utf-8", errors="surrogatepass")).hexdigest(),
                    "pathTruncated": True,
                }
                entry_chars = len(json.dumps(display_entry))
            else:
                display_entry = None
            if result_chars + entry_chars > _MODEL_RESULT_BUDGET_CHARS:
                state.pending = (candidate, is_file)
                response_budget_hit = True
                break
            if display_entry is None:
                entries.append(relative)
            else:
                oversized_entries.append(display_entry)
            result_chars += entry_chars
            state.matched_entries += 1

        if exhausted:
            self._close_listing_cursor(cursor_id)
            next_cursor = None
            truncation_reason = None
        else:
            next_cursor = cursor_id
            truncation_reason = ("RESPONSE_BUDGET" if response_budget_hit else
                                 "PAGE_LIMIT" if len(entries) + len(oversized_entries) >= limit else "SCAN_LIMIT")
        self._trace(
            "workspace_list",
            path=state.path,
            count=len(entries) + len(oversized_entries),
            oversizedCount=len(oversized_entries),
            cursor=cursor_id,
            nextCursor=next_cursor,
            fileGlob=state.file_glob,
            scannedEntries=scanned_entries,
            truncationReason=truncation_reason,
        )
        return {
            "status": "ok",
            "workspaceKind": self.workspace_kind,
            "cycle": self.cycle,
            "files": entries,
            "oversizedEntries": oversized_entries,
            "pathDetailsOmitted": bool(oversized_entries),
            "path": state.path,
            "fileGlob": state.file_glob,
            "cursor": cursor_id,
            "nextCursor": next_cursor,
            "totalMatches": state.matched_entries if exhausted else None,
            "totalMatchesExact": exhausted,
            "scannedEntries": scanned_entries,
            "cumulativeScannedEntries": state.scanned_entries,
            "truncated": not exhausted,
            "complete": exhausted,
            "moreExists": not exhausted,
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
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not query or len(query) > 500:
            raise ValueError("query must contain 1-500 characters")
        directory = self.workspace.repository_directory(path)
        relative_root = directory.relative_to(self.workspace.repository).as_posix()
        previous_path = ""
        previous_line = 0
        if cursor is not None:
            state = self._search_cursors.pop(cursor, None)
            if state is None or state[:3] != (query, relative_root, file_glob):
                raise ValueError("Unknown, expired, or mismatched search cursor")
            previous_path, previous_line = state[3:]
        result_limit = max(1, min(max_results, 500))
        file_limit = max(1, min(max_files, 20_000))
        results: list[dict[str, Any]] = []
        result_chars = 0
        searched_files = 0
        last_scanned_path = previous_path
        last_scanned_line = previous_line
        truncated = False
        truncation_reason = None
        for candidate in sorted(directory.rglob("*")):
            if searched_files >= file_limit:
                truncated = True
                truncation_reason = "FILE_LIMIT"
                break
            if (
                is_generated_evidence_path(candidate.relative_to(self.workspace.repository))
                or not candidate.is_file()
            ):
                continue
            if file_glob and not candidate.match(file_glob):
                continue
            relative = candidate.relative_to(self.workspace.repository).as_posix()
            if relative < previous_path:
                continue
            if candidate.stat().st_size > self.max_file_bytes:
                continue
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            if relative == previous_path and previous_line >= len(lines):
                continue
            searched_files += 1
            last_scanned_path = relative
            last_scanned_line = len(lines)
            for line_number, line in enumerate(lines, start=1):
                if relative == previous_path and line_number <= previous_line:
                    continue
                if query.casefold() not in line.casefold():
                    continue
                match = {"path": relative, "line": line_number, "text": line[:500]}
                match_chars = len(json.dumps(match))
                if match_chars > _MODEL_RESULT_BUDGET_CHARS:
                    raise ValueError("Search match exceeds response budget")
                if result_chars + match_chars > _MODEL_RESULT_BUDGET_CHARS:
                    truncated = True
                    truncation_reason = "RESPONSE_BUDGET"
                    break
                results.append(match)
                result_chars += match_chars
                if len(results) >= result_limit:
                    truncated = True
                    truncation_reason = "RESULT_LIMIT"
                    break
            if truncation_reason in {"RESPONSE_BUDGET", "RESULT_LIMIT"}:
                break
        self._trace(
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
            "workspaceKind": self.workspace_kind,
            "cycle": self.cycle,
            "query": query,
            "results": results,
            "searchedFiles": searched_files,
            "truncated": truncated,
            "truncationReason": truncation_reason,
            "complete": not truncated,
            "moreExists": truncated,
            "nextCursor": self._issue_search_cursor(query, relative_root, file_glob,
                                                      results[-1]["path"] if results and truncation_reason in {"RESPONSE_BUDGET", "RESULT_LIMIT"} else last_scanned_path,
                                                      results[-1]["line"] if results and truncation_reason in {"RESPONSE_BUDGET", "RESULT_LIMIT"} else last_scanned_line)
                          if truncated else None,
        }

    def _issue_search_cursor(self, query: str, path: str, file_glob: str | None,
                             last_path: str, last_line: int) -> str:
        if len(self._search_cursors) >= 8:
            self._search_cursors.pop(next(iter(self._search_cursors)))
        token = uuid.uuid4().hex
        self._search_cursors[token] = (query, path, file_glob, last_path, last_line)
        return token

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
            "workspaceKind": self.workspace_kind,
            "cycle": self.cycle,
            "action": normalized_action,
            "path": path.replace("\\", "/"),
            "beforeSha256": _sha256(before),
            "afterSha256": _sha256(after) if target.exists() else None,
            "bytes": len(after),
        }
        self._trace("workspace_edit", **result)
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
    pending: tuple[Path, bool] | None = None


def _walk_repository_entries(directory: Path) -> Iterator[tuple[Path, bool]]:
    iterators = [os.scandir(directory)]
    try:
        while iterators:
            try:
                entry = next(iterators[-1])
            except StopIteration:
                iterators.pop().close()
                continue
            if entry.name in EVIDENCE_EXCLUDED_DIRECTORIES:
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
