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
        self.old = fixture_support.STATE
        self.temp = tempfile.TemporaryDirectory()
        fixture_support.STATE = Path(self.temp.name) / "fixture"
        fixture_support.STATE.mkdir()
        self.data = fixture_support.fixture_setup()
        self.task_root = Path(self.data["database"]).parents[1]
        self.store = SQLiteTaskStore(Path(self.data["database"]))

    def tearDown(self):
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
        self.assertIn("-m openhands_shared.stop_hook",
                      request["hook_config"]["stop"][0]["hooks"][0]["command"])
        self.assertNotIn("api_key", request["agent"]["llm"])
        self.assertNotIn("base_url", request["agent"]["llm"])
        self.assertNotIn("api_key", native_first.show_safe_summary(request))

    def test_native_response_rejects_missing_hook_wrong_workspace_or_id(self):
        request = self.build()
        response = {
            "id": request["conversation_id"], "execution_status": "idle",
            "workspace": request["workspace"], "hook_config": request["hook_config"],
        }
        self.assertEqual(native_first.validate_native_response(response, request),
                         self.data["conversationId"])
        for key, val in (
            ("id", "wrong"), ("execution_status", "finished"),
            ("workspace", {"working_dir": "/tmp/foreign"}),
            ("hook_config", {})
        ):
            corrupt = {**response, key: val}
            with self.subTest(key=key), self.assertRaises(native_first.HandoffError):
                native_first.validate_native_response(corrupt, request)

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
