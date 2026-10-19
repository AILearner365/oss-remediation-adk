"""Fail-closed tests of native task finalization without running model/tools."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_finalize as mod


class FinalizeSafetyTests(unittest.TestCase):
    def test_nonterminal_native_does_not_validate_or_reconcile(self):
        store = MagicMock()
        store.get_openhands_runtime.return_value = SimpleNamespace(conversation_id="native-one")
        store.get_execution_claim.return_value = SimpleNamespace(conversation_id="native-one")
        context = MagicMock()
        context.__enter__.return_value = store
        with patch.object(mod, "load_stop_hook_config", return_value=(Path("/tmp/tasks.sqlite3"), object())), \
             patch.object(mod, "SQLiteTaskStore", return_value=context), \
             patch.object(mod.native, "http", return_value={"execution_status": "running"}), \
             patch.object(mod, "SharedValidationService") as service:
            with self.assertRaisesRegex(ValueError, "not finished"):
                mod.finalize("task-one", Path("/tmp/hook.json"))
            service.assert_not_called()
            store.record_native_execution_terminal.assert_not_called()

    def test_unclaimed_native_conversation_not_accepted(self):
        store = MagicMock()
        store.get_openhands_runtime.return_value = None
        store.get_execution_claim.return_value = None
        context = MagicMock()
        context.__enter__.return_value = store
        with patch.object(mod, "load_stop_hook_config", return_value=(Path("/tmp/tasks.sqlite3"), object())), \
             patch.object(mod, "SQLiteTaskStore", return_value=context), \
             patch.object(mod.native, "http") as api:
            with self.assertRaisesRegex(ValueError, "not bound"):
                mod.finalize("task-one", Path("/tmp/hook.json"))
            api.assert_not_called()

    def test_no_dispatch_or_retry_mechanism(self):
        from inspect import getsource
        source = getsource(mod)
        self.assertNotIn("dispatch_native_once", source)
        self.assertNotIn("claim_execution(", source)
        self.assertNotIn('native.http("POST"', source)
        self.assertIn("verify_validated_state", source)
        self.assertIn("record_native_execution_terminal", source)


if __name__ == "__main__":
    unittest.main()
