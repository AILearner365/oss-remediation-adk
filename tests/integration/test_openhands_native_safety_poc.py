"""POC4 offline safety checks against existing durable validation service."""
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_safety_poc as safety
import openhands_native_validator_poc as bridge
from openhands_shared.store import SQLiteTaskStore


class NativeSafetyOfflineTests(unittest.TestCase):
    def run_case(self, case):
        old_case, old_safety_state, old_bridge_state = safety.CASE, safety.STATE, bridge.STATE
        with tempfile.TemporaryDirectory() as d:
            safety.CASE = case
            safety.STATE = Path(d) / "safety"
            safety.STATE.mkdir()
            bridge.STATE = safety.STATE
            root = None
            try:
                data = bridge.fixture_setup()
                root = Path(data["database"]).parents[1]
                results = []
                num = 4 if case == "exhausted" else 1
                for _ in range(num):
                    with patch("sys.stdin", io.StringIO('{"event_type":"Stop"}')):
                        with patch("sys.stdout", new_callable=io.StringIO) as output:
                            if case == "hook-crash":
                                with self.assertRaises(SystemExit) as raised:
                                    safety.hook()
                                results.append((raised.exception.code, None))
                            else:
                                code = safety.hook()
                                results.append((code, json.loads(output.getvalue())["decision"]))
                store = SQLiteTaskStore(Path(data["database"]))
                try:
                    attempts = store.list_validation_attempts(data["taskId"])
                    self.assertFalse(store.get_status(data["taskId"]).accepted)
                    self.assertEqual(len(attempts), 0 if case == "hook-crash" else num)
                    expected = {
                        "infrastructure": "INFRASTRUCTURE_FAILURE",
                        "malformed": "VALIDATOR_FAILURE",
                        "exhausted": "REMEDIATION_FAILURE",
                    }.get(case)
                    if expected:
                        self.assertEqual({a.outcome.value for a in attempts}, {expected})
                finally:
                    store.close()
                if case == "exhausted":
                    self.assertTrue(all(x == (2, "deny") for x in results[:-1]))
                    self.assertEqual(results[-1], (0, "allow"))
                elif case == "hook-crash":
                    self.assertEqual(results, [(37, None)])
                else:
                    self.assertEqual(results, [(0, "allow")])
            finally:
                safety.CASE, safety.STATE, bridge.STATE = old_case, old_safety_state, old_bridge_state
                if root and root.is_dir():
                    shutil.rmtree(root, ignore_errors=True)

    def test_infrastructure_is_unaccepted(self):
        self.run_case("infrastructure")

    def test_malformed_report_is_unaccepted(self):
        self.run_case("malformed")

    def test_exhausted_denials_are_unaccepted(self):
        self.run_case("exhausted")

    def test_hook_crash_does_not_create_validation_pass(self):
        self.run_case("hook-crash")


if __name__ == "__main__":
    unittest.main()
