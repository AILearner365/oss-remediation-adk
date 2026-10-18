"""Offline validation-service bridge contract; no OpenHands, model or scanner."""
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_validator_poc as poc
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.validation import SharedValidationService


class NativeValidationBridgeTests(unittest.TestCase):
    def test_fixture_repair_waits_for_native_denial_and_one_durable_failure(self):
        from unittest.mock import patch
        old = poc.STATE
        with tempfile.TemporaryDirectory() as d:
            poc.STATE = Path(d) / "case"
            poc.STATE.mkdir()
            task_root = None
            try:
                data = poc.fixture_setup()
                task_root = Path(data["database"]).parents[1]
                uid = data["conversationId"]
                target = Path(data["workspace"]) / "poc3-repaired.txt"
                # No native feedback -> cannot repair.
                poc.repair_after_denial(data, [{"role": "user", "content": "start"}], uid)
                self.assertFalse(target.exists())
                # Feedback without native hook event is rejected.
                with patch.object(poc, "collect_events", return_value=[]):
                    with self.assertRaises(poc.native.Failure):
                        poc.repair_after_denial(data, [{"content": poc.MARKER}], uid)
                self.assertFalse(target.exists())
                # Native DENY alone is insufficient without a completed attempt.
                events = [{"kind": "HookExecutionEvent", "hook_event_type": "Stop",
                           "blocked": True, "exit_code": 2}]
                with patch.object(poc, "collect_events", return_value=events):
                    with self.assertRaises(poc.native.Failure):
                        poc.repair_after_denial(data, [{"content": poc.MARKER}], uid)
                self.assertFalse(target.exists())
                with patch("sys.stdin", io.StringIO('{"event_type":"Stop"}')):
                    with patch("sys.stdout", new_callable=io.StringIO):
                        self.assertEqual(poc.native_hook(), 2)
                with patch.object(poc, "collect_events", return_value=events):
                    poc.repair_after_denial(data, [{"content": poc.MARKER}], uid)
                self.assertTrue(target.is_file())
                checkpoint = poc.read_json(poc.STATE / "repair-checkpoint.json")
                self.assertEqual(checkpoint["priorValidationAttempts"], 1)
            finally:
                poc.STATE = old
                if task_root and task_root.is_dir():
                    shutil.rmtree(task_root, ignore_errors=True)

    def test_real_service_denies_until_repo_state_changes(self):
        old = poc.STATE
        with tempfile.TemporaryDirectory() as d:
            poc.STATE = Path(d) / "case"
            poc.STATE.mkdir()
            task_root = None
            try:
                data = poc.fixture_setup()
                task_root = Path(data["database"]).parents[1]
                with patch("sys.stdin", io.StringIO('{"event_type":"Stop"}')):
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        first_code = poc.native_hook()
                self.assertEqual(first_code, 2)
                self.assertEqual(json.loads(stdout.getvalue())["decision"], "deny")
                Path(data["workspace"], "poc3-repaired.txt").write_bytes(b"POC3-REPAIRED\\n")
                with patch("sys.stdin", io.StringIO('{"event_type":"Stop"}')):
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        second_code = poc.native_hook()
                self.assertEqual(second_code, 0)
                self.assertEqual(json.loads(stdout.getvalue())["decision"], "allow")
                db, config = load_stop_hook_config(Path(data["hookConfig"]))
                store = SQLiteTaskStore(db)
                try:
                    attempts = store.list_validation_attempts(data["taskId"])
                    self.assertEqual(len(attempts), 2)
                    self.assertNotEqual(attempts[0].outcome.value, "PASS")
                    self.assertEqual(attempts[1].outcome.value, "PASS")
                    self.assertTrue(store.get_status(data["taskId"]).accepted)
                    self.assertTrue(SharedValidationService(
                        store, config, runner=poc.ArtifactRunner()
                    ).verify_validated_state(data["taskId"]))
                    Path(data["workspace"], "poc3-repaired.txt").write_bytes(b"TAMPER")
                    self.assertFalse(SharedValidationService(
                        store, config, runner=poc.ArtifactRunner()
                    ).verify_validated_state(data["taskId"]))
                finally:
                    store.close()
            finally:
                poc.STATE = old
                if task_root and task_root.is_dir():
                    shutil.rmtree(task_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
