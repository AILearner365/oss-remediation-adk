"""Offline guards around the real idle-only OpenHands attachment workflow."""
import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_native_idle as step


class RealIdleGuards(unittest.TestCase):
    def test_readonly_mode_never_touches_native_transport(self):
        source = inspect.getsource(step.inspect)
        self.assertNotIn("native.http", source)
        self.assertNotIn("attach_idle(", source)
        self.assertIn("verify_stored(", source)

    def test_attach_mode_keeps_run_forbidden(self):
        source = inspect.getsource(step.attach_idle)
        self.assertIn("create_idle_native_conversation", source)
        self.assertIn("render_task_objective", source)
        self.assertIn("validate_native_response", source)
        self.assertIn("link_openhands_event", source)
        self.assertNotIn('"/run"', source)
        self.assertNotIn("dispatch_native_once(", source)
        self.assertNotIn("native.launch(", source)

    def test_missing_store_never_calls_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            from openhands_shared.store import SQLiteTaskStore
            from openhands_shared.store import TaskNotFoundError
            with SQLiteTaskStore(Path(tmp) / "missing.sqlite3") as store:
                with patch.object(step.native, "http", side_effect=AssertionError("No transport allowed")):
                    with self.assertRaises(TaskNotFoundError):
                        step.inspect(store, "task_unregistered", Path(tmp) / "hook.json")

if __name__ == "__main__":
    unittest.main()
