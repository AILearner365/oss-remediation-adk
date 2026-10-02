"""Bounded summaries of Git unified text diffs, with explicit parsing limits."""
from __future__ import annotations

import re


_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@(?:.*)$")
_METADATA = ("index ", "old mode ", "new mode ", "new file mode ",
             "deleted file mode ", "similarity index ", "dissimilarity index ",
             "rename from ", "rename to ", "copy from ", "copy to ")
_METADATA_ONLY = ("old mode ", "new mode ", "new file mode ", "deleted file mode ",
                  "rename from ", "rename to ", "copy from ", "copy to ")


def parse_line_changes(diff: str) -> list[dict]:
    """Count hunk lines, keeping at most 12 added and 20 removed raw excerpts.

    Binary/combined diffs and malformed hunks have unknown counts, never zero
    changes. No semantic conclusions about the changed text are inferred.
    """
    changes: list[dict] = []
    current = None
    remaining = None
    headers = 0
    hunks = 0
    metadata_only = False
    can_mark_newline = False

    def fail(status: str, reason: str) -> None:
        current.update(summaryStatus=status, summaryError=reason, countsComplete=False,
                       addedCount=None, removedCount=None)

    def finish() -> None:
        if current is not None and current["countsComplete"]:
            if remaining is not None and any(remaining):
                fail("unparseable", "Hunk ended before its declared line counts were consumed.")
            elif not hunks and not metadata_only:
                fail("unparseable", "File section contains no supported hunks or metadata-only change.")
            elif headers == 1:
                fail("unparseable", "Incomplete unified file headers.")

    # Split only on LF: other Unicode line separators can be literal file content.
    for line in diff.split("\n"):
        if line.startswith(("diff --git ", "diff --cc ", "diff --combined ")):
            finish()
            current = {"file": line.split(" b/", 1)[-1] if line.startswith("diff --git ") else None,
                       "addedCount": 0, "removedCount": 0, "addedExcerpts": [], "removedExcerpts": [],
                       "countsComplete": True, "summaryStatus": "parsed"}
            changes.append(current)
            remaining, headers, hunks, metadata_only, can_mark_newline = None, 0, 0, False, False
            if not line.startswith("diff --git "):
                fail("unsupported", "Combined diff is not a two-sided unified text diff.")
            continue
        if current is None:
            if not line:
                continue
            current = {"file": None, "addedExcerpts": [], "removedExcerpts": []}
            changes.append(current)
            fail("unsupported", "Content outside a supported Git diff file section.")
        if not current["countsComplete"]:
            continue
        if line == "\\ No newline at end of file" and can_mark_newline:
            can_mark_newline = False
            continue
        can_mark_newline = False
        if remaining is not None and any(remaining):
            prefix = line[:1]
            if prefix not in {"+", "-", " "}:
                fail("unparseable", "Invalid or truncated unified hunk content.")
                continue
            old, new = remaining
            old -= prefix in {"-", " "}
            new -= prefix in {"+", " "}
            if old < 0 or new < 0:
                fail("unparseable", "Hunk content exceeds its declared line counts.")
                continue
            remaining = (old, new)
            can_mark_newline = True
            if prefix in {"+", "-"}:
                kind, limit = ("added", 12) if prefix == "+" else ("removed", 20)
                current[kind + "Count"] += 1
                if len(current[kind + "Excerpts"]) < limit:
                    current[kind + "Excerpts"].append(line[1:])
            continue
        remaining = None
        match = _HUNK.fullmatch(line)
        if match and headers == 2:
            remaining = tuple(int(value) if value is not None else 1 for value in match.groups())
            hunks += 1
        elif line.startswith("--- ") and not hunks and headers == 0:
            headers = 1
            current["file"] = line[6:] if line.startswith("--- a/") else line[4:]
        elif line.startswith("+++ ") and not hunks and headers == 1:
            headers = 2
            if line != "+++ /dev/null":
                current["file"] = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith(("GIT binary patch", "Binary files ", "@@@")):
            fail("unsupported", "Binary or combined content has no supported text-line summary.")
        elif not hunks and not headers and line.startswith(_METADATA):
            metadata_only |= line.startswith(_METADATA_ONLY)
        elif line:
            fail("unparseable", "Unexpected content outside a unified hunk.")
    finish()
    return changes


def bound_line_changes(changes: list[dict], added_limit: int, removed_limit: int) -> list[dict]:
    """Apply the same character and completeness rules to either summary level."""
    result = []
    for change in changes:
        bounded = dict(change)
        for kind, limit in (("added", added_limit), ("removed", removed_limit)):
            excerpts = change[kind + "Excerpts"][:limit]
            clipped = sum(len(line) > 160 for line in excerpts)
            bounded[kind + "Excerpts"] = [line[:160] for line in excerpts]
            bounded[kind + "ExcerptsClippedLines"] = clipped
            bounded[kind + "ExcerptsComplete"] = (
                change["countsComplete"] and change[kind + "Count"] == len(excerpts) and not clipped
            )
        result.append(bounded)
    return result
