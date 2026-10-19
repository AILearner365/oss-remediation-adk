import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_app_task_resume as subject

class ResumeSafetyTests(unittest.TestCase):
    def test_missing_database_never_registers(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(subject, "SQLiteTaskStore", side_effect=AssertionError("created task store")):
                with self.assertRaisesRegex(ValueError, "database or scanner unavailable"):
                    subject.resume(Path(d), Path(__file__))

    def test_missing_run_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                subject.resume(Path(d) / "nonexistent", Path(__file__))

if __name__ == "__main__":
    unittest.main()
