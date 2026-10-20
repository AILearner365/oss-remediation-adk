"""Pinned local SDK API integration tests: no run(), model or target repository."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from native_remediation.contract import load_task
from native_remediation.files import Blocked, digest, write
from native_remediation.native import open_conversation, hook_config
from tests_native.test_product import GitFixture, task_input

try:
    from openhands.sdk import LLM, Agent, Conversation
    from openhands.sdk.workspace import LocalWorkspace
    from openhands.sdk.hooks import HookConfig
except ImportError:
    Conversation = None


@unittest.skipIf(Conversation is None, "Requires installed standalone SDK 1.55.1")
class InstalledSdkTests(unittest.TestCase):
    def test_initialize_and_restore_real_sdk_without_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            task = load_task(task_input())
            bound = dict(task=task, taskDigest=digest(task), conversationId=str(uuid.uuid4()))
            write(state / "task.json", bound)
            # Trap calls, rather than asserting mocks are a successful model run.
            with patch.object(LLM, "completion", side_effect=AssertionError("Inference forbidden")):
                conversation = open_conversation(state, bound, task)
                self.assertIsInstance(conversation.workspace, LocalWorkspace)
                self.assertEqual(len(conversation.state.events), 0)
                self.assertEqual(str(conversation.state.id), bound["conversationId"])
                persisted = Path(conversation.state.persistence_dir)
                self.assertTrue((persisted / "base_state.json").is_file())
                conversation.close()
                restored = open_conversation(state, bound, task)
                self.assertEqual(str(restored.state.id), bound["conversationId"])
                self.assertEqual(Path(restored.state.persistence_dir), persisted)
                self.assertEqual(len(restored.state.events), 0)
                restored.close()
                write(state / "preparation-intent.json", {})
                (persisted / "base_state.json").unlink()
                with self.assertRaisesRegex(Blocked, "persistence missing"):
                    open_conversation(state, bound, task)

    def test_native_stop_callback_executes_harmless_deny_without_inference(self):
        from openhands.sdk.hooks import HookDefinition, HookMatcher
        from openhands.sdk.hooks.conversation_hooks import HookEventProcessor
        from openhands.sdk.hooks.manager import HookManager
        import shlex
        import sys
        with tempfile.TemporaryDirectory() as directory:
            config = HookConfig(stop=[HookMatcher(hooks=[HookDefinition(type="command",
                command=shlex.join([sys.executable, "-c", "raise SystemExit(2)"]))])])
            events = []
            processor = HookEventProcessor(HookManager(config, working_dir=directory,
                session_id=str(uuid.uuid4())), original_callback=events.append)
            allowed, _ = processor.run_stop(reason="agent_finished")
            self.assertFalse(allowed)
            self.assertTrue(events[0].blocked)

    def test_registered_evidence_tool_and_stop_configuration(self):
        from native_remediation.evidence_tool import CycleEvidenceTool, CycleAction
        self.assertEqual(CycleEvidenceTool.name, "cycle_evidence")
        self.assertEqual(CycleAction(record_type="intent", document={}).record_type, "intent")
        config = hook_config(Path("/private/offline-state"), load_task(task_input()))
        self.assertEqual(config.stop[0].hooks[0].timeout, 2700)

    def test_real_sdk_initializes_retained_adapter_and_denies_missing_preparation(self):
        from openhands.sdk.hooks.conversation_hooks import HookEventProcessor
        from openhands.sdk.hooks.manager import HookManager
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            control = state / "control"
            control.mkdir()
            task = load_task(task_input())
            uid = uuid.uuid4()
            write(state / "task.json", dict(task=task, taskDigest=digest(task), conversationId=str(uid),
                  executionFramework="standalone-sdk-1.55.1"))
            config = hook_config(state, task)
            with patch.object(LLM, "completion", side_effect=AssertionError("Inference forbidden")):
                conversation = Conversation(agent=Agent(llm=LLM(model=task["model"]), tools=[]),
                    workspace=LocalWorkspace(working_dir=control), persistence_dir=state / "native-probe",
                    conversation_id=uid, hook_config=config, visualizer=None)
                try:
                    conversation.send_message("Local initialization probe only; do not run")
                    self.assertEqual(conversation.state.hook_config, config)
                    events = []
                    processor = HookEventProcessor(HookManager(config, working_dir=str(control),
                        session_id=str(uid)), original_callback=events.append)
                    allowed, _ = processor.run_stop(reason="agent_finished")
                    self.assertFalse(allowed)
                    self.assertTrue(events[0].blocked)
                    self.assertFalse((state / "delivery.json").exists())
                    self.assertEqual(sum(type(e).__name__ == "MessageEvent" for e in conversation.state.events), 1)
                    self.assertFalse(any(type(e).__name__ == "ActionEvent" for e in conversation.state.events))
                finally:
                    conversation.close()


@unittest.skipIf(Conversation is None, "Requires installed standalone SDK 1.55.1")
class InstalledEvidenceToolTests(GitFixture):
    def test_supported_local_execute_tool_records_intent_without_inference(self):
        from openhands.sdk import Tool
        from native_remediation.evidence_tool import CycleAction, CycleEvidenceTool
        from native_remediation.journal import INTENT_FIELDS
        from native_remediation.files import read
        control = self.state / "control"
        control.mkdir()
        with patch.object(LLM, "completion", side_effect=AssertionError("Inference forbidden")):
            conversation = Conversation(agent=Agent(llm=LLM(model=self.task["model"]),
                tools=[Tool(name=CycleEvidenceTool.name)]), workspace=LocalWorkspace(working_dir=control),
                conversation_id=uuid.UUID(self.bound["conversationId"]),
                persistence_dir=self.state / "native-probe", visualizer=None)
            try:
                result = conversation.execute_tool("cycle_evidence", CycleAction(record_type="intent",
                    document={k: ["verified candidate"] if k == "candidates" else "fixture evidence" for k in INTENT_FIELDS}))
                self.assertFalse(result.is_error)
                self.assertEqual(read(self.state / "journal/1.intent.json")["conversationId"], self.bound["conversationId"])
            finally:
                conversation.close()


if __name__ == "__main__":
    unittest.main()
