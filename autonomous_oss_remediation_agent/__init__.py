"""Independent autonomous OSS remediation agent package."""

from .config import RemediationRequest
from .journal import CaptureStatus, DeliveryEligibility, RemediationOutcome, ValidationStatus
from .models import Outcome, RunResult

__all__ = [
    "AutonomousRemediationOrchestrator",
    "CaptureStatus",
    "DeliveryEligibility",
    "Outcome",
    "RemediationOutcome",
    "RemediationRequest",
    "RunResult",
    "ValidationStatus",
]


def __getattr__(name: str):
    """Keep legacy orchestration opt-in; deterministic imports need no ADK."""
    if name == "AutonomousRemediationOrchestrator":
        from .orchestrator import AutonomousRemediationOrchestrator
        return AutonomousRemediationOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
