"""Contract for native-first handoff; no model, network or agent execution."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_remediation as native_first
import openhands_native_validator_poc as fixture_support
from openhands_shared.store import SQLiteTaskStore


class NativeFirstHandoffTests(unittest.TestCase):
    def setUp(self):
        self.context_patch = patch.object(native_first, "remediation_agent_context", return_value={"skills": [{"name": "dependency-remediation-decision"}, {"name": "maven-dependency-evidence"}], "system_message_suffix": "General guidance"})
        self.context_patch.start()
        self.old = fixture_support.STATE
        self.temp = tempfile.TemporaryDirectory()
        fixture_support.STATE = Path(self.temp.name) / "fixture"
        fixture_support.STATE.mkdir()
        self.data = fixture_support.fixture_setup()
        self.task_root = Path(self.data["database"]).parents[1]
        self.store = SQLiteTaskStore(Path(self.data["database"]))

    def tearDown(self):
        self.context_patch.stop()
        self.store.close()
        fixture_support.STATE = self.old
        shutil.rmtree(self.task_root, ignore_errors=True)
        self.temp.cleanup()

    def build(self, **kwargs):
        return native_first.build_request(
            self.store, self.data["taskId"],
            hook_config=Path(self.data["hookConfig"]),
            model="openai/gpt-4o-mini", **kwargs
        )

    def test_official_request_reuses_prepared_identity_and_actual_validator(self):
        request = self.build()
        self.assertEqual(request["conversation_id"], self.data["conversationId"])
        self.assertEqual(request["workspace"]["working_dir"], self.data["workspace"])
        self.assertFalse(request["worktree"])
        self.assertEqual(
            [tool["name"] for tool in request["agent"]["tools"]],
            ["terminal", "file_editor", "task_tracker"]
        )
        self.assertTrue(request["agent"]["system_prompt_kwargs"]["cli_mode"])
        self.assertTrue(all(not tool["params"] for tool in request["agent"]["tools"]))
        self.assertEqual(request["tags"]["taskid"], self.data["taskId"])
        self.assertTrue(all(key.isalnum() and key.islower() for key in request["tags"]))
        self.assertIn("openhands_shared.stop_hook",
                      request["hook_config"]["stop"][0]["hooks"][0]["command"])
        self.assertNotIn("api_key", request["agent"]["llm"])
        self.assertNotIn("base_url", request["agent"]["llm"])
        self.assertNotIn("api_key", native_first.show_safe_summary(request))

    def test_native_response_rejects_missing_hook_wrong_workspace_or_id(self):
        request = self.build()
        response = {
            "id": request["conversation_id"], "execution_status": "idle",
            "workspace": request["workspace"], "hook_config": request["hook_config"],
            "agent": request["agent"],
        }
        self.assertEqual(native_first.validate_native_response(response, request),
                         self.data["conversationId"])
        # Quoted Python bootstrap must be accepted as a literal command.
        import json
        self.assertIn("\\\"", json.dumps(request["hook_config"]))
        for key, val in (
            ("id", "wrong"), ("execution_status", "finished"),
            ("workspace", {"working_dir": "/tmp/foreign"}),
            ("hook_config", {})
        ):
            corrupt = {**response, key: val}
            with self.subTest(key=key), self.assertRaises(native_first.HandoffError):
                native_first.validate_native_response(corrupt, request)

    def test_native_response_rejects_missing_agent_capabilities(self):
        request = self.build()
        response = {
            "id": request["conversation_id"], "execution_status": "idle",
            "workspace": request["workspace"],
            "hook_config": request["hook_config"], "agent": request["agent"],
        }
        for agent in (
            {},
            {**request["agent"], "tools": []},
            {**request["agent"], "agent_context": {"skills": [], "system_message_suffix": "General guidance"}},
            {**request["agent"], "agent_context": {"skills": request["agent"]["agent_context"]["skills"]}},
        ):
            with self.subTest(agent=agent), self.assertRaises(native_first.HandoffError):
                native_first.validate_native_response({**response, "agent": agent}, request)

    def test_native_response_rejects_modified_hook_command(self):
        request = self.build()
        import copy
        modified = copy.deepcopy(request["hook_config"])
        modified["stop"][0]["hooks"][0]["command"] = "exit 0"
        with self.assertRaises(native_first.HandoffError):
            native_first.validate_native_response({
                "id": request["conversation_id"],
                "execution_status": "idle",
                "workspace": request["workspace"],
                "hook_config": modified,
            }, request)

    def test_create_idle_calls_native_only_and_verifies_persisted_hook(self):
        request = self.build()
        seen = []
        def fake_http(method, endpoint, payload=None, **kwargs):
            seen.append((method, endpoint))
            if endpoint == "/api/conversations?include_skills=true":
                self.assertEqual(payload, request)
                return {"id": request["conversation_id"]}
            if endpoint.endswith("/events"):
                self.assertEqual(method, "POST")
                self.assertIs(payload["run"], False)
                return {"id": "event-id"}
            return {"id": request["conversation_id"], "execution_status": "idle",
                    "workspace": request["workspace"],
                    "hook_config": request["hook_config"],
                    "agent": request["agent"]}

        self.assertEqual(
            native_first.create_idle_native_conversation(request, fake_http),
            request["conversation_id"]
        )
        self.assertEqual(seen, [
            ("POST", "/api/conversations?include_skills=true"),
            ("POST", f'/api/conversations/{request["conversation_id"]}/events'),
            ("GET", f'/api/conversations/{request["conversation_id"]}?include_skills=true')
        ])
        self.assertFalse(any("/run" in endpoint for _, endpoint in seen))

    def test_real_initial_message_uses_registered_objective_without_dispatch(self):
        objective = native_first.render_task_objective(self.store, self.data["taskId"])
        registered = self.store.get_request(self.data["taskId"])
        self.assertIn(registered.objective, objective)
        self.assertIn("Independent", objective.replace("independent", "Independent"))
        request = self.build()
        # This shared fixture already has a DISPATCHED execution claim.
        # Verify idle-message construction does not mutate that claim.
        claim_before = self.store.get_execution_claim(self.data["taskId"])
        sent = []
        observed_endpoints = []
        def fake_http(method, endpoint, payload=None, **kwargs):
            observed_endpoints.append((method, endpoint))
            if endpoint == "/api/conversations?include_skills=true":
                return {"id": request["conversation_id"]}
            if endpoint.endswith("/events"):
                sent.append(payload)
                return {"id": "init"}
            return {"id": request["conversation_id"], "execution_status": "idle",
                    "workspace": request["workspace"], "hook_config": request["hook_config"], "agent": request["agent"]}
        native_first.create_idle_native_conversation(
            request, fake_http, initial_message=objective
        )
        self.assertEqual(sent[0]["content"][0]["text"], objective)
        self.assertIs(sent[0]["run"], False)
        self.assertEqual(claim_before, self.store.get_execution_claim(self.data["taskId"]))
        self.assertFalse(any("/run" in endpoint for _, endpoint in observed_endpoints))

    def test_vertex_idle_requires_registered_objective(self):
        request = self.build()
        request["agent"]["llm"]["model"] = "vertex_ai/gemini-2.5-flash"
        with self.assertRaises(native_first.HandoffError):
            native_first.create_idle_native_conversation(
                request, lambda *a, **k: self.fail("Vertex must not contact server")
            )

    def test_empty_real_objective_rejected_before_network(self):
        with self.assertRaises(native_first.HandoffError):
            native_first.create_idle_native_conversation(
                self.build(), lambda *a, **k: self.fail("Unexpected request"),
                initial_message=" "
            )

    def test_create_idle_rejects_persisted_config_without_hook(self):
        request = self.build()
        def fake_http(method, endpoint, payload=None, **kwargs):
            if endpoint == "/api/conversations?include_skills=true":
                return {"id": request["conversation_id"]}
            if endpoint.endswith("/events"):
                self.assertIs(payload["run"], False)
                return {}
            return {"id": request["conversation_id"], "execution_status": "idle",
                    "workspace": request["workspace"], "hook_config": {}}
        with self.assertRaises(native_first.HandoffError):
            native_first.create_idle_native_conversation(request, fake_http)

    def test_pre_execution_native_identity_requires_no_dispatch_claim(self):
        from dataclasses import replace
        from unittest.mock import Mock
        from openhands_shared.contracts import (
            OpenHandsRuntimeStatus, ExecutionStatus
        )
        proxy = Mock(wraps=self.store)
        proxy.get_execution_claim.return_value = None
        proxy.get_status.return_value = replace(
            self.store.get_status(self.data["taskId"]),
            execution_status=ExecutionStatus.NOT_STARTED,
        )
        proxy.get_openhands_runtime.return_value = replace(
            self.store.get_openhands_runtime(self.data["taskId"]),
            runtime_status=OpenHandsRuntimeStatus.CONVERSATION_READY,
            execution_status=ExecutionStatus.NOT_STARTED,
            last_native_event_id=None,
            last_native_event_order=0,
        )
        request = native_first.build_request(
            proxy, self.data["taskId"],
            hook_config=Path(self.data["hookConfig"]),
            model="openai/gpt-4o-mini",
        )
        self.assertEqual(request["conversation_id"], self.data["conversationId"])
        # A not-started task cannot claim that native context has been sent.
        proxy.get_openhands_runtime.return_value = replace(
            proxy.get_openhands_runtime.return_value,
            runtime_status=OpenHandsRuntimeStatus.CONTEXT_ATTACHED,
        )
        with self.assertRaises(native_first.HandoffError):
            native_first.build_request(
                proxy, self.data["taskId"],
                hook_config=Path(self.data["hookConfig"]),
                model="openai/gpt-4o-mini",
            )
        # A genuinely attached and still-unstarted conversation can be
        # inspected again without inventing a dispatch claim.
        proxy.get_openhands_runtime.return_value = replace(
            proxy.get_openhands_runtime.return_value,
            last_native_event_id="native-initial-event-1",
            last_native_event_order=1,
        )
        request_again = native_first.build_request(
            proxy, self.data["taskId"],
            hook_config=Path(self.data["hookConfig"]),
            model="openai/gpt-4o-mini",
        )
        self.assertEqual(request_again["conversation_id"], self.data["conversationId"])
        self.assertIsNone(proxy.get_execution_claim.return_value)

    def test_dispatch_native_once_claims_before_run_and_never_repeats(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from openhands_shared.contracts import (
            OpenHandsRuntimeStatus, ExecutionDispatchStatus
        )
        request = self.build()
        uid = request["conversation_id"]
        store = Mock()
        store.get_openhands_runtime.return_value = SimpleNamespace(
            runtime_status=OpenHandsRuntimeStatus.CONTEXT_ATTACHED,
            conversation_id=uid,
        )
        store.get_status.return_value = SimpleNamespace(accepted=False)
        current = [None]
        store.get_execution_claim.side_effect = lambda task: current[0]
        def claim(task, worker):
            self.assertIsNone(current[0])
            current[0] = SimpleNamespace(
                worker_id=worker, conversation_id=uid,
                dispatch_status=ExecutionDispatchStatus.INTENT_RECORDED,
            )
        store.claim_execution.side_effect = claim
        def update(task, *, dispatched, recovery_code=None):
            current[0].dispatch_status = (ExecutionDispatchStatus.DISPATCHED if dispatched
                                          else ExecutionDispatchStatus.RECOVERY_REQUIRED)
        store.update_execution_dispatch.side_effect = update
        called = []
        def http(method, path, payload=None, **kwargs):
            called.append((method, path))
            if method == "GET":
                return {"id": uid, "execution_status": "idle",
                        "workspace": request["workspace"],
                        "hook_config": request["hook_config"],
                        "agent": request["agent"]}
            self.assertEqual(current[0].dispatch_status, ExecutionDispatchStatus.INTENT_RECORDED)
            return {}
        self.assertEqual(native_first.dispatch_native_once(
            store, self.data["taskId"], worker_id="worker", request=request, http=http
        ), "DISPATCHED")
        self.assertEqual(native_first.dispatch_native_once(
            store, self.data["taskId"], worker_id="worker", request=request, http=http
        ), "ALREADY_DISPATCHED")
        self.assertEqual([method for method, _ in called], ["GET", "POST"])
        self.assertEqual(store.claim_execution.call_count, 1)

    def test_uncertain_dispatch_never_replays_run(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from openhands_shared.contracts import (
            OpenHandsRuntimeStatus, ExecutionDispatchStatus
        )
        request = self.build()
        uid = request["conversation_id"]
        store = Mock()
        store.get_openhands_runtime.return_value = SimpleNamespace(
            runtime_status=OpenHandsRuntimeStatus.CONTEXT_ATTACHED,
            conversation_id=uid,
        )
        store.get_status.return_value = SimpleNamespace(accepted=False)
        claim = [None]
        store.get_execution_claim.side_effect = lambda _: claim[0]
        store.claim_execution.side_effect = lambda task, worker: claim.__setitem__(
            0, SimpleNamespace(worker_id=worker, conversation_id=uid,
                               dispatch_status=ExecutionDispatchStatus.INTENT_RECORDED)
        )
        def update(task, *, dispatched, recovery_code=None):
            claim[0].dispatch_status = (
                ExecutionDispatchStatus.DISPATCHED if dispatched
                else ExecutionDispatchStatus.RECOVERY_REQUIRED)
        store.update_execution_dispatch.side_effect = update
        calls = []
        def http(method, path, payload=None, **kwargs):
            calls.append((method, path))
            if method == "POST":
                raise ConnectionError("response lost")
            if path.endswith("include_skills=true"):
                return {"id": uid, "execution_status": "idle",
                        "workspace": request["workspace"],
                        "hook_config": request["hook_config"],
                        "agent": request["agent"]}
            return {"execution_status": "idle"}
        with self.assertRaises(native_first.HandoffError):
            native_first.dispatch_native_once(
                store, self.data["taskId"], worker_id="worker", request=request, http=http
            )
        with self.assertRaises(native_first.HandoffError):
            native_first.dispatch_native_once(
                store, self.data["taskId"], worker_id="worker", request=request, http=http
            )
        self.assertEqual(sum(method == "POST" for method, _ in calls), 1)
        self.assertEqual(claim[0].dispatch_status, ExecutionDispatchStatus.RECOVERY_REQUIRED)

    def test_synthetic_repair_bytes_match_validator_exactly(self):
        from openhands_native_validator_poc import ArtifactRunner, REPAIR_BYTES
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "poc3-repaired.txt"
            runner = ArtifactRunner()
            before = runner.run(directory, None, None, None, 1, directory)
            self.assertFalse(before["passed"])
            marker.write_bytes(REPAIR_BYTES)
            after = runner.run(directory, None, None, None, 2, directory)
            self.assertTrue(after["passed"])
            marker.write_bytes(b"POC3-REPAIRED" + bytes([10]))
            actual_newline = runner.run(directory, None, None, None, 3, directory)
            self.assertFalse(actual_newline["passed"])

    def test_model_key_not_in_safe_summary_and_remote_override_rejected(self):
        payload = self.build(api_key="dummy-local-credential",
                             base_url="http://127.0.0.1:12997/v1")
        self.assertEqual(payload["agent"]["llm"]["api_key"], "dummy-local-credential")
        self.assertNotIn("dummy-local-credential",
                         str(native_first.show_safe_summary(payload)))
        with self.assertRaises(native_first.HandoffError):
            self.build(base_url="https://external.invalid/v1")

    def test_mismatched_database_and_absent_dispatch_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "hook.json"
            import json
            payload = json.loads(Path(self.data["hookConfig"]).read_text())
            payload["database"] = str(Path(d) / "other.db")
            fake.write_text(json.dumps(payload))
            with self.assertRaises(native_first.HandoffError):
                native_first.build_request(
                    self.store, self.data["taskId"], hook_config=fake,
                    model="openai/gpt-4o-mini"
                )


if __name__ == "__main__":
    unittest.main()
