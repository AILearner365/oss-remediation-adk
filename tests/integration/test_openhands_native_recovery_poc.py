"""Offline interrupted validation recovery, real store and existing service."""
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_recovery_poc as recovery
import openhands_native_validator_poc as bridge
from openhands_shared.store import SQLiteTaskStore


class RecoveryOfflineTests(unittest.TestCase):
    def test_interrupted_attempt_without_report_cannot_accept(self):
        old = (recovery.STATE, bridge.STATE)
        with tempfile.TemporaryDirectory() as d:
            recovery.STATE = bridge.STATE = Path(d) / "case"
            recovery.STATE.mkdir()
            task_root = None
            try:
                data = bridge.fixture_setup()
                task_root = Path(data["database"]).parents[1]
                with patch("sys.stdin", io.StringIO('{"event_type":"Stop"}')):
                    with self.assertRaises(SystemExit) as interrupted:
                        recovery.hook()
                self.assertEqual(interrupted.exception.code, 37)
                before = recovery.status_snapshot(data)
                self.assertFalse(before["accepted"])
                self.assertEqual([(x["state"], x["outcome"]) for x in before["attempts"]],
                                 [("RUNNING", None)])
                with patch("sys.stdin", io.StringIO('{"event_type":"Stop"}')):
                    with patch("sys.stdout", new_callable=io.StringIO) as output:
                        result = recovery.hook()
                self.assertEqual(result, 0)
                self.assertEqual(__import__("json").loads(output.getvalue())["decision"], "allow")
                after = recovery.status_snapshot(data)
                self.assertFalse(after["accepted"])
                self.assertEqual(len(after["attempts"]), 1)
                self.assertEqual(after["attempts"][0]["state"], "COMPLETED")
                self.assertEqual(after["attempts"][0]["outcome"], "VALIDATOR_FAILURE")
                self.assertFalse((recovery.STATE / "validator-invoked.json").exists())
                self.assertEqual({x["conversationId"] for x in after["attempts"]},
                                 {data["conversationId"]})
            finally:
                recovery.STATE, bridge.STATE = old
                if task_root and task_root.is_dir():
                    shutil.rmtree(task_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
