"""No-model, no-live-claim guards for independent validator probe."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from inspect import getsource

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_validator_probe as probe


class ValidatorProbeGuards(unittest.TestCase):
    def test_no_implicit_live_dispatch_or_stop_hook(self):
        source = getsource(probe.probe)
        self.assertIn("ExistingDeterministicValidationRunner().run(", source)
        self.assertIn("TemporaryDirectory(", source)
        self.assertIn("get_execution_claim(task_id)", source)
        self.assertNotIn("claim_execution(", source)
        self.assertNotIn("handle_stop(", source)
        self.assertNotIn("native.http(", source)
        self.assertNotIn("dispatch_native_once(", source)

    def test_unknown_task_fails_before_validator(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(probe, "ExistingDeterministicValidationRunner") as runner:
                from openhands_shared.store import TaskNotFoundError
                with self.assertRaises(TaskNotFoundError):
                    probe.probe(Path(td) / "tasks.sqlite3", "task_unknown", Path(td) / "hook.json")
                runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
