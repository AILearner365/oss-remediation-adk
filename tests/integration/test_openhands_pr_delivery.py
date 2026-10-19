import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import openhands_pr_delivery as delivery
import openhands_cloud_shell_doctor as doctor

class TestDelivery(unittest.TestCase):
    def test_no_remote_call_without_approval(self):
        with patch.object(delivery, 'request_github', side_effect=AssertionError('network')):
            with self.assertRaises(ValueError):
                delivery.deliver({'status': 'READY_FOR_EXPLICIT_PR_APPROVAL', 'repository': delivery.REPO}, '', '')

    def test_reject_bad_task_identity(self):
        with self.assertRaises(ValueError):
            delivery.plan('not-a-task', Path('/tmp/none'), expected_base='abc')

    def test_archive_missing(self):
        self.assertEqual(doctor.check_archive(Path('/tmp/no-such-archive')).get('status'), 'MISSING')

if __name__ == '__main__':
    unittest.main()
