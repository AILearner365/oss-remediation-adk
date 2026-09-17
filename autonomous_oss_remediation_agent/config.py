from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ExecutionBudgetConfig:
    max_cycles: int = 3
    max_tool_calls: int = 80
    max_llm_calls_per_turn: int = 40
    command_timeout_seconds: int = 1800
    model_turn_timeout_seconds: int = 1800
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
class OsvScannerConfig:
    mode: str = "configured"
    executable: str = "osv-scanner"
    version: str | None = None
    sha256: str | None = None
    download_url: str | None = None
    archive_member: str | None = None
    timeout_seconds: int = 300


@dataclass(frozen=True)
class XrayScannerConfig:
    url: str
    auth_method: str = "access-token"
    verify_tls: bool = True
    ca_bundle: str | None = None
    connect_timeout_seconds: int = 10
    read_timeout_seconds: int = 60
    poll_interval_seconds: float = 3.0
    poll_timeout_seconds: int = 300

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("scanner.xray.url must be an absolute HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("scanner.xray.url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("scanner.xray.url must not contain a query string or fragment")
        if self.auth_method not in {"access-token", "basic"}:
            raise ValueError("scanner.xray.authMethod must be access-token or basic")
        if not isinstance(self.verify_tls, bool):
            raise ValueError("scanner.xray.verifyTls must be a boolean")
        for name in ("connect_timeout_seconds", "read_timeout_seconds", "poll_timeout_seconds"):
            if getattr(self, name) <= 0:
                raise ValueError(f"scanner.xray.{name} must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("scanner.xray.pollIntervalSeconds must be positive")


@dataclass(frozen=True, init=False)
class ScannerConfig:
    backend: str
    osv: OsvScannerConfig
    xray: XrayScannerConfig | None

    def __init__(
        self,
        backend: str = "osv",
        osv: OsvScannerConfig | None = None,
        xray: XrayScannerConfig | None = None,
        *,
        mode: str | None = None,
        executable: str | None = None,
        version: str | None = None,
        sha256: str | None = None,
        download_url: str | None = None,
        archive_member: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        normalized_backend = str(backend).strip().lower()
        if normalized_backend not in {"osv", "xray"}:
            raise ValueError(f"Unsupported scanner backend: {backend}")
        legacy_values = (mode, executable, version, sha256, download_url, archive_member, timeout_seconds)
        if osv is not None and any(value is not None for value in legacy_values):
            raise ValueError("Do not combine scanner.osv with legacy flat OSV settings")
        if osv is None:
            defaults = OsvScannerConfig()
            osv = OsvScannerConfig(
                mode=mode if mode is not None else defaults.mode,
                executable=executable if executable is not None else defaults.executable,
                version=version,
                sha256=sha256,
                download_url=download_url,
                archive_member=archive_member,
                timeout_seconds=timeout_seconds if timeout_seconds is not None else defaults.timeout_seconds,
            )
        if normalized_backend == "xray" and xray is None:
            raise ValueError("scanner.xray is required when scanner.backend is xray")
        object.__setattr__(self, "backend", normalized_backend)
        object.__setattr__(self, "osv", osv)
        object.__setattr__(self, "xray", xray)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScannerConfig":
        normalized = _snake_keys(data)
        _reject_scanner_secrets(normalized)
        backend_value = normalized.pop("backend", None)
        type_value = normalized.pop("type", None)
        if backend_value is not None and type_value is not None:
            if str(backend_value).strip().lower() != str(type_value).strip().lower():
                raise ValueError("scanner.backend and scanner.type must not conflict")
        backend = str(backend_value if backend_value is not None else type_value or "osv").strip().lower()
        if backend not in {"osv", "xray"}:
            raise ValueError(f"Unsupported scanner backend: {backend}")
        osv_data = normalized.pop("osv", None)
        xray_data = normalized.pop("xray", None)
        legacy_names = {
            "mode",
            "executable",
            "version",
            "sha256",
            "download_url",
            "archive_member",
            "timeout_seconds",
        }
        legacy_osv = {name: normalized.pop(name) for name in tuple(normalized) if name in legacy_names}
        if normalized:
            names = ", ".join(sorted(normalized))
            raise ValueError(f"Unsupported scanner setting(s): {names}")
        if osv_data is not None and legacy_osv:
            raise ValueError("Do not combine scanner.osv with legacy flat OSV settings")
        if osv_data is not None and not isinstance(osv_data, dict):
            raise ValueError("scanner.osv must be an object")
        if xray_data is not None and not isinstance(xray_data, dict):
            raise ValueError("scanner.xray must be an object")
        osv = OsvScannerConfig(**_snake_keys(osv_data or legacy_osv))
        xray = XrayScannerConfig(**_snake_keys(xray_data)) if xray_data is not None else None
        return cls(backend=backend, osv=osv, xray=xray)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "backend": self.backend,
            "osv": self.osv.__dict__,
        }
        if self.xray is not None:
            value["xray"] = self.xray.__dict__
        return value

    @property
    def mode(self) -> str:
        return self.osv.mode

    @property
    def executable(self) -> str:
        return self.osv.executable

    @property
    def version(self) -> str | None:
        return self.osv.version

    @property
    def sha256(self) -> str | None:
        return self.osv.sha256

    @property
    def download_url(self) -> str | None:
        return self.osv.download_url

    @property
    def archive_member(self) -> str | None:
        return self.osv.archive_member

    @property
    def timeout_seconds(self) -> int:
        return self.osv.timeout_seconds


@dataclass(frozen=True)
class SpringBootVersionPolicy:
    allow_patch: bool = True
    allow_minor: bool = True
    allow_major: bool = False
    allow_downgrade: bool = False
    approved_versions: tuple[str, ...] = ()
    required_version: str | None = None

    def __post_init__(self) -> None:
        for name in ("allow_patch", "allow_minor", "allow_major", "allow_downgrade"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"Spring Boot version policy field {name} must be a boolean")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpringBootVersionPolicy":
        normalized = _snake_keys(data)
        normalized["approved_versions"] = tuple(
            str(value) for value in normalized.get("approved_versions", ()) or ()
        )
        if normalized.get("required_version") is not None:
            normalized["required_version"] = str(normalized["required_version"])
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_patch": self.allow_patch,
            "allow_minor": self.allow_minor,
            "allow_major": self.allow_major,
            "allow_downgrade": self.allow_downgrade,
            "approved_versions": list(self.approved_versions),
            "required_version": self.required_version,
        }


@dataclass(frozen=True)
class ConstraintSpec:
    protected_java_version: str | None = None
    protected_spring_boot_version: str | None = None
    spring_boot_version_policy: SpringBootVersionPolicy = field(default_factory=SpringBootVersionPolicy)
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
        version_policy_data = constraint_data.get("version_policies", constraint_data.get("versionPolicies", {})) or {}
        unsupported_version_policies = set(version_policy_data) - {"spring_boot", "springBoot"}
        if unsupported_version_policies:
            unsupported = ", ".join(sorted(str(value) for value in unsupported_version_policies))
            raise ValueError(f"Unsupported version policy component: {unsupported}")
        spring_boot_policy_data = version_policy_data.get(
            "spring_boot",
            version_policy_data.get("springBoot", {}),
        ) or {}
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
            scanner=ScannerConfig.from_dict(scanner_data),
            constraints=ConstraintSpec(
                protected_java_version=constraint_data.get("protected_java_version", constraint_data.get("protectedJavaVersion")),
                protected_spring_boot_version=constraint_data.get("protected_spring_boot_version", constraint_data.get("protectedSpringBootVersion")),
                spring_boot_version_policy=SpringBootVersionPolicy.from_dict(spring_boot_policy_data),
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
        constraint_values = {
            key: value
            for key, value in self.constraints.__dict__.items()
            if key != "spring_boot_version_policy"
        }
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
            "scanner": self.scanner.to_dict(),
            "constraints": {
                **constraint_values,
                "version_policies": {
                    "spring_boot": self.constraints.spring_boot_version_policy.to_dict(),
                },
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


def _reject_scanner_secrets(data: dict[str, Any]) -> None:
    prohibited = {"access_token", "token", "username", "password"}
    for key, value in data.items():
        if key in prohibited:
            raise ValueError(f"Scanner credentials must not be provided in request JSON: {key}")
        if isinstance(value, dict):
            _reject_scanner_secrets(_snake_keys(value))
