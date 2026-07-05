from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.agents.artifact_catalog import (
    build_artifact_catalog,
    select_relevant_artifacts,
)

_DEFAULT_LOG_KEYWORDS = [
    "failed",
    "failure",
    "error",
    "exception",
    "banned",
    "convergence",
    "cannot",
    "unable",
]

_MAX_FULL_JSON_BYTES = 200_000
_MAX_FULL_TEXT_BYTES = 200_000
_TEXT_EXTENSIONS = {
    ".txt",
    ".log",
    ".md",
    ".json",
    ".xml",
    ".pom",
    ".properties",
    ".yml",
    ".yaml",
    ".gradle",
    ".diff",
    ".patch",
    ".csv",
}


def list_workspace_artifacts(workspace_root: str, attempt_number: int = 1) -> dict[str, Any]:
    """Return default metadata context for workspace artifacts indexed by manifest.json."""
    workspace = Path(workspace_root).resolve()
    manifest = _read_json(workspace / "manifest.json")
    if not manifest:
        return {
            "status": "FAILED",
            "failureCode": "MANIFEST_NOT_FOUND_OR_INVALID",
            "workspaceRoot": str(workspace),
            "artifactCatalog": {},
            "relevantArtifacts": [],
        }
    catalog = build_artifact_catalog(workspace, manifest, attempt_number)
    relevant = select_relevant_artifacts(catalog, manifest, attempt_number)
    return {
        "status": "SUCCESS",
        "workspaceRoot": str(workspace),
        "attemptNumber": attempt_number,
        "manifestStatus": manifest.get("status"),
        "artifactCatalog": catalog,
        "relevantArtifacts": relevant,
    }


def read_workspace_artifact(
    workspace_root: str,
    artifact_path: str,
    mode: str = "compact",
    attempt_number: int = 1,
) -> dict[str, Any]:
    """Safely read a workspace artifact.

    Public modes:
    - compact: default. Return a bounded, LLM-friendly representation when
      available. Known JSON artifacts use artifact-specific compact views,
      unknown JSON uses a generic compact view, and readable text artifacts use
      bounded excerpts. If no compact representation is available for a readable
      supported artifact, safely fall back to full content within size limits.
    - full: return complete JSON or complete supported text content only when
      explicitly requested and size limits allow it.

    Backward-compatible aliases accepted: metadata, full_json, full_text,
    raw_text, log_excerpt.
    """
    workspace = Path(workspace_root).resolve()
    try:
        path = _safe_resolve(workspace, artifact_path)
    except ValueError as exc:
        return {"status": "FAILED", "failureCode": "UNSAFE_ARTIFACT_PATH", "error": str(exc)}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "log_excerpt":
        return read_workspace_log_excerpt(workspace_root, artifact_path)

    if not path.exists() or not path.is_file():
        return {
            "status": "FAILED",
            "failureCode": "ARTIFACT_NOT_FOUND",
            "workspaceRoot": str(workspace),
            "artifactPath": artifact_path,
        }

    metadata = _metadata_for_path(workspace, artifact_path, attempt_number)
    if normalized_mode == "metadata":
        return {
            "status": "SUCCESS",
            "workspaceRoot": str(workspace),
            "artifactPath": artifact_path,
            "mode": "metadata",
            "metadata": metadata,
        }

    if normalized_mode == "full":
        return _read_full_artifact(workspace, artifact_path, path, metadata)

    compact = _read_compact_artifact(workspace_root, workspace, artifact_path, path, metadata)
    if compact.get("status") == "FAILED" and compact.get("failureCode") == "UNSUPPORTED_COMPACT_ARTIFACT":
        full = _read_full_artifact(workspace, artifact_path, path, metadata)
        if full.get("status") == "SUCCESS":
            full["mode"] = "compact"
            full["compactStrategy"] = "SAFE_FULL_FALLBACK"
            full["message"] = "No compact representation was available; returned safe full artifact content within size limits."
        return full
    return compact


def read_workspace_log_excerpt(
    workspace_root: str,
    log_path: str,
    keywords: list[str] | None = None,
    max_lines: int = 80,
) -> dict[str, Any]:
    """Safely read bounded excerpts from a workspace log or text artifact."""
    workspace = Path(workspace_root).resolve()
    try:
        path = _safe_resolve(workspace, log_path)
    except ValueError as exc:
        return {"status": "FAILED", "failureCode": "UNSAFE_LOG_PATH", "error": str(exc)}

    if not path.exists() or not path.is_file():
        return {
            "status": "FAILED",
            "failureCode": "LOG_NOT_FOUND",
            "workspaceRoot": str(workspace),
            "logPath": log_path,
        }

    terms = [term.lower() for term in (keywords or _DEFAULT_LOG_KEYWORDS)]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return {"status": "FAILED", "failureCode": "LOG_READ_FAILED", "logPath": log_path, "error": str(exc)}

    matching = [line for line in lines if any(term in line.lower() for term in terms)]
    selected = matching[-max_lines:] if matching else lines[-max_lines:]
    return {
        "status": "SUCCESS",
        "workspaceRoot": str(workspace),
        "logPath": log_path,
        "lineCount": len(lines),
        "matchedLineCount": len(matching),
        "excerpt": selected,
    }


def _normalize_mode(mode: str) -> str:
    value = str(mode or "compact").lower()
    if value in {"full", "complete", "complete_file", "full_file", "full_json", "full_text", "raw_text"}:
        return "full"
    if value in {"log_excerpt", "excerpt"}:
        return "log_excerpt"
    if value == "metadata":
        return "metadata"
    return "compact"


def _read_compact_artifact(
    workspace_root: str,
    workspace: Path,
    artifact_path: str,
    path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if path.suffix != ".json":
        if path.suffix.lower() not in _TEXT_EXTENSIONS:
            return {
                "status": "FAILED",
                "failureCode": "UNSUPPORTED_COMPACT_ARTIFACT",
                "workspaceRoot": str(workspace),
                "artifactPath": artifact_path,
                "mode": "compact",
                "metadata": metadata,
                "message": "Compact mode could not summarize this artifact type.",
            }
        excerpt = read_workspace_log_excerpt(workspace_root, artifact_path)
        return {
            "status": excerpt.get("status"),
            "workspaceRoot": str(workspace),
            "artifactPath": artifact_path,
            "mode": "compact",
            "compactStrategy": "TEXT_EXCERPT",
            "metadata": metadata,
            "content": {
                "artifactKind": "TEXT_EXCERPT",
                "lineCount": excerpt.get("lineCount"),
                "matchedLineCount": excerpt.get("matchedLineCount"),
                "excerpt": excerpt.get("excerpt", []),
            },
            "failureCode": excerpt.get("failureCode"),
            "error": excerpt.get("error"),
        }

    payload = _read_json(path)
    artifact_type = str((metadata or {}).get("artifactType") or _infer_artifact_type(artifact_path))
    compact = _compact_by_type(artifact_type, payload)
    strategy = "GENERIC_JSON" if artifact_type == "UNKNOWN_ARTIFACT" else f"{artifact_type}_COMPACT"
    log_refs = _find_log_references(payload)
    if log_refs:
        compact["logReferences"] = log_refs[:10]
        compact["logExcerpts"] = [
            read_workspace_log_excerpt(workspace_root, log_ref).get("excerpt")
            for log_ref in log_refs[:5]
        ]
        compact["logExcerpts"] = [excerpt for excerpt in compact["logExcerpts"] if excerpt]

    return {
        "status": "SUCCESS",
        "workspaceRoot": str(workspace),
        "artifactPath": artifact_path,
        "mode": "compact",
        "compactStrategy": strategy,
        "metadata": metadata,
        "content": compact,
    }


def _read_full_artifact(workspace: Path, artifact_path: str, path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    size = path.stat().st_size
    if path.suffix == ".json":
        if size > _MAX_FULL_JSON_BYTES:
            return {
                "status": "FAILED",
                "failureCode": "ARTIFACT_TOO_LARGE_FOR_FULL",
                "artifactPath": artifact_path,
                "sizeBytes": size,
                "maxBytes": _MAX_FULL_JSON_BYTES,
                "metadata": metadata,
            }
        return {
            "status": "SUCCESS",
            "workspaceRoot": str(workspace),
            "artifactPath": artifact_path,
            "mode": "full",
            "metadata": metadata,
            "sizeBytes": size,
            "content": _read_json(path),
        }

    if path.suffix.lower() not in _TEXT_EXTENSIONS:
        return {
            "status": "FAILED",
            "failureCode": "UNSUPPORTED_FULL_ARTIFACT",
            "artifactPath": artifact_path,
            "extension": path.suffix,
            "metadata": metadata,
        }
    if size > _MAX_FULL_TEXT_BYTES:
        return {
            "status": "FAILED",
            "failureCode": "ARTIFACT_TOO_LARGE_FOR_FULL",
            "artifactPath": artifact_path,
            "sizeBytes": size,
            "maxBytes": _MAX_FULL_TEXT_BYTES,
            "metadata": metadata,
        }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"status": "FAILED", "failureCode": "FULL_READ_FAILED", "artifactPath": artifact_path, "error": str(exc), "metadata": metadata}
    return {
        "status": "SUCCESS",
        "workspaceRoot": str(workspace),
        "artifactPath": artifact_path,
        "mode": "full",
        "metadata": metadata,
        "sizeBytes": size,
        "content": text,
    }


def _metadata_for_path(workspace: Path, artifact_path: str, attempt_number: int) -> dict[str, Any]:
    manifest = _read_json(workspace / "manifest.json")
    if not manifest:
        return {}
    catalog = build_artifact_catalog(workspace, manifest, attempt_number)
    normalized = _workspace_relative(workspace, artifact_path)

    def walk(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            if _workspace_relative(workspace, str(value.get("path") or "")) == normalized:
                return value
            for child in value.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return None

    return walk(catalog) or {"path": normalized, "artifactType": _infer_artifact_type(normalized)}


def _compact_by_type(artifact_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if artifact_type == "MANIFEST":
        return {
            "status": payload.get("status"),
            "repository": payload.get("repository", {}),
            "baseline": payload.get("baseline", {}),
            "planning": payload.get("planning", {}),
            "attempts": payload.get("attempts", []),
            "acceptedPatchSet": payload.get("acceptedPatchSet", {}),
            "final": payload.get("final", {}),
        }
    if artifact_type == "REMEDIATION_PATCH_PLAN":
        return {
            "status": payload.get("status"),
            "decisionType": payload.get("decisionType"),
            "summary": payload.get("summary", {}),
            "vulnerabilityDecisions": payload.get("vulnerabilityDecisions", []),
            "manualReviewItems": _manual_review_items(payload),
        }
    if artifact_type == "VALIDATION_RESULT":
        return {
            "status": payload.get("status"),
            "summary": payload.get("summary", {}),
            "changeScopeValidation": payload.get("changeScopeValidation", {}),
            "buildValidation": payload.get("buildValidation", {}),
            "testValidation": payload.get("testValidation", {}),
            "osvValidation": payload.get("osvValidation", {}),
            "errors": payload.get("errors", []),
            "warnings": payload.get("warnings", []),
        }
    if artifact_type == "REMEDIATION_PLANNING_CONTEXT":
        return _compact_planning_context(payload)
    if artifact_type == "PROJECT_ANALYZER_REPORT":
        return {
            "status": payload.get("status"),
            "projectFacts": payload.get("projectFacts", {}),
            "pomEvidence": payload.get("pomEvidence", [])[:50],
            "dependencyResolutionEvidence": payload.get("dependencyResolutionEvidence", [])[:50],
            "warnings": payload.get("warnings", []),
            "errors": payload.get("errors", []),
        }
    if artifact_type == "VULNERABILITY_ASSESSMENT_REPORT":
        return {
            "status": payload.get("status"),
            "summary": payload.get("summary", {}),
            "vulnerabilities": payload.get("vulnerabilities", [])[:50],
        }
    return {
        key: payload.get(key)
        for key in (
            "status",
            "artifactId",
            "workflowId",
            "summary",
            "failureCode",
            "failureSummary",
            "patchResults",
            "filesChanged",
            "logExcerpt",
            "errors",
            "warnings",
        )
        if key in payload
    }


def _compact_planning_context(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence") or {}
    project = evidence.get("projectAnalyzer") or {}
    assessment = evidence.get("vulnerabilityAssessment") or {}
    return {
        "agent": payload.get("agent"),
        "attemptNumber": payload.get("attemptNumber"),
        "artifactReferences": payload.get("artifactReferences", {}),
        "promptAvailable": bool(payload.get("prompt")),
        "notes": evidence.get("notes", [])[:20],
        "previousAttempt": evidence.get("previousAttempt"),
        "vulnerabilityAssessmentSummary": assessment.get("summary") if isinstance(assessment, dict) else None,
        "vulnerabilitiesSample": (assessment.get("vulnerabilities", []) if isinstance(assessment, dict) else [])[:25],
        "projectAnalyzerKeys": sorted(project.keys()) if isinstance(project, dict) else [],
        "pomEvidenceSample": (project.get("pomEvidence", []) if isinstance(project, dict) else [])[:25],
        "dependencyResolutionEvidenceSample": (project.get("dependencyResolutionEvidence", []) if isinstance(project, dict) else [])[:25],
        "baselineBuildResult": evidence.get("baselineBuildResult"),
    }


def _manual_review_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for decision in payload.get("vulnerabilityDecisions", []) or []:
        decision_type = str(decision.get("decision") or "").upper()
        if decision_type == "MANUAL_REVIEW" or decision.get("manualReviewCategory"):
            items.append({
                "vulnerabilityId": decision.get("vulnerabilityId"),
                "dependency": decision.get("dependency", {}),
                "manualReviewCategory": decision.get("manualReviewCategory"),
                "statusReason": decision.get("statusReason") or decision.get("reason"),
            })
    return items


def _infer_artifact_type(path: str) -> str:
    name = Path(path).name
    mapping = {
        "manifest.json": "MANIFEST",
        "baseline-build-result.json": "BASELINE_BUILD_RESULT",
        "vulnerability-assessment-report.json": "VULNERABILITY_ASSESSMENT_REPORT",
        "project-analyzer-report.json": "PROJECT_ANALYZER_REPORT",
        "remediation-planning-context.json": "REMEDIATION_PLANNING_CONTEXT",
        "remediation-patch-plan.json": "REMEDIATION_PATCH_PLAN",
        "patch-dry-run-result.json": "PATCH_DRY_RUN_RESULT",
        "patch-application-proof.json": "PATCH_APPLICATION_PROOF",
        "validation-result.json": "VALIDATION_RESULT",
        "outcome-analysis-context.json": "OUTCOME_ANALYSIS_CONTEXT",
        "outcome-analysis-summary.json": "OUTCOME_ANALYSIS_SUMMARY",
    }
    return mapping.get(name, "UNKNOWN_ARTIFACT")


def _find_log_references(payload: Any) -> list[str]:
    refs: list[str] = []

    def walk(value: Any, key_hint: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, str(key))
        elif isinstance(value, list):
            for item in value:
                walk(item, key_hint)
        elif isinstance(value, str):
            lowered = value.lower()
            if ("log" in key_hint.lower() or lowered.endswith(".log") or ".log" in lowered) and value not in refs:
                refs.append(value)

    walk(payload)
    return refs


def _safe_resolve(workspace: Path, requested_path: str) -> Path:
    path = Path(requested_path)
    resolved = path.resolve() if path.is_absolute() else (workspace / path).resolve()
    if resolved == workspace or workspace in resolved.parents:
        return resolved
    raise ValueError(f"Path is outside workspace: {requested_path}")


def _workspace_relative(workspace: Path, path_value: str) -> str:
    if not path_value:
        return ""
    try:
        path = _safe_resolve(workspace, path_value)
        return str(path.relative_to(workspace))
    except Exception:
        return path_value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
