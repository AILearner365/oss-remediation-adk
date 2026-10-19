"""No-cost safety checks for the explicit one-shot real Vertex dispatch CLI."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from inspect import getsource

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_dispatch_once as dispatch


class RealDispatchGuards(unittest.TestCase):
    def test_requires_exact_authorization_before_network_or_database(self):
        with patch.object(dispatch.native, "http", side_effect=AssertionError("network")), \
             patch.object(dispatch, "SQLiteTaskStore", side_effect=AssertionError("database")):
            with self.assertRaises(ValueError):
                dispatch.run("not-approved")

    def test_one_shot_never_creates_conversation_or_replays_run(self):
        source = getsource(dispatch.run)
        self.assertIn("dispatch_native_once(", source)
        self.assertIn("get_execution_claim(TASK)", source)
        self.assertIn("validate_native_response(", source)
        self.assertNotIn("create_idle_native_conversation(", source)
        self.assertNotIn("POST", source)
        self.assertNotIn("claim_execution(", source)

    def test_approved_identity_is_pinned(self):
        self.assertEqual(dispatch.CONVERSATION, "0de4c085-fced-4714-a995-856929e32afc")
        self.assertEqual(dispatch.MODEL, "vertex_ai/gemini-2.5-flash")
        self.assertEqual(dispatch.TASK, "task_93531f4571724ab183e2e2defea6def8")


if __name__ == "__main__":
    unittest.main()
