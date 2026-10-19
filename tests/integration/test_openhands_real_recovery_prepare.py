"""Offline safety assertions for baseline-reuse recovery (no paid calls)."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_recovery_prepare as recovery


class RecoveryTests(unittest.TestCase):
    def test_absent_original_blocks_before_registration(self):
        from unittest.mock import Mock
        fake = Mock()
        fake.get_openhands_runtime.return_value = None
        fake.get_execution_claim.return_value = None
        with self.assertRaisesRegex(ValueError, "not the dispatched"):
            recovery.prepare_recovery(fake, "task_absent", Path("/tmp/not-present"))
        fake.register_task.assert_not_called()

    def test_never_runs_scanner_model_or_mutates_original(self):
        from inspect import getsource
        body = getsource(recovery.prepare_recovery)
        self.assertNotIn("subprocess.run([\"mvn\"", body)
        self.assertNotIn("osv-scanner", body)
        self.assertNotIn("native.http", body)
        self.assertNotIn("dispatch_native_once", body)
        self.assertNotIn("claim_execution(", body)
        self.assertNotIn("update_execution_dispatch(", body)
        self.assertIn('new_contract["metadata"]["correlationId"] = original', body)
        self.assertIn("verify_stored(store, new_id, hook)", body)
        self.assertNotIn("verify_stored(store, original, hook)", body)
        self.assertIn("Original baseline target advisory is not verified", body)
        self.assertIn("baselineReexecuted", getsource(recovery))


if __name__ == "__main__":
    unittest.main()
