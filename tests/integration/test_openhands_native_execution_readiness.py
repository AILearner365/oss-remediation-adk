"""Read-only execution-readiness audit contract tests; no server, no model."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from inspect import getsource

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_execution_readiness as ready


class ReadinessAuditTests(unittest.TestCase):
    def test_absent_environment_does_not_claim_vertex_available(self):
        with tempfile.TemporaryDirectory() as td:
            versions = ready.package_versions_from_site_packages(Path(td))
            self.assertTrue(all(value is None for value in versions.values()))

    def test_venv_discovery_fails_closed_without_server(self):
        with tempfile.TemporaryDirectory() as td:
            path, reason = ready.find_running_server_site_packages(Path(td))
            self.assertIsNone(path)
            self.assertEqual(reason, "PROCESS_ENVIRONMENT_NOT_IDENTIFIED")

    def test_inspection_requires_registered_task_without_native_calls(self):
        with tempfile.TemporaryDirectory() as td:
            from openhands_shared.store import SQLiteTaskStore, TaskNotFoundError
            with SQLiteTaskStore(Path(td) / "task.sqlite3") as store:
                with patch.object(ready.native, "http", side_effect=AssertionError("network forbidden")):
                    with self.assertRaises(TaskNotFoundError):
                        ready.inspect_task(store, "task_absent", Path(td) / "hook.json")

    def test_audit_is_explicitly_unapproved_and_has_no_run_path(self):
        body = getsource(ready.audit)
        self.assertIn('"executionAuthorization": False', body)
        self.assertIn('"hardStopAtSpendLimitProven": False', body)
        self.assertIn('handoff.validate_native_response', body)
        self.assertNotIn('dispatch_native_once(', body)
        self.assertNotIn('claim_execution(', body)
        self.assertNotIn('"/run"', body)


if __name__ == "__main__":
    unittest.main()
