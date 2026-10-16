"""Shared OpenHands task metadata and deterministic preparation foundation.

M2 Changes 1 and 2 deliberately contain no worker or agent execution.
"""

from .contracts import (
    ArtifactMetadata,
    ContractValidationError,
    DeliveryStatus,
    ExecutionStatus,
    PreparationRecord,
    ResultOutcome,
    TaskEvent,
    TaskRequest,
    TaskResult,
    TaskStatus,
    TaskStatusSnapshot,
    ValidationStatus,
)
from .preparation import (
    DeterministicPreparer,
    PreparationConfig,
    PreparationError,
    TrustedRepository,
)
from .store import IdempotencyConflictError, PreparationConflictError, SQLiteTaskStore

__all__ = [
    "ArtifactMetadata",
    "ContractValidationError",
    "DeliveryStatus",
    "ExecutionStatus",
    "IdempotencyConflictError",
    "DeterministicPreparer",
    "PreparationConfig",
    "PreparationConflictError",
    "PreparationError",
    "PreparationRecord",
    "ResultOutcome",
    "SQLiteTaskStore",
    "TaskEvent",
    "TaskRequest",
    "TaskResult",
    "TaskStatus",
    "TaskStatusSnapshot",
    "TrustedRepository",
    "ValidationStatus",
]
