"""Fail-closed offline guard checks for accepted remediation audit."""
from pathlib import Path
from unittest.mock import patch
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_run_audit as audit


class AcceptedAuditTests(unittest.TestCase):
    def test_missing_hook_does_not_claim_success(self):
        with self.assertRaises((FileNotFoundError, OSError)):
            audit.audit("task_absent", Path("/missing/openhands-hook.json"), check_native=False)

    def test_audit_contains_no_execution_entrypoint(self):
        from inspect import getsource
        source = getsource(audit)
        self.assertNotIn("dispatch_native_once", source)
        self.assertNotIn("claim_execution(", source)
        self.assertNotIn("subprocess.run", source)
        self.assertNotIn("mvn clean", source)
        self.assertIn("verify_validated_state", source)
        self.assertIn("hashlib.sha256(data)", source)
        self.assertIn("destination.open(\"x\"", source)


if __name__ == "__main__":
    unittest.main()
