"""Shared OpenHands task contracts and durable metadata service.

M2 Change 1 deliberately contains no worker or agent execution integration.
"""

from .contracts import (
    ArtifactMetadata,
    ContractValidationError,
    DeliveryStatus,
    ExecutionStatus,
    ResultOutcome,
    TaskEvent,
    TaskRequest,
    TaskResult,
    TaskStatus,
    TaskStatusSnapshot,
    ValidationStatus,
)
from .store import IdempotencyConflictError, SQLiteTaskStore

__all__ = [
    "ArtifactMetadata",
    "ContractValidationError",
    "DeliveryStatus",
    "ExecutionStatus",
    "IdempotencyConflictError",
    "ResultOutcome",
    "SQLiteTaskStore",
    "TaskEvent",
    "TaskRequest",
    "TaskResult",
    "TaskStatus",
    "TaskStatusSnapshot",
    "ValidationStatus",
]
