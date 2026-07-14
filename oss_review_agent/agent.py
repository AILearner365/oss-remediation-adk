from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.adk.agents.llm_agent import LlmAgent


_MAX_FILES = 40
_MAX_CHARS_PER_FILE = 12_000
_REVIEWABLE_SUFFIXES = {".json", ".md", ".txt", ".log", ".xml", ".diff", ".patch"}
_PRIORITY_NAMES = {
    "attempt-manifest.json",
    "vulnerability-assessment.json",
    "project-analyzer-report.json",
    "project-analysis.json",
    "exact-remediation-patch-plan.json",
    "patch-plan.json",
    "patch-application-proof.json",
    "validation-result.json",
    "outcome-analysis-summary.json",
    "pr-summary.json",
    "pom.xml",
}


def collect_remediation_workspace_evidence(workspace_root: str) -> dict[str, Any]:
    """Read reviewable artifacts from an existing remediation workspace.

    This POC is intentionally read-only. It does not rerun remediation and does
    not modify the workspace. The returned evidence is bounded so it remains
    suitable for an ADK tool result.
    """
    root = Path(workspace_root).expanduser().resolve()
    if not root.exists():
        return {
            "status": "FAILED",
            "failureCode": "WORKSPACE_NOT_FOUND",
            "message": f"Workspace does not exist: {root}",
        }
    if not root.is_dir():
        return {
            "status": "FAILED",
            "failureCode": "WORKSPACE_NOT_DIRECTORY",
            "message": f"Workspace path is not a directory: {root}",
        }

    candidates = [path for path in root.rglob("*") if _is_reviewable(path)]
    candidates.sort(key=_review_priority)

    evidence: list[dict[str, Any]] = []
    unreadable: list[str] = []
    for path in candidates[:_MAX_FILES]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            unreadable.append(str(path.relative_to(root)))
            continue

        relative_path = str(path.relative_to(root))
        content = text[:_MAX_CHARS_PER_FILE]
        item: dict[str, Any] = {
            "path": relative_path,
            "content": content,
            "truncated": len(text) > len(content),
        }

        if path.suffix.lower() == ".json":
            try:
                item["json"] = json.loads(text)
                item.pop("content", None)
            except json.JSONDecodeError:
                item["parseWarning"] = "Invalid JSON; supplied as text."

        evidence.append(item)

    return {
        "status": "SUCCESS",
        "workspaceRoot": str(root),
        "filesDiscovered": len(candidates),
        "filesIncluded": len(evidence),
        "filesOmitted": max(0, len(candidates) - len(evidence)),
        "unreadableFiles": unreadable,
        "evidence": evidence,
        "reviewScope": (
            "Single-pass, read-only POC review of persisted remediation artifacts. "
            "The reviewer must not invent reasons that are absent from evidence."
        ),
    }


def _is_reviewable(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name in _PRIORITY_NAMES:
        return True
    return path.suffix.lower() in _REVIEWABLE_SUFFIXES


def _review_priority(path: Path) -> tuple[int, str]:
    priority = 0 if path.name in _PRIORITY_NAMES else 1
    return priority, str(path).lower()


root_agent = LlmAgent(
    name="oss_review_agent",
    model="gemini-2.5-flash",
    description=(
        "Reviews an existing OSS remediation workspace and explains why the "
        "recorded dependency and file changes were made."
    ),
    instruction=(
        "You are a pragmatic senior developer reviewing an already completed OSS remediation run. "
        "The user must provide workspace_root, which is the path to an existing remediation workspace. "
        "Call collect_remediation_workspace_evidence exactly once with that path. "
        "If the tool fails, clearly report the failure and stop. "
        "Otherwise perform one lightweight review pass only. "
        "Use only the returned evidence. Do not claim you inspected files that are not included, "
        "do not rerun remediation, and do not modify any file. "
        "Produce these sections: Review Scope; Changes Observed; Reviewer Questions and Evidence-Based Answers; "
        "Validation Evidence; Gaps or Concerns; Final Decision. "
        "Ask only useful why-questions, such as why a dependency changed, why that target version was selected, "
        "why a particular POM was changed, and whether validation supports the change. "
        "Immediately answer each question from the evidence as the developer would. "
        "When the evidence does not explain a decision, say 'Not documented in the available workspace evidence' "
        "instead of guessing. End with exactly one decision: APPROVED, CHANGES_REQUESTED, or NEEDS_HUMAN_REVIEW."
    ),
    tools=[collect_remediation_workspace_evidence],
)
