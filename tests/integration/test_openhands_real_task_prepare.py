"""Offline fail-closed checks for real durable task preparation."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_task_prepare as setup


class DurablePreparationTests(unittest.TestCase):
    def test_missing_source_rejected_without_creating_run_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(FileNotFoundError):
                setup.prepare(root / "not-present", root / "scanner", root / "run")
            self.assertFalse((root / "run").exists())

    def test_refuses_existing_run_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            scanner = root / "scanner"
            scanner.write_bytes(b"mock")
            state = root / "run"
            state.mkdir()
            with self.assertRaises(ValueError):
                setup.prepare(source, scanner, state)

    def test_local_only_target_ignore_is_narrow(self):
        from inspect import getsource
        source = getsource(setup.prepare)
        self.assertIn('local_source / ".git" / "info" / "exclude"', source)
        self.assertIn('target/\\n', source)
        self.assertNotIn('status.showUntrackedFiles', source)
        self.assertNotIn('git add', source)
        self.assertNotIn('git commit', source)

    def test_no_agent_execution_or_known_fix_in_objective(self):
        from inspect import getsource
        source = getsource(setup)
        assert "ExistingDeterministicBaselineRunner" not in source  # assessor uses default
        self.assertIn("DeterministicBaselineAssessor(", source)
        self.assertIn("SharedIntelligenceAssessor(", source)
        self.assertIn("load_stop_hook_config(", source)
        self.assertNotIn("dispatch_native_once(", source)
        self.assertNotIn("native.http(", source)
        self.assertNotIn("snakeyaml:2.0", source)
        self.assertIn('"modelExecutionAuthorized": False', source)

if __name__ == "__main__":
    unittest.main()
