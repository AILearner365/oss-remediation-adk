"""Shared OpenHands task, preparation and deterministic baseline foundation.

M2 Changes 1 through 3 deliberately contain no agent execution.
"""

from .baseline import (
    BaselineConfig,
    BaselineError,
    BaselineProfile,
    BaselineRunEvidence,
    DeterministicBaselineAssessor,
    ExistingDeterministicBaselineRunner,
)

from .contracts import (
    ArtifactMetadata,
    BaselineAssessmentStatus,
    BaselineRecord,
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
from .store import (
    BaselineConflictError,
    IdempotencyConflictError,
    PreparationConflictError,
    SQLiteTaskStore,
)

__all__ = [
    "ArtifactMetadata",
    "BaselineAssessmentStatus",
    "BaselineConfig",
    "BaselineConflictError",
    "BaselineError",
    "BaselineProfile",
    "BaselineRecord",
    "BaselineRunEvidence",
    "ContractValidationError",
    "DeliveryStatus",
    "ExecutionStatus",
    "IdempotencyConflictError",
    "DeterministicBaselineAssessor",
    "DeterministicPreparer",
    "ExistingDeterministicBaselineRunner",
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
