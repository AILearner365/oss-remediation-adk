import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import openhands_real_app_baseline as baseline

class BaselineSafetyTests(unittest.TestCase):
    def test_bad_commit_no_process(self):
        with patch.object(baseline, 'run_git', side_effect=AssertionError('git called')):
            with self.assertRaisesRegex(ValueError, '40-character'):
                baseline.baseline(Path('/tmp/nonexistent'), 'main', Path('/tmp/output'), 'osv-scanner')

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(baseline, 'run_git', side_effect=AssertionError('git called')):
                with self.assertRaises(ValueError):
                    baseline.baseline(Path(directory), 'a'*40, Path(directory), 'osv-scanner')

if __name__ == '__main__':
    unittest.main()
