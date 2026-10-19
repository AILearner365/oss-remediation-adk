"""Offline test of bounded native observation with no model dispatch."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_workflow as workflow


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hook = Path(self.tmp.name) / "hook.json"
        self.hook.write_text("{}", encoding="utf-8")

    def test_finished_calls_finalize_once_without_dispatch(self):
        store = MagicMock()
        store.get_openhands_runtime.return_value = SimpleNamespace(conversation_id="conv-1")
        store.get_execution_claim.return_value = SimpleNamespace(conversation_id="conv-1")
        cm = MagicMock()
        cm.__enter__.return_value = store
        with patch.object(workflow, "load_dummy_unused", create=True), \
             patch("openhands_shared.stop_hook.load_stop_hook_config", return_value=(Path(self.tmp.name) / "db", object())), \
             patch.object(workflow, "SQLiteTaskStore", return_value=cm), \
             patch.object(workflow.native, "http", return_value={"execution_status": "finished"}), \
             patch.object(workflow, "finalize", return_value={"status": "FINALIZED_VERIFIED_ACCEPTED"}) as finalize:
            result = workflow.monitor_finalize("task-1", self.hook, 0, 1)
        self.assertEqual(result["status"], "FINALIZED_VERIFIED_ACCEPTED")
        finalize.assert_called_once_with("task-1", self.hook)

    def test_unclaimed_run_cannot_poll_or_finalize(self):
        store = MagicMock()
        store.get_openhands_runtime.return_value = None
        store.get_execution_claim.return_value = None
        cm = MagicMock()
        cm.__enter__.return_value = store
        with patch("openhands_shared.stop_hook.load_stop_hook_config", return_value=(Path(self.tmp.name) / "db", object())), \
             patch.object(workflow, "SQLiteTaskStore", return_value=cm), \
             patch.object(workflow.native, "http") as http, \
             patch.object(workflow, "finalize") as finalize:
            with self.assertRaisesRegex(ValueError, "claimed native"):
                workflow.monitor_finalize("task-1", self.hook, 0, 1)
            http.assert_not_called()
            finalize.assert_not_called()

    def test_nonterminal_timeout_never_finalizes(self):
        store = MagicMock()
        store.get_openhands_runtime.return_value = SimpleNamespace(conversation_id="conv-1")
        store.get_execution_claim.return_value = SimpleNamespace(conversation_id="conv-1")
        cm = MagicMock()
        cm.__enter__.return_value = store
        with patch("openhands_shared.stop_hook.load_stop_hook_config", return_value=(Path(self.tmp.name) / "db", object())), \
             patch.object(workflow, "SQLiteTaskStore", return_value=cm), \
             patch.object(workflow.native, "http", return_value={"execution_status": "running"}), \
             patch.object(workflow, "finalize") as finalize:
            result = workflow.monitor_finalize("task-1", self.hook, 0, 1)
            self.assertEqual(result["status"], "MONITOR_TIMEOUT_NO_DISPATCH")
            finalize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
