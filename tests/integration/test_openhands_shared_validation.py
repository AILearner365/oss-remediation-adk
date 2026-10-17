from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import subprocess
import socket
import urllib.request
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from autonomous_oss_remediation_agent.config import MavenConfig, OsvScannerConfig, ScannerConfig
from openhands_shared.contracts import (
    ExecutionDispatchStatus,
    ResultOutcome,
    StopHookDecision,
    TaskStatus,
    ValidationOutcome,
)
from openhands_shared.openhands_runtime import (
    OpenHandsRuntimeConfig,
    RuntimeConfigurationError,
    RuntimeRecoveryRequiredError,
)
from openhands_shared.store import (
    ExecutionClaimConflictError,
    SQLiteTaskStore,
)
from openhands_shared.validation import (
    SharedValidationService,
    ValidationConfig,
    ValidationInfrastructureError,
    ValidationProfile,
    ValidationRecoveryRequiredError,
)
from tests.integration import test_openhands_shared_runtime as runtime_test_support


class FakeValidator:
    def __init__(self, reports):
        self.reports = list(reports)
        self.calls = 0

    def run(self, repository, request, profile, baseline_document, attempt, runtime_root):
        self.calls += 1
        value = self.reports.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def report(*, passed: bool, remaining: int = 0, unknown: int = 0, new: int = 0):
    checks = [
        {"name": "baseline_ancestry", "passed": True, "message": "baseline retained"},
        {"name": "build_test_startup", "passed": True, "message": "build passed"},
        {"name": "fresh_vulnerability_scan", "passed": True, "message": "scan complete"},
        {"name": "target_findings_resolved", "passed": passed, "message": "coverage"},
        {"name": "no_new_prohibited_findings", "passed": not new, "message": "new findings", "evidence": {"newFindings": [{}] * new}},
        {"name": "suppression_policy", "passed": True, "message": "constraints passed"},
    ]
    return {
        "passed": passed,
        "checks": checks,
        "scan": {"succeeded": True, "findings": [], "outcome": "COMPLETED_CLEAN"},
        "resolvedTargetFindings": ([{"identity": "CVE-OFFLINE-1|example:demo"}] if not remaining and not unknown else []),
        "remainingTargetFindings": [{}] * remaining,
        "unknownTargetFindings": [{}] * unknown,
    }


class SharedValidationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = runtime_test_support.SharedOpenHandsRuntimeIntegrationTests(
            methodName="test_pinned_request_mapping_context_and_non_running_persistence"
        )
        self.fixture.setUp()
        self.hook = self.fixture.root / "shared-stop-hook"
        self.hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.hook.chmod(0o700)
        self.validation_profile = ValidationProfile(
            profile_id="gate2-dependency-remediation-v1",
            build_commands=("mvn clean verify",),
            maven=MavenConfig(mode="auto"),
            scanner=ScannerConfig(
                backend="osv",
                osv=OsvScannerConfig(mode="configured", executable="/approved/osv", version="2.6.0"),
            ),
        )
        self.validation_config = ValidationConfig(
            artifact_root=self.fixture.artifacts,
            profiles=(self.validation_profile,),
        )
        self.hook_config = self.fixture.root / "stop-hook.json"
        self.hook_config.write_text(
            json.dumps(
                {
                    "database": str(self.fixture.database.resolve()),
                    "artifactRoot": str(self.fixture.artifacts.resolve()),
                    "profiles": [{
                        "profileId": self.validation_profile.profile_id,
                        "buildCommands": list(self.validation_profile.build_commands),
                        "maven": self.validation_profile.maven.__dict__,
                        "scanner": self.validation_profile.scanner.to_dict(),
                    }],
                }
            ),
            encoding="utf-8",
        )
        self.fixture.profile = replace(
            self.fixture.profile,
            stop_hook_argv=(
                str(self.hook), "--config", str(self.hook_config),
                "--task-id", "{task_id}", "--workspace", "{workspace}",
            ),
            stop_hook_sha256=hashlib.sha256(self.hook.read_bytes()).hexdigest(),
        )
        self.fixture.config = OpenHandsRuntimeConfig(
            artifact_root=self.fixture.artifacts,
            agent_server_identity="primary-agent-server",
            profiles=(self.fixture.profile,),
        )

    def tearDown(self):
        self.fixture.tearDown()

    def ready_and_running(self, suffix):
        task_id, workspace = self.fixture._ready(suffix)
        adapter = self.fixture._adapter()
        adapter.provision(task_id)
        adapter.start_execution(task_id, worker_id="worker_one")
        return task_id, workspace, adapter

    def service(self, runner):
        return SharedValidationService(
            self.fixture.store, self.validation_config, runner=runner
        )

    def test_execution_start_gate_and_single_dispatch(self):
        task_id, workspace = self.fixture._ready("start-gate")
        adapter = self.fixture._adapter()
        runtime = adapter.provision(task_id)
        started = adapter.start_execution(task_id, worker_id="worker_one")
        self.assertEqual(runtime.conversation_id, started.conversation_id)
        self.assertEqual(1, self.fixture.server.run_calls)
        claim = self.fixture.store.get_execution_claim(task_id)
        self.assertEqual(ExecutionDispatchStatus.DISPATCHED, claim.dispatch_status)
        self.assertEqual("RUNNING", self.fixture.store.get_status(task_id).execution_status.value)
        (workspace / "agent-edit.txt").write_text("legitimate in-flight edit\n", encoding="utf-8")
        adapter.start_execution(task_id, worker_id="worker_one")
        self.assertEqual(1, self.fixture.server.run_calls)
        with self.assertRaises(ExecutionClaimConflictError):
            adapter.start_execution(task_id, worker_id="worker_two")
        self.assertEqual([], self._remote_refs(workspace))

    def test_execution_start_rejects_missing_validation_configuration(self):
        task_id, _ = self.fixture._ready("missing-hook-config")
        adapter = self.fixture._adapter()
        adapter.provision(task_id)
        self.hook_config.unlink()
        with self.assertRaises(RuntimeConfigurationError):
            adapter.start_execution(task_id, worker_id="worker_one")
        self.assertEqual(0, self.fixture.server.run_calls)
        self.assertIsNone(self.fixture.store.get_execution_claim(task_id))

    def test_uncertain_run_response_reconciles_without_duplicate(self):
        task_id, _ = self.fixture._ready("run-response-loss")
        adapter = self.fixture._adapter()
        adapter.provision(task_id)
        self.fixture.server.fail_after_run = True
        adapter.start_execution(task_id, worker_id="worker_one")
        self.assertEqual(1, self.fixture.server.run_calls)
        adapter.start_execution(task_id, worker_id="worker_one")
        self.assertEqual(1, self.fixture.server.run_calls)

    def test_restart_after_intent_with_idle_native_requires_recovery(self):
        task_id, _ = self.fixture._ready("intent-crash")
        adapter = self.fixture._adapter()
        adapter.provision(task_id)
        self.fixture.store.claim_execution(task_id, "worker_one")
        with self.assertRaises(RuntimeRecoveryRequiredError):
            adapter.start_execution(task_id, worker_id="worker_one")
        self.assertEqual(0, self.fixture.server.run_calls)
        self.assertEqual(
            ExecutionDispatchStatus.RECOVERY_REQUIRED,
            self.fixture.store.get_execution_claim(task_id).dispatch_status,
        )

    def test_pass_allows_and_accepts_only_independent_report(self):
        task_id, workspace, adapter = self.ready_and_running("pass")
        (workspace / "pom.xml").write_text("<project><fixed/></project>\n", encoding="utf-8")
        response = self.service(FakeValidator([report(passed=True)])).handle_stop(task_id)
        self.assertEqual(StopHookDecision.ALLOW, response.decision)
        status = self.fixture.store.get_status(task_id)
        self.assertEqual(TaskStatus.ACCEPTED, status.status)
        self.assertTrue(status.accepted)
        attempt = self.fixture.store.list_validation_attempts(task_id)[0]
        self.assertEqual(ValidationOutcome.PASS, attempt.outcome)
        self.assertEqual(40, len(attempt.validated_tree))
        self.assertTrue(self.service(FakeValidator([])).verify_validated_state(task_id))
        self.fixture.server.conversations[attempt.conversation_id]["execution_status"] = "finished"
        final = adapter.reconcile_execution(task_id)
        self.assertEqual("COMPLETED", final.execution_status.value)
        event_count = len(self.fixture.store.list_events(task_id))
        adapter.reconcile_execution(task_id)
        self.assertEqual(event_count, len(self.fixture.store.list_events(task_id)))
        result = self.fixture.store.get_result(task_id)
        self.assertEqual(attempt.validated_tree, result.validated_tree)
        self.assertEqual("NOT_REQUESTED", result.delivery_status.value)

    def test_remediation_failures_deny_same_conversation_then_bound_terminates(self):
        task_id, _, _ = self.ready_and_running("denials")
        runner = FakeValidator([report(passed=False, remaining=1) for _ in range(4)])
        service = self.service(runner)
        conversation_ids = []
        for expected in range(1, 4):
            response = service.handle_stop(task_id)
            self.assertEqual(StopHookDecision.DENY, response.decision)
            self.assertIn("DETERMINISTIC_VALIDATION_FAILED", response.additional_context)
            attempt = self.fixture.store.list_validation_attempts(task_id)[-1]
            conversation_ids.append(attempt.conversation_id)
            self.assertEqual(expected, attempt.attempt)
            self.assertEqual(TaskStatus.AGENT_RUNNING, self.fixture.store.get_status(task_id).status)
        bounded = service.handle_stop(task_id)
        self.assertEqual(StopHookDecision.ALLOW, bounded.decision)
        self.assertIn("NOT passed", bounded.reason)
        self.assertEqual(TaskStatus.FAILED_VALIDATION, self.fixture.store.get_status(task_id).status)
        self.assertEqual(1, len(set(conversation_ids)))

    def test_infrastructure_and_corrupt_reports_never_accept(self):
        task_id, _, adapter = self.ready_and_running("infra")
        response = self.service(
            FakeValidator([ValidationInfrastructureError("offline scanner failed")])
        ).handle_stop(task_id)
        self.assertEqual(StopHookDecision.ALLOW, response.decision)
        attempt = self.fixture.store.list_validation_attempts(task_id)[0]
        self.assertEqual(ValidationOutcome.INFRASTRUCTURE_FAILURE, attempt.outcome)
        self.assertFalse(self.fixture.store.get_status(task_id).accepted)
        runtime = self.fixture.store.get_openhands_runtime(task_id)
        self.fixture.server.conversations[runtime.conversation_id]["execution_status"] = "finished"
        adapter.reconcile_execution(task_id)
        result = self.fixture.store.get_result(task_id)
        self.assertEqual(ResultOutcome.FAILED_INFRASTRUCTURE, result.outcome)
        self.assertEqual(attempt.report_artifact_id, result.validation_report_artifact_id)

        other, _, _ = self.ready_and_running("corrupt")
        response = self.service(FakeValidator([{}])).handle_stop(other)
        self.assertEqual(StopHookDecision.ALLOW, response.decision)
        attempt = self.fixture.store.list_validation_attempts(other)[0]
        self.assertEqual(ValidationOutcome.VALIDATOR_FAILURE, attempt.outcome)
        self.assertFalse(self.fixture.store.get_status(other).accepted)

        scanner_task, _, _ = self.ready_and_running("scanner-incomplete")
        incomplete = report(passed=False, remaining=1)
        incomplete["scan"] = {"succeeded": False, "outcome": "INCOMPLETE_RETRYABLE_FAILURE"}
        response = self.service(FakeValidator([incomplete])).handle_stop(scanner_task)
        self.assertEqual(StopHookDecision.ALLOW, response.decision)
        attempt = self.fixture.store.list_validation_attempts(scanner_task)[0]
        self.assertEqual(ValidationOutcome.INFRASTRUCTURE_FAILURE, attempt.outcome)

    def test_workspace_change_after_pass_invalidates_validated_state(self):
        task_id, workspace, _ = self.ready_and_running("state-change")
        service = self.service(FakeValidator([report(passed=True)]))
        service.handle_stop(task_id)
        self.assertTrue(service.verify_validated_state(task_id))
        (workspace / "after-validation.txt").write_text("changed\n", encoding="utf-8")
        self.assertFalse(service.verify_validated_state(task_id))

    def test_validation_metadata_artifact_status_and_event_are_atomic(self):
        task_id, _, _ = self.ready_and_running("atomic-validation")
        with sqlite3.connect(self.fixture.database) as connection:
            connection.execute(
                """CREATE TRIGGER reject_validation_completed BEFORE INSERT ON events
                WHEN NEW.type = 'validation.completed'
                BEGIN SELECT RAISE(ABORT, 'offline atomicity fixture'); END"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.service(FakeValidator([report(passed=True)])).handle_stop(task_id)
        status = self.fixture.store.get_status(task_id)
        self.assertEqual(TaskStatus.VALIDATING, status.status)
        self.assertFalse(status.accepted)
        self.assertFalse(any(item.kind == "validation-report" for item in self.fixture.store.list_artifacts(task_id)))

    def test_crash_after_report_write_reconciles_without_validator_rerun(self):
        task_id, _, _ = self.ready_and_running("report-recovery")
        runner = FakeValidator([report(passed=True)])
        service = self.service(runner)
        with patch.object(
            self.fixture.store,
            "complete_validation",
            side_effect=RuntimeError("offline commit interruption"),
        ):
            with self.assertRaises(RuntimeError):
                service.handle_stop(task_id)
        self.assertEqual(1, runner.calls)
        self.assertEqual("VALIDATING", self.fixture.store.get_status(task_id).status.value)
        response = service.handle_stop(task_id)
        self.assertEqual(StopHookDecision.ALLOW, response.decision)
        self.assertEqual(1, runner.calls)
        self.assertEqual(TaskStatus.ACCEPTED, self.fixture.store.get_status(task_id).status)

    def test_recovery_rejects_stale_or_tampered_report(self):
        task_id, _, _ = self.ready_and_running("tampered-recovery")
        runner = FakeValidator([report(passed=True)])
        service = self.service(runner)
        with patch.object(
            self.fixture.store,
            "complete_validation",
            side_effect=RuntimeError("offline commit interruption"),
        ):
            with self.assertRaises(RuntimeError):
                service.handle_stop(task_id)
        report_path = (
            self.fixture.artifacts / task_id / "validation" / "attempt-1" / "report.json"
        )
        envelope = json.loads(report_path.read_text(encoding="utf-8"))
        envelope["validatedRepository"]["tree"] = "0" * 40
        report_path.write_text(json.dumps(envelope), encoding="utf-8")
        with self.assertRaises(ValidationRecoveryRequiredError):
            service.handle_stop(task_id)
        self.assertEqual(1, runner.calls)
        self.assertFalse(self.fixture.store.get_status(task_id).accepted)

    def test_restart_with_running_attempt_and_no_report_fails_closed_without_rerun(self):
        task_id, _, _ = self.ready_and_running("interrupted-no-report")
        self.fixture.store.begin_validation(task_id)
        runner = FakeValidator([report(passed=True)])
        response = self.service(runner).handle_stop(task_id)
        self.assertEqual(StopHookDecision.ALLOW, response.decision)
        self.assertEqual(0, runner.calls)
        attempt = self.fixture.store.list_validation_attempts(task_id)[0]
        self.assertEqual(ValidationOutcome.VALIDATOR_FAILURE, attempt.outcome)
        self.assertFalse(self.fixture.store.get_status(task_id).accepted)

    def test_native_response_shape_and_offline_boundary(self):
        task_id, _, _ = self.ready_and_running("native-shape")
        with patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("network forbidden")
        ), patch.object(
            socket.socket, "connect", side_effect=AssertionError("socket forbidden")
        ):
            response = self.service(
                FakeValidator([report(passed=False, remaining=1)])
            ).handle_stop(task_id)
        self.assertEqual(2, response.exit_code)
        self.assertEqual(
            {"decision", "reason", "additionalContext"},
            set(response.to_native_dict()),
        )
        self.assertEqual("deny", response.to_native_dict()["decision"])

    def test_native_finish_without_pass_is_failed_not_accepted(self):
        task_id, _, adapter = self.ready_and_running("finish-no-pass")
        runtime = self.fixture.store.get_openhands_runtime(task_id)
        self.fixture.server.conversations[runtime.conversation_id]["execution_status"] = "finished"
        status = adapter.reconcile_execution(task_id)
        self.assertEqual(TaskStatus.FAILED_VALIDATION, status.status)
        self.assertFalse(status.accepted)
        result = self.fixture.store.get_result(task_id)
        self.assertEqual(ResultOutcome.FAILED_VALIDATION, result.outcome)
        self.assertIsNone(result.validation_report_artifact_id)

    def test_native_event_association_restart_and_no_secret_copy(self):
        task_id, _, _ = self.ready_and_running("association")
        service = self.service(FakeValidator([report(passed=False, remaining=1)]))
        service.handle_stop(task_id)
        service.associate_native_hook_event(
            task_id,
            1,
            {"id": "native-hook-event-1", "kind": "HookExecutionEvent", "hook_event_type": "Stop", "blocked": True},
        )
        self.fixture.store.close()
        self.fixture.store = SQLiteTaskStore(self.fixture.database)
        attempt = self.fixture.store.list_validation_attempts(task_id)[0]
        self.assertEqual("native-hook-event-1", attempt.native_hook_event_id)
        serialized = json.dumps(attempt.__dict__, default=str)
        self.assertNotIn("GITHUB_TOKEN", serialized)
        self.assertNotIn("private reasoning", serialized)

    def test_secret_shaped_validator_evidence_is_not_persisted(self):
        task_id, _, _ = self.ready_and_running("secret-evidence")
        unsafe = report(passed=False, remaining=1)
        unsafe["checks"][0]["message"] = "api_key=must-not-persist"
        response = self.service(FakeValidator([unsafe])).handle_stop(task_id)
        self.assertEqual(StopHookDecision.ALLOW, response.decision)
        attempt = self.fixture.store.list_validation_attempts(task_id)[0]
        self.assertEqual(ValidationOutcome.VALIDATOR_FAILURE, attempt.outcome)
        artifact = next(
            item for item in self.fixture.store.list_artifacts(task_id)
            if item.artifact_id == attempt.report_artifact_id
        )
        payload = (self.fixture.artifacts / artifact.relative_path).read_text()
        self.assertNotIn("must-not-persist", payload)

    @staticmethod
    def _remote_refs(workspace):
        return subprocess.run(
            ["git", "-C", str(workspace), "for-each-ref", "refs/remotes"],
            check=True,
            text=True,
            capture_output=True,
            env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
        ).stdout.splitlines()


class SharedValidationMigrationTests(unittest.TestCase):
    def test_v5_database_migrates_without_rebuilding_tasks(self):
        with tempfile.TemporaryDirectory() as value:
            database = Path(value) / "tasks.sqlite3"
            store = SQLiteTaskStore(database)
            store.close()
            with sqlite3.connect(database) as connection:
                connection.executescript(
                    """
                    DROP TRIGGER validation_attempts_no_delete;
                    DROP TRIGGER validation_attempts_identity_immutable;
                    DROP TRIGGER execution_claims_no_delete;
                    DROP TRIGGER execution_claims_identity_immutable;
                    DROP TABLE validation_attempts;
                    DROP TABLE execution_claims;
                    UPDATE schema_info SET version = 5 WHERE singleton = 1;
                    """
                )
            reopened = SQLiteTaskStore(database)
            reopened.close()
            with sqlite3.connect(database) as connection:
                self.assertEqual(6, connection.execute("SELECT version FROM schema_info").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
