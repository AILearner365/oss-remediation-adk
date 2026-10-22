"""Connected production workflow with explicit TEST ONLY process/model injection.

Actual SDK run/Agent/tool/event/hook/persistence and product orchestration execute.
Scripted generate() responses are NOT model inference or autonomous reasoning.
"""
from contextlib import ExitStack
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import unittest
from unittest.mock import patch
import uuid

from native_remediation import capabilities, delivery, native, repository, runtime
from native_remediation.files import Blocked, digest, read, write
from tests_native.test_product import GitFixture, task_input
from tests_native.workflow_fixture import evaluator

try:
    from openhands.sdk import LLM
except ImportError:
    LLM = None


HELPER = Path(__file__).with_name("workflow_fixture.py").resolve()


@unittest.skipIf(LLM is None, "Requires pinned standalone SDK/Tools 1.55.1")
class ConnectedWorkflowTests(GitFixture):
    def setUp(self):
        super().setUp()
        (self.workspace / "pom.xml").write_text('<project><parent><groupId>org.springframework.boot</groupId>'
            '<artifactId>spring-boot-starter-parent</artifactId><version>4.0.6</version></parent>'
            '<properties><library.version>1.0.0</library.version></properties></project>')
        self.git("add", "pom.xml")
        self.git("commit", "-m", "authored SDK workflow fixture")
        self.destination = self.state / "product"
        self.backend = self.state / "sbri-fixture"
        self.backend.write_text("#!/bin/sh\nexec " + shlex.join([sys.executable, str(HELPER), "sbri"]) + ' "$@"\n')
        self.backend.chmod(0o700)
        self.input = dict(task_input(self.git("rev-parse", "HEAD")),
            delivery=dict(mode="report_only"), tools=dict(profiles=["approved-fixture"]),
            sbri=dict(mode="on", executable=str(self.backend), versions=["4.0.8"]),
            limits=dict(max_iterations=12))

    def prepare(self):
        def preparer(state, task):
            shutil.copytree(self.workspace, state / "workspace", dirs_exist_ok=True)
            return state / "workspace"
        return runtime.prepare_task(self.input, self.destination, preparer=preparer, evaluator=evaluator)

    def retain_evidence(self, **facts):
        """Optional TEST ONLY export; normal tests leave no permanent state."""
        if not os.environ.get("OSS_TEST_WORKFLOW_EVIDENCE"):
            return
        destination = Path(os.environ["OSS_TEST_WORKFLOW_EVIDENCE"]) / self._testMethodName
        destination.mkdir(parents=True, exist_ok=False)
        for name in ("baseline.json", "preparation.json", "sbri-pre-edit.json", "feedback.json", "result.json",
                     "attempts/1/validation.json", "attempts/2/validation.json"):
            source = self.destination / name
            if source.exists():
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        write(destination / "facts.json", dict(
            execution="REAL_SDK_LOOP_WITH_SCRIPTED_TEST_RESPONSES_NOT_AUTONOMOUS_REASONING",
            injected=["LLM.generate response sequence; completion forbidden",
                "local repository copy and local base check; fixture preflight",
                "Maven/OSV process outputs, parsed by real validator",
                "SBRI executable is an authored subprocess fixture",
                "Stop subprocess command selects test helper with injected evaluator"], **facts))

    def injections(self):
        """All injections are scoped to this test, never installed/configured live."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(LLM, "completion", side_effect=AssertionError("Paid inference forbidden")))
        stack.enter_context(patch.object(LLM, "resolve_runtime_metadata"))
        # Exercise the approved nonblocking authority checkpoint unmodified.
        stack.enter_context(patch.object(runtime, "verify_base", side_effect=lambda task:
            self.assertEqual(task["base_sha"], self.git("rev-parse", "HEAD"))))
        original_check = capabilities.self_validate
        stack.enter_context(patch.object(capabilities, "self_validate",
            side_effect=lambda state: original_check(state, evaluator=evaluator)))
        self.no_remote = stack.enter_context(patch.object(delivery, "GitHub",
            side_effect=AssertionError("No remote operations in report_only")))
        from openhands.sdk.hooks.executor import HookExecutor
        execute = HookExecutor.execute
        def hook_command(executor, hook, event, env=None):
            if event.event_type == "Stop":
                # Keep production persisted hook config; substitute ONLY the test
                # subprocess command so it can inject fixture Maven/OSV outputs.
                hook = hook.model_copy(update={"command": shlex.join([
                    sys.executable, str(HELPER), "hook", str(self.destination)])})
            return execute(executor, hook, event, env)
        stack.enter_context(patch.object(HookExecutor, "execute", new=hook_command))
        return stack

    def test_connected_denial_recovery_correction_and_report_only_acceptance(self):
        from litellm.types.utils import ModelResponse
        from openhands.sdk.llm import LLMResponse, Message, MessageToolCall
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot
        self.injections()
        bound = self.prepare()
        state = self.destination
        task = bound["task"]
        self.assertEqual(read(state / "preparation.json")["outcome"], "COMPLETE")
        pre_edit = read(state / "sbri-pre-edit.json")
        self.assertEqual(pre_edit["status"], "COMPLETE")
        self.assertEqual(pre_edit["request"]["profiles"], ["approved-fixture"])
        baseline = read(state / "baseline.json")
        with patch.object(LLM, "generate", side_effect=AssertionError("Incomplete baseline reached agent")) as generation:
            write(state / "baseline.json", dict(baseline, outcome="INCONCLUSIVE"))
            with self.assertRaises(Blocked):
                runtime.dispatch(state, preflight=lambda task: {})
            generation.assert_not_called()
        write(state / "baseline.json", baseline)
        calls = [
            ("sbri_intelligence", {}),
            ("terminal", dict(command="printf '\\n<!-- rejected fixture candidate -->\\n' >> pom.xml", timeout=5)),
            ("finish", dict(message="Fixture completion request, not a success claim")),
            None,  # An explicit fixture interruption AFTER Stop denies.
            ("terminal", dict(command="sed -i 's/1.0.0/1.0.1/' pom.xml", timeout=5)),
            ("validate_remediation", {}),
            ("finish", dict(message="Corrected fixture submitted for independent acceptance")),
        ]
        index = 0
        def generate(_llm, *args, **kwargs):
            nonlocal index
            item = calls[index]
            index += 1
            if item is None:
                self.assertEqual(read(state / "feedback.json")["outcome"], "FAIL")
                raise RuntimeError("TEST ONLY interruption after Stop denial")
            if index == 5:
                # Resume must contain current candidate tree and prior feedback.
                history = str(kwargs.get("messages", args))
                self.assertIn(rejected_tree, history)
                self.assertIn("Validation feedback", history)
            if index == 7:
                self.assertFalse((state / "result.json").exists())
                self.assertFalse((state / "delivery.json").exists())
                self.assertEqual(len(list((state / "attempts").glob("*/validation.json"))), 1)
                checks = list((state / "self-validation").glob("*/result.json"))
                self.assertEqual(read(checks[0])["outcome"], "PASS")
                self.assertEqual(read(checks[0])["authority"], "AGENT_SELF_CHECK_ONLY")
            name, action = item
            return LLMResponse(message=Message(role="assistant", content=[], tool_calls=[MessageToolCall(
                id="fixture-" + str(index), name=name, arguments=json.dumps(action), origin="completion")]),
                metrics=MetricsSnapshot(), raw_response=ModelResponse(id="fixture-response-" + str(index)))
        with patch.object(LLM, "generate", new=generate):
            from openhands.sdk.conversation.exceptions import ConversationRunError
            with self.assertRaises(ConversationRunError):
                runtime.dispatch(state, preflight=lambda task: {})
            first = read(state / "attempts/1/validation.json")
            self.assertEqual(first["outcome"], "FAIL")
            rejected_tree = first["validatedTree"]
            self.assertNotEqual(rejected_tree, baseline["tree"])
            prior = {str(p.relative_to(state)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (state / "attempts/1").rglob("*") if p.is_file()}
            native_path = state / "conversations" / uuid.UUID(bound["conversationId"]).hex
            native_prior = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (native_path / "events").glob("event-*.json")}
            result = runtime.dispatch(state, resume_reason="TEST ONLY restore after denied candidate",
                                      preflight=lambda task: {})
        self.assertEqual(index, len(calls))
        self.assertEqual(result["nativeStatus"], "finished")
        self.assertEqual(result["result"]["outcome"], "VALIDATED")
        self.assertEqual(result["result"]["deliveryStatus"], "NOT_REQUESTED")
        second = read(state / "attempts/2/validation.json")
        self.assertEqual(second["outcome"], "PASS")
        tree = repository.snapshot(state / "workspace", task)
        self.assertNotEqual(tree, rejected_tree)
        self.assertEqual(second["validatedTree"], tree)
        self.assertEqual(result["result"]["validatedTree"], tree)
        self.assertEqual(second["taskDigest"], bound["taskDigest"])
        self.assertEqual(second["conversationId"], bound["conversationId"])
        for name, sha in prior.items():
            self.assertEqual(hashlib.sha256((state / name).read_bytes()).hexdigest(), sha)
        native_path = state / "conversations" / uuid.UUID(bound["conversationId"]).hex
        for name, sha in native_prior.items():
            self.assertEqual(hashlib.sha256((native_path / "events" / name).read_bytes()).hexdigest(), sha)
        events = [read(p) for p in sorted((native_path / "events").glob("event-*.json"))]
        encoded = json.dumps(events)
        self.assertIn("Independent FAIL", encoded)
        self.assertIn("Reassess facts/candidates", encoded)
        self.assertIn('"reused": true'.replace('"', '\\"'), encoded)
        stops = [e for e in events if e.get("hook_event_type") == "Stop"]
        self.assertEqual([e["blocked"] for e in stops], [True, False])
        self.assertEqual(len(list((state / "sbri").glob("*/intent.json"))), 1)
        self.assertEqual(len(list((state / "runs").glob("*.json"))), 2)
        latest = read(state / "evidence/latest.json")
        evidence = read(state / latest["path"])
        self.assertEqual(latest["digest"], digest(evidence))
        self.assertEqual(evidence["candidateTree"], tree)
        self.assertEqual(evidence["eventCount"], len(events))
        self.assertEqual(evidence["references"]["result.json"], "result.json")
        for metrics in result["modelUsage"]["usage_to_metrics"].values():
            self.assertEqual(metrics["accumulated_cost"], 0)
            self.assertEqual(metrics["accumulated_token_usage"]["completion_tokens"], 0)
        for reference in evidence["references"].values():
            self.assertTrue((state / reference).exists())
        self.assertFalse((state / "delivery.json").exists())
        self.no_remote.assert_not_called()
        self.retain_evidence(conversationId=bound["conversationId"], nativeStatus=result["nativeStatus"],
            scriptedResponses=index - 1, fixtureInterruptions=1, modelCalls=0, remoteMutations=0,
            eventCount=len(events), eventTypes=dict(Counter(e.get("kind") for e in events)),
            eventManifestDigest=evidence["eventManifestDigest"], stopEvents=stops,
            priorNativeEventHashesUnchanged=native_prior,
            rejectedTree=rejected_tree, validatedTree=tree, priorAttemptHashesUnchanged=prior,
            phaseEvidenceReferences=evidence["references"], baselineGate="INCOMPLETE_BLOCKED_COMPLETE_PERMITTED",
            selfValidation="PASS_DID_NOT_ACCEPT_OR_CONSUME_STOP_ATTEMPT", runs=2,
            sbri="PRE_EDIT_AND_AGENT_TOOL_SHARED_PROFILE_BOUND_CACHE", modelUsage=result["modelUsage"])

    def test_optional_sbri_failure_preserves_baseline_and_native_tool_diagnostics(self):
        from native_remediation.agent_tools import SbriAction
        self.injections()
        self.backend.write_text("#!/bin/sh\nexec " + shlex.join([sys.executable, str(HELPER), "sbri-failure"]) + ' "$@"\n')
        bound = self.prepare()
        state = self.destination
        runtime.require_preparation(state)
        result = read(state / "sbri-pre-edit.json")
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIn("approved profile repository unavailable", str(result["reasons"]))
        self.assertIn("approved profile repository unavailable", read(state / result["commandEvidence"])["stderr"])
        conversation = native.open_conversation(state, bound, bound["task"])
        try:
            response = conversation.execute_tool("sbri_intelligence", SbriAction())
            self.assertFalse(response.is_error)
            payload = json.loads(response.text)
            self.assertEqual(payload["status"], "INCONCLUSIVE")
            self.assertTrue(payload["reused"])
            self.assertIn("approved profile repository unavailable", str(payload["reasons"]))
        finally:
            conversation.close()
        self.assertEqual(read(state / "preparation.json")["outcome"], "COMPLETE")
        self.assertFalse((state / "result.json").exists())
        self.no_remote.assert_not_called()
        self.retain_evidence(conversationId=bound["conversationId"], preparation="COMPLETE",
            sbriStatus=payload["status"], nativeToolReused=payload["reused"],
            diagnostics=payload["reasons"], commandEvidence=read(state / result["commandEvidence"]),
            resultPresent=False, modelCalls=0, remoteMutations=0)
