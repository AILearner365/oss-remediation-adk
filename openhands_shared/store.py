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
    ExecutionStatus,
    IntelligenceOutcome,
    IntelligenceRecord,
    PreparationRecord,
    TaskEvent,
    TaskRequest,
    TaskResult,
    TaskStatus,
    TaskStatusSnapshot,
    ValidationStatus,
    canonical_json,
    utc_now,
)


SCHEMA_VERSION = 4


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
