"""Installed native contract probes, not a model run or preparation workaround."""
import hashlib
import inspect
import json
from pathlib import Path
import shlex
import sys
import tempfile
from types import MethodType, SimpleNamespace
import unittest

try:
    from importlib.metadata import version
    from openhands.agent_server.models import StartConversationRequest
    from openhands.sdk.agent import Agent
    from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
    from openhands.sdk.conversation.state import ConversationState, ConversationExecutionStatus
    from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
    from openhands.sdk.hooks.conversation_hooks import HookEventProcessor
    from openhands.sdk.hooks.manager import HookManager
    from openhands.sdk.hooks.executor import HookResult
except ImportError:
    HookManager = None


@unittest.skipIf(HookManager is None, "Requires installed native 1.55.1 Python; no services/inference")
class PreparationContractTests(unittest.TestCase):
    def manager(self, event, exit_code):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        command = shlex.join([sys.executable, "-c", "raise SystemExit(" + str(exit_code) + ")"])
        return HookManager(HookConfig(**{event: [HookMatcher(hooks=[HookDefinition(
            type="command", command=command, timeout=5)])]}), working_dir=directory.name,
            session_id="05f7716a-90bc-4ec5-a90e-01b7a4de5fa0")

    def test_session_start_denial_is_observed_but_not_propagated_as_gate(self):
        events = []
        processor = HookEventProcessor(self.manager("session_start", 2), original_callback=events.append)
        self.assertIsNone(processor.run_session_start())
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].blocked)
        self.assertEqual(events[0].exit_code, 2)

    def test_user_prompt_command_error_and_timeout_are_not_fail_closed(self):
        proceed, _, results = self.manager("user_prompt_submit", 1).run_user_prompt_submit("task")
        self.assertTrue(proceed)
        self.assertFalse(results[0].success)
        self.assertTrue(HookResult(success=False, exit_code=-1, error="timeout").should_continue)

    def test_prompt_denial_is_consumed_not_a_persistent_pre_inference_gate(self):
        class ReachedLlmPreparation(Exception):
            pass
        def tripwire():
            raise ReachedLlmPreparation("Stop before any LLM/context preparation")
        state = SimpleNamespace(last_user_message_id="message", blocked_messages={"message": "baseline failed"},
            execution_status=ConversationExecutionStatus.RUNNING, active_branch=lambda: [])
        state.pop_blocked_message = MethodType(ConversationState.pop_blocked_message, state)
        conversation = SimpleNamespace(state=state, get_llm_call_context=tripwire)
        # The real native step consumes the denial and finishes without inference.
        Agent._step(SimpleNamespace(), conversation, lambda event: None, None)
        self.assertEqual(state.execution_status, ConversationExecutionStatus.FINISHED)
        self.assertFalse(state.blocked_messages)
        # Native Stop DENY sets RUNNING and continues. The next native step now
        # passes the consumed prompt denial. A tripwire halts BEFORE any LLM work.
        state.execution_status = ConversationExecutionStatus.RUNNING
        with self.assertRaises(ReachedLlmPreparation):
            Agent._step(SimpleNamespace(), conversation, lambda event: None, None)

    def test_remote_execute_tool_is_explicitly_unsupported(self):
        with self.assertRaisesRegex(NotImplementedError, "not yet supported"):
            RemoteConversation.execute_tool(object(), "terminal", None)
        fields = StartConversationRequest.model_fields
        self.assertFalse({"preparation", "pre_run", "baseline"} & set(fields))

    def test_reviewed_installed_sources_are_identical(self):
        self.assertEqual(version("openhands-sdk"), "1.55.1")
        self.assertEqual(version("openhands-agent-server"), "1.55.1")
        record = json.loads((Path(__file__).resolve().parents[1] /
                             "docs/evidence/native-preparation-1551.json").read_text())
        root = Path(inspect.getfile(HookManager)).parents[2]
        for name, expected in record["installedSourceSha256"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected, name)


if __name__ == "__main__":
    unittest.main()
