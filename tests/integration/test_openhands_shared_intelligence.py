from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from openhands_shared.contracts import (
    ArtifactMetadata,
    BaselineAssessmentStatus,
    BaselineRecord,
    IntelligenceOutcome,
    PreparationRecord,
    TaskRequest,
    TaskStatus,
    utc_now,
)
from openhands_shared.intelligence import (
    IntelligenceConfig,
    IntelligenceEvidenceError,
    IntelligenceProfile,
    SharedIntelligenceAssessor,
)
from openhands_shared.preparation import branch_for_task
from openhands_shared.store import SQLiteTaskStore
from scripts.openhands.sbri_integration import project_fingerprint
from tests.openhands_shared_fixtures import task_request_data


LOGICAL_REPOSITORY = "https://github.com/example/maven-app.git"


def _counts(original=1, addressed=0, remaining=1, new=0, total=1):
    def severities(value):
        return {"CRITICAL": value, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}

    return {
        "original": severities(original),
        "addressed": severities(addressed),
        "remaining": severities(remaining),
        "new": severities(new),
        "total": severities(total),
    }


class FakeSbriRunner:
    def __init__(self, status="COMPLETE", *, corrupt_fingerprint=False, mutate=False, error=False):
        self.status = status
        self.corrupt_fingerprint = corrupt_fingerprint
        self.mutate = mutate
        self.error = error
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def run(self, *, profile, project, objective, state_dir):
        with self.lock:
            self.calls.append(objective)
        if self.error:
            raise RuntimeError("offline operational fixture")
        root = state_dir / "sbri"
        root.mkdir(parents=True, exist_ok=True)
        if self.status == "NOT_APPLICABLE":
            record = {
                "status": "NOT_APPLICABLE",
                "applicability": {"applicable": False, "reason": "no Spring Boot controller"},
                "invoked": False,
                "reused": False,
            }
            (root / "latest.json").write_text(json.dumps(record), encoding="utf-8")
            return record
        if self.status == "INVALID_RELEASE_SELECTION":
            record = {
                "status": "INVALID_RELEASE_SELECTION",
                "applicability": {
                    "applicable": True,
                    "reason": "Spring Boot Maven security remediation",
                    "baseline": "4.0.6",
                },
                "invoked": False,
                "reused": False,
                "message": "candidate limit exceeded",
                "releaseSelection": {"versions": "4.0.8,4.1.1"},
            }
            (root / "latest.json").write_text(json.dumps(record), encoding="utf-8")
            return record

        selection = {
            "baseline": "4.0.6",
            "mode": "explicit",
            "source": "deployment-profile",
            "requested": ["4.0.8"],
            "resolved_candidates": ["4.0.8"],
            "candidate_count": 1,
            "max_candidates": 4,
            "metadata": {"source": "offline-fixture", "sha256": "a" * 64},
            "prereleases_allowed": False,
            "selection_filters": {
                "published_only": True,
                "stable_numeric_only": True,
                "forward_from_baseline_only": True,
            },
            "exclusion_reporting": "fixture",
        }
        request = {
            "baseline": "4.0.6",
            "releases": ["4.0.8"],
            "scanner": {"requested": "/trusted/osv-scanner"},
            "config": None,
            "releaseSelection": selection,
        }
        fingerprint, before = project_fingerprint(project, request)
        run_dir = root / fingerprint
        output = run_dir / "output"
        output.mkdir(parents=True)
        result = {
            "schema_version": "1.0",
            "status": "SUCCESS" if self.status == "COMPLETE" else "PARTIAL",
            "application": {"original_spring_boot_version": "4.0.6"},
            "execution": {
                "evaluated_releases": ["4.0.6", "4.0.8"],
                "release_selection": selection,
            },
            "scanner": {"name": "offline"},
            "releases": [
                {
                    "version": "4.0.6",
                    "assessment_status": "COMPLETE",
                    "rank": None,
                    "counts": _counts(),
                },
                {
                    "version": "4.0.8",
                    "assessment_status": "COMPLETE",
                    "rank": 1,
                    "counts": _counts(addressed=1, remaining=0, total=0),
                },
            ],
            "dependencies": [],
            "findings": [],
            "evidence": {},
            "errors": [] if self.status == "COMPLETE" else [{"stage": "scanner"}],
        }
        result_path = output / "result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        (output / "report.html").write_text("<html>offline</html>\n", encoding="utf-8")
        evidence = output / "evidence"
        evidence.mkdir()
        (evidence / "scanner.json").write_text("{}\n", encoding="utf-8")
        selection_path = run_dir / "release-selection.json"
        selection_path.write_text(json.dumps(selection), encoding="utf-8")
        summary_path = run_dir / "agent-summary.txt"
        summary_path.write_text(
            "SBRI pre-edit release intelligence (security evidence; not an upgrade instruction)\n"
            "The evaluated release set is not necessarily the complete set of credible remediation candidates.\n",
            encoding="utf-8",
        )
        summary_json = run_dir / "agent-summary.json"
        summary_json.write_text(json.dumps({"status": self.status, "errors": result["errors"]}), encoding="utf-8")
        command_log = run_dir / "command.log"
        command_log.write_text("offline fixture\n", encoding="utf-8")
        if self.mutate:
            (project / "mutated.txt").write_text("unexpected\n", encoding="utf-8")
        after_fingerprint, after = project_fingerprint(project, request)
        record = {
            "status": self.status,
            "applicability": {
                "applicable": True,
                "reason": "Spring Boot Maven security remediation",
                "baseline": "4.0.6",
                "controller": "parent",
            },
            "invoked": True,
            "reused": False,
            "fingerprint": "b" * 64 if self.corrupt_fingerprint else fingerprint,
            "request": request,
            "releaseSelection": selection,
            "sourceUnchanged": fingerprint == after_fingerprint and before == after,
            "sourceBefore": before,
            "sourceAfter": after,
            "summaryPath": str(summary_path),
            "summaryJsonPath": str(summary_json),
            "resultPath": str(result_path),
            "reportPath": str(output / "report.html"),
            "evidencePath": str(evidence),
            "commandLog": str(command_log),
            "releaseSelectionPath": str(selection_path),
            "deliveredBeforeAgentRun": self.status in {"COMPLETE", "PARTIAL"},
            "rankForcedAsStrategy": False,
        }
        (run_dir / "execution.json").write_text(json.dumps(record), encoding="utf-8")
        (root / "latest.json").write_text(json.dumps(record), encoding="utf-8")
        return record


class SharedIntelligenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source"
        self.workspaces = self.root / "workspaces"
        self.artifacts = self.root / "artifacts"
        self.database = self.root / "state" / "tasks.sqlite3"
        self._git("init", "-b", "main", str(self.source))
        self._git("-C", str(self.source), "config", "user.name", "Intelligence Test")
        self._git("-C", str(self.source), "config", "user.email", "intelligence@example.invalid")
        (self.source / "pom.xml").write_text(
            '<project xmlns="http://maven.apache.org/POM/4.0.0">'
            "<modelVersion>4.0.0</modelVersion><parent>"
            "<groupId>org.springframework.boot</groupId>"
            "<artifactId>spring-boot-starter-parent</artifactId>"
            "<version>4.0.6</version></parent><groupId>example</groupId>"
            "<artifactId>app</artifactId><version>1</version></project>\n",
            encoding="utf-8",
        )
        self._git("-C", str(self.source), "add", "pom.xml")
        self._git("-C", str(self.source), "commit", "-m", "baseline")
        self.commit = self._git("-C", str(self.source), "rev-parse", "HEAD").stdout.strip()
        self.store = SQLiteTaskStore(self.database)
        self.scanner = self.root / "trusted-osv-scanner"
        self.scanner.write_text("offline fixture\n", encoding="utf-8")
        self.profile = IntelligenceProfile(
            profile_id="gate2-sbri-v1",
            task_agent_profile="gate2-dependency-remediation-v1",
            control_repo=Path(__file__).resolve().parents[2],
            scanner=self.scanner,
            release_versions="4.0.8",
            max_candidates=4,
        )
        self.config = IntelligenceConfig(self.artifacts, (self.profile,))

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_disabled_skips_collector_and_marks_agent_stage_pending(self):
        task_id, _ = self._ready("disabled", mode="disabled")
        runner = FakeSbriRunner()

        record = self._assessor(runner).assess(task_id)

        self.assertEqual(IntelligenceOutcome.DISABLED, record.outcome)
        self.assertIsNone(record.applicable)
        self.assertEqual([], runner.calls)
        self.assertEqual(TaskStatus.AGENT_RUNNING, self.store.get_status(task_id).status)
        self.assertEqual("NOT_STARTED", self.store.get_status(task_id).execution_status.value)
        self.assertEqual("intelligence.skipped", self.store.list_events(task_id)[-1].type)

    def test_not_applicable_skips_without_candidate_evaluation(self):
        task_id, _ = self._ready("not-applicable")
        record = self._assessor(FakeSbriRunner("NOT_APPLICABLE")).assess(task_id)
        self.assertEqual(IntelligenceOutcome.NOT_APPLICABLE, record.outcome)
        self.assertFalse(record.applicable)
        self.assertFalse(record.invoked)
        self.assertEqual(TaskStatus.AGENT_RUNNING, self.store.get_status(task_id).status)

    def test_complete_and_partial_preserve_selection_summary_and_reasoning_boundary(self):
        complete_task, _ = self._ready("complete")
        complete = self._assessor(FakeSbriRunner()).assess(complete_task)
        self.assertEqual(IntelligenceOutcome.COMPLETE, complete.outcome)
        self.assertEqual(("4.0.6", "4.0.8"), complete.evaluated_versions)
        self.assertEqual(["4.0.8"], complete.selection_manifest["resolved_candidates"])
        summary = self._artifact_text(complete_task, complete.summary_artifact_id)
        self.assertIn("<SBRI_PRE_EDIT_EVIDENCE>", summary)
        self.assertIn("not necessarily the complete set", summary)
        self.assertIn("not implementation approval", summary)
        self.assertIn("Independent validation remains authoritative", summary)

        partial_task, _ = self._ready("partial")
        partial = self._assessor(FakeSbriRunner("PARTIAL")).assess(partial_task)
        self.assertEqual(IntelligenceOutcome.PARTIAL, partial.outcome)
        self.assertEqual(TaskStatus.AGENT_RUNNING, self.store.get_status(partial_task).status)
        self.assertEqual("intelligence.incomplete", self.store.list_events(partial_task)[-1].type)

    def test_operational_failure_continues_with_explicitly_incomplete_evidence(self):
        task_id, _ = self._ready("failed")
        record = self._assessor(FakeSbriRunner(error=True)).assess(task_id)
        self.assertEqual(IntelligenceOutcome.FAILED, record.outcome)
        self.assertEqual(TaskStatus.AGENT_RUNNING, self.store.get_status(task_id).status)
        summary = self._artifact_text(task_id, record.summary_artifact_id)
        self.assertIn("not evidence that Spring Boot upgrades are impossible", summary)

    def test_invalid_selection_and_corrupt_fingerprint_fail_closed(self):
        invalid_task, _ = self._ready("invalid")
        invalid = self._assessor(FakeSbriRunner("INVALID_RELEASE_SELECTION")).assess(invalid_task)
        self.assertEqual(IntelligenceOutcome.INVALID_SELECTION, invalid.outcome)
        self.assertEqual(TaskStatus.FAILED_INFRASTRUCTURE, self.store.get_status(invalid_task).status)

        corrupt_task, _ = self._ready("corrupt")
        corrupt = self._assessor(FakeSbriRunner(corrupt_fingerprint=True)).assess(corrupt_task)
        self.assertEqual(IntelligenceOutcome.CORRUPT_EVIDENCE, corrupt.outcome)
        self.assertEqual(TaskStatus.FAILED_INFRASTRUCTURE, self.store.get_status(corrupt_task).status)

    def test_corrupt_baseline_artifact_is_recorded_and_fails_closed(self):
        task_id, _ = self._ready("corrupt-baseline")
        baseline_artifact = next(
            item for item in self.store.list_artifacts(task_id)
            if item.artifact_id == "baseline-report"
        )
        (self.artifacts / baseline_artifact.relative_path).write_text("tampered\n", encoding="utf-8")

        record = self._assessor(FakeSbriRunner()).assess(task_id)

        self.assertEqual(IntelligenceOutcome.CORRUPT_EVIDENCE, record.outcome)
        self.assertEqual(TaskStatus.FAILED_INFRASTRUCTURE, self.store.get_status(task_id).status)

    def test_repository_mutation_is_detected_and_never_advances(self):
        task_id, workspace = self._ready("mutation")
        record = self._assessor(FakeSbriRunner(mutate=True)).assess(task_id)
        self.assertEqual(IntelligenceOutcome.REPOSITORY_MUTATION, record.outcome)
        self.assertEqual(TaskStatus.FAILED_INFRASTRUCTURE, self.store.get_status(task_id).status)
        self.assertTrue((workspace / "mutated.txt").is_file())

    def test_duplicate_restart_and_artifact_integrity(self):
        task_id, _ = self._ready("restart")
        runner = FakeSbriRunner()
        first = self._assessor(runner).assess(task_id)
        events = self.store.list_events(task_id)
        second = self._assessor(runner).assess(task_id)
        self.assertEqual(first, second)
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(events, self.store.list_events(task_id))

        self.store.close()
        self.store = SQLiteTaskStore(self.database)
        third = self._assessor(runner).assess(task_id)
        self.assertEqual(first, third)
        artifact = next(
            item for item in self.store.list_artifacts(task_id)
            if item.artifact_id == first.summary_artifact_id
        )
        (self.artifacts / artifact.relative_path).write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(IntelligenceEvidenceError, "checksum"):
            self._assessor(runner).assess(task_id)

    def test_interrupted_database_commit_reconciles_without_collector_rerun(self):
        task_id, _ = self._ready("interrupted")
        runner = FakeSbriRunner()
        assessor = self._assessor(runner)
        original = self.store.complete_intelligence
        count = 0

        def interrupt(record, artifacts):
            nonlocal count
            count += 1
            if count == 1:
                raise RuntimeError("simulated interruption")
            return original(record, artifacts)

        with patch.object(self.store, "complete_intelligence", side_effect=interrupt):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                assessor.assess(task_id)
            recovered = assessor.assess(task_id)

        self.assertEqual(IntelligenceOutcome.COMPLETE, recovered.outcome)
        self.assertEqual(1, len(runner.calls))
        self.assertEqual(TaskStatus.AGENT_RUNNING, self.store.get_status(task_id).status)

    def test_status_metadata_and_event_transaction_roll_back_together(self):
        task_id, _ = self._ready("atomic")
        runner = FakeSbriRunner()
        with patch.object(self.store, "_append_event", side_effect=RuntimeError("event failure")):
            with self.assertRaisesRegex(RuntimeError, "event failure"):
                self._assessor(runner).assess(task_id)

        self.assertIsNone(self.store.get_intelligence(task_id))
        self.assertEqual(TaskStatus.INTELLIGENCE, self.store.get_status(task_id).status)
        self.assertFalse(
            any(
                artifact.kind.startswith("intelligence-")
                for artifact in self.store.list_artifacts(task_id)
            )
        )

    def test_concurrent_tasks_are_isolated(self):
        tasks = [self._ready(f"concurrent-{index}")[0] for index in range(3)]
        runner = FakeSbriRunner()
        assessor = self._assessor(runner)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            records = list(executor.map(assessor.assess, tasks))
        self.assertEqual(set(tasks), {record.task_id for record in records})
        paths = [
            artifact.relative_path
            for task_id in tasks
            for artifact in self.store.list_artifacts(task_id)
            if artifact.kind.startswith("intelligence-")
        ]
        self.assertEqual(len(paths), len(set(paths)))

    def test_offline_boundary_never_invokes_network_model_or_real_collector(self):
        task_id, _ = self._ready("offline")
        runner = FakeSbriRunner()
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("network forbidden")
        ), patch(
            "openhands_shared.intelligence.run_pre_edit_intelligence",
            side_effect=AssertionError("real SBRI forbidden"),
        ):
            record = self._assessor(runner).assess(task_id)
        self.assertEqual(IntelligenceOutcome.COMPLETE, record.outcome)

    def _assessor(self, runner):
        return SharedIntelligenceAssessor(self.store, self.config, runner=runner)

    def _ready(self, suffix: str, *, mode="auto"):
        data = task_request_data(
            idempotency_key=f"intelligence-{suffix}",
            repository_url=LOGICAL_REPOSITORY,
            expected_commit=self.commit,
        )
        data["intelligence"]["sbri"]["mode"] = mode
        request = TaskRequest.from_dict(data)
        task_id = self.store.register_task(request).status.task_id
        self.store.start_preparation(task_id)
        workspace = self.workspaces / task_id / "repository"
        workspace.parent.mkdir(parents=True)
        branch = branch_for_task(task_id)
        self._git("-C", str(self.source), "worktree", "add", "-b", branch, str(workspace), self.commit)
        prepared_at = utc_now()
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
                prepared_at=prepared_at,
            )
        )
        completed_at = utc_now()
        report = {
            "contractVersion": "1",
            "kind": "openhands-shared-baseline",
            "taskId": task_id,
            "baselineCommit": self.commit,
            "assessmentStatus": "COMPLETED",
        }
        payload = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
        relative = f"{task_id}/baseline/report.json"
        path = self.artifacts / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        artifact = ArtifactMetadata(
            artifact_id="baseline-report",
            task_id=task_id,
            kind="baseline-report",
            relative_path=relative,
            media_type="application/json",
            sha256=digest,
            size_bytes=len(payload),
            created_at=completed_at,
        )
        self.store.complete_baseline(
            BaselineRecord(
                task_id=task_id,
                baseline_commit=self.commit,
                assessment_status=BaselineAssessmentStatus.COMPLETED,
                build_succeeded=True,
                scanner_outcome="COMPLETED_WITH_FINDINGS",
                finding_count=1,
                report_artifact_id=artifact.artifact_id,
                report_sha256=digest,
                tool_versions={"scanner": {"version": "offline"}},
                completed_at=completed_at,
            ),
            (artifact,),
        )
        return task_id, workspace

    def _artifact_text(self, task_id, artifact_id):
        artifact = next(
            item for item in self.store.list_artifacts(task_id) if item.artifact_id == artifact_id
        )
        return (self.artifacts / artifact.relative_path).read_text(encoding="utf-8")

    @staticmethod
    def _git(*arguments):
        return subprocess.run(
            ["git", *arguments],
            check=True,
            text=True,
            capture_output=True,
            env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
        )


class SharedIntelligenceSchemaMigrationTests(unittest.TestCase):
    def test_v3_database_migrates_in_place_and_preserves_existing_task(self):
        with tempfile.TemporaryDirectory() as value:
            database = Path(value) / "tasks.sqlite3"
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
                    UPDATE schema_info SET version = 3 WHERE singleton = 1;
                    """
                )
                connection.commit()
            finally:
                connection.close()
            reopened = SQLiteTaskStore(database)
            try:
                self.assertEqual(task_id, reopened.get_status(task_id).task_id)
                self.assertIsNone(reopened.get_intelligence(task_id))
                with sqlite3.connect(database) as check:
                    self.assertEqual(4, check.execute("SELECT version FROM schema_info").fetchone()[0])
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
