"""Offline safety tests for the commit-pinned real-app checkout."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_app_prepare as target


class RealAppPreparationTests(unittest.TestCase):
    def test_rejects_unpinned_checkout_without_network(self):
        with patch.object(target, "run_git", side_effect=AssertionError("git executed")):
            with self.assertRaisesRegex(ValueError, "40-character"):
                target.prepare(Path("/tmp/example"), "main-runrunning")

    def test_existing_destination_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(target, "run_git", side_effect=AssertionError("git executed")):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    target.prepare(Path(directory), "a" * 40)

    def test_moved_remote_branch_prevents_clone(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "isolated"
            with patch.object(target, "run_git", return_value="b" * 40 + "\trefs/heads/main-runrunning") as git:
                with self.assertRaisesRegex(ValueError, "moved"):
                    target.prepare(destination, "a" * 40)
                git.assert_called_once()
                self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
