from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import sqlite3
import socket
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

from openhands_shared.api import TaskApi
from openhands_shared.contracts import (
    ArtifactMetadata,
    BaselineAssessmentStatus,
    BaselineRecord,
    IntelligenceOutcome,
    IntelligenceRecord,
    OpenHandsRuntimeStatus,
    PreparationRecord,
    TaskRequest,
    TaskStatus,
    utc_now,
)
from openhands_shared.openhands_runtime import (
    AgentServerCompatibilityError,
    AgentServerUnavailableError,
    OpenHandsAgentProfile,
    OpenHandsRuntimeConfig,
    RuntimeConfigurationError,
    RuntimeIdentityError,
    RuntimeRecoveryRequiredError,
    SharedOpenHandsRuntime,
)
from openhands_shared.preparation import branch_for_task
from openhands_shared.store import SQLiteTaskStore
from tests.openhands_shared_fixtures import task_request_data


LOGICAL_REPOSITORY = "https://github.com/example/maven-app.git"
NATIVE_PROFILE_ID = "4e6d7335-c08e-49a9-b765-e21cb49d0c96"


def _contains(value: Any, text: str) -> bool:
    if isinstance(value, str):
        return text in value
    if isinstance(value, Mapping):
        return any(_contains(item, text) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, text) for item in value)
    return False


class FakeAgentServer:
    """Pinned-shape in-process transport with a no-model run boundary."""

    def __init__(self):
        self.info = {
            "version": "1.50.0",
            "sdk_version": "1.50.0",
            "tools_version": "1.50.0",
        }
        self.conversations: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.create_calls = 0
        self.message_calls = 0
        self.fail_after_create = False
        self.fail_after_message = False
        self.last_request: dict[str, Any] | None = None
        self.last_message: dict[str, Any] | None = None
        self.unavailable = False
        self.run_calls = 0
        self.fail_after_run = False

    def server_info(self):
        if self.unavailable:
            raise AgentServerUnavailableError("offline unavailable fixture")
        return dict(self.info)

    def get_conversation(self, conversation_id):
        value = self.conversations.get(conversation_id)
        return None if value is None else copy.deepcopy(value)

    def create_conversation(self, request):
        self.create_calls += 1
        self.last_request = copy.deepcopy(dict(request))
        conversation_id = request["conversation_id"]
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = {
                "id": conversation_id,
                "workspace": copy.deepcopy(request["workspace"]),
                "max_iterations": request["max_iterations"],
                "stuck_detection": request["stuck_detection"],
                "execution_status": "idle",
                "hook_config": copy.deepcopy(request["hook_config"]),
                "tags": copy.deepcopy(request["tags"]),
                "launched_agent_profile": {
                    "agent_profile_id": NATIVE_PROFILE_ID,
                    "revision": 7,
                    "secret_refs": [],
                },
                "agent": {
                    "llm": {"model": "vertex_ai/gemini-2.5-flash"},
                    "tools": [
                        {
                            "name": "terminal",
                            "params": {
                                "env": {"PATH": "/usr/bin"},
                                "shell_path": "/bin/bash",
                                "terminal_type": "subprocess",
                            },
                        }
                    ],
                    "agent_context": {
                        "system_message_suffix": (
                            "server profile guidance\n\n"
                            + request["agent_launch_additions"]["system_message_suffix_append"]
                        ),
                        "skills": [
                            {"name": "dependency-remediation-decision"},
                            {"name": "maven-dependency-evidence"},
                        ],
                    },
                },
            }
            self.events[conversation_id] = []
        if self.fail_after_create:
            self.fail_after_create = False
            raise AgentServerUnavailableError("offline response loss")
        return copy.deepcopy(self.conversations[conversation_id])

    def send_message(self, conversation_id, request):
        self.message_calls += 1
        self.last_message = copy.deepcopy(dict(request))
        self.events[conversation_id].append(
            {
                "id": f"native-event-{len(self.events[conversation_id]) + 1}",
                "kind": "MessageEvent",
                "timestamp": "2026-10-16T12:00:00.000Z",
                "message": copy.deepcopy(dict(request)),
            }
        )
        if self.fail_after_message:
            self.fail_after_message = False
            raise AgentServerUnavailableError("offline response loss")

    def run_conversation(self, conversation_id):
        self.run_calls += 1
        self.conversations[conversation_id]["execution_status"] = "running"
        if self.fail_after_run:
            self.fail_after_run = False
            raise AgentServerUnavailableError("offline run response loss")

    def search_events(self, conversation_id, *, page_id=None, body=None):
        assert page_id is None
        items = self.events.get(conversation_id, [])
        if body is not None:
            items = [item for item in items if _contains(item, body)]
        return {"items": copy.deepcopy(items), "next_page_id": None}


class SharedOpenHandsRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source"
        self.workspaces = self.root / "workspaces"
        self.artifacts = self.root / "artifacts"
        self.database = self.root / "state" / "tasks.sqlite3"
        self._git("init", "-b", "main", str(self.source))
        self._git("-C", str(self.source), "config", "user.name", "Runtime Test")
        self._git("-C", str(self.source), "config", "user.email", "runtime@example.invalid")
        (self.source / "pom.xml").write_text("<project/>\n", encoding="utf-8")
        self._git("-C", str(self.source), "add", "pom.xml")
        self._git("-C", str(self.source), "commit", "-m", "baseline")
        self.commit = self._git("-C", str(self.source), "rev-parse", "HEAD").stdout.strip()
        self.store = SQLiteTaskStore(self.database)
        self.server = FakeAgentServer()
        repo = Path(__file__).resolve().parents[2]
        self.profile = OpenHandsAgentProfile(
            profile_id="gate2-dependency-remediation-v1",
            model_profile_id="vertex-gemini-2-5-flash",
            native_agent_profile_id=NATIVE_PROFILE_ID,
            native_agent_profile_revision=7,
            native_model="vertex_ai/gemini-2.5-flash",
            required_skills=(
                "dependency-remediation-decision",
                "maven-dependency-evidence",
            ),
            allowed_terminal_environment=("PATH",),
            guidance_files=(
                repo / "scripts/openhands/guidance/general-engineering.md",
                repo / "scripts/openhands/project-context/AGENTS.md",
            ),
            stop_hook_argv=(
                "/opt/openhands-shared/bin/stop-hook",
                "--task-id",
                "{task_id}",
                "--workspace",
                "{workspace}",
            ),
        )
        self.config = OpenHandsRuntimeConfig(
            artifact_root=self.artifacts,
            agent_server_identity="primary-agent-server",
            profiles=(self.profile,),
        )

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_pinned_request_mapping_context_and_non_running_persistence(self):
        task_id, workspace = self._ready("mapping")

        runtime = self._adapter().provision(task_id)

        request = self.server.last_request
        self.assertIsNotNone(request)
        self.assertNotIn("initial_message", request)
        self.assertFalse(request["worktree"])
        self.assertFalse(request["autotitle"])
        self.assertEqual(str(workspace.resolve()), request["workspace"]["working_dir"])
        self.assertEqual("LocalWorkspace", request["workspace"]["kind"])
        self.assertEqual(NATIVE_PROFILE_ID, request["agent_profile_id"])
        self.assertEqual(250, request["max_iterations"])
        self.assertEqual("command", request["hook_config"]["stop"][0]["hooks"][0]["type"])
        self.assertEqual(False, request["hook_config"]["stop"][0]["hooks"][0]["async"])
        self.assertEqual(False, self.server.last_message["run"])
        instruction = self.server.last_message["content"][0]["text"]
        self.assertIn("Resolve the identified HIGH and CRITICAL", instruction)
        self.assertIn('"javaVersionUnchanged":true', instruction)
        self.assertIn('"buildCommands":["mvn clean verify"]', instruction)
        self.assertIn("<SBRI_PRE_EDIT_EVIDENCE>", instruction)
        self.assertIn("selection limits collected evidence", instruction)
        self.assertIn("Independent deterministic validation remains authoritative", instruction)
        self.assertEqual(OpenHandsRuntimeStatus.CONTEXT_ATTACHED, runtime.runtime_status)
        self.assertEqual("NOT_STARTED", runtime.execution_status.value)
        status = self.store.get_status(task_id)
        self.assertEqual(TaskStatus.AGENT_RUNNING, status.status)
        self.assertEqual(runtime.conversation_id, status.conversation_id)
        self.assertFalse(status.accepted)
        self.assertEqual(1, len(self.store.list_openhands_event_links(task_id)))
        self.assertEqual(0, getattr(self.server, "run_calls", 0))
        captured: dict[str, Any] = {}

        def start_response(value, headers):
            captured["status"] = value

        response = json.loads(
            b"".join(
                TaskApi(self.store)(
                    {
                        "REQUEST_METHOD": "GET",
                        "PATH_INFO": f"/v1/tasks/{task_id}",
                        "QUERY_STRING": "",
                        "wsgi.input": io.BytesIO(),
                    },
                    start_response,
                )
            )
        )
        self.assertEqual("200 OK", captured["status"])
        self.assertEqual(runtime.conversation_id, response["openhands"]["conversationId"])
        self.assertEqual("NOT_STARTED", response["openhands"]["executionStatus"])

    def test_duplicate_retry_and_restart_reuse_one_conversation_and_message(self):
        task_id, _ = self._ready("retry")
        first = self._adapter().provision(task_id)
        second = self._adapter().provision(task_id)
        self.assertEqual(first, second)
        self.assertEqual(1, self.server.create_calls)
        self.assertEqual(1, self.server.message_calls)

        self.store.close()
        self.store = SQLiteTaskStore(self.database)
        third = self._adapter().provision(task_id)
        self.assertEqual(first, third)
        self.assertEqual(1, self.server.create_calls)
        self.assertEqual(1, self.server.message_calls)

    def test_response_loss_after_conversation_creation_reconciles_by_deterministic_id(self):
        task_id, _ = self._ready("create-crash")
        self.server.fail_after_create = True
        runtime = self._adapter().provision(task_id)
        self.assertEqual(1, self.server.create_calls)
        self.assertEqual(1, len(self.server.conversations))
        self.assertEqual(OpenHandsRuntimeStatus.CONTEXT_ATTACHED, runtime.runtime_status)

    def test_response_loss_after_context_event_does_not_duplicate_message(self):
        task_id, _ = self._ready("message-crash")
        self.server.fail_after_message = True
        runtime = self._adapter().provision(task_id)
        self.assertEqual(OpenHandsRuntimeStatus.CONTEXT_ATTACHED, runtime.runtime_status)
        self.assertEqual(1, self.server.message_calls)
        self.assertEqual(1, len(self.server.events[runtime.conversation_id]))

    def test_conversation_association_and_product_event_are_atomic(self):
        task_id, _ = self._ready("atomic")
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """CREATE TRIGGER reject_conversation_event BEFORE INSERT ON events
                WHEN NEW.type = 'agent.conversation.created'
                BEGIN SELECT RAISE(ABORT, 'offline atomicity fixture'); END"""
            )
            connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self._adapter().provision(task_id)
        self.assertIsNone(self.store.get_openhands_runtime(task_id))
        self.assertIsNone(self.store.get_status(task_id).conversation_id)
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP TRIGGER reject_conversation_event")
            connection.commit()
        runtime = self._adapter().provision(task_id)
        self.assertEqual(1, self.server.create_calls)
        self.assertEqual(runtime.conversation_id, self.store.get_status(task_id).conversation_id)

    def test_event_references_preserve_order_without_copying_native_payload(self):
        task_id, _ = self._ready("events")
        runtime = self._adapter().provision(task_id)
        self.server.events[runtime.conversation_id].extend(
            [
                {
                    "id": "native-event-2",
                    "kind": "ActionEvent",
                    "timestamp": "2026-10-16T12:01:00.000Z",
                    "secretBearingPayload": "must-not-be-copied",
                },
                {
                    "id": "native-event-3",
                    "kind": "ObservationEvent",
                    "timestamp": "2026-10-16T12:02:00.000Z",
                    "largePayload": {"content": "native owns this"},
                },
            ]
        )
        links = self._adapter().synchronize_event_references(task_id)
        self.assertEqual([1, 2, 3], [link.native_order for link in links])
        self.assertEqual(
            ["native-event-1", "native-event-2", "native-event-3"],
            [link.native_event_id for link in links],
        )
        with sqlite3.connect(self.database) as connection:
            stored = " ".join(
                row[0]
                for row in connection.execute(
                    "SELECT data_json FROM events WHERE task_id = ?", (task_id,)
                )
            )
        self.assertNotIn("must-not-be-copied", stored)
        self.assertNotIn("native owns this", stored)

    def test_disabled_sbri_is_explicit_and_not_wrapped_as_evidence(self):
        task_id, _ = self._ready("disabled", outcome=IntelligenceOutcome.DISABLED)
        self._adapter().provision(task_id)
        instruction = self.server.last_message["content"][0]["text"]
        self.assertIn("SBRI status: DISABLED", instruction)
        self.assertNotIn("<SBRI_PRE_EDIT_EVIDENCE>", instruction)

    def test_workspace_verifier_allows_changes_only_after_agent_boundary(self):
        task_id, workspace = self._ready("dirty-descendant")
        (workspace / "pom.xml").write_text("<project><changed/></project>\n", encoding="utf-8")
        (workspace / "untracked.txt").write_text("agent edit\n", encoding="utf-8")
        request = self.store.get_request(task_id)
        preparation = self.store.get_preparation(task_id)
        self.assertIsNotNone(preparation)
        verified = self._adapter()._verify_workspace(
            request, preparation, allow_agent_changes=True
        )
        self.assertEqual(workspace.resolve(), verified)
        with self.assertRaisesRegex(RuntimeIdentityError, "unapproved changes"):
            self._adapter().provision(task_id)
        self.assertEqual(0, self.server.create_calls)

    def test_foreign_workspace_branch_is_rejected(self):
        task_id, workspace = self._ready("foreign-branch")
        self._git("-C", str(workspace), "checkout", "--detach")
        with self.assertRaisesRegex(RuntimeIdentityError, "foreign branch"):
            self._adapter().provision(task_id)
        self.assertEqual(0, self.server.create_calls)

    def test_incompatible_server_and_invalid_stop_hook_fail_closed(self):
        task_id, _ = self._ready("incompatible")
        self.server.info["version"] = "1.51.0"
        with self.assertRaises(AgentServerCompatibilityError):
            self._adapter().provision(task_id)
        self.assertEqual(0, self.server.create_calls)

        with self.assertRaises(RuntimeConfigurationError):
            OpenHandsAgentProfile(
                **{
                    **self.profile.__dict__,
                    "stop_hook_argv": ("/bin/true",),
                }
            )

    def test_missing_agent_server_is_retryable_without_persisted_side_effect(self):
        task_id, _ = self._ready("missing-server")
        self.server.unavailable = True
        with self.assertRaises(AgentServerUnavailableError):
            self._adapter().provision(task_id)
        self.assertIsNone(self.store.get_openhands_runtime(task_id))
        self.assertIsNone(self.store.get_status(task_id).conversation_id)
        self.assertEqual(0, self.server.create_calls)

    def test_native_finished_never_becomes_validation_pass_or_acceptance(self):
        task_id, _ = self._ready("native-finished")
        runtime = self._adapter().provision(task_id)
        self.server.conversations[runtime.conversation_id]["execution_status"] = "finished"
        with self.assertRaises(RuntimeRecoveryRequiredError):
            self._adapter().provision(task_id)
        status = self.store.get_status(task_id)
        self.assertEqual(TaskStatus.AGENT_RUNNING, status.status)
        self.assertEqual("NOT_VALIDATED", status.validation_status.value)
        self.assertFalse(status.accepted)
        self.assertEqual("NOT_STARTED", status.execution_status.value)

    def test_inherited_credentials_never_enter_native_request_or_message(self):
        task_id, _ = self._ready("credentials")
        previous = dict(os.environ)
        try:
            os.environ.update(
                {
                    "GITHUB_TOKEN": "not-forwarded",
                    "GOOGLE_APPLICATION_CREDENTIALS": "/secret/adc.json",
                    "VERTEXAI_API_KEY": "not-forwarded",
                }
            )
            self._adapter().provision(task_id)
        finally:
            os.environ.clear()
            os.environ.update(previous)
        serialized = json.dumps(
            {"request": self.server.last_request, "message": self.server.last_message}
        )
        self.assertNotIn("not-forwarded", serialized)
        self.assertNotIn("/secret/adc.json", serialized)
        self.assertNotIn('"secrets"', serialized)
        self.assertNotIn('"env"', serialized)

    def test_offline_adapter_invokes_no_external_network_or_live_tools(self):
        task_id, _ = self._ready("offline-only")
        with patch.object(
            urllib.request,
            "urlopen",
            side_effect=AssertionError("external network forbidden"),
        ), patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("external socket forbidden"),
        ):
            runtime = self._adapter().provision(task_id)
        self.assertEqual(OpenHandsRuntimeStatus.CONTEXT_ATTACHED, runtime.runtime_status)
        self.assertEqual(0, getattr(self.server, "run_calls", 0))

    def _adapter(self):
        return SharedOpenHandsRuntime(self.store, self.config, self.server)

    def _ready(self, suffix: str, *, outcome=IntelligenceOutcome.COMPLETE):
        request = TaskRequest.from_dict(
            task_request_data(
                idempotency_key=f"runtime-{suffix}",
                repository_url=LOGICAL_REPOSITORY,
                expected_commit=self.commit,
            )
        )
        task_id = self.store.register_task(request).status.task_id
        self.store.start_preparation(task_id)
        workspace = self.workspaces / task_id / "repository"
        workspace.parent.mkdir(parents=True)
        branch = branch_for_task(task_id)
        self._git(
            "-C", str(self.source), "worktree", "add", "-b", branch, str(workspace), self.commit
        )
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
        completed = utc_now()
        baseline_payload = json.dumps(
            {
                "kind": "openhands-shared-baseline",
                "taskId": task_id,
                "baselineCommit": self.commit,
                "assessmentStatus": "COMPLETED",
                "repository": {
                    "url": LOGICAL_REPOSITORY,
                    "baseRef": "refs/heads/main",
                    "localBranch": branch,
                },
                "originalVulnerabilityFindings": [{
                    "vulnerabilityId": "CVE-OFFLINE-1", "aliases": [], "severity": "HIGH",
                    "dependency": {"groupId": "example", "artifactId": "demo", "packageName": "example:demo", "currentVersion": "1.0", "ecosystem": "Maven"},
                    "fixedVersions": ["1.1"], "summary": "offline", "backendEvidence": {},
                }],
                "scan": {
                    "succeeded": True,
                    "findings": [{
                        "vulnerabilityId": "CVE-OFFLINE-1", "aliases": [], "severity": "HIGH",
                        "dependency": {"groupId": "example", "artifactId": "demo", "packageName": "example:demo", "currentVersion": "1.0", "ecosystem": "Maven"},
                        "fixedVersions": ["1.1"], "summary": "offline", "backendEvidence": {},
                    }],
                    "outcome": "COMPLETED_WITH_FINDINGS",
                    "backend": "osv",
                    "evidence": {},
                },
                "constraints": {
                    "javaVersions": ["17"],
                    "springBootVersions": ["3.4.0"],
                    "suppressionFiles": {},
                },
            },
            sort_keys=True,
        ).encode()
        baseline_artifact = self._write_artifact(
            task_id,
            "baseline-report",
            "baseline-report",
            f"{task_id}/baseline/report.json",
            baseline_payload,
            completed,
        )
        self.store.complete_baseline(
            BaselineRecord(
                task_id=task_id,
                baseline_commit=self.commit,
                assessment_status=BaselineAssessmentStatus.COMPLETED,
                build_succeeded=True,
                scanner_outcome="COMPLETED_WITH_FINDINGS",
                finding_count=1,
                report_artifact_id=baseline_artifact.artifact_id,
                report_sha256=baseline_artifact.sha256,
                tool_versions={"scanner": {"version": "offline"}},
                completed_at=completed,
            ),
            (baseline_artifact,),
        )
        if outcome is IntelligenceOutcome.DISABLED:
            summary_text = "SBRI is disabled for this registered task.\n"
            applicable = None
            invoked = False
            fingerprint = None
        else:
            summary_text = (
                "<SBRI_PRE_EDIT_EVIDENCE>\n"
                "Offline candidate evidence; the set is bounded and non-prescriptive.\n"
                "</SBRI_PRE_EDIT_EVIDENCE>\n"
            )
            applicable = True
            invoked = True
            fingerprint = "f" * 64
        summary_artifact = self._write_artifact(
            task_id,
            "intelligence-summary",
            "intelligence-summary",
            f"{task_id}/intelligence/summary.txt",
            summary_text.encode(),
            completed,
        )
        record_payload = json.dumps(
            {"taskId": task_id, "baselineCommit": self.commit, "outcome": outcome.value},
            sort_keys=True,
        ).encode()
        record_artifact = self._write_artifact(
            task_id,
            "intelligence-record",
            "intelligence-record",
            f"{task_id}/intelligence/record.json",
            record_payload,
            completed,
        )
        self.store.complete_intelligence(
            IntelligenceRecord(
                task_id=task_id,
                baseline_commit=self.commit,
                outcome=outcome,
                applicable=applicable,
                invoked=invoked,
                reused=False,
                profile_id="gate2-sbri-v1",
                fingerprint=fingerprint,
                selection_manifest={},
                evaluated_versions=(),
                record_artifact_id=record_artifact.artifact_id,
                record_sha256=record_artifact.sha256,
                summary_artifact_id=summary_artifact.artifact_id,
                explanation="offline fixture",
                completed_at=completed,
            ),
            (record_artifact, summary_artifact),
        )
        return task_id, workspace

    def _write_artifact(self, task_id, artifact_id, kind, relative, payload, created_at):
        path = self.artifacts / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return ArtifactMetadata(
            artifact_id=artifact_id,
            task_id=task_id,
            kind=kind,
            relative_path=relative,
            media_type="text/plain" if relative.endswith(".txt") else "application/json",
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            created_at=created_at,
        )

    @staticmethod
    def _git(*arguments):
        return subprocess.run(
            ["git", *arguments],
            check=True,
            text=True,
            capture_output=True,
            env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
        )


class SharedOpenHandsRuntimeMigrationTests(unittest.TestCase):
    def test_v4_database_migrates_in_place(self):
        with tempfile.TemporaryDirectory() as value:
            database = Path(value) / "tasks.sqlite3"
            store = SQLiteTaskStore(database)
            task_id = store.register_task(
                TaskRequest.from_dict(task_request_data(idempotency_key="runtime-migration"))
            ).status.task_id
            store.close()
            with sqlite3.connect(database) as connection:
                connection.executescript(
                    """
                    DROP TRIGGER openhands_event_links_immutable_delete;
                    DROP TRIGGER openhands_event_links_immutable_update;
                    DROP TRIGGER openhands_runtimes_no_delete;
                    DROP TRIGGER openhands_runtimes_identity_immutable;
                    DROP TABLE openhands_event_links;
                    DROP TABLE openhands_runtimes;
                    UPDATE schema_info SET version = 4 WHERE singleton = 1;
                    """
                )
                connection.commit()
            reopened = SQLiteTaskStore(database)
            try:
                self.assertEqual(task_id, reopened.get_status(task_id).task_id)
                self.assertIsNone(reopened.get_openhands_runtime(task_id))
                with sqlite3.connect(database) as connection:
                    self.assertEqual(
                        6, connection.execute("SELECT version FROM schema_info").fetchone()[0]
                    )
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
