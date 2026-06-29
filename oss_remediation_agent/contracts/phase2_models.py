from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .artifacts import Artifact


@dataclass
class BaselineBuildResult(Artifact):
    command: str = ""
    exit_code: int | None = None
    log_file: str | None = None


@dataclass
class VulnerabilityAssessmentReport(Artifact):
    report_type: str = "VULNERABILITY_ASSESSMENT"
    vulnerabilities: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectAnalyzerReport(Artifact):
    report_type: str = "PROJECT_ANALYZER"
    project_facts: dict[str, Any] = field(default_factory=dict)
    dependency_resolution_evidence: list[dict[str, Any]] = field(default_factory=list)
    pom_evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExactRemediationPatchPlan(Artifact):
    plan_id: str = ""
    attempt_number: int = 1
    vulnerability_decisions: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class PatchApplicationProof(Artifact):
    attempt_number: int = 1
    plan_id: str = ""
    patches_requested: int = 0
    patches_applied: int = 0
    files_changed: list[str] = field(default_factory=list)
    patch_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationResult(Artifact):
    attempt_number: int = 1
    change_scope_validation: dict[str, Any] = field(default_factory=dict)
    build_validation: dict[str, Any] = field(default_factory=dict)
    test_validation: dict[str, Any] = field(default_factory=dict)
    osv_validation: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutcomeAnalysisSummary(Artifact):
    attempt_number: int = 1
    failure_category: str | None = None
    what_we_tried: str = ""
    what_changed: list[dict[str, Any]] = field(default_factory=list)
    what_happened: dict[str, Any] = field(default_factory=dict)
    new_facts_learned: list[str] = field(default_factory=list)
    recommended_focus_for_planner: list[str] = field(default_factory=list)
    capability_gaps: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PrSummary(Artifact):
    pr_title: str = "OSS vulnerability remediation"
    pr_type: str = "NOT_ELIGIBLE"
    pull_request_eligibility: dict[str, Any] = field(default_factory=dict)
    remediation_summary: list[dict[str, Any]] = field(default_factory=list)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    pr_body_markdown: str = ""
