from __future__ import annotations

import concurrent.futures
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openhands_shared.contracts import (
    ArtifactMetadata,
    ContractValidationError,
    DeliveryStatus,
    ExecutionStatus,
    PreparationRecord,
    ResultOutcome,
    TaskRequest,
    TaskResult,
    TaskStatus,
    ValidationStatus,
    utc_now,
)
from openhands_shared.store import (
    ArtifactConflictError,
    IdempotencyConflictError,
    PreparationConflictError,
    SQLiteTaskStore,
)
from tests.openhands_shared_fixtures import task_request_data


class SQLiteTaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "state" / "tasks.sqlite3"
        self.store = SQLiteTaskStore(self.database)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_duplicate_submission_is_idempotent_and_conflicting_reuse_fails(self):
        request = TaskRequest.from_dict(task_request_data())
        first = self.store.register_task(request)
        duplicate = self.store.register_task(request)

        self.assertTrue(first.created)
        self.assertFalse(duplicate.created)
        self.assertEqual(first.status.task_id, duplicate.status.task_id)
        self.assertEqual(1, len(self.store.list_events(first.status.task_id)))

        changed = TaskRequest.from_dict(task_request_data(objective="A different remediation objective."))
        with self.assertRaises(IdempotencyConflictError) as conflict:
            self.store.register_task(changed)
        self.assertEqual(first.status.task_id, conflict.exception.task_id)

    def test_transition_and_event_append_are_one_atomic_transaction(self):
        registration = self.store.register_task(TaskRequest.from_dict(task_request_data()))
        task_id = registration.status.task_id
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                """
                CREATE TRIGGER reject_preparation_event BEFORE INSERT ON events
                WHEN NEW.type = 'preparation.started'
                BEGIN SELECT RAISE(ABORT, 'test event failure'); END
                """
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.transition_task(
                task_id,
                TaskStatus.PREPARING,
                event_type="preparation.started",
            )

        self.assertEqual(TaskStatus.QUEUED, self.store.get_status(task_id).status)
        self.assertEqual([1], [event.sequence for event in self.store.list_events(task_id)])

    def test_preparation_record_status_and_completion_event_are_atomic(self):
        task_id = self.store.register_task(TaskRequest.from_dict(task_request_data())).status.task_id
        self.store.start_preparation(task_id)
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                """
                CREATE TRIGGER reject_preparation_completion BEFORE INSERT ON events
                WHEN NEW.type = 'preparation.completed'
                BEGIN SELECT RAISE(ABORT, 'test preparation event failure'); END
                """
            )
            connection.commit()
        finally:
            connection.close()
        record = PreparationRecord(
            task_id=task_id,
            repository_url="https://github.com/example/maven-app.git",
            base_ref="refs/heads/main",
            expected_commit="a" * 40,
            baseline_commit="a" * 40,
            source_path="/durable/source",
            workspace_path=f"/durable/workspaces/{task_id}/repository",
            local_branch=f"openhands-shared/{task_id}",
            prepared_at=utc_now(),
        )

        with self.assertRaises(PreparationConflictError):
            self.store.complete_preparation(record)

        self.assertIsNone(self.store.get_preparation(task_id))
        self.assertEqual(TaskStatus.PREPARING, self.store.get_status(task_id).status)
        self.assertEqual(
            ["task.registered", "preparation.started"],
            [event.type for event in self.store.list_events(task_id)],
        )

    def test_events_are_strictly_ordered_across_status_and_artifact_transactions(self):
        registration = self.store.register_task(TaskRequest.from_dict(task_request_data()))
        task_id = registration.status.task_id
        self.store.transition_task(task_id, TaskStatus.PREPARING, event_type="preparation.started")
        self.store.add_artifact(self._artifact(task_id, "baseline", "baseline/report.json"))
        self.store.transition_task(task_id, TaskStatus.BASELINING, event_type="baseline.started")

        events = self.store.list_events(task_id)
        self.assertEqual([1, 2, 3, 4], [event.sequence for event in events])
        self.assertEqual(
            ["task.registered", "preparation.started", "artifact.registered", "baseline.started"],
            [event.type for event in events],
        )
        self.assertEqual([3, 4], [event.sequence for event in self.store.list_events(task_id, after_sequence=2)])

        connection = sqlite3.connect(self.database)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("UPDATE events SET type = 'rewritten' WHERE task_id = ?", (task_id,))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("DELETE FROM artifacts WHERE task_id = ?", (task_id,))
        finally:
            connection.close()

    def test_concurrent_same_key_registration_creates_one_durable_task(self):
        request = TaskRequest.from_dict(task_request_data())

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            registrations = list(executor.map(lambda _: self.store.register_task(request), range(24)))

        self.assertEqual(1, sum(registration.created for registration in registrations))
        task_ids = {registration.status.task_id for registration in registrations}
        self.assertEqual(1, len(task_ids))
        self.assertEqual(1, len(self.store.list_events(task_ids.pop())))

    def test_concurrent_distinct_registration_preserves_every_task(self):
        requests = [
            TaskRequest.from_dict(task_request_data(idempotency_key=f"concurrent-{index}"))
            for index in range(16)
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            registrations = list(executor.map(self.store.register_task, requests))

        self.assertEqual(16, len({registration.status.task_id for registration in registrations}))
        self.assertTrue(all(registration.created for registration in registrations))
        self.assertTrue(all(len(self.store.list_events(registration.status.task_id)) == 1 for registration in registrations))

    def test_close_and_reopen_preserves_task_request_events_artifacts_and_result(self):
        request = TaskRequest.from_dict(task_request_data())
        task_id = self.store.register_task(request).status.task_id
        self.store.add_artifact(self._artifact(task_id, "validation-1", "validation/attempt-1.json"))
        self._advance_to_accepted(task_id)
        result = TaskResult(
            task_id=task_id,
            outcome=ResultOutcome.ACCEPTED,
            execution_status=ExecutionStatus.COMPLETED,
            validation_status=ValidationStatus.PASSED,
            delivery_status=DeliveryStatus.NOT_REQUESTED,
            baseline_commit="a" * 40,
            validated_tree="b" * 40,
            validation_attempt=1,
            validation_report_artifact_id="validation-1",
            artifact_ids=("validation-1",),
        )
        self.store.record_result(result)
        event_count = len(self.store.list_events(task_id))
        self.store.close()

        self.store = SQLiteTaskStore(self.database)
        self.assertEqual(TaskStatus.ACCEPTED, self.store.get_status(task_id).status)
        self.assertEqual(request, self.store.get_request(task_id))
        self.assertEqual(result, self.store.get_result(task_id))
        self.assertEqual("validation-1", self.store.list_artifacts(task_id)[0].artifact_id)
        self.assertEqual(event_count, len(self.store.list_events(task_id)))

    def test_separate_process_reads_the_same_durable_identity_and_state(self):
        task_id = self.store.register_task(TaskRequest.from_dict(task_request_data())).status.task_id
        code = (
            "import sys; "
            "from openhands_shared.store import SQLiteTaskStore; "
            "store=SQLiteTaskStore(sys.argv[1]); "
            "status=store.get_status(sys.argv[2]); "
            "print(status.task_id, status.status.value, len(store.list_events(status.task_id))); "
            "store.close()"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code, str(self.database), task_id],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(f"{task_id} QUEUED 1", completed.stdout.strip())

    def test_openhands_completion_does_not_allow_unvalidated_acceptance(self):
        task_id = self.store.register_task(TaskRequest.from_dict(task_request_data())).status.task_id
        self.store.transition_task(task_id, TaskStatus.PREPARING, event_type="preparation.started")
        self.store.transition_task(task_id, TaskStatus.BASELINING, event_type="baseline.started")
        self.store.transition_task(task_id, TaskStatus.INTELLIGENCE, event_type="intelligence.skipped")
        self.store.transition_task(
            task_id,
            TaskStatus.AGENT_RUNNING,
            event_type="agent.started",
            execution_status=ExecutionStatus.RUNNING,
        )
        self.store.transition_task(
            task_id,
            TaskStatus.VALIDATING,
            event_type="agent.completed",
            execution_status=ExecutionStatus.COMPLETED,
            validation_status=ValidationStatus.RUNNING,
            validation_attempts=1,
        )

        with self.assertRaises(ContractValidationError):
            self.store.transition_task(task_id, TaskStatus.ACCEPTED, event_type="task.accepted")
        status = self.store.get_status(task_id)
        self.assertEqual(TaskStatus.VALIDATING, status.status)
        self.assertEqual(ExecutionStatus.COMPLETED, status.execution_status)
        self.assertFalse(status.accepted)

    def test_artifact_metadata_is_immutable_and_path_unique(self):
        task_id = self.store.register_task(TaskRequest.from_dict(task_request_data())).status.task_id
        artifact = self._artifact(task_id, "baseline", "baseline/report.json")
        self.store.add_artifact(artifact)
        self.store.add_artifact(artifact)
        self.assertEqual((artifact,), self.store.list_artifacts(task_id))

        changed = ArtifactMetadata(
            artifact_id="baseline",
            task_id=task_id,
            kind="baseline-report",
            relative_path="baseline/other.json",
            media_type="application/json",
            sha256="d" * 64,
            size_bytes=99,
            created_at=artifact.created_at,
        )
        with self.assertRaises(ArtifactConflictError):
            self.store.add_artifact(changed)

    def _advance_to_accepted(self, task_id: str) -> None:
        self.store.transition_task(task_id, TaskStatus.PREPARING, event_type="preparation.started")
        self.store.transition_task(task_id, TaskStatus.BASELINING, event_type="baseline.started")
        self.store.transition_task(task_id, TaskStatus.INTELLIGENCE, event_type="intelligence.skipped")
        self.store.transition_task(
            task_id,
            TaskStatus.AGENT_RUNNING,
            event_type="agent.started",
            execution_status=ExecutionStatus.RUNNING,
        )
        self.store.transition_task(
            task_id,
            TaskStatus.VALIDATING,
            event_type="agent.completed",
            execution_status=ExecutionStatus.COMPLETED,
            validation_status=ValidationStatus.RUNNING,
            validation_attempts=1,
        )
        self.store.transition_task(
            task_id,
            TaskStatus.ACCEPTED,
            event_type="validation.passed",
            validation_status=ValidationStatus.PASSED,
            validation_attempts=1,
        )

    @staticmethod
    def _artifact(task_id: str, artifact_id: str, path: str) -> ArtifactMetadata:
        return ArtifactMetadata(
            artifact_id=artifact_id,
            task_id=task_id,
            kind="validation-report" if artifact_id.startswith("validation") else "baseline-report",
            relative_path=path,
            media_type="application/json",
            sha256="c" * 64,
            size_bytes=42,
            created_at=utc_now(),
        )


if __name__ == "__main__":
    unittest.main()
