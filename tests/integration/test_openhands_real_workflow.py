"""Offline no-dispatch guards for consolidated workflow and preservation."""
from pathlib import Path
from unittest.mock import patch
from inspect import getsource
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_workflow as workflow
import openhands_real_preserve_evidence as preserve


class SafeWorkflowTests(unittest.TestCase):
    def test_entrypoint_excludes_dispatch(self):
        source = getsource(workflow)
        self.assertNotIn("dispatch_native_once(", source)
        self.assertNotIn("approve-billable-run", source)
        self.assertIn("prepare-idle", source)
        self.assertIn("preserve", source)

    def test_archive_needs_valid_accepted_audit(self):
        with patch.object(preserve, "audit", side_effect=ValueError("NOT ACCEPTED")):
            with self.assertRaisesRegex(ValueError, "NOT ACCEPTED"):
                preserve.preserve("task_fake", Path("/tmp/fake-hook"), Path("/tmp/fake-output"))
    def test_credential_exclusion_and_checksum_checks(self):
        source = getsource(preserve)
        self.assertIn("src.backup(dst)", source)
        self.assertIn("digest(copied)", source)
        self.assertIn("native-event-metadata.json", source)
        self.assertNotIn("session-key.txt", source)
        self.assertNotIn("dispatch_native_once", source)


if __name__ == "__main__":
    unittest.main()
