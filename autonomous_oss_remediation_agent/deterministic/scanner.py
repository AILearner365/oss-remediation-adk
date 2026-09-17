from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..capabilities.execution import ProcessRunner
from ..config import MavenConfig, ScannerConfig
from ..models import ScanReport
from ..workspace import RunWorkspace, TraceStore


class ScannerPreflightError(RuntimeError):
    pass


class VulnerabilityScanner(Protocol):
    backend: str

    def preflight(self, config: ScannerConfig) -> object:
        ...

    def scan(self, repository: Path, severity_scope: tuple[str, ...], label: str) -> ScanReport:
        ...


def create_scanner(
    config: ScannerConfig,
    workspace: RunWorkspace,
    process_runner: ProcessRunner,
    trace: TraceStore,
    *,
    maven_config: MavenConfig | None = None,
) -> VulnerabilityScanner:
    from .osv import OsvScanner
    from .xray import XrayScanner

    if config.backend == "osv":
        return OsvScanner(workspace, process_runner, trace)
    if config.backend == "xray":
        return XrayScanner(
            workspace,
            process_runner,
            trace,
            maven_config=maven_config or MavenConfig(),
        )
    raise ScannerPreflightError(f"Unsupported scanner backend: {config.backend}")
