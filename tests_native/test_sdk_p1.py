"""Real native hooks/foreground timeout on harmless fixtures, never run()."""
import json
import time
import unittest
from unittest.mock import patch

from native_remediation import native
from tests_native.test_p1 import PreparedFixture

try:
    from openhands.sdk import LLM
except ImportError:
    LLM = None


@unittest.skipIf(LLM is None, "Requires installed standalone SDK 1.55.1")
class NativeP1Tests(PreparedFixture):
    def test_native_pre_tool_hook_marks_action_blocked_before_execution(self):
        from openhands.sdk.event import ActionEvent
        from openhands.sdk.llm import MessageToolCall
        from openhands.sdk.hooks.manager import HookManager
        from openhands.sdk.hooks.conversation_hooks import HookEventProcessor
        from openhands.tools.terminal import TerminalAction
        with patch.object(LLM, "completion", side_effect=AssertionError("No inference")):
            conversation = native.open_conversation(self.state, self.bound, self.task)
            try:
                self.prepared()
                events = []
                manager = HookManager(native.hook_config(self.state, self.task),
                    working_dir=str(self.workspace), session_id=self.bound["conversationId"])
                processor = HookEventProcessor(manager, original_callback=events.append)
                processor.set_conversation_state(conversation.state)
                for timeout, blocked in ((None, True), (999999, True), (1, False)):
                    action = TerminalAction(command="printf HARMLESS_FIXTURE", timeout=timeout)
                    event = ActionEvent(thought=[], tool_name="terminal", action=action, tool_call_id="fixture",
                        llm_response_id="fixture", tool_call=MessageToolCall(id="fixture", name="terminal",
                            arguments=json.dumps(action.model_dump()), origin="completion"))
                    processor.on_event(event)
                    self.assertEqual(event.id in conversation.state.blocked_actions, blocked)
                self.assertEqual(sum(type(e).__name__ == "HookExecutionEvent" for e in events), 3)
            finally:
                conversation.close()

    def test_native_terminal_timeout_returns_control_then_allows_interrupt(self):
        from openhands.tools.terminal import TerminalAction
        with patch.object(LLM, "completion", side_effect=AssertionError("No inference")):
            conversation = native.open_conversation(self.state, self.bound, self.task)
            try:
                # execute_tool is a trusted SDK probe and bypasses action hooks.
                ready = conversation.execute_tool("terminal", TerminalAction(command="true", timeout=5))
                # The SDK wait timeout is soft, including for shell warm-up.
                for _ in range(3):
                    if ready.metadata.exit_code != -1:
                        break
                    ready = conversation.execute_tool("terminal", TerminalAction(command="", timeout=5))
                self.assertFalse(ready.is_error)
                self.assertEqual(ready.metadata.exit_code, 0,
                                 "Shell warm-up did not finish; timeout probe not submitted")
                started = time.monotonic()
                result = conversation.execute_tool("terminal", TerminalAction(command="sleep 5", timeout=0.1))
                self.assertLess(time.monotonic() - started, 4)
                self.assertFalse(result.is_error, "Timeout command must actually be submitted")
                # SDK 1.55.1 leaves observation.timeout at its default False;
                # foreground timeout is represented by metadata and suffix.
                self.assertEqual(result.metadata.exit_code, -1)
                self.assertIn("timed out", "\n".join(c.text for c in result.to_llm_content))
                interrupted = conversation.execute_tool("terminal", TerminalAction(command="C-c", is_input=True))
                self.assertFalse(interrupted.is_error)
                recovered = conversation.execute_tool("terminal", TerminalAction(
                    command="printf TERMINAL_RECOVERED", timeout=5))
                self.assertFalse(recovered.is_error)
                self.assertEqual(recovered.metadata.exit_code, 0)
                self.assertIn("TERMINAL_RECOVERED", recovered.text)
            finally:
                conversation.close()


if __name__ == "__main__":
    unittest.main()
