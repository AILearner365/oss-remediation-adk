"""Actual installed SDK Skill rendering/tools, never Gemini execution."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from native_remediation.contract import load_task
from native_remediation import guidance, native
from native_remediation.files import write, digest
from tests_native.test_product import task_input

try:
    from openhands.sdk import LLM
except ImportError:
    LLM = None


@unittest.skipIf(LLM is None, "Requires installed SDK 1.55.1")
class NativeGuidanceParityTests(unittest.TestCase):
    def test_loaded_skills_are_rendered_not_just_present_and_tools_are_exposed(self):
        from openhands.sdk import Message, TextContent
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            task = load_task(task_input())
            bound = dict(task=task, taskDigest=digest(task), conversationId=str(uuid.uuid4()))
            write(state / "task.json", bound)
            with patch.object(LLM, "completion", side_effect=AssertionError("No inference")):
                conversation = native.open_conversation(state, bound, task)
                try:
                    context = conversation.agent.agent_context
                    text = native.task_message(state, bound, task, dict(findings=[]))
                    rendered = context.get_user_message_suffix(Message(role="user", content=[TextContent(text=text)]), [])
                    self.assertEqual(set(rendered[1]), set(task["guidance"]["skills"]))
                    self.assertIn("original findings", rendered[0].text)
                    self.assertIn("maven-metadata.xml", rendered[0].text)
                    self.assertIn("<available_skills>", context.get_system_message_suffix())
                    info = guidance.delivery_evidence(context, text)
                    self.assertEqual(info["status"], "SDK_RENDERED_NOT_MODEL_USE")
                    names = [t.name for t in conversation.agent.tools]
                    self.assertIn("validate_remediation", names)
                    self.assertIn("sbri_intelligence", names)
                    self.assertFalse(any(n in names for n in ("deliver", "accept", "push")))
                    self.assertNotIn("facts, uncertainties, assumptions", text)
                    from native_remediation.agent_tools import ValidateAction, SbriAction
                    with patch("native_remediation.capabilities.self_validate", return_value=dict(
                            outcome="PASS", authority="AGENT_SELF_CHECK_ONLY")) as check:
                        observation = conversation.execute_tool("validate_remediation", ValidateAction())
                        self.assertFalse(observation.is_error)
                        check.assert_called_once_with(state)
                    with patch("native_remediation.capabilities.sbri", return_value=dict(
                            status="UNAVAILABLE")) as intelligence:
                        observation = conversation.execute_tool("sbri_intelligence",
                            SbriAction(ranges=["4.1.x"], scopes=["runtime"]))
                        self.assertFalse(observation.is_error)
                        intelligence.assert_called_once_with(state, versions=None,
                            ranges=["4.1.x"], scopes=["runtime"])
                finally:
                    conversation.close()


if __name__ == "__main__":
    unittest.main()
