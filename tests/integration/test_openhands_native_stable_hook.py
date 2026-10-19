"""Focused regression for stable independent Stop Hook command verification."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_remediation as bridge


def native_pair(command):
    hook = {"type": "command", "command": command, "timeout": 3600}
    context = {"skills": [{"name": "maven-dependency-evidence"}],
               "system_message_suffix": "Validated engineering guidance"}
    tools = [{"name": "terminal"}]
    config = {"stop": [{"matcher": "*", "hooks": [hook]}]}
    request = {"conversation_id": "example-id", "hook_config": config,
               "workspace": {"working_dir": "/tmp/isolated"},
               "agent": {"tools": tools, "agent_context": context}}
    persisted = {"id": "example-id", "execution_status": "idle", "hook_config": config,
                 "workspace": request["workspace"], "agent": request["agent"]}
    return request, persisted


class StableStopHookTests(unittest.TestCase):
    def test_command_uses_stable_interpreter(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            workspace.mkdir()
            hook = Path(root) / "stop-hook.json"
            hook.write_text("{}")
            command = bridge.stable_stop_hook_command(
                task_id="task_1234", workspace=workspace, hook_config=hook)
            self.assertTrue(command.startswith("/usr/bin/python3 "))
            self.assertIn("openhands_shared.stop_hook", command)
            self.assertNotIn("/uv-cache/", command)

    def test_persisted_command_must_match_exactly(self):
        req, stored = native_pair("/usr/bin/python3 -c 'print(1)'")
        self.assertEqual(bridge.validate_native_response(stored, req), "example-id")
        stored["hook_config"] = {"stop": [{"matcher": "*", "hooks": [{
            "type": "command", "command": "/tmp/uv-cache/builds-v0/deleted/bin/python -c 'print(1)'",
            "timeout": 3600
        }]}]}
        with self.assertRaisesRegex(bridge.HandoffError, "independent Stop Hook"):
            bridge.validate_native_response(stored, req)


if __name__ == "__main__":
    unittest.main()
