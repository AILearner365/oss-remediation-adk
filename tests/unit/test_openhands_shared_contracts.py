from __future__ import annotations

import unittest

from openhands_shared.contracts import (
    ArtifactMetadata,
    BaselineAssessmentStatus,
    BaselineRecord,
    ContractValidationError,
    DeliveryStatus,
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
)
from tests.openhands_shared_fixtures import task_request_data


class SharedContractTests(unittest.TestCase):
    def test_task_request_round_trip_is_versioned_and_canonical(self):
        source = task_request_data()
        request = TaskRequest.from_dict(source)

        self.assertEqual(source, request.to_dict())
        self.assertEqual(request, TaskRequest.from_dict(request.to_dict()))
        self.assertEqual("1", request.contract_version)

    def test_contract_rejects_missing_unknown_and_invalid_values(self):
        cases = []
        missing = task_request_data()
        del missing["objective"]
        cases.append(missing)
        unknown = task_request_data()
        unknown["worker"] = {"enabled": True}
        cases.append(unknown)
        wrong_version = task_request_data()
        wrong_version["contractVersion"] = "2"
        cases.append(wrong_version)
        short_commit = task_request_data()
        short_commit["repository"]["expectedCommit"] = "abc"
        cases.append(short_commit)
        credential_url = task_request_data()
        credential_url["repository"]["url"] = "https://token@example.test/repository.git"
        cases.append(credential_url)
        execution_delivery = task_request_data()
        execution_delivery["delivery"]["mode"] = "pull-request"
        cases.append(execution_delivery)

        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ContractValidationError):
                    TaskRequest.from_dict(invalid)

    def test_contract_rejects_secret_fields_environment_and_raw_private_keys(self):
        secret_cases = []
        for field in ("apiKey", "access_token", "credentials", "environment", "envVars"):
            request = task_request_data()
            request["metadata"][field] = "do-not-store"
            secret_cases.append(request)
        private_key = task_request_data(objective="-----BEGIN PRIVATE KEY----- raw material")
        secret_cases.append(private_key)

        for request in secret_cases:
            with self.subTest(keys=list(request["metadata"])):
                with self.assertRaisesRegex(ContractValidationError, "credential|secret|environment"):
                    TaskRequest.from_dict(request)

    def test_status_keeps_execution_validation_and_delivery_independent(self):
        snapshot = TaskStatusSnapshot(
            task_id="task_" + "1" * 32,
            status=TaskStatus.VALIDATING,
            stage="validation",
            created_at="2026-10-16T00:00:00.000Z",
            updated_at="2026-10-16T00:01:00.000Z",
            execution_status=ExecutionStatus.COMPLETED,
            validation_status=ValidationStatus.RUNNING,
            validation_attempts=1,
            accepted=False,
            delivery_status=DeliveryStatus.NOT_REQUESTED,
        )
        serialized = snapshot.to_dict()

        self.assertEqual("COMPLETED", serialized["openhands"]["executionStatus"])
        self.assertEqual("RUNNING", serialized["validation"]["status"])
        self.assertFalse(serialized["validation"]["accepted"])
        self.assertEqual("NOT_REQUESTED", serialized["delivery"]["status"])

    def test_unvalidated_success_and_acceptance_are_rejected(self):
        with self.assertRaisesRegex(ContractValidationError, "validation PASS"):
            TaskStatusSnapshot(
                task_id="task_" + "1" * 32,
                status=TaskStatus.SUCCEEDED,
                stage="complete",
                created_at="2026-10-16T00:00:00.000Z",
                updated_at="2026-10-16T00:01:00.000Z",
                execution_status=ExecutionStatus.COMPLETED,
                validation_status=ValidationStatus.NOT_VALIDATED,
                accepted=False,
                delivery_status=DeliveryStatus.COMPLETED,
            )
        with self.assertRaisesRegex(ContractValidationError, "validation PASS"):
            TaskResult(
                task_id="task_" + "1" * 32,
                outcome=ResultOutcome.ACCEPTED,
                execution_status=ExecutionStatus.COMPLETED,
                validation_status=ValidationStatus.NOT_VALIDATED,
                delivery_status=DeliveryStatus.NOT_REQUESTED,
                validated_tree="b" * 40,
                validation_report_artifact_id="validation-1",
            )

    def test_preparation_contract_requires_exact_baseline_and_absolute_paths(self):
        record = PreparationRecord(
            task_id="task_" + "1" * 32,
            repository_url="https://github.com/example/maven-app.git",
            base_ref="refs/heads/main",
            expected_commit="a" * 40,
            baseline_commit="a" * 40,
            source_path="/durable/source",
            workspace_path="/durable/workspaces/task/repository",
            local_branch="openhands-shared/task_111",
            prepared_at="2026-10-16T00:00:00.000Z",
        )
        self.assertEqual("1", record.to_dict()["contractVersion"])
        self.assertEqual("a" * 40, record.to_dict()["baselineCommit"])

        with self.assertRaisesRegex(ContractValidationError, "must equal"):
            PreparationRecord(
                **{
                    **record.__dict__,
                    "baseline_commit": "b" * 40,
                }
            )
        with self.assertRaisesRegex(ContractValidationError, "absolute normalized"):
            PreparationRecord(
                **{
                    **record.__dict__,
                    "workspace_path": "relative/repository",
                }
            )

    def test_baseline_contract_serializes_and_rejects_false_completion(self):
        record = BaselineRecord(
            task_id="task_" + "1" * 32,
            baseline_commit="a" * 40,
            assessment_status=BaselineAssessmentStatus.COMPLETED,
            build_succeeded=True,
            scanner_outcome="COMPLETED_WITH_FINDINGS",
            finding_count=2,
            report_artifact_id="baseline-report",
            report_sha256="b" * 64,
            tool_versions={"scanner": {"version": "2.6.0"}},
            completed_at="2026-10-16T00:01:00.000Z",
        )
        self.assertEqual("COMPLETED", record.to_dict()["assessmentStatus"])
        self.assertEqual(2, record.to_dict()["findingCount"])

        with self.assertRaisesRegex(ContractValidationError, "successful build"):
            BaselineRecord(
                **{
                    **record.__dict__,
                    "build_succeeded": False,
                }
            )

    def test_intelligence_contract_preserves_explicit_optional_outcomes(self):
        record = IntelligenceRecord(
            task_id="task_" + "1" * 32,
            baseline_commit="a" * 40,
            outcome=IntelligenceOutcome.PARTIAL,
            applicable=True,
            invoked=True,
            reused=False,
            profile_id="gate2-sbri-v1",
            fingerprint="b" * 64,
            selection_manifest={"resolved_candidates": ["4.0.8"]},
            evaluated_versions=("4.0.6", "4.0.8"),
            record_artifact_id="intelligence-record",
            record_sha256="c" * 64,
            summary_artifact_id="intelligence-summary",
            explanation="partial evidence retains explicit uncertainty",
            completed_at="2026-10-16T00:02:00.000Z",
        )
        self.assertEqual("PARTIAL", record.to_dict()["outcome"])
        self.assertTrue(record.to_dict()["applicable"])

        with self.assertRaisesRegex(ContractValidationError, "must not be invoked"):
            IntelligenceRecord(
                **{
                    **record.__dict__,
                    "outcome": IntelligenceOutcome.NOT_APPLICABLE,
                    "applicable": False,
                }
            )

    def test_result_event_and_artifact_serialize_without_secrets(self):
        task_id = "task_" + "1" * 32
        result = TaskResult(
            task_id=task_id,
            outcome=ResultOutcome.ACCEPTED,
            execution_status=ExecutionStatus.COMPLETED,
            validation_status=ValidationStatus.PASSED,
            delivery_status=DeliveryStatus.NOT_REQUESTED,
            baseline_commit="a" * 40,
            validated_tree="b" * 40,
            validation_attempt=2,
            validation_report_artifact_id="validation-2",
            artifact_ids=("validation-2",),
        )
        event = TaskEvent(
            event_id="event_" + "2" * 32,
            task_id=task_id,
            sequence=2,
            timestamp="2026-10-16T00:01:00.000Z",
            type="validation.completed",
            stage="validation",
            data={"passed": True},
        )
        artifact = ArtifactMetadata(
            artifact_id="validation-2",
            task_id=task_id,
            kind="validation-report",
            relative_path="validation/attempt-2.json",
            media_type="application/json",
            sha256="c" * 64,
            size_bytes=42,
            created_at="2026-10-16T00:01:00.000Z",
        )

        self.assertEqual(result, TaskResult.from_dict(result.to_dict()))
        self.assertEqual(2, event.to_dict()["sequence"])
        self.assertEqual("validation/attempt-2.json", artifact.to_dict()["relativePath"])

    def test_artifact_rejects_unsafe_relative_paths(self):
        for path in ("/tmp/report.json", "../report.json", "reports/../../secret", "reports\\secret.json", "."):
            with self.subTest(path=path):
                with self.assertRaises(ContractValidationError):
                    ArtifactMetadata(
                        artifact_id="report",
                        task_id="task_" + "1" * 32,
                        kind="report",
                        relative_path=path,
                        media_type="application/json",
                        sha256="c" * 64,
                        size_bytes=1,
                        created_at="2026-10-16T00:00:00.000Z",
                    )

    def test_openhands_runtime_and_event_link_are_bounded_versioned_contracts(self):
        runtime = OpenHandsRuntimeRecord(
            task_id="task_" + "1" * 32,
            conversation_id="4e6d7335-c08e-49a9-b765-e21cb49d0c96",
            agent_server_identity="primary-agent-server",
            agent_server_version="1.50.0",
            sdk_version="1.50.0",
            tools_version="1.50.0",
            agent_profile_id="gate2-dependency-remediation-v1",
            native_agent_profile_id="d360c86d-a779-45e1-a773-f888477a08cf",
            native_agent_profile_revision=7,
            model_profile_id="vertex-gemini-2-5-flash",
            native_model="vertex_ai/gemini-2.5-flash",
            profile_fingerprint="a" * 64,
            request_fingerprint="b" * 64,
            workspace_path="/durable/workspaces/task/repository",
            baseline_commit="c" * 40,
            runtime_status=OpenHandsRuntimeStatus.CONTEXT_ATTACHED,
            execution_status=ExecutionStatus.NOT_STARTED,
            last_native_event_id="native-event-1",
            last_native_event_order=1,
            failure_code=None,
            failure_detail=None,
            created_at="2026-10-16T00:00:00.000Z",
            updated_at="2026-10-16T00:01:00.000Z",
        )
        link = OpenHandsEventLink(
            task_id=runtime.task_id,
            conversation_id=runtime.conversation_id,
            native_event_id="native-event-1",
            native_order=1,
            native_kind="MessageEvent",
            native_timestamp="2026-10-16T00:00:30.000Z",
            observed_at=runtime.updated_at,
        )
        self.assertEqual("1", runtime.to_dict()["contractVersion"])
        self.assertEqual(runtime.conversation_id, link.to_dict()["conversationId"])
        self.assertNotIn("payload", link.to_dict())

        with self.assertRaisesRegex(ContractValidationError, "credential"):
            OpenHandsRuntimeRecord(
                **{
                    **runtime.__dict__,
                    "runtime_status": OpenHandsRuntimeStatus.RECOVERY_REQUIRED,
                    "failure_code": "REMOTE_FAILURE",
                    "failure_detail": "api_key=raw-secret-value",
                }
            )


if __name__ == "__main__":
    unittest.main()
