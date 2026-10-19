import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_app_task_prepare as prep

class RealTaskRegistrationSafetyTests(unittest.TestCase):
    def test_missing_source_refuses_all_registration(self):
        with tempfile.TemporaryDirectory() as d:
            scanner = Path(d) / "scanner"
            scanner.write_text("stub")
            with self.assertRaises(ValueError):
                prep.prepare(Path(d) / "missing-source", scanner, Path(d) / "new-task")
            self.assertFalse((Path(d) / "new-task").exists())

    def test_existing_run_root_blocks_before_source_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, scanner = root / "source", root / "scanner"
            source.mkdir()
            scanner.write_text("stub")
            with patch.object(prep, "git", side_effect=AssertionError("git must not run")):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    prep.prepare(source, scanner, root)
                
    def test_real_target_uses_explicit_approval_identity(self):
        self.assertEqual(prep.REPO_ID, "https://github.com/AILearner365/maven-multimodule-app.git")
        self.assertEqual(prep.MODEL, "vertex_ai/gemini-2.5-flash")

if __name__ == "__main__":
    unittest.main()
