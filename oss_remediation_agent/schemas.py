"""Schema helpers and reason codes for agent report handoffs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class RemediationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class ItemStatus(str, Enum):
    FIXED = "FIXED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"
    UNRESOLVED = "UNRESOLVED"


class PrDecision(str, Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SchemaValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()


def vulnerability_key(item: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    return (
        str(item.get("dependencyName") or ""),
        tuple(sorted(str(value) for value in item.get("vulnerabilityIds", []) or [])),
    )


def make_vulnerability_assessment_report(repository_url: str, reference_branch: str, workspace_path: str, policy_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "reportType": "VULNERABILITY_ASSESSMENT",
        "repositoryUrl": repository_url,
        "referenceBranch": reference_branch,
        "latestCommitId": None,
        "featureBranch": None,
        "buildStatus": "NOT_RUN",
        "scanTool": "OSV Scanner",
        "scannerResults": [],
        "projectType": "UNKNOWN",
        "projectMetadata": {},
        "isMultiModuleProject": False,
        "criticalCount": 0,
        "highCount": 0,
        "workspacePath": workspace_path,
        "vulnerabilities": [],
        "toolExecutionStatus": "RUNNING",
        "policy": policy_metadata or {},
        "errors": [],
    }


def make_remediation_report(assessment_report: dict[str, Any], workspace_path: Path, policy_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "reportType": "REMEDIATION",
        "repositoryUrl": assessment_report.get("repositoryUrl"),
        "referenceBranch": assessment_report.get("referenceBranch"),
        "featureBranch": assessment_report.get("featureBranch"),
        "remediationStatus": RemediationStatus.FAILED.value,
        "buildStatus": "NOT_RUN",
        "testStatus": "NOT_RUN",
        "workspacePath": str(workspace_path),
        "modifiedFiles": [],
        "remediatedVulnerabilities": [],
        "manualReviewItems": [],
        "failedItems": [],
        "decisionLog": [],
        "policy": policy_metadata or {},
        "postRemediationScan": {
            "criticalRemaining": 0,
            "highRemaining": 0,
            "newCriticalOrHighIntroduced": False,
            "remainingCriticalOrHighItems": [],
        },
    }


def validate_assessment_report(report: dict[str, Any]) -> SchemaValidationResult:
    return _validate_required(report, ("repositoryUrl", "referenceBranch", "buildStatus", "workspacePath", "vulnerabilities"))


def validate_remediation_report(report: dict[str, Any]) -> SchemaValidationResult:
    required = ("repositoryUrl", "referenceBranch", "featureBranch", "remediationStatus", "buildStatus", "testStatus", "modifiedFiles", "postRemediationScan")
    result = _validate_required(report, required)
    errors = list(result.errors)
    if not isinstance(report.get("postRemediationScan"), dict):
        errors.append("postRemediationScan must be an object")
    for field_name in ("modifiedFiles", "remediatedVulnerabilities", "manualReviewItems", "failedItems"):
        if field_name in report and not isinstance(report[field_name], list):
            errors.append(f"{field_name} must be a list")
    return SchemaValidationResult(not errors, tuple(errors))


def _validate_required(report: dict[str, Any], required: tuple[str, ...]) -> SchemaValidationResult:
    errors = [f"Missing required field: {field}" for field in required if field not in report]
    return SchemaValidationResult(not errors, tuple(errors))
