from __future__ import annotations

import io
import json
import socket
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from openhands_shared.api import TaskApi
from openhands_shared.contracts import (
    ArtifactMetadata,
    DeliveryStatus,
    ExecutionStatus,
    ResultOutcome,
    TaskRequest,
    TaskResult,
    TaskStatus,
    ValidationStatus,
    utc_now,
)
from openhands_shared.store import SQLiteTaskStore
from tests.openhands_shared_fixtures import task_request_data


class SharedTaskApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SQLiteTaskStore(Path(self.temp_dir.name) / "tasks.sqlite3")
        self.api = TaskApi(self.store)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_register_and_read_all_resources_without_external_invocation(self):
        with patch.object(subprocess, "run", side_effect=AssertionError("subprocess must not run")), patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("network must not run")
        ), patch.object(
            socket.socket, "connect", side_effect=AssertionError("socket must not connect")
        ):
            status, created = self._request("POST", "/v1/tasks", task_request_data())
            self.assertEqual(201, status)
            self.assertTrue(created["created"])
            task_id = created["task"]["taskId"]

            status, duplicate = self._request("POST", "/v1/tasks", task_request_data())
            self.assertEqual(200, status)
            self.assertFalse(duplicate["created"])
            self.assertEqual(task_id, duplicate["task"]["taskId"])

            status, task = self._request("GET", f"/v1/tasks/{task_id}")
            self.assertEqual(200, status)
            self.assertEqual("QUEUED", task["status"])
            self.assertEqual("NOT_STARTED", task["openhands"]["executionStatus"])
            self.assertEqual("NOT_VALIDATED", task["validation"]["status"])
            self.assertEqual("NOT_REQUESTED", task["delivery"]["status"])

            status, events = self._request("GET", f"/v1/tasks/{task_id}/events")
            self.assertEqual(200, status)
            self.assertEqual([1], [event["sequence"] for event in events["events"]])

            status, artifacts = self._request("GET", f"/v1/tasks/{task_id}/artifacts")
            self.assertEqual(200, status)
            self.assertEqual([], artifacts["artifacts"])

            status, result = self._request("GET", f"/v1/tasks/{task_id}/result")
            self.assertEqual(404, status)
            self.assertEqual("result_not_ready", result["error"]["code"])

    def test_api_reads_durable_artifact_metadata(self):
        registration = self.store.register_task(TaskRequest.from_dict(task_request_data()))
        task_id = registration.status.task_id
        artifact = ArtifactMetadata(
            artifact_id="baseline",
            task_id=task_id,
            kind="baseline-report",
            relative_path="baseline/report.json",
            media_type="application/json",
            sha256="a" * 64,
            size_bytes=128,
            created_at=utc_now(),
        )
        self.store.add_artifact(artifact)

        status, response = self._request("GET", f"/v1/tasks/{task_id}/artifacts")
        self.assertEqual(200, status)
        self.assertEqual([artifact.to_dict()], response["artifacts"])

    def test_api_returns_a_validation_backed_result(self):
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
        self.store.transition_task(
            task_id,
            TaskStatus.ACCEPTED,
            event_type="validation.passed",
            validation_status=ValidationStatus.PASSED,
            validation_attempts=1,
        )
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
        )
        self.store.record_result(result)

        status, response = self._request("GET", f"/v1/tasks/{task_id}/result")
        self.assertEqual(200, status)
        self.assertEqual(result.to_dict(), response)

    def test_api_rejects_conflict_invalid_json_secret_and_mutating_read_route(self):
        self.assertEqual(201, self._request("POST", "/v1/tasks", task_request_data())[0])
        conflict = task_request_data(objective="Different objective")
        status, body = self._request("POST", "/v1/tasks", conflict)
        self.assertEqual(409, status)
        self.assertEqual("idempotency_conflict", body["error"]["code"])

        secret = task_request_data(idempotency_key="another-key")
        secret["agent"]["apiKey"] = "raw-secret"
        status, body = self._request("POST", "/v1/tasks", secret)
        self.assertEqual(400, status)
        self.assertEqual("invalid_request", body["error"]["code"])

        status, body = self._request("POST", "/v1/tasks", raw=b"not-json")
        self.assertEqual(400, status)
        self.assertEqual("invalid_json", body["error"]["code"])

        task_id = self.store.register_task(TaskRequest.from_dict(task_request_data(idempotency_key="third-key"))).status.task_id
        status, body = self._request("POST", f"/v1/tasks/{task_id}", {})
        self.assertEqual(405, status)
        self.assertEqual("method_not_allowed", body["error"]["code"])

    def _request(
        self,
        method: str,
        path: str,
        body: object | None = None,
        *,
        raw: bytes | None = None,
    ) -> tuple[int, dict[str, object]]:
        payload = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else b"")
        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        path_info, _, query = path.partition("?")
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path_info,
            "QUERY_STRING": query,
            "CONTENT_TYPE": "application/json" if method == "POST" else "",
            "CONTENT_LENGTH": str(len(payload)) if method == "POST" else "",
            "wsgi.input": io.BytesIO(payload),
        }
        response = b"".join(self.api(environ, start_response))
        return int(str(captured["status"]).split()[0]), json.loads(response)


if __name__ == "__main__":
    unittest.main()
