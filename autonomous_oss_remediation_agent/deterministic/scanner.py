from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..capabilities.execution import ProcessRunner
from ..config import ScannerConfig
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
) -> VulnerabilityScanner:
    from .osv import OsvScanner
    from .xray import XrayScanner

    scanners = {
        "osv": OsvScanner,
        "xray": XrayScanner,
    }
    try:
        scanner_type = scanners[config.backend]
    except KeyError as exc:
        raise ScannerPreflightError(f"Unsupported scanner backend: {config.backend}") from exc
    return scanner_type(workspace, process_runner, trace)
