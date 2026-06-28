"""Runtime policy for OSS remediation workflow."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INCLUDED_SEVERITIES = ("CRITICAL", "HIGH")
DEFAULT_ALLOWED_MODIFIED_FILE_NAMES = ("pom.xml",)
DEFAULT_PR_ALLOWED_STATUSES = ("SUCCESS",)
DEFAULT_BUILD_GOALS = ("clean", "install")
DEFAULT_TEST_GOALS = ("test",)


def _csv_env(name: str, default: Iterable[str]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return tuple(default)
    return tuple(part.strip() for part in raw.replace(";", ",").split(",") if part.strip())


def _goals_env(name: str, default: Iterable[str]) -> tuple[str, ...]:
    raw = os.getenv(name)
    return tuple(shlex.split(raw)) if raw else tuple(default)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class RemediationPolicy:
    included_severities: tuple[str, ...] = DEFAULT_INCLUDED_SEVERITIES
    allowed_modified_file_names: tuple[str, ...] = DEFAULT_ALLOWED_MODIFIED_FILE_NAMES
    pr_allowed_statuses: tuple[str, ...] = DEFAULT_PR_ALLOWED_STATUSES
    build_goals: tuple[str, ...] = DEFAULT_BUILD_GOALS
    test_goals: tuple[str, ...] = DEFAULT_TEST_GOALS
    maven_args: tuple[str, ...] = field(default_factory=tuple)
    osv_command: tuple[str, ...] | None = None
    allow_dependency_management_overrides: bool = True
    require_transitive_dependency_evidence: bool = True
    block_java_or_jdk_upgrade: bool = True
    pr_title: str = "OSS vulnerability remediation"
    pr_template_path: str | None = None

    @classmethod
    def from_env(cls) -> "RemediationPolicy":
        osv_command_raw = os.getenv("OSS_REMEDIATION_OSV_COMMAND")
        return cls(
            included_severities=tuple(value.upper() for value in _csv_env("OSS_REMEDIATION_SEVERITIES", DEFAULT_INCLUDED_SEVERITIES)),
            allowed_modified_file_names=_csv_env("OSS_REMEDIATION_ALLOWED_FILE_NAMES", DEFAULT_ALLOWED_MODIFIED_FILE_NAMES),
            pr_allowed_statuses=tuple(value.upper() for value in _csv_env("OSS_REMEDIATION_PR_ALLOWED_STATUSES", DEFAULT_PR_ALLOWED_STATUSES)),
            build_goals=_goals_env("OSS_REMEDIATION_BUILD_GOALS", DEFAULT_BUILD_GOALS),
            test_goals=_goals_env("OSS_REMEDIATION_TEST_GOALS", DEFAULT_TEST_GOALS),
            maven_args=tuple(shlex.split(os.getenv("OSS_REMEDIATION_MAVEN_ARGS", ""))),
            osv_command=tuple(shlex.split(osv_command_raw)) if osv_command_raw else None,
            allow_dependency_management_overrides=_bool_env("OSS_REMEDIATION_ALLOW_DEPENDENCY_MANAGEMENT_OVERRIDES", True),
            require_transitive_dependency_evidence=_bool_env("OSS_REMEDIATION_REQUIRE_TRANSITIVE_EVIDENCE", True),
            block_java_or_jdk_upgrade=_bool_env("OSS_REMEDIATION_BLOCK_JAVA_OR_JDK_UPGRADE", True),
            pr_title=os.getenv("OSS_REMEDIATION_PR_TITLE", "OSS vulnerability remediation"),
            pr_template_path=os.getenv("OSS_REMEDIATION_PR_TEMPLATE"),
        )

    def allows_severity(self, severity: Any) -> bool:
        return str(severity or "").upper() in self.included_severities

    def allows_file(self, path: str) -> bool:
        return Path(path).name in self.allowed_modified_file_names

    def as_report_metadata(self) -> dict[str, Any]:
        return {
            "includedSeverities": list(self.included_severities),
            "allowedModifiedFileNames": list(self.allowed_modified_file_names),
            "prAllowedStatuses": list(self.pr_allowed_statuses),
            "buildGoals": list(self.build_goals),
            "testGoals": list(self.test_goals),
            "mavenArgsConfigured": bool(self.maven_args),
            "osvCommandConfigured": bool(self.osv_command),
            "allowDependencyManagementOverrides": self.allow_dependency_management_overrides,
            "requireTransitiveDependencyEvidence": self.require_transitive_dependency_evidence,
            "blockJavaOrJdkUpgrade": self.block_java_or_jdk_upgrade,
            "prTemplateConfigured": bool(self.pr_template_path),
        }


DEFAULT_POLICY = RemediationPolicy()
