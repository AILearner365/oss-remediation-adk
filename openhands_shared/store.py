"""SQLite persistence for shared OpenHands task metadata.

Each operation uses its own connection.  SQLite transactions, not process-local
locks, therefore provide correctness across threads and service processes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import (
    ArtifactMetadata,
    BaselineAssessmentStatus,
    BaselineRecord,
    DeliveryStatus,
    ExecutionClaimRecord,
    ExecutionDispatchStatus,
    ExecutionStatus,
    IntelligenceOutcome,
    IntelligenceRecord,
    OpenHandsEventLink,
    OpenHandsRuntimeRecord,
    OpenHandsRuntimeStatus,
    PreparationRecord,
    ResultOutcome,
    TaskEvent,
    TaskRequest,
    TaskResult,
    TaskStatus,
    TaskStatusSnapshot,
    ValidationStatus,
    ValidationAttemptRecord,
    ValidationAttemptState,
    ValidationOutcome,
    StopHookDecision,
    canonical_json,
    utc_now,
)


SCHEMA_VERSION = 6


class TaskStoreError(RuntimeError):
    pass


class TaskNotFoundError(TaskStoreError):
    pass


class IdempotencyConflictError(TaskStoreError):
    def __init__(self, idempotency_key: str, task_id: str):
        super().__init__(f"idempotency key {idempotency_key!r} is already bound to a different request")
        self.idempotency_key = idempotency_key
        self.task_id = task_id


class InvalidTransitionError(TaskStoreError):
    pass


class ArtifactConflictError(TaskStoreError):
    pass


class PreparationConflictError(TaskStoreError):
    pass


class BaselineConflictError(TaskStoreError):
    pass


class IntelligenceConflictError(TaskStoreError):
    pass


class OpenHandsRuntimeConflictError(TaskStoreError):
    pass


class ExecutionClaimConflictError(TaskStoreError):
    pass


class ValidationConflictError(TaskStoreError):
    pass


@dataclass(frozen=True)
class TaskRegistration:
    status: TaskStatusSnapshot
    created: bool


_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.QUEUED: frozenset({TaskStatus.PREPARING, TaskStatus.FAILED_INFRASTRUCTURE, TaskStatus.CANCELLED}),
    TaskStatus.PREPARING: frozenset({TaskStatus.BASELINING, TaskStatus.FAILED_INFRASTRUCTURE, TaskStatus.CANCELLED}),
    TaskStatus.BASELINING: frozenset({TaskStatus.INTELLIGENCE, TaskStatus.FAILED_INFRASTRUCTURE, TaskStatus.FAILED_VALIDATION, TaskStatus.CANCELLED}),
    TaskStatus.INTELLIGENCE: frozenset({TaskStatus.AGENT_RUNNING, TaskStatus.FAILED_INFRASTRUCTURE, TaskStatus.CANCELLED}),
    TaskStatus.AGENT_RUNNING: frozenset({TaskStatus.VALIDATING, TaskStatus.FAILED_INFRASTRUCTURE, TaskStatus.CANCELLED}),
    TaskStatus.VALIDATING: frozenset({TaskStatus.AGENT_RUNNING, TaskStatus.ACCEPTED, TaskStatus.FAILED_INFRASTRUCTURE, TaskStatus.FAILED_VALIDATION, TaskStatus.CANCELLED}),
    TaskStatus.ACCEPTED: frozenset({TaskStatus.DELIVERING}),
    TaskStatus.DELIVERING: frozenset({TaskStatus.SUCCEEDED, TaskStatus.FAILED_INFRASTRUCTURE}),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.FAILED_INFRASTRUCTURE: frozenset(),
    TaskStatus.FAILED_VALIDATION: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

_STATUS_STAGE = {
    TaskStatus.QUEUED: "queued",
    TaskStatus.PREPARING: "preparation",
    TaskStatus.BASELINING: "baseline",
    TaskStatus.INTELLIGENCE: "intelligence",
    TaskStatus.AGENT_RUNNING: "agent",
    TaskStatus.VALIDATING: "validation",
    TaskStatus.ACCEPTED: "accepted",
    TaskStatus.DELIVERING: "delivery",
    TaskStatus.SUCCEEDED: "complete",
    TaskStatus.FAILED_INFRASTRUCTURE: "failed",
    TaskStatus.FAILED_VALIDATION: "failed",
    TaskStatus.CANCELLED: "cancelled",
}


class SQLiteTaskStore:
    """Durable task, event, artifact, and result metadata store."""

    def __init__(self, database_path: str | Path, *, timeout_seconds: float = 10.0):
        self.database_path = Path(database_path)
        self.timeout_seconds = timeout_seconds
        self._closed = False
        if self.database_path == Path(":memory:"):
            raise ValueError("SQLiteTaskStore requires a durable filesystem path")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def close(self) -> None:
        """Prevent this handle from opening more connections.

        Operations are connection-scoped, so close is deterministic even when a
        preceding request raised.  A new store handle can reopen the same file.
        """

        self._closed = True

    def __enter__(self) -> "SQLiteTaskStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _connect(self) -> sqlite3.Connection:
        if self._closed:
            raise TaskStoreError("task store is closed")
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self.timeout_seconds * 1000)}")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS schema_info (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_hash TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    execution_status TEXT NOT NULL,
                    conversation_id TEXT,
                    validation_status TEXT NOT NULL,
                    validation_attempts INTEGER NOT NULL,
                    accepted INTEGER NOT NULL CHECK (accepted IN (0, 1)),
                    delivery_status TEXT NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    openhands_event_id TEXT,
                    PRIMARY KEY (task_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
                    artifact_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, artifact_id),
                    UNIQUE (task_id, relative_path)
                );
                CREATE INDEX IF NOT EXISTS events_task_order ON events(task_id, sequence);
                CREATE INDEX IF NOT EXISTS artifacts_task_order ON artifacts(task_id, created_at, artifact_id);
                CREATE TRIGGER IF NOT EXISTS events_append_only_update
                BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_append_only_delete
                BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS artifacts_immutable_update
                BEFORE UPDATE ON artifacts
                BEGIN SELECT RAISE(ABORT, 'artifact metadata is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS artifacts_immutable_delete
                BEFORE DELETE ON artifacts
                BEGIN SELECT RAISE(ABORT, 'artifact metadata is immutable'); END;
                COMMIT;
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_info(singleton, version) VALUES (1, 1)"
            )
            row = connection.execute("SELECT version FROM schema_info WHERE singleton = 1").fetchone()
            version = row["version"]
            if version == 1:
                self._migrate_v1_to_v2(connection)
                version = 2
            if version == 2:
                self._migrate_v2_to_v3(connection)
                version = 3
            if version == 3:
                self._migrate_v3_to_v4(connection)
                version = 4
            if version == 4:
                self._migrate_v4_to_v5(connection)
                version = 5
            if version == 5:
                self._migrate_v5_to_v6(connection)
                version = 6
            if version != SCHEMA_VERSION:
                raise TaskStoreError(f"unsupported task database schema version {row['version']}")
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        """Add immutable preparation metadata without rebuilding v1 tables."""

        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute(
                "SELECT version FROM schema_info WHERE singleton = 1"
            ).fetchone()["version"]
            if current == 2:
                connection.commit()
                return
            if current != 1:
                raise TaskStoreError(f"cannot migrate task database schema version {current}")
            connection.execute(
                """CREATE TABLE preparations (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE RESTRICT,
                    repository_url TEXT NOT NULL,
                    base_ref TEXT NOT NULL,
                    expected_commit TEXT NOT NULL,
                    baseline_commit TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    workspace_path TEXT NOT NULL UNIQUE,
                    local_branch TEXT NOT NULL UNIQUE,
                    prepared_at TEXT NOT NULL,
                    CHECK (expected_commit = baseline_commit)
                )"""
            )
            connection.execute(
                """CREATE TRIGGER preparations_immutable_update
                BEFORE UPDATE ON preparations
                BEGIN SELECT RAISE(ABORT, 'preparation metadata is immutable'); END"""
            )
            connection.execute(
                """CREATE TRIGGER preparations_immutable_delete
                BEFORE DELETE ON preparations
                BEGIN SELECT RAISE(ABORT, 'preparation metadata is immutable'); END"""
            )
            connection.execute("UPDATE schema_info SET version = 2 WHERE singleton = 1")
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    @staticmethod
    def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
        """Add immutable baseline assessment metadata without rebuilding data."""

        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute(
                "SELECT version FROM schema_info WHERE singleton = 1"
            ).fetchone()["version"]
            if current == 3:
                connection.commit()
                return
            if current != 2:
                raise TaskStoreError(f"cannot migrate task database schema version {current}")
            connection.execute(
                """CREATE TABLE baseline_assessments (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE RESTRICT,
                    baseline_commit TEXT NOT NULL,
                    assessment_status TEXT NOT NULL CHECK (
                        assessment_status IN ('COMPLETED', 'NO_TARGET_FINDINGS', 'FAILED_BUILD', 'FAILED_SCANNER')
                    ),
                    build_succeeded INTEGER NOT NULL CHECK (build_succeeded IN (0, 1)),
                    scanner_outcome TEXT NOT NULL,
                    finding_count INTEGER NOT NULL CHECK (finding_count >= 0),
                    report_artifact_id TEXT NOT NULL,
                    report_sha256 TEXT NOT NULL,
                    tool_versions_json TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    FOREIGN KEY (task_id, report_artifact_id)
                        REFERENCES artifacts(task_id, artifact_id) ON DELETE RESTRICT
                )"""
            )
            connection.execute(
                """CREATE TRIGGER baseline_assessments_immutable_update
                BEFORE UPDATE ON baseline_assessments
                BEGIN SELECT RAISE(ABORT, 'baseline metadata is immutable'); END"""
            )
            connection.execute(
                """CREATE TRIGGER baseline_assessments_immutable_delete
                BEFORE DELETE ON baseline_assessments
                BEGIN SELECT RAISE(ABORT, 'baseline metadata is immutable'); END"""
            )
            connection.execute("UPDATE schema_info SET version = 3 WHERE singleton = 1")
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    @staticmethod
    def _migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
        """Add immutable optional intelligence metadata without rebuilding data."""

        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute(
                "SELECT version FROM schema_info WHERE singleton = 1"
            ).fetchone()["version"]
            if current == 4:
                connection.commit()
                return
            if current != 3:
                raise TaskStoreError(f"cannot migrate task database schema version {current}")
            connection.execute(
                """CREATE TABLE intelligence_assessments (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE RESTRICT,
                    baseline_commit TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK (
                        outcome IN (
                            'DISABLED', 'NOT_APPLICABLE', 'COMPLETE', 'PARTIAL', 'FAILED',
                            'INVALID_SELECTION', 'CORRUPT_EVIDENCE', 'REPOSITORY_MUTATION'
                        )
                    ),
                    applicable INTEGER CHECK (applicable IS NULL OR applicable IN (0, 1)),
                    invoked INTEGER NOT NULL CHECK (invoked IN (0, 1)),
                    reused INTEGER NOT NULL CHECK (reused IN (0, 1)),
                    profile_id TEXT NOT NULL,
                    fingerprint TEXT,
                    selection_manifest_json TEXT NOT NULL,
                    evaluated_versions_json TEXT NOT NULL,
                    record_artifact_id TEXT NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    summary_artifact_id TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    FOREIGN KEY (task_id, record_artifact_id)
                        REFERENCES artifacts(task_id, artifact_id) ON DELETE RESTRICT,
                    FOREIGN KEY (task_id, summary_artifact_id)
                        REFERENCES artifacts(task_id, artifact_id) ON DELETE RESTRICT
                )"""
            )
            connection.execute(
                """CREATE TRIGGER intelligence_assessments_immutable_update
                BEFORE UPDATE ON intelligence_assessments
                BEGIN SELECT RAISE(ABORT, 'intelligence metadata is immutable'); END"""
            )
            connection.execute(
                """CREATE TRIGGER intelligence_assessments_immutable_delete
                BEFORE DELETE ON intelligence_assessments
                BEGIN SELECT RAISE(ABORT, 'intelligence metadata is immutable'); END"""
            )
            connection.execute("UPDATE schema_info SET version = 4 WHERE singleton = 1")
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    @staticmethod
    def _migrate_v4_to_v5(connection: sqlite3.Connection) -> None:
        """Add native conversation associations and bounded event references."""

        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute(
                "SELECT version FROM schema_info WHERE singleton = 1"
            ).fetchone()["version"]
            if current == 5:
                connection.commit()
                return
            if current != 4:
                raise TaskStoreError(f"cannot migrate task database schema version {current}")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS openhands_runtimes (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE RESTRICT,
                    conversation_id TEXT NOT NULL UNIQUE,
                    agent_server_identity TEXT NOT NULL,
                    agent_server_version TEXT NOT NULL,
                    sdk_version TEXT NOT NULL,
                    tools_version TEXT NOT NULL,
                    agent_profile_id TEXT NOT NULL,
                    native_agent_profile_id TEXT NOT NULL,
                    native_agent_profile_revision INTEGER NOT NULL CHECK (native_agent_profile_revision >= 0),
                    model_profile_id TEXT NOT NULL,
                    native_model TEXT NOT NULL,
                    profile_fingerprint TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    workspace_path TEXT NOT NULL UNIQUE,
                    baseline_commit TEXT NOT NULL,
                    runtime_status TEXT NOT NULL CHECK (
                        runtime_status IN ('CONVERSATION_READY', 'CONTEXT_ATTACHED', 'RECOVERY_REQUIRED')
                    ),
                    execution_status TEXT NOT NULL CHECK (
                        execution_status IN ('NOT_STARTED', 'RUNNING', 'COMPLETED', 'FAILED')
                    ),
                    last_native_event_id TEXT,
                    last_native_event_order INTEGER NOT NULL DEFAULT 0 CHECK (last_native_event_order >= 0),
                    failure_code TEXT,
                    failure_detail TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK ((last_native_event_id IS NULL) = (last_native_event_order = 0)),
                    CHECK (
                        (runtime_status = 'RECOVERY_REQUIRED' AND failure_code IS NOT NULL AND failure_detail IS NOT NULL)
                        OR
                        (runtime_status != 'RECOVERY_REQUIRED' AND failure_code IS NULL AND failure_detail IS NULL)
                    )
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS openhands_event_links (
                    task_id TEXT NOT NULL REFERENCES openhands_runtimes(task_id) ON DELETE RESTRICT,
                    native_event_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    native_order INTEGER NOT NULL CHECK (native_order > 0),
                    native_kind TEXT NOT NULL,
                    native_timestamp TEXT,
                    observed_at TEXT NOT NULL,
                    product_event_sequence INTEGER NOT NULL,
                    PRIMARY KEY (task_id, native_event_id),
                    UNIQUE (task_id, native_order),
                    FOREIGN KEY (task_id, product_event_sequence)
                        REFERENCES events(task_id, sequence) ON DELETE RESTRICT
                )"""
            )
            connection.execute(
                """CREATE TRIGGER IF NOT EXISTS openhands_runtimes_identity_immutable
                BEFORE UPDATE ON openhands_runtimes
                WHEN OLD.task_id != NEW.task_id
                  OR OLD.conversation_id != NEW.conversation_id
                  OR OLD.agent_server_identity != NEW.agent_server_identity
                  OR OLD.agent_server_version != NEW.agent_server_version
                  OR OLD.sdk_version != NEW.sdk_version
                  OR OLD.tools_version != NEW.tools_version
                  OR OLD.agent_profile_id != NEW.agent_profile_id
                  OR OLD.native_agent_profile_id != NEW.native_agent_profile_id
                  OR OLD.native_agent_profile_revision != NEW.native_agent_profile_revision
                  OR OLD.model_profile_id != NEW.model_profile_id
                  OR OLD.native_model != NEW.native_model
                  OR OLD.profile_fingerprint != NEW.profile_fingerprint
                  OR OLD.request_fingerprint != NEW.request_fingerprint
                  OR OLD.workspace_path != NEW.workspace_path
                  OR OLD.baseline_commit != NEW.baseline_commit
                  OR OLD.created_at != NEW.created_at
                BEGIN SELECT RAISE(ABORT, 'OpenHands runtime identity is immutable'); END"""
            )
            connection.execute(
                """CREATE TRIGGER IF NOT EXISTS openhands_runtimes_no_delete
                BEFORE DELETE ON openhands_runtimes
                BEGIN SELECT RAISE(ABORT, 'OpenHands runtime metadata cannot be deleted'); END"""
            )
            connection.execute(
                """CREATE TRIGGER IF NOT EXISTS openhands_event_links_immutable_update
                BEFORE UPDATE ON openhands_event_links
                BEGIN SELECT RAISE(ABORT, 'OpenHands event links are immutable'); END"""
            )
            connection.execute(
                """CREATE TRIGGER IF NOT EXISTS openhands_event_links_immutable_delete
                BEFORE DELETE ON openhands_event_links
                BEGIN SELECT RAISE(ABORT, 'OpenHands event links are immutable'); END"""
            )
            connection.execute("UPDATE schema_info SET version = 5 WHERE singleton = 1")
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    @staticmethod
    def _migrate_v5_to_v6(connection: sqlite3.Connection) -> None:
        """Add durable execution ownership and independent validation attempts."""

        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute(
                "SELECT version FROM schema_info WHERE singleton = 1"
            ).fetchone()["version"]
            if current == 6:
                connection.commit()
                return
            if current != 5:
                raise TaskStoreError(f"cannot migrate task database schema version {current}")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_claims (
                    task_id TEXT PRIMARY KEY REFERENCES openhands_runtimes(task_id) ON DELETE RESTRICT,
                    conversation_id TEXT NOT NULL UNIQUE,
                    worker_id TEXT NOT NULL,
                    claim_token TEXT NOT NULL UNIQUE,
                    dispatch_status TEXT NOT NULL CHECK (
                        dispatch_status IN ('INTENT_RECORDED', 'DISPATCHED', 'RECOVERY_REQUIRED')
                    ),
                    intent_recorded_at TEXT NOT NULL,
                    dispatched_at TEXT,
                    recovery_code TEXT,
                    updated_at TEXT NOT NULL,
                    CHECK (
                        (dispatch_status = 'DISPATCHED' AND dispatched_at IS NOT NULL AND recovery_code IS NULL)
                        OR (dispatch_status = 'RECOVERY_REQUIRED' AND recovery_code IS NOT NULL)
                        OR (dispatch_status = 'INTENT_RECORDED' AND dispatched_at IS NULL AND recovery_code IS NULL)
                    )
                );
                CREATE TABLE IF NOT EXISTS validation_attempts (
                    task_id TEXT NOT NULL REFERENCES openhands_runtimes(task_id) ON DELETE RESTRICT,
                    attempt INTEGER NOT NULL CHECK (attempt > 0),
                    state TEXT NOT NULL CHECK (state IN ('RUNNING', 'COMPLETED')),
                    outcome TEXT CHECK (outcome IN (
                        'PASS', 'REMEDIATION_FAILURE', 'INFRASTRUCTURE_FAILURE', 'VALIDATOR_FAILURE'
                    )),
                    hook_decision TEXT CHECK (hook_decision IN ('ALLOW', 'DENY')),
                    report_artifact_id TEXT,
                    report_sha256 TEXT,
                    validated_head TEXT,
                    validated_tree TEXT,
                    repository_state_sha256 TEXT,
                    original_finding_count INTEGER CHECK (original_finding_count >= 0),
                    resolved_finding_count INTEGER CHECK (resolved_finding_count >= 0),
                    remaining_finding_count INTEGER CHECK (remaining_finding_count >= 0),
                    unknown_finding_count INTEGER CHECK (unknown_finding_count >= 0),
                    new_prohibited_finding_count INTEGER CHECK (new_prohibited_finding_count >= 0),
                    constraints_passed INTEGER CHECK (constraints_passed IS NULL OR constraints_passed IN (0, 1)),
                    bounded_feedback TEXT,
                    conversation_id TEXT NOT NULL,
                    native_hook_event_id TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    PRIMARY KEY (task_id, attempt),
                    UNIQUE (task_id, native_hook_event_id),
                    FOREIGN KEY (task_id, report_artifact_id)
                        REFERENCES artifacts(task_id, artifact_id) ON DELETE RESTRICT,
                    CHECK (
                        (state = 'RUNNING' AND outcome IS NULL AND hook_decision IS NULL
                         AND report_artifact_id IS NULL AND completed_at IS NULL)
                        OR
                        (state = 'COMPLETED' AND outcome IS NOT NULL AND hook_decision IS NOT NULL
                         AND report_artifact_id IS NOT NULL AND report_sha256 IS NOT NULL
                         AND validated_head IS NOT NULL AND validated_tree IS NOT NULL
                         AND repository_state_sha256 IS NOT NULL AND completed_at IS NOT NULL)
                    )
                );
                CREATE TRIGGER IF NOT EXISTS execution_claims_identity_immutable
                BEFORE UPDATE ON execution_claims
                WHEN OLD.task_id != NEW.task_id OR OLD.conversation_id != NEW.conversation_id
                  OR OLD.worker_id != NEW.worker_id OR OLD.claim_token != NEW.claim_token
                  OR OLD.intent_recorded_at != NEW.intent_recorded_at
                BEGIN SELECT RAISE(ABORT, 'execution claim identity is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS execution_claims_no_delete BEFORE DELETE ON execution_claims
                BEGIN SELECT RAISE(ABORT, 'execution claims cannot be deleted'); END;
                CREATE TRIGGER IF NOT EXISTS execution_claims_terminal_immutable
                BEFORE UPDATE ON execution_claims
                WHEN OLD.dispatch_status IN ('DISPATCHED', 'RECOVERY_REQUIRED')
                  AND (OLD.dispatch_status != NEW.dispatch_status
                       OR OLD.dispatched_at IS NOT NEW.dispatched_at
                       OR OLD.recovery_code IS NOT NEW.recovery_code)
                BEGIN SELECT RAISE(ABORT, 'execution claim terminal state is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS validation_attempts_identity_immutable
                BEFORE UPDATE ON validation_attempts
                WHEN OLD.task_id != NEW.task_id OR OLD.attempt != NEW.attempt
                  OR OLD.conversation_id != NEW.conversation_id OR OLD.started_at != NEW.started_at
                BEGIN SELECT RAISE(ABORT, 'validation attempt identity is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS validation_attempts_no_delete BEFORE DELETE ON validation_attempts
                BEGIN SELECT RAISE(ABORT, 'validation attempts cannot be deleted'); END;
                CREATE TRIGGER IF NOT EXISTS validation_attempts_verdict_immutable
                BEFORE UPDATE ON validation_attempts
                WHEN OLD.state = 'COMPLETED' AND (
                    OLD.state != NEW.state OR OLD.outcome IS NOT NEW.outcome
                    OR OLD.hook_decision IS NOT NEW.hook_decision
                    OR OLD.report_artifact_id IS NOT NEW.report_artifact_id
                    OR OLD.report_sha256 IS NOT NEW.report_sha256
                    OR OLD.validated_head IS NOT NEW.validated_head
                    OR OLD.validated_tree IS NOT NEW.validated_tree
                    OR OLD.repository_state_sha256 IS NOT NEW.repository_state_sha256
                    OR OLD.original_finding_count IS NOT NEW.original_finding_count
                    OR OLD.resolved_finding_count IS NOT NEW.resolved_finding_count
                    OR OLD.remaining_finding_count IS NOT NEW.remaining_finding_count
                    OR OLD.unknown_finding_count IS NOT NEW.unknown_finding_count
                    OR OLD.new_prohibited_finding_count IS NOT NEW.new_prohibited_finding_count
                    OR OLD.constraints_passed IS NOT NEW.constraints_passed
                    OR OLD.bounded_feedback IS NOT NEW.bounded_feedback
                    OR OLD.completed_at IS NOT NEW.completed_at
                )
                BEGIN SELECT RAISE(ABORT, 'validation verdict is immutable'); END;
                UPDATE schema_info SET version = 6 WHERE singleton = 1;
                """
            )
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    def register_task(self, request: TaskRequest) -> TaskRegistration:
        # Revalidate direct Python callers as strictly as REST callers.
        request = TaskRequest.from_dict(request.to_dict())
        request_json = canonical_json(request.to_dict())
        request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT task_id, request_hash FROM tasks WHERE idempotency_key = ?",
                (request.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["request_hash"] != request_hash:
                    raise IdempotencyConflictError(request.idempotency_key, existing["task_id"])
                status = self._status_from_row(self._task_row(connection, existing["task_id"]))
                connection.commit()
                return TaskRegistration(status=status, created=False)

            task_id = f"task_{uuid.uuid4().hex}"
            now = utc_now()
            connection.execute(
                """
                INSERT INTO tasks(
                    task_id, idempotency_key, request_hash, request_json,
                    status, stage, execution_status, conversation_id,
                    validation_status, validation_attempts, accepted,
                    delivery_status, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 0, 0, ?, NULL, ?, ?)
                """,
                (
                    task_id,
                    request.idempotency_key,
                    request_hash,
                    request_json,
                    TaskStatus.QUEUED.value,
                    _STATUS_STAGE[TaskStatus.QUEUED],
                    ExecutionStatus.NOT_STARTED.value,
                    ValidationStatus.NOT_VALIDATED.value,
                    DeliveryStatus.NOT_REQUESTED.value,
                    now,
                    now,
                ),
            )
            self._append_event(
                connection,
                task_id=task_id,
                event_type="task.registered",
                stage="queued",
                data={"source": request.source},
                timestamp=now,
            )
            status = self._status_from_row(self._task_row(connection, task_id))
            connection.commit()
            return TaskRegistration(status=status, created=True)
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_status(self, task_id: str) -> TaskStatusSnapshot:
        connection = self._connect()
        try:
            return self._status_from_row(self._task_row(connection, task_id))
        finally:
            connection.close()

    def get_request(self, task_id: str) -> TaskRequest:
        connection = self._connect()
        try:
            row = self._task_row(connection, task_id)
            return TaskRequest.from_dict(json.loads(row["request_json"]))
        finally:
            connection.close()

    def get_preparation(self, task_id: str) -> PreparationRecord | None:
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            row = connection.execute(
                "SELECT * FROM preparations WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            return None if row is None else self._preparation_from_row(row)
        finally:
            connection.close()

    def get_baseline(self, task_id: str) -> BaselineRecord | None:
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            row = connection.execute(
                "SELECT * FROM baseline_assessments WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            return None if row is None else self._baseline_from_row(row)
        finally:
            connection.close()

    def get_intelligence(self, task_id: str) -> IntelligenceRecord | None:
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            row = connection.execute(
                "SELECT * FROM intelligence_assessments WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            return None if row is None else self._intelligence_from_row(row)
        finally:
            connection.close()

    def get_openhands_runtime(self, task_id: str) -> OpenHandsRuntimeRecord | None:
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            row = connection.execute(
                "SELECT * FROM openhands_runtimes WHERE task_id = ?", (task_id,)
            ).fetchone()
            return None if row is None else self._openhands_runtime_from_row(row)
        finally:
            connection.close()

    def list_openhands_event_links(self, task_id: str) -> tuple[OpenHandsEventLink, ...]:
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            rows = connection.execute(
                """SELECT * FROM openhands_event_links
                WHERE task_id = ? ORDER BY native_order ASC""",
                (task_id,),
            ).fetchall()
            return tuple(self._openhands_event_link_from_row(row) for row in rows)
        finally:
            connection.close()

    def get_execution_claim(self, task_id: str) -> ExecutionClaimRecord | None:
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            row = connection.execute(
                "SELECT * FROM execution_claims WHERE task_id = ?", (task_id,)
            ).fetchone()
            return None if row is None else self._execution_claim_from_row(row)
        finally:
            connection.close()

    def claim_execution(self, task_id: str, worker_id: str) -> ExecutionClaimRecord:
        """Record one irreversible dispatch intent before the external /run call."""

        now = utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, task_id)
            runtime_row = connection.execute(
                "SELECT * FROM openhands_runtimes WHERE task_id = ?", (task_id,)
            ).fetchone()
            if runtime_row is None:
                raise ExecutionClaimConflictError("execution requires a native conversation")
            runtime = self._openhands_runtime_from_row(runtime_row)
            if runtime.runtime_status is not OpenHandsRuntimeStatus.CONTEXT_ATTACHED:
                raise ExecutionClaimConflictError("execution requires attached task context")
            if TaskStatus(task["status"]) is not TaskStatus.AGENT_RUNNING:
                raise InvalidTransitionError("execution can start only from AGENT_RUNNING")
            existing = connection.execute(
                "SELECT * FROM execution_claims WHERE task_id = ?", (task_id,)
            ).fetchone()
            if existing is not None:
                current = self._execution_claim_from_row(existing)
                if current.worker_id != worker_id:
                    raise ExecutionClaimConflictError("task is already owned by another worker")
                connection.commit()
                return current
            claim = ExecutionClaimRecord(
                task_id=task_id,
                conversation_id=runtime.conversation_id,
                worker_id=worker_id,
                claim_token=f"claim_{uuid.uuid4().hex}",
                dispatch_status=ExecutionDispatchStatus.INTENT_RECORDED,
                intent_recorded_at=now,
                dispatched_at=None,
                recovery_code=None,
                updated_at=now,
            )
            connection.execute(
                """INSERT INTO execution_claims(
                    task_id, conversation_id, worker_id, claim_token, dispatch_status,
                    intent_recorded_at, dispatched_at, recovery_code, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)""",
                (
                    claim.task_id, claim.conversation_id, claim.worker_id,
                    claim.claim_token, claim.dispatch_status.value,
                    claim.intent_recorded_at, claim.updated_at,
                ),
            )
            connection.execute(
                """UPDATE tasks SET execution_status = ?, updated_at = ? WHERE task_id = ?""",
                (ExecutionStatus.RUNNING.value, now, task_id),
            )
            connection.execute(
                """UPDATE openhands_runtimes SET execution_status = ?, updated_at = ?
                WHERE task_id = ?""",
                (ExecutionStatus.RUNNING.value, now, task_id),
            )
            self._append_event(
                connection, task_id=task_id, event_type="agent.execution.intent-recorded",
                stage="agent", data={"conversationId": claim.conversation_id}, timestamp=now,
            )
            connection.commit()
            return claim
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def update_execution_dispatch(
        self, task_id: str, *, dispatched: bool, recovery_code: str | None = None
    ) -> ExecutionClaimRecord:
        now = utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM execution_claims WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise ExecutionClaimConflictError("execution has no durable intent")
            current = self._execution_claim_from_row(row)
            desired = (
                ExecutionDispatchStatus.DISPATCHED
                if dispatched
                else ExecutionDispatchStatus.RECOVERY_REQUIRED
            )
            if current.dispatch_status is desired:
                connection.commit()
                return current
            if current.dispatch_status is not ExecutionDispatchStatus.INTENT_RECORDED:
                raise ExecutionClaimConflictError("execution dispatch decision is already final")
            if dispatched and recovery_code is not None:
                raise ExecutionClaimConflictError("confirmed dispatch cannot have a recovery code")
            if not dispatched and not recovery_code:
                raise ExecutionClaimConflictError("uncertain dispatch requires a recovery code")
            connection.execute(
                """UPDATE execution_claims SET dispatch_status = ?, dispatched_at = ?,
                    recovery_code = ?, updated_at = ? WHERE task_id = ?""",
                (desired.value, now if dispatched else None, recovery_code, now, task_id),
            )
            self._append_event(
                connection,
                task_id=task_id,
                event_type=("agent.execution.dispatched" if dispatched else "agent.execution.recovery-required"),
                stage="agent",
                data={"conversationId": current.conversation_id, **({"recoveryCode": recovery_code} if recovery_code else {})},
                timestamp=now,
            )
            connection.commit()
            return self._execution_claim_from_row(
                connection.execute("SELECT * FROM execution_claims WHERE task_id = ?", (task_id,)).fetchone()
            )
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def record_native_execution_terminal(
        self, task_id: str, *, completed: bool
    ) -> TaskStatusSnapshot:
        """Reconcile native termination without ever inferring validation PASS."""

        now = utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, task_id)
            runtime = connection.execute(
                "SELECT * FROM openhands_runtimes WHERE task_id = ?", (task_id,)
            ).fetchone()
            if runtime is None:
                raise OpenHandsRuntimeConflictError("task has no native runtime")
            execution = ExecutionStatus.COMPLETED if completed else ExecutionStatus.FAILED
            if (
                ExecutionStatus(task["execution_status"]) is execution
                and ExecutionStatus(runtime["execution_status"]) is execution
            ):
                status = self._status_from_row(task)
                connection.commit()
                return status
            current_status = TaskStatus(task["status"])
            validation = ValidationStatus(task["validation_status"])
            if completed and validation is ValidationStatus.PASSED:
                next_status = TaskStatus.ACCEPTED
            elif current_status is TaskStatus.FAILED_INFRASTRUCTURE:
                next_status = current_status
            elif completed:
                next_status = TaskStatus.FAILED_VALIDATION
            else:
                next_status = TaskStatus.FAILED_INFRASTRUCTURE
            if current_status in {TaskStatus.FAILED_VALIDATION, TaskStatus.CANCELLED}:
                next_status = current_status
            connection.execute(
                """UPDATE tasks SET status = ?, stage = ?, execution_status = ?,
                    accepted = ?, updated_at = ? WHERE task_id = ?""",
                (next_status.value, _STATUS_STAGE[next_status], execution.value,
                 int(validation is ValidationStatus.PASSED), now, task_id),
            )
            connection.execute(
                "UPDATE openhands_runtimes SET execution_status = ?, updated_at = ? WHERE task_id = ?",
                (execution.value, now, task_id),
            )
            self._append_event(
                connection, task_id=task_id,
                event_type=("agent.execution.completed" if completed else "agent.execution.failed"),
                stage="agent", data={"accepted": validation is ValidationStatus.PASSED}, timestamp=now,
            )
            request_mode = json.loads(task["request_json"])["delivery"]["mode"]
            if next_status is TaskStatus.ACCEPTED and request_mode == "github_pr":
                connection.execute(
                    "UPDATE tasks SET delivery_status = ? WHERE task_id = ?",
                    (DeliveryStatus.PENDING.value, task_id),
                )
            if next_status in {
                TaskStatus.ACCEPTED,
                TaskStatus.FAILED_VALIDATION,
                TaskStatus.FAILED_INFRASTRUCTURE,
            } and task["result_json"] is None and not (
                next_status is TaskStatus.ACCEPTED and request_mode == "github_pr"
            ):
                attempt = connection.execute(
                    """SELECT * FROM validation_attempts WHERE task_id = ? AND state = 'COMPLETED'
                    ORDER BY attempt DESC LIMIT 1""", (task_id,),
                ).fetchone()
                if next_status is TaskStatus.ACCEPTED and (
                    attempt is None or attempt["outcome"] != ValidationOutcome.PASS.value
                ):
                    raise ValidationConflictError("accepted task has no durable PASS attempt")
                artifact_ids = tuple(
                    row["artifact_id"] for row in connection.execute(
                        "SELECT artifact_id FROM artifacts WHERE task_id = ? ORDER BY created_at, artifact_id",
                        (task_id,),
                    ).fetchall()
                )
                result = TaskResult(
                    task_id=task_id,
                    outcome=ResultOutcome(next_status.value),
                    execution_status=execution,
                    validation_status=validation,
                    delivery_status=DeliveryStatus.NOT_REQUESTED,
                    baseline_commit=runtime["baseline_commit"],
                    validated_tree=attempt["validated_tree"] if attempt is not None else None,
                    validation_attempt=attempt["attempt"] if attempt is not None else None,
                    validation_report_artifact_id=(
                        attempt["report_artifact_id"] if attempt is not None else None
                    ),
                    conversation_id=runtime["conversation_id"],
                    artifact_ids=artifact_ids,
                    completed_at=now,
                )
                connection.execute(
                    "UPDATE tasks SET result_json = ? WHERE task_id = ?",
                    (canonical_json(result.to_dict()), task_id),
                )
            connection.commit()
            return self._status_from_row(self._task_row(connection, task_id))
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def begin_validation(self, task_id: str) -> ValidationAttemptRecord:
        """Atomically reserve the next Stop Hook attempt and enter VALIDATING."""

        now = utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, task_id)
            current = TaskStatus(task["status"])
            running = connection.execute(
                """SELECT * FROM validation_attempts WHERE task_id = ? AND state = 'RUNNING'
                ORDER BY attempt DESC LIMIT 1""", (task_id,),
            ).fetchone()
            if running is not None:
                connection.commit()
                return self._validation_attempt_from_row(running)
            if current is not TaskStatus.AGENT_RUNNING:
                raise InvalidTransitionError("validation can start only from AGENT_RUNNING")
            runtime = connection.execute(
                "SELECT conversation_id FROM openhands_runtimes WHERE task_id = ?", (task_id,)
            ).fetchone()
            claim = connection.execute(
                "SELECT dispatch_status FROM execution_claims WHERE task_id = ?", (task_id,)
            ).fetchone()
            if runtime is None or claim is None or claim["dispatch_status"] not in {
                ExecutionDispatchStatus.DISPATCHED.value,
                ExecutionDispatchStatus.RECOVERY_REQUIRED.value,
            }:
                raise ValidationConflictError("validation requires a durably dispatched execution")
            attempt = int(task["validation_attempts"]) + 1
            connection.execute(
                """INSERT INTO validation_attempts(
                    task_id, attempt, state, conversation_id, started_at
                ) VALUES (?, ?, 'RUNNING', ?, ?)""",
                (task_id, attempt, runtime["conversation_id"], now),
            )
            connection.execute(
                """UPDATE tasks SET status = ?, stage = ?, validation_status = ?,
                    validation_attempts = ?, accepted = 0, updated_at = ? WHERE task_id = ?""",
                (TaskStatus.VALIDATING.value, _STATUS_STAGE[TaskStatus.VALIDATING],
                 ValidationStatus.RUNNING.value, attempt, now, task_id),
            )
            self._append_event(
                connection, task_id=task_id, event_type="validation.started",
                stage="validation", data={"attempt": attempt, "conversationId": runtime["conversation_id"]},
                timestamp=now,
            )
            connection.commit()
            return self._validation_attempt_from_row(
                connection.execute(
                    "SELECT * FROM validation_attempts WHERE task_id = ? AND attempt = ?",
                    (task_id, attempt),
                ).fetchone()
            )
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def complete_validation(
        self, record: ValidationAttemptRecord, artifact: ArtifactMetadata
    ) -> TaskStatusSnapshot:
        """Commit immutable evidence, verdict, lifecycle and event in one transaction."""

        if record.state is not ValidationAttemptState.COMPLETED:
            raise ValidationConflictError("validation verdict must be complete")
        if artifact.task_id != record.task_id or artifact.artifact_id != record.report_artifact_id or artifact.sha256 != record.report_sha256:
            raise ValidationConflictError("validation artifact identity differs from verdict")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, record.task_id)
            existing = connection.execute(
                "SELECT * FROM validation_attempts WHERE task_id = ? AND attempt = ?",
                (record.task_id, record.attempt),
            ).fetchone()
            if existing is None:
                raise ValidationConflictError("validation attempt was not reserved")
            current = self._validation_attempt_from_row(existing)
            if current.state is ValidationAttemptState.COMPLETED:
                if current != record:
                    raise ValidationConflictError("validation verdict is immutable")
                connection.commit()
                return self._status_from_row(task)
            if TaskStatus(task["status"]) is not TaskStatus.VALIDATING:
                raise InvalidTransitionError("task is not validating")
            try:
                connection.execute(
                    """INSERT INTO artifacts(task_id, artifact_id, kind, relative_path,
                        media_type, sha256, size_bytes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (artifact.task_id, artifact.artifact_id, artifact.kind, artifact.relative_path,
                     artifact.media_type, artifact.sha256, artifact.size_bytes, artifact.created_at),
                )
            except sqlite3.IntegrityError as exc:
                prior = connection.execute(
                    "SELECT * FROM artifacts WHERE task_id = ? AND artifact_id = ?",
                    (artifact.task_id, artifact.artifact_id),
                ).fetchone()
                if prior is None or self._artifact_from_row(prior) != artifact:
                    raise ArtifactConflictError("validation artifact conflicts with durable metadata") from exc
            connection.execute(
                """UPDATE validation_attempts SET state = ?, outcome = ?, hook_decision = ?,
                    report_artifact_id = ?, report_sha256 = ?, validated_head = ?,
                    validated_tree = ?, repository_state_sha256 = ?, original_finding_count = ?,
                    resolved_finding_count = ?, remaining_finding_count = ?, unknown_finding_count = ?,
                    new_prohibited_finding_count = ?, constraints_passed = ?, bounded_feedback = ?,
                    completed_at = ? WHERE task_id = ? AND attempt = ?""",
                (record.state.value, record.outcome.value, record.hook_decision.value,
                 record.report_artifact_id, record.report_sha256, record.validated_head,
                 record.validated_tree, record.repository_state_sha256, record.original_finding_count,
                 record.resolved_finding_count, record.remaining_finding_count,
                 record.unknown_finding_count, record.new_prohibited_finding_count,
                 int(bool(record.constraints_passed)), record.bounded_feedback, record.completed_at,
                 record.task_id, record.attempt),
            )
            if record.outcome is ValidationOutcome.PASS:
                status, validation = TaskStatus.ACCEPTED, ValidationStatus.PASSED
            elif record.outcome is ValidationOutcome.REMEDIATION_FAILURE and record.hook_decision is StopHookDecision.DENY:
                status, validation = TaskStatus.AGENT_RUNNING, ValidationStatus.FAILED
            elif record.outcome is ValidationOutcome.REMEDIATION_FAILURE:
                status, validation = TaskStatus.FAILED_VALIDATION, ValidationStatus.FAILED
            elif record.outcome is ValidationOutcome.INFRASTRUCTURE_FAILURE:
                status, validation = TaskStatus.FAILED_INFRASTRUCTURE, ValidationStatus.INFRASTRUCTURE_ERROR
            else:
                status, validation = TaskStatus.FAILED_INFRASTRUCTURE, ValidationStatus.INFRASTRUCTURE_ERROR
            connection.execute(
                """UPDATE tasks SET status = ?, stage = ?, validation_status = ?,
                    accepted = ?, updated_at = ? WHERE task_id = ?""",
                (status.value, _STATUS_STAGE[status], validation.value,
                 int(validation is ValidationStatus.PASSED), record.completed_at, record.task_id),
            )
            self._append_event(
                connection, task_id=record.task_id, event_type="validation.completed",
                stage="validation",
                data={"attempt": record.attempt, "outcome": record.outcome.value,
                      "decision": record.hook_decision.value,
                      "reportArtifactId": record.report_artifact_id,
                      "validatedTree": record.validated_tree},
                timestamp=record.completed_at or utc_now(),
            )
            connection.commit()
            return self._status_from_row(self._task_row(connection, record.task_id))
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def list_validation_attempts(self, task_id: str) -> tuple[ValidationAttemptRecord, ...]:
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            rows = connection.execute(
                "SELECT * FROM validation_attempts WHERE task_id = ? ORDER BY attempt", (task_id,)
            ).fetchall()
            return tuple(self._validation_attempt_from_row(row) for row in rows)
        finally:
            connection.close()

    def link_validation_hook_event(self, task_id: str, attempt: int, native_event_id: str) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT native_hook_event_id FROM validation_attempts WHERE task_id = ? AND attempt = ?",
                (task_id, attempt),
            ).fetchone()
            if row is None:
                raise ValidationConflictError("validation attempt was not found")
            if row["native_hook_event_id"] not in (None, native_event_id):
                raise ValidationConflictError("validation attempt is linked to another native event")
            connection.execute(
                "UPDATE validation_attempts SET native_hook_event_id = ? WHERE task_id = ? AND attempt = ?",
                (native_event_id, task_id, attempt),
            )
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def start_preparation(self, task_id: str) -> TaskStatusSnapshot:
        """Idempotently reserve the PREPARING stage for a trusted internal caller."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._task_row(connection, task_id)
            current = TaskStatus(row["status"])
            if current is TaskStatus.PREPARING:
                status = self._status_from_row(row)
                connection.commit()
                return status
            preparation = connection.execute(
                "SELECT task_id FROM preparations WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if preparation is not None:
                status = self._status_from_row(row)
                connection.commit()
                return status
            if current is not TaskStatus.QUEUED:
                raise InvalidTransitionError(
                    f"task {task_id!r} cannot start preparation from {current.value}"
                )
            now = utc_now()
            connection.execute(
                "UPDATE tasks SET status = ?, stage = ?, updated_at = ? WHERE task_id = ?",
                (TaskStatus.PREPARING.value, _STATUS_STAGE[TaskStatus.PREPARING], now, task_id),
            )
            self._append_event(
                connection,
                task_id=task_id,
                event_type="preparation.started",
                stage=_STATUS_STAGE[TaskStatus.PREPARING],
                data={},
                timestamp=now,
            )
            status = self._status_from_row(self._task_row(connection, task_id))
            connection.commit()
            return status
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def complete_preparation(self, preparation: PreparationRecord) -> TaskStatusSnapshot:
        """Atomically persist immutable baseline identity and enter BASELINING."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, preparation.task_id)
            request = TaskRequest.from_dict(json.loads(task["request_json"]))
            if (
                preparation.repository_url != request.repository.url
                or preparation.base_ref != request.repository.base_ref
                or preparation.expected_commit != request.repository.expected_commit
            ):
                raise PreparationConflictError(
                    "preparation identity does not match the registered task contract"
                )
            existing = connection.execute(
                "SELECT * FROM preparations WHERE task_id = ?",
                (preparation.task_id,),
            ).fetchone()
            if existing is not None:
                recorded = self._preparation_from_row(existing)
                if recorded != preparation:
                    raise PreparationConflictError("preparation metadata is immutable")
                status = self._status_from_row(task)
                connection.commit()
                return status
            if TaskStatus(task["status"]) is not TaskStatus.PREPARING:
                raise InvalidTransitionError(
                    "preparation can complete only while the task is PREPARING"
                )
            connection.execute(
                """INSERT INTO preparations(
                    task_id, repository_url, base_ref, expected_commit,
                    baseline_commit, source_path, workspace_path,
                    local_branch, prepared_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    preparation.task_id,
                    preparation.repository_url,
                    preparation.base_ref,
                    preparation.expected_commit,
                    preparation.baseline_commit,
                    preparation.source_path,
                    preparation.workspace_path,
                    preparation.local_branch,
                    preparation.prepared_at,
                ),
            )
            connection.execute(
                "UPDATE tasks SET status = ?, stage = ?, updated_at = ? WHERE task_id = ?",
                (
                    TaskStatus.BASELINING.value,
                    _STATUS_STAGE[TaskStatus.BASELINING],
                    preparation.prepared_at,
                    preparation.task_id,
                ),
            )
            self._append_event(
                connection,
                task_id=preparation.task_id,
                event_type="preparation.completed",
                stage=_STATUS_STAGE[TaskStatus.PREPARING],
                data={
                    "baselineCommit": preparation.baseline_commit,
                    "localBranch": preparation.local_branch,
                },
                timestamp=preparation.prepared_at,
            )
            status = self._status_from_row(self._task_row(connection, preparation.task_id))
            connection.commit()
            return status
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise PreparationConflictError(
                "preparation metadata could not be committed atomically"
            ) from exc
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def complete_baseline(
        self,
        baseline: BaselineRecord,
        artifacts: tuple[ArtifactMetadata, ...],
    ) -> TaskStatusSnapshot:
        """Atomically register evidence and finish the BASELINING stage."""

        target_status = {
            BaselineAssessmentStatus.COMPLETED: TaskStatus.INTELLIGENCE,
            BaselineAssessmentStatus.NO_TARGET_FINDINGS: TaskStatus.FAILED_VALIDATION,
            BaselineAssessmentStatus.FAILED_BUILD: TaskStatus.FAILED_VALIDATION,
            BaselineAssessmentStatus.FAILED_SCANNER: TaskStatus.FAILED_INFRASTRUCTURE,
        }[baseline.assessment_status]
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, baseline.task_id)
            preparation_row = connection.execute(
                "SELECT * FROM preparations WHERE task_id = ?", (baseline.task_id,)
            ).fetchone()
            if preparation_row is None:
                raise BaselineConflictError("baseline requires immutable preparation metadata")
            preparation = self._preparation_from_row(preparation_row)
            if baseline.baseline_commit != preparation.baseline_commit:
                raise BaselineConflictError("baseline commit differs from immutable preparation")
            existing = connection.execute(
                "SELECT * FROM baseline_assessments WHERE task_id = ?", (baseline.task_id,)
            ).fetchone()
            if existing is not None:
                if self._baseline_from_row(existing) != baseline:
                    raise BaselineConflictError("baseline metadata is immutable")
                status = self._status_from_row(task)
                if status.status is not target_status:
                    raise BaselineConflictError("baseline metadata and task status disagree")
                connection.commit()
                return status
            if TaskStatus(task["status"]) is not TaskStatus.BASELINING:
                raise InvalidTransitionError("baseline can complete only while the task is BASELINING")
            if not artifacts:
                raise BaselineConflictError("baseline completion requires artifact metadata")
            report_artifacts = [item for item in artifacts if item.artifact_id == baseline.report_artifact_id]
            if (
                len(report_artifacts) != 1
                or report_artifacts[0].task_id != baseline.task_id
                or report_artifacts[0].sha256 != baseline.report_sha256
            ):
                raise BaselineConflictError("baseline report artifact does not match baseline metadata")
            for artifact in artifacts:
                if artifact.task_id != baseline.task_id:
                    raise BaselineConflictError("baseline artifact belongs to another task")
                try:
                    connection.execute(
                        """INSERT INTO artifacts(
                            task_id, artifact_id, kind, relative_path, media_type,
                            sha256, size_bytes, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            artifact.task_id,
                            artifact.artifact_id,
                            artifact.kind,
                            artifact.relative_path,
                            artifact.media_type,
                            artifact.sha256,
                            artifact.size_bytes,
                            artifact.created_at,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise BaselineConflictError("baseline artifact metadata conflicts with existing data") from exc
            connection.execute(
                """INSERT INTO baseline_assessments(
                    task_id, baseline_commit, assessment_status, build_succeeded,
                    scanner_outcome, finding_count, report_artifact_id,
                    report_sha256, tool_versions_json, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    baseline.task_id,
                    baseline.baseline_commit,
                    baseline.assessment_status.value,
                    int(baseline.build_succeeded),
                    baseline.scanner_outcome,
                    baseline.finding_count,
                    baseline.report_artifact_id,
                    baseline.report_sha256,
                    canonical_json(dict(baseline.tool_versions)),
                    baseline.completed_at,
                ),
            )
            connection.execute(
                "UPDATE tasks SET status = ?, stage = ?, updated_at = ? WHERE task_id = ?",
                (
                    target_status.value,
                    _STATUS_STAGE[target_status],
                    baseline.completed_at,
                    baseline.task_id,
                ),
            )
            event_type = (
                "baseline.completed"
                if baseline.assessment_status is BaselineAssessmentStatus.COMPLETED
                else "baseline.failed"
            )
            self._append_event(
                connection,
                task_id=baseline.task_id,
                event_type=event_type,
                stage=_STATUS_STAGE[TaskStatus.BASELINING],
                data={
                    "assessmentStatus": baseline.assessment_status.value,
                    "baselineCommit": baseline.baseline_commit,
                    "reportArtifactId": baseline.report_artifact_id,
                    "scannerOutcome": baseline.scanner_outcome,
                },
                timestamp=baseline.completed_at,
            )
            status = self._status_from_row(self._task_row(connection, baseline.task_id))
            connection.commit()
            return status
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def complete_intelligence(
        self,
        intelligence: IntelligenceRecord,
        artifacts: tuple[ArtifactMetadata, ...],
    ) -> TaskStatusSnapshot:
        """Atomically persist optional intelligence and leave its stage."""

        continuing = {
            IntelligenceOutcome.DISABLED,
            IntelligenceOutcome.NOT_APPLICABLE,
            IntelligenceOutcome.COMPLETE,
            IntelligenceOutcome.PARTIAL,
            IntelligenceOutcome.FAILED,
        }
        target_status = (
            TaskStatus.AGENT_RUNNING
            if intelligence.outcome in continuing
            else TaskStatus.FAILED_INFRASTRUCTURE
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, intelligence.task_id)
            baseline_row = connection.execute(
                "SELECT * FROM baseline_assessments WHERE task_id = ?",
                (intelligence.task_id,),
            ).fetchone()
            if baseline_row is None:
                raise IntelligenceConflictError("intelligence requires durable baseline metadata")
            baseline = self._baseline_from_row(baseline_row)
            if (
                baseline.assessment_status is not BaselineAssessmentStatus.COMPLETED
                or baseline.baseline_commit != intelligence.baseline_commit
            ):
                raise IntelligenceConflictError("intelligence requires a successful matching baseline")
            existing = connection.execute(
                "SELECT * FROM intelligence_assessments WHERE task_id = ?",
                (intelligence.task_id,),
            ).fetchone()
            if existing is not None:
                if self._intelligence_from_row(existing) != intelligence:
                    raise IntelligenceConflictError("intelligence metadata is immutable")
                status = self._status_from_row(task)
                if status.status is not target_status:
                    raise IntelligenceConflictError("intelligence metadata and task status disagree")
                connection.commit()
                return status
            if TaskStatus(task["status"]) is not TaskStatus.INTELLIGENCE:
                raise InvalidTransitionError(
                    "intelligence can complete only while the task is INTELLIGENCE"
                )
            by_id = {artifact.artifact_id: artifact for artifact in artifacts}
            record_artifact = by_id.get(intelligence.record_artifact_id)
            summary_artifact = by_id.get(intelligence.summary_artifact_id)
            if (
                len(by_id) != len(artifacts)
                or record_artifact is None
                or summary_artifact is None
                or record_artifact.sha256 != intelligence.record_sha256
            ):
                raise IntelligenceConflictError(
                    "intelligence record and artifact metadata disagree"
                )
            for artifact in artifacts:
                if artifact.task_id != intelligence.task_id:
                    raise IntelligenceConflictError("intelligence artifact belongs to another task")
                try:
                    connection.execute(
                        """INSERT INTO artifacts(
                            task_id, artifact_id, kind, relative_path, media_type,
                            sha256, size_bytes, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            artifact.task_id,
                            artifact.artifact_id,
                            artifact.kind,
                            artifact.relative_path,
                            artifact.media_type,
                            artifact.sha256,
                            artifact.size_bytes,
                            artifact.created_at,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise IntelligenceConflictError(
                        "intelligence artifact metadata conflicts with existing data"
                    ) from exc
            connection.execute(
                """INSERT INTO intelligence_assessments(
                    task_id, baseline_commit, outcome, applicable, invoked, reused,
                    profile_id, fingerprint, selection_manifest_json,
                    evaluated_versions_json, record_artifact_id, record_sha256,
                    summary_artifact_id, explanation, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    intelligence.task_id,
                    intelligence.baseline_commit,
                    intelligence.outcome.value,
                    None if intelligence.applicable is None else int(intelligence.applicable),
                    int(intelligence.invoked),
                    int(intelligence.reused),
                    intelligence.profile_id,
                    intelligence.fingerprint,
                    canonical_json(dict(intelligence.selection_manifest)),
                    canonical_json({"versions": list(intelligence.evaluated_versions)}),
                    intelligence.record_artifact_id,
                    intelligence.record_sha256,
                    intelligence.summary_artifact_id,
                    intelligence.explanation,
                    intelligence.completed_at,
                ),
            )
            connection.execute(
                "UPDATE tasks SET status = ?, stage = ?, updated_at = ? WHERE task_id = ?",
                (
                    target_status.value,
                    _STATUS_STAGE[target_status],
                    intelligence.completed_at,
                    intelligence.task_id,
                ),
            )
            if intelligence.outcome in {
                IntelligenceOutcome.DISABLED,
                IntelligenceOutcome.NOT_APPLICABLE,
            }:
                event_type = "intelligence.skipped"
            elif intelligence.outcome in {IntelligenceOutcome.PARTIAL, IntelligenceOutcome.FAILED}:
                event_type = "intelligence.incomplete"
            elif intelligence.outcome is IntelligenceOutcome.COMPLETE:
                event_type = "intelligence.completed"
            else:
                event_type = "intelligence.failed"
            self._append_event(
                connection,
                task_id=intelligence.task_id,
                event_type=event_type,
                stage=_STATUS_STAGE[TaskStatus.INTELLIGENCE],
                data={
                    "outcome": intelligence.outcome.value,
                    "recordArtifactId": intelligence.record_artifact_id,
                    "summaryArtifactId": intelligence.summary_artifact_id,
                    "agentStagePending": target_status is TaskStatus.AGENT_RUNNING,
                },
                timestamp=intelligence.completed_at,
            )
            status = self._status_from_row(self._task_row(connection, intelligence.task_id))
            connection.commit()
            return status
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def record_openhands_runtime(
        self, runtime: OpenHandsRuntimeRecord
    ) -> OpenHandsRuntimeRecord:
        """Atomically bind one product task to one native conversation."""

        if runtime.execution_status is not ExecutionStatus.NOT_STARTED:
            raise OpenHandsRuntimeConflictError(
                "Change 5 can only persist a non-running native conversation"
            )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, runtime.task_id)
            if TaskStatus(task["status"]) is not TaskStatus.AGENT_RUNNING:
                raise InvalidTransitionError(
                    "OpenHands conversation provisioning requires AGENT_RUNNING"
                )
            if ExecutionStatus(task["execution_status"]) is not ExecutionStatus.NOT_STARTED:
                raise InvalidTransitionError(
                    "OpenHands conversation provisioning requires NOT_STARTED execution"
                )
            if connection.execute(
                "SELECT 1 FROM preparations WHERE task_id = ?", (runtime.task_id,)
            ).fetchone() is None:
                raise OpenHandsRuntimeConflictError(
                    "OpenHands conversation requires durable preparation metadata"
                )
            if connection.execute(
                "SELECT 1 FROM baseline_assessments WHERE task_id = ?", (runtime.task_id,)
            ).fetchone() is None:
                raise OpenHandsRuntimeConflictError(
                    "OpenHands conversation requires durable baseline metadata"
                )
            if connection.execute(
                "SELECT 1 FROM intelligence_assessments WHERE task_id = ?", (runtime.task_id,)
            ).fetchone() is None:
                raise OpenHandsRuntimeConflictError(
                    "OpenHands conversation requires durable intelligence metadata"
                )
            existing = connection.execute(
                "SELECT * FROM openhands_runtimes WHERE task_id = ?", (runtime.task_id,)
            ).fetchone()
            if existing is not None:
                current = self._openhands_runtime_from_row(existing)
                if self._openhands_runtime_identity(current) != self._openhands_runtime_identity(runtime):
                    raise OpenHandsRuntimeConflictError(
                        "OpenHands task/conversation association is immutable"
                    )
                connection.commit()
                return current
            if task["conversation_id"] not in (None, runtime.conversation_id):
                raise OpenHandsRuntimeConflictError(
                    "task is already associated with another conversation"
                )
            try:
                connection.execute(
                    """INSERT INTO openhands_runtimes(
                        task_id, conversation_id, agent_server_identity,
                        agent_server_version, sdk_version, tools_version,
                        agent_profile_id, native_agent_profile_id,
                        native_agent_profile_revision, model_profile_id,
                        native_model, profile_fingerprint, request_fingerprint,
                        workspace_path, baseline_commit, runtime_status,
                        execution_status, last_native_event_id,
                        last_native_event_order, failure_code, failure_detail,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        runtime.task_id,
                        runtime.conversation_id,
                        runtime.agent_server_identity,
                        runtime.agent_server_version,
                        runtime.sdk_version,
                        runtime.tools_version,
                        runtime.agent_profile_id,
                        runtime.native_agent_profile_id,
                        runtime.native_agent_profile_revision,
                        runtime.model_profile_id,
                        runtime.native_model,
                        runtime.profile_fingerprint,
                        runtime.request_fingerprint,
                        runtime.workspace_path,
                        runtime.baseline_commit,
                        runtime.runtime_status.value,
                        runtime.execution_status.value,
                        runtime.last_native_event_id,
                        runtime.last_native_event_order,
                        runtime.failure_code,
                        runtime.failure_detail,
                        runtime.created_at,
                        runtime.updated_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise OpenHandsRuntimeConflictError(
                    "native conversation or workspace is already associated"
                ) from exc
            connection.execute(
                """UPDATE tasks SET conversation_id = ?, updated_at = ?
                WHERE task_id = ?""",
                (runtime.conversation_id, runtime.updated_at, runtime.task_id),
            )
            event_type = (
                "agent.recovery.required"
                if runtime.runtime_status is OpenHandsRuntimeStatus.RECOVERY_REQUIRED
                else "agent.conversation.created"
            )
            self._append_event(
                connection,
                task_id=runtime.task_id,
                event_type=event_type,
                stage="agent",
                data={
                    "conversationId": runtime.conversation_id,
                    "runtimeStatus": runtime.runtime_status.value,
                    "executionStarted": False,
                    **(
                        {"failureCode": runtime.failure_code}
                        if runtime.failure_code is not None
                        else {}
                    ),
                },
                timestamp=runtime.updated_at,
            )
            connection.commit()
            return runtime
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def mark_openhands_recovery_required(
        self, task_id: str, *, failure_code: str, failure_detail: str
    ) -> OpenHandsRuntimeRecord:
        """Stop uncertain native operations without inferring execution success."""

        now = utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._task_row(connection, task_id)
            row = connection.execute(
                "SELECT * FROM openhands_runtimes WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise OpenHandsRuntimeConflictError(
                    "cannot mark recovery before conversation identity is recorded"
                )
            current = self._openhands_runtime_from_row(row)
            if current.runtime_status is OpenHandsRuntimeStatus.RECOVERY_REQUIRED:
                if (
                    current.failure_code != failure_code
                    or current.failure_detail != failure_detail
                ):
                    raise OpenHandsRuntimeConflictError(
                        "existing recovery metadata differs"
                    )
                connection.commit()
                return current
            candidate = OpenHandsRuntimeRecord(
                **{
                    **current.__dict__,
                    "runtime_status": OpenHandsRuntimeStatus.RECOVERY_REQUIRED,
                    "failure_code": failure_code,
                    "failure_detail": failure_detail,
                    "updated_at": now,
                }
            )
            connection.execute(
                """UPDATE openhands_runtimes
                SET runtime_status = ?, failure_code = ?, failure_detail = ?, updated_at = ?
                WHERE task_id = ?""",
                (
                    candidate.runtime_status.value,
                    candidate.failure_code,
                    candidate.failure_detail,
                    candidate.updated_at,
                    task_id,
                ),
            )
            self._append_event(
                connection,
                task_id=task_id,
                event_type="agent.recovery.required",
                stage="agent",
                data={
                    "conversationId": candidate.conversation_id,
                    "failureCode": candidate.failure_code,
                    "executionStarted": False,
                },
                timestamp=now,
            )
            connection.execute(
                "UPDATE tasks SET updated_at = ? WHERE task_id = ?", (now, task_id)
            )
            connection.commit()
            return candidate
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def complete_openhands_recovery(
        self, task_id: str, *, expected_failure_code: str
    ) -> OpenHandsRuntimeRecord:
        """Acknowledge one explicitly reverified, non-running native identity.

        Historical recovery events remain append-only; only the runtime's
        current condition is advanced so its verified context event can be
        linked in a separate atomic operation.
        """

        now = utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = self._task_row(connection, task_id)
            row = connection.execute(
                "SELECT * FROM openhands_runtimes WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise OpenHandsRuntimeConflictError("task has no native runtime")
            current = self._openhands_runtime_from_row(row)
            if (
                current.runtime_status is not OpenHandsRuntimeStatus.RECOVERY_REQUIRED
                or current.failure_code != expected_failure_code
                or current.execution_status is not ExecutionStatus.NOT_STARTED
                or ExecutionStatus(task["execution_status"])
                is not ExecutionStatus.NOT_STARTED
            ):
                raise OpenHandsRuntimeConflictError(
                    "native recovery condition differs from the explicit request"
                )
            connection.execute(
                """UPDATE openhands_runtimes
                SET runtime_status = ?, failure_code = NULL, failure_detail = NULL,
                    updated_at = ? WHERE task_id = ?""",
                (OpenHandsRuntimeStatus.CONVERSATION_READY.value, now, task_id),
            )
            self._append_event(
                connection,
                task_id=task_id,
                event_type="agent.recovery.completed",
                stage="agent",
                data={
                    "conversationId": current.conversation_id,
                    "resolvedFailureCode": expected_failure_code,
                    "executionStarted": False,
                },
                timestamp=now,
            )
            connection.execute(
                "UPDATE tasks SET updated_at = ? WHERE task_id = ?", (now, task_id)
            )
            updated = self._openhands_runtime_from_row(
                connection.execute(
                    "SELECT * FROM openhands_runtimes WHERE task_id = ?", (task_id,)
                ).fetchone()
            )
            connection.commit()
            return updated
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def link_openhands_event(
        self,
        link: OpenHandsEventLink,
        *,
        context_attached: bool = False,
    ) -> OpenHandsRuntimeRecord:
        """Append a bounded native-event pointer and its product event atomically."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._task_row(connection, link.task_id)
            runtime_row = connection.execute(
                "SELECT * FROM openhands_runtimes WHERE task_id = ?", (link.task_id,)
            ).fetchone()
            if runtime_row is None:
                raise OpenHandsRuntimeConflictError(
                    "native event cannot be linked before conversation association"
                )
            runtime = self._openhands_runtime_from_row(runtime_row)
            if runtime.conversation_id != link.conversation_id:
                raise OpenHandsRuntimeConflictError(
                    "native event belongs to another conversation"
                )
            existing = connection.execute(
                """SELECT * FROM openhands_event_links
                WHERE task_id = ? AND native_event_id = ?""",
                (link.task_id, link.native_event_id),
            ).fetchone()
            if existing is not None:
                if self._openhands_event_link_from_row(existing) != link:
                    raise OpenHandsRuntimeConflictError("native event link is immutable")
                connection.commit()
                return runtime
            if runtime.runtime_status is OpenHandsRuntimeStatus.RECOVERY_REQUIRED:
                raise OpenHandsRuntimeConflictError(
                    "operator recovery is required before linking more native events"
                )
            if link.native_order != runtime.last_native_event_order + 1:
                raise OpenHandsRuntimeConflictError(
                    "native event links must be recorded in contiguous order"
                )
            event = self._append_event(
                connection,
                task_id=link.task_id,
                event_type=(
                    "agent.context.attached"
                    if context_attached
                    else "agent.event.observed"
                ),
                stage="agent",
                data={
                    "conversationId": link.conversation_id,
                    "nativeEventOrder": link.native_order,
                    "nativeKind": link.native_kind,
                    "executionStarted": False,
                },
                timestamp=link.observed_at,
            )
            try:
                connection.execute(
                    """INSERT INTO openhands_event_links(
                        task_id, native_event_id, conversation_id, native_order,
                        native_kind, native_timestamp, observed_at,
                        product_event_sequence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        link.task_id,
                        link.native_event_id,
                        link.conversation_id,
                        link.native_order,
                        link.native_kind,
                        link.native_timestamp,
                        link.observed_at,
                        event.sequence,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise OpenHandsRuntimeConflictError(
                    "native event id/order conflicts with recorded history"
                ) from exc
            next_status = (
                OpenHandsRuntimeStatus.CONTEXT_ATTACHED
                if context_attached
                else runtime.runtime_status
            )
            connection.execute(
                """UPDATE openhands_runtimes
                SET runtime_status = ?, last_native_event_id = ?,
                    last_native_event_order = ?, updated_at = ?
                WHERE task_id = ?""",
                (
                    next_status.value,
                    link.native_event_id,
                    link.native_order,
                    link.observed_at,
                    link.task_id,
                ),
            )
            connection.execute(
                "UPDATE tasks SET updated_at = ? WHERE task_id = ?",
                (link.observed_at, link.task_id),
            )
            updated = self._openhands_runtime_from_row(
                connection.execute(
                    "SELECT * FROM openhands_runtimes WHERE task_id = ?", (link.task_id,)
                ).fetchone()
            )
            connection.commit()
            return updated
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def list_events(self, task_id: str, *, after_sequence: int = 0) -> tuple[TaskEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence cannot be negative")
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            rows = connection.execute(
                "SELECT * FROM events WHERE task_id = ? AND sequence > ? ORDER BY sequence ASC",
                (task_id, after_sequence),
            ).fetchall()
            return tuple(self._event_from_row(row) for row in rows)
        finally:
            connection.close()

    def transition_task(
        self,
        task_id: str,
        new_status: TaskStatus,
        *,
        event_type: str,
        event_data: dict[str, Any] | None = None,
        execution_status: ExecutionStatus | None = None,
        validation_status: ValidationStatus | None = None,
        validation_attempts: int | None = None,
        delivery_status: DeliveryStatus | None = None,
        conversation_id: str | None = None,
    ) -> TaskStatusSnapshot:
        """Atomically update status and append its next sequenced event.

        This is an internal foundation method.  Change 1 exposes no HTTP route
        that can call it and has no worker that advances a queued task.
        """

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._task_row(connection, task_id)
            current = TaskStatus(row["status"])
            if new_status not in _ALLOWED_TRANSITIONS[current]:
                raise InvalidTransitionError(f"cannot transition task from {current.value} to {new_status.value}")
            effective_execution = execution_status or ExecutionStatus(row["execution_status"])
            effective_validation = validation_status or ValidationStatus(row["validation_status"])
            effective_delivery = delivery_status or DeliveryStatus(row["delivery_status"])
            attempts = row["validation_attempts"] if validation_attempts is None else validation_attempts
            accepted = effective_validation is ValidationStatus.PASSED
            now = utc_now()
            candidate = TaskStatusSnapshot(
                task_id=task_id,
                status=new_status,
                stage=_STATUS_STAGE[new_status],
                created_at=row["created_at"],
                updated_at=now,
                execution_status=effective_execution,
                conversation_id=conversation_id if conversation_id is not None else row["conversation_id"],
                validation_status=effective_validation,
                validation_attempts=attempts,
                accepted=accepted,
                delivery_status=effective_delivery,
            )
            connection.execute(
                """
                UPDATE tasks SET status = ?, stage = ?, execution_status = ?,
                    conversation_id = ?, validation_status = ?, validation_attempts = ?,
                    accepted = ?, delivery_status = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    candidate.status.value,
                    candidate.stage,
                    candidate.execution_status.value,
                    candidate.conversation_id,
                    candidate.validation_status.value,
                    candidate.validation_attempts,
                    int(candidate.accepted),
                    candidate.delivery_status.value,
                    candidate.updated_at,
                    task_id,
                ),
            )
            self._append_event(
                connection,
                task_id=task_id,
                event_type=event_type,
                stage=candidate.stage,
                data=event_data or {},
                timestamp=now,
            )
            connection.commit()
            return candidate
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def add_artifact(self, artifact: ArtifactMetadata) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._task_row(connection, artifact.task_id)
            existing = connection.execute(
                "SELECT * FROM artifacts WHERE task_id = ? AND artifact_id = ?",
                (artifact.task_id, artifact.artifact_id),
            ).fetchone()
            if existing is not None:
                if self._artifact_from_row(existing) == artifact:
                    connection.commit()
                    return
                raise ArtifactConflictError(f"artifact {artifact.artifact_id!r} is immutable")
            try:
                connection.execute(
                    """
                    INSERT INTO artifacts(task_id, artifact_id, kind, relative_path, media_type, sha256, size_bytes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.task_id,
                        artifact.artifact_id,
                        artifact.kind,
                        artifact.relative_path,
                        artifact.media_type,
                        artifact.sha256,
                        artifact.size_bytes,
                        artifact.created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ArtifactConflictError("artifact id and relative path must be unique per task") from exc
            self._append_event(
                connection,
                task_id=artifact.task_id,
                event_type="artifact.registered",
                stage="artifact",
                data={"artifactId": artifact.artifact_id, "kind": artifact.kind},
                timestamp=artifact.created_at,
            )
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def list_artifacts(self, task_id: str) -> tuple[ArtifactMetadata, ...]:
        connection = self._connect()
        try:
            self._task_row(connection, task_id)
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at ASC, artifact_id ASC",
                (task_id,),
            ).fetchall()
            return tuple(self._artifact_from_row(row) for row in rows)
        finally:
            connection.close()

    def record_result(self, result: TaskResult) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._task_row(connection, result.task_id)
            expected_status = TaskStatus(result.outcome.value)
            if TaskStatus(row["status"]) is not expected_status:
                raise InvalidTransitionError("result outcome must match the task's durable terminal or accepted status")
            if ExecutionStatus(row["execution_status"]) is not result.execution_status:
                raise InvalidTransitionError("result execution status differs from durable task status")
            if ValidationStatus(row["validation_status"]) is not result.validation_status:
                raise InvalidTransitionError("result validation status differs from durable task status")
            if DeliveryStatus(row["delivery_status"]) is not result.delivery_status:
                raise InvalidTransitionError("result delivery status differs from durable task status")
            result_json = canonical_json(result.to_dict())
            existing = row["result_json"]
            if existing is not None:
                if existing == result_json:
                    connection.commit()
                    return
                raise InvalidTransitionError("task result is immutable once recorded")
            connection.execute(
                "UPDATE tasks SET result_json = ?, updated_at = ? WHERE task_id = ?",
                (result_json, result.completed_at, result.task_id),
            )
            self._append_event(
                connection,
                task_id=result.task_id,
                event_type="task.result-recorded",
                stage=_STATUS_STAGE[expected_status],
                data={"outcome": result.outcome.value},
                timestamp=result.completed_at,
            )
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_result(self, task_id: str) -> TaskResult | None:
        connection = self._connect()
        try:
            row = self._task_row(connection, task_id)
            if row["result_json"] is None:
                return None
            return TaskResult.from_dict(json.loads(row["result_json"]))
        finally:
            connection.close()

    @staticmethod
    def _task_row(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskNotFoundError(f"task {task_id!r} was not found")
        return row

    @staticmethod
    def _status_from_row(row: sqlite3.Row) -> TaskStatusSnapshot:
        return TaskStatusSnapshot(
            task_id=row["task_id"],
            status=TaskStatus(row["status"]),
            stage=row["stage"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            execution_status=ExecutionStatus(row["execution_status"]),
            conversation_id=row["conversation_id"],
            validation_status=ValidationStatus(row["validation_status"]),
            validation_attempts=row["validation_attempts"],
            accepted=bool(row["accepted"]),
            delivery_status=DeliveryStatus(row["delivery_status"]),
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        event_type: str,
        stage: str,
        data: dict[str, Any],
        timestamp: str,
    ) -> TaskEvent:
        next_sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM events WHERE task_id = ?",
            (task_id,),
        ).fetchone()["next_sequence"]
        event = TaskEvent(
            event_id=f"event_{uuid.uuid4().hex}",
            task_id=task_id,
            sequence=next_sequence,
            timestamp=timestamp,
            type=event_type,
            stage=stage,
            data=data,
        )
        connection.execute(
            """
            INSERT INTO events(task_id, sequence, event_id, timestamp, type, stage, data_json, openhands_event_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.task_id,
                event.sequence,
                event.event_id,
                event.timestamp,
                event.type,
                event.stage,
                canonical_json(dict(event.data)),
                event.openhands_event_id,
            ),
        )
        return event

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> TaskEvent:
        return TaskEvent(
            event_id=row["event_id"],
            task_id=row["task_id"],
            sequence=row["sequence"],
            timestamp=row["timestamp"],
            type=row["type"],
            stage=row["stage"],
            data=json.loads(row["data_json"]),
            openhands_event_id=row["openhands_event_id"],
        )

    @staticmethod
    def _artifact_from_row(row: sqlite3.Row) -> ArtifactMetadata:
        return ArtifactMetadata(
            artifact_id=row["artifact_id"],
            task_id=row["task_id"],
            kind=row["kind"],
            relative_path=row["relative_path"],
            media_type=row["media_type"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _preparation_from_row(row: sqlite3.Row) -> PreparationRecord:
        return PreparationRecord(
            task_id=row["task_id"],
            repository_url=row["repository_url"],
            base_ref=row["base_ref"],
            expected_commit=row["expected_commit"],
            baseline_commit=row["baseline_commit"],
            source_path=row["source_path"],
            workspace_path=row["workspace_path"],
            local_branch=row["local_branch"],
            prepared_at=row["prepared_at"],
        )

    @staticmethod
    def _baseline_from_row(row: sqlite3.Row) -> BaselineRecord:
        return BaselineRecord(
            task_id=row["task_id"],
            baseline_commit=row["baseline_commit"],
            assessment_status=BaselineAssessmentStatus(row["assessment_status"]),
            build_succeeded=bool(row["build_succeeded"]),
            scanner_outcome=row["scanner_outcome"],
            finding_count=row["finding_count"],
            report_artifact_id=row["report_artifact_id"],
            report_sha256=row["report_sha256"],
            tool_versions=json.loads(row["tool_versions_json"]),
            completed_at=row["completed_at"],
        )

    @staticmethod
    def _intelligence_from_row(row: sqlite3.Row) -> IntelligenceRecord:
        applicable = None if row["applicable"] is None else bool(row["applicable"])
        evaluated = json.loads(row["evaluated_versions_json"])
        return IntelligenceRecord(
            task_id=row["task_id"],
            baseline_commit=row["baseline_commit"],
            outcome=IntelligenceOutcome(row["outcome"]),
            applicable=applicable,
            invoked=bool(row["invoked"]),
            reused=bool(row["reused"]),
            profile_id=row["profile_id"],
            fingerprint=row["fingerprint"],
            selection_manifest=json.loads(row["selection_manifest_json"]),
            evaluated_versions=tuple(evaluated["versions"]),
            record_artifact_id=row["record_artifact_id"],
            record_sha256=row["record_sha256"],
            summary_artifact_id=row["summary_artifact_id"],
            explanation=row["explanation"],
            completed_at=row["completed_at"],
        )

    @staticmethod
    def _openhands_runtime_from_row(row: sqlite3.Row) -> OpenHandsRuntimeRecord:
        return OpenHandsRuntimeRecord(
            task_id=row["task_id"],
            conversation_id=row["conversation_id"],
            agent_server_identity=row["agent_server_identity"],
            agent_server_version=row["agent_server_version"],
            sdk_version=row["sdk_version"],
            tools_version=row["tools_version"],
            agent_profile_id=row["agent_profile_id"],
            native_agent_profile_id=row["native_agent_profile_id"],
            native_agent_profile_revision=row["native_agent_profile_revision"],
            model_profile_id=row["model_profile_id"],
            native_model=row["native_model"],
            profile_fingerprint=row["profile_fingerprint"],
            request_fingerprint=row["request_fingerprint"],
            workspace_path=row["workspace_path"],
            baseline_commit=row["baseline_commit"],
            runtime_status=OpenHandsRuntimeStatus(row["runtime_status"]),
            execution_status=ExecutionStatus(row["execution_status"]),
            last_native_event_id=row["last_native_event_id"],
            last_native_event_order=row["last_native_event_order"],
            failure_code=row["failure_code"],
            failure_detail=row["failure_detail"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _openhands_event_link_from_row(row: sqlite3.Row) -> OpenHandsEventLink:
        return OpenHandsEventLink(
            task_id=row["task_id"],
            conversation_id=row["conversation_id"],
            native_event_id=row["native_event_id"],
            native_order=row["native_order"],
            native_kind=row["native_kind"],
            native_timestamp=row["native_timestamp"],
            observed_at=row["observed_at"],
        )

    @staticmethod
    def _openhands_runtime_identity(runtime: OpenHandsRuntimeRecord) -> tuple[Any, ...]:
        return (
            runtime.task_id,
            runtime.conversation_id,
            runtime.agent_server_identity,
            runtime.agent_server_version,
            runtime.sdk_version,
            runtime.tools_version,
            runtime.agent_profile_id,
            runtime.native_agent_profile_id,
            runtime.native_agent_profile_revision,
            runtime.model_profile_id,
            runtime.native_model,
            runtime.profile_fingerprint,
            runtime.request_fingerprint,
            runtime.workspace_path,
            runtime.baseline_commit,
            runtime.created_at,
        )

    @staticmethod
    def _execution_claim_from_row(row: sqlite3.Row) -> ExecutionClaimRecord:
        return ExecutionClaimRecord(
            task_id=row["task_id"],
            conversation_id=row["conversation_id"],
            worker_id=row["worker_id"],
            claim_token=row["claim_token"],
            dispatch_status=ExecutionDispatchStatus(row["dispatch_status"]),
            intent_recorded_at=row["intent_recorded_at"],
            dispatched_at=row["dispatched_at"],
            recovery_code=row["recovery_code"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _validation_attempt_from_row(row: sqlite3.Row) -> ValidationAttemptRecord:
        return ValidationAttemptRecord(
            task_id=row["task_id"],
            attempt=row["attempt"],
            state=ValidationAttemptState(row["state"]),
            outcome=ValidationOutcome(row["outcome"]) if row["outcome"] else None,
            hook_decision=StopHookDecision(row["hook_decision"]) if row["hook_decision"] else None,
            report_artifact_id=row["report_artifact_id"],
            report_sha256=row["report_sha256"],
            validated_head=row["validated_head"],
            validated_tree=row["validated_tree"],
            repository_state_sha256=row["repository_state_sha256"],
            original_finding_count=row["original_finding_count"],
            resolved_finding_count=row["resolved_finding_count"],
            remaining_finding_count=row["remaining_finding_count"],
            unknown_finding_count=row["unknown_finding_count"],
            new_prohibited_finding_count=row["new_prohibited_finding_count"],
            constraints_passed=(bool(row["constraints_passed"]) if row["constraints_passed"] is not None else None),
            bounded_feedback=row["bounded_feedback"],
            conversation_id=row["conversation_id"],
            native_hook_event_id=row["native_hook_event_id"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
