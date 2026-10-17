"""Offline tests for the read-only task-to-Canvas smoke checker."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "shared_task_canvas_smoke.py"
SPEC = importlib.util.spec_from_file_location("shared_task_canvas_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
TASK_ID = "task_" + "a" * 32
CONVERSATION_ID = "20268fdb-0145-4321-86a8-d59d720bf105"


def fake_get(base, path):
    if path == "/v1/tasks/" + TASK_ID:
        return {
            "taskId": TASK_ID,
            "status": "AGENT_RUNNING",
            "openhands": {
                "conversationId": CONVERSATION_ID,
                "executionStatus": "NOT_STARTED",
            },
            "validation": {"accepted": False},
        }
    if path == "/v1/tasks/" + TASK_ID + "/events":
        return {"taskId": TASK_ID, "events": [{"type": "task.registered"}]}
    if "/events/search" in path:
        return {"items": [{"id": "native_event_1"}], "next_page_id": None}
    if "/api/conversations/" in path:
        return {
            "id": CONVERSATION_ID,
            "execution_status": "idle",
            "hook_config": {"stop": [{"hooks": [{"type": "command"}]}]},
        }
    raise AssertionError("Unexpected GET: " + path)


class TaskCanvasSmokeTests(unittest.TestCase):
    def run_check(self, get=fake_get):
        with patch.object(smoke, "get_json", side_effect=get):
            return smoke.check("http://127.0.0.1:8080", "http://127.0.0.1:8000", "http://127.0.0.1:3000", TASK_ID)

    def test_read_only_mapping(self):
        result = self.run_check()
        self.assertEqual("API_MAPPING_PASSED__CANVAS_BROWSER_NOT_PROVEN", result["verdict"])
        self.assertEqual(CONVERSATION_ID, result["nativeConversationId"])
        self.assertEqual(1, result["nativeEventCount"])
        self.assertTrue(result["canvasUrl"].endswith("/conversations/" + CONVERSATION_ID))

    def test_pending_hook_is_rejected(self):
        def missing_hook(base, path):
            data = fake_get(base, path)
            if "/api/conversations/" in path and "/events/search" not in path:
                data["hook_config"] = None
            return data
        with self.assertRaisesRegex(smoke.SmokeFailure, "Stop Hook"):
            self.run_check(missing_hook)

    def test_running_native_conversation_is_rejected(self):
        def active(base, path):
            data = fake_get(base, path)
            if "/api/conversations/" in path and "/events/search" not in path:
                data["execution_status"] = "running"
            return data
        with self.assertRaisesRegex(smoke.SmokeFailure, "idle"):
            self.run_check(active)

    def test_no_product_acceptance_without_validation(self):
        def accepted(base, path):
            data = fake_get(base, path)
            if path == "/v1/tasks/" + TASK_ID:
                data["validation"]["accepted"] = True
            return data
        with self.assertRaisesRegex(smoke.SmokeFailure, "not be accepted"):
            self.run_check(accepted)

    def test_absent_native_events_is_rejected(self):
        def missing_events(base, path):
            data = fake_get(base, path)
            if "/events/search" in path:
                data["items"] = []
            return data
        with self.assertRaisesRegex(smoke.SmokeFailure, "no native events"):
            self.run_check(missing_events)

    def test_invalid_task_id_never_calls_network(self):
        with patch.object(smoke, "get_json", side_effect=AssertionError("network called")):
            with self.assertRaisesRegex(smoke.SmokeFailure, "task-id"):
                smoke.check("http://localhost:1", "http://localhost:2", "http://localhost:3", "unsafe/path")


if __name__ == "__main__":
    unittest.main()
