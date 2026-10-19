"""Check the installed pinned OpenHands schema; no API calls or inference."""
from pathlib import Path
import unittest

from native_remediation.contract import load_task
from native_remediation.native import request_config

try:
    from importlib.metadata import version
    from openhands.agent_server.models import StartConversationRequest
    from openhands.sdk.hooks import HookConfig
except ImportError:
    StartConversationRequest = None


@unittest.skipIf(StartConversationRequest is None, "Run with installed native 1.55.1 Python for schema verification")
class InstalledSdkTests(unittest.TestCase):
    def test_actual_creation_schema_and_hook_config(self):
        self.assertEqual(version("openhands-sdk"), "1.55.1")
        task = load_task(dict(repository="AILearner365/maven-multimodule-app", base_branch="main-runrunning",
            base_sha="a" * 40, goal="Resolve baseline vulnerabilities", delivery=dict(
                repository="AILearner365/maven-multimodule-app", base_branch="main-runrunning", draft=True)))
        request = request_config(Path("/private/offline-state"),
            dict(conversationId="05f7716a-90bc-4ec5-a90e-01b7a4de5fa0"), task)
        parsed = StartConversationRequest.model_validate(request)
        self.assertIsInstance(parsed.hook_config, HookConfig)
        self.assertEqual(parsed.agent.agent_context.system_message_suffix, request["agent"]["agent_context"]["system_message_suffix"])
        self.assertEqual(parsed.hook_config.stop[0].hooks[0].timeout, 2700)


if __name__ == "__main__":
    unittest.main()
