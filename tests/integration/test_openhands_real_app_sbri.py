import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import openhands_real_app_sbri as target

class SbriReadinessTests(unittest.TestCase):
    def test_bad_commit_never_runs_collector(self):
        with patch.object(target, 'run_pre_edit_intelligence', side_effect=AssertionError('collector called')):
            with self.assertRaisesRegex(ValueError, 'Exact source commit'):
                target.assess(Path('/tmp/no'), Path('/tmp/no'), Path('/tmp/no'), Path('/tmp/no'),
                              'main-runrunning', Path('/tmp/no'), None, None, 6)

    def test_existing_output_never_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(target, 'run_pre_edit_intelligence', side_effect=AssertionError('collector called')):
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    target.assess(Path(d), Path(d), Path(d), Path(d), 'a'*40, Path(d), None, None, 6)

if __name__ == '__main__':
    unittest.main()
