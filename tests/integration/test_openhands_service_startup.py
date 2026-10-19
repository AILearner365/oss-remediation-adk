"""Offline contract tests for product startup and persistent native state."""
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_service as service


class ProductStartupTests(unittest.TestCase):
    def test_persistent_native_state_and_keys(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            temp_key = root / "temporary" / "session-key.txt"
            temp_key.parent.mkdir()
            with patch.object(service.native, "KEY_FILE", temp_key):
                env = service.configure_persistent_environment({"UV_CACHE_DIR": "/tmp/cache"}, root / "persistent")
                self.assertEqual(env["UV_CACHE_DIR"], "/tmp/cache")
                self.assertEqual(env["LOCAL_BACKEND_API_KEY"], temp_key.read_text())
                self.assertTrue(Path(env["OPENHANDS_AGENT_SERVER_CONFIG_PATH"]).is_file())
                cfg = json.loads(Path(env["OPENHANDS_AGENT_SERVER_CONFIG_PATH"]).read_text())
                self.assertEqual(cfg["session_api_key"], env["LOCAL_BACKEND_API_KEY"])
                self.assertTrue(Path(cfg["conversations_path"]).is_dir())
                self.assertEqual(stat.S_IMODE((root / "persistent" / "session-key.txt").stat().st_mode), 0o600)
                previous = env["LOCAL_BACKEND_API_KEY"]
                updated = service.configure_persistent_environment({}, root / "persistent")
                self.assertEqual(updated["LOCAL_BACKEND_API_KEY"], previous)

    def test_unowned_smoke_server_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(service.native, "configure_server_version"), \
                 patch.object(service.native, "ROOT", Path(d)), \
                 patch.object(service.native, "owned_pid", return_value=100), \
                 patch.object(service.native, "preflight", side_effect=AssertionError("startup attempted")):
                with self.assertRaisesRegex(ValueError, "different native smoke"):
                    service.serve(Path(d) / "home")


if __name__ == "__main__":
    unittest.main()
