from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecutionBudgetConfig:
    max_cycles: int = 3
    max_tool_calls: int = 80
    command_timeout_seconds: int = 1800
    overall_timeout_seconds: int = 7200
    max_returned_output_chars: int = 30_000


@dataclass(frozen=True)
class RuntimePolicy:
    trusted_repository: bool = False
    dedicated_runner: bool = False
    enable_autonomous_shell: bool = False
    allow_network: bool = True

    @property
    def autonomous_shell_approved(self) -> bool:
        return self.trusted_repository and self.dedicated_runner and self.enable_autonomous_shell


@dataclass(frozen=True)
class ScannerConfig:
    mode: str = "configured"
    executable: str = "osv-scanner"
    version: str | None = None
    sha256: str | None = None
    download_url: str | None = None
    archive_member: str | None = None
    timeout_seconds: int = 300


@dataclass(frozen=True)
class ConstraintSpec:
    protected_java_version: str | None = None
    protected_spring_boot_version: str | None = None
    prohibit_suppressions: bool = True
    prohibited_new_severities: tuple[str, ...] = ("CRITICAL", "HIGH")
    allowed_paths: tuple[str, ...] = ()
    protected_paths: tuple[str, ...] = ()
    engineering_constraints: tuple[str, ...] = ()
    informational_constraints: tuple[str, ...] = ()

    @property
    def unenforced_constraints(self) -> tuple[str, ...]:
        informational = set(self.informational_constraints)
        return tuple(value for value in self.engineering_constraints if value not in informational)


@dataclass(frozen=True)
class DeliveryConfig:
    mode: str = "manual"
    adapter: str = "none"
    github_api_base: str = "https://api.github.com"
    branch_prefix: str = "oss-remediation"
    draft: bool = True


@dataclass(frozen=True)
class RemediationRequest:
    repository_url: str
    reference_branch: str = "main"
    workspace_parent: str = "autonomous-oss-remediation-workspaces"
    vulnerability_ids: tuple[str, ...] = ()
    severity_scope: tuple[str, ...] = ("CRITICAL", "HIGH")
    build_commands: tuple[str, ...] = ()
    test_commands: tuple[str, ...] = ()
    startup_commands: tuple[str, ...] = ()
    model: str = "gemini-2.5-flash"
    budget: ExecutionBudgetConfig = field(default_factory=ExecutionBudgetConfig)
    runtime_policy: RuntimePolicy = field(default_factory=RuntimePolicy)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    constraints: ConstraintSpec = field(default_factory=ConstraintSpec)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RemediationRequest":
        def tuple_value(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
            return tuple(str(value) for value in data.get(name, default) or ())

        budget_data = data.get("budget") or {}
        runtime_data = data.get("runtime_policy") or data.get("runtimePolicy") or {}
        scanner_data = data.get("scanner") or {}
        constraint_data = data.get("constraints") or {}
        delivery_data = data.get("delivery") or {}
        return cls(
            repository_url=str(data["repository_url"] if "repository_url" in data else data["repositoryUrl"]),
            reference_branch=str(data.get("reference_branch", data.get("referenceBranch", "main"))),
            workspace_parent=str(data.get("workspace_parent", data.get("workspaceParent", "autonomous-oss-remediation-workspaces"))),
            vulnerability_ids=tuple_value("vulnerability_ids", tuple(data.get("vulnerabilityIds", ()) or ())),
            severity_scope=tuple(value.upper() for value in tuple_value("severity_scope", tuple(data.get("severityScope", ("CRITICAL", "HIGH")) or ()))),
            build_commands=tuple_value("build_commands", tuple(data.get("buildCommands", ()) or ())),
            test_commands=tuple_value("test_commands", tuple(data.get("testCommands", ()) or ())),
            startup_commands=tuple_value("startup_commands", tuple(data.get("startupCommands", ()) or ())),
            model=str(data.get("model", "gemini-2.5-flash")),
            budget=ExecutionBudgetConfig(**_snake_keys(budget_data)),
            runtime_policy=RuntimePolicy(**_snake_keys(runtime_data)),
            scanner=ScannerConfig(**_snake_keys(scanner_data)),
            constraints=ConstraintSpec(
                protected_java_version=constraint_data.get("protected_java_version", constraint_data.get("protectedJavaVersion")),
                protected_spring_boot_version=constraint_data.get("protected_spring_boot_version", constraint_data.get("protectedSpringBootVersion")),
                prohibit_suppressions=bool(constraint_data.get("prohibit_suppressions", constraint_data.get("prohibitSuppressions", True))),
                prohibited_new_severities=tuple(str(value).upper() for value in constraint_data.get("prohibited_new_severities", constraint_data.get("prohibitedNewSeverities", ("CRITICAL", "HIGH"))) or ()),
                allowed_paths=tuple(str(value) for value in constraint_data.get("allowed_paths", constraint_data.get("allowedPaths", ())) or ()),
                protected_paths=tuple(str(value) for value in constraint_data.get("protected_paths", constraint_data.get("protectedPaths", ())) or ()),
                engineering_constraints=tuple(str(value) for value in constraint_data.get("engineering_constraints", constraint_data.get("engineeringConstraints", ())) or ()),
                informational_constraints=tuple(str(value) for value in constraint_data.get("informational_constraints", constraint_data.get("informationalConstraints", ())) or ()),
            ),
            delivery=DeliveryConfig(**_snake_keys(delivery_data)),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "RemediationRequest":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repositoryUrl": self.repository_url,
            "referenceBranch": self.reference_branch,
            "workspaceParent": self.workspace_parent,
            "vulnerabilityIds": list(self.vulnerability_ids),
            "severityScope": list(self.severity_scope),
            "buildCommands": list(self.build_commands),
            "testCommands": list(self.test_commands),
            "startupCommands": list(self.startup_commands),
            "model": self.model,
            "budget": self.budget.__dict__,
            "runtimePolicy": self.runtime_policy.__dict__,
            "scanner": self.scanner.__dict__,
            "constraints": {
                **self.constraints.__dict__,
                "prohibited_new_severities": list(self.constraints.prohibited_new_severities),
                "allowed_paths": list(self.constraints.allowed_paths),
                "protected_paths": list(self.constraints.protected_paths),
                "engineering_constraints": list(self.constraints.engineering_constraints),
                "informational_constraints": list(self.constraints.informational_constraints),
            },
            "delivery": self.delivery.__dict__,
        }


def _snake_keys(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        output = []
        for char in key:
            if char.isupper():
                output.extend(("_", char.lower()))
            else:
                output.append(char)
        result["".join(output)] = value
    return result
