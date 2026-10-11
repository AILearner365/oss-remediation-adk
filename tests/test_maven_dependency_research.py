import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/openhands/maven-dependency-research.py"
SPEC = importlib.util.spec_from_file_location("dependency_research", RUNNER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class FakeModel:
    def __init__(self, value): self.value = value
    def model_dump(self, **_kwargs): return self.value


class FakeStatus:
    value = "running"


class FakeState:
    def __init__(self, events, invoked_skills=None):
        self.events = events
        self.invoked_skills = invoked_skills or []
        self.execution_status = FakeStatus()
        self.stats = None


class FakeConversation:
    def __init__(self, events, run_error=None, close_error=None, invoked_skills=None):
        self.state = FakeState(events, invoked_skills)
        self.run_error = run_error
        self.close_error = close_error

    def send_message(self, _prompt): pass
    def run(self):
        if self.run_error: raise self.run_error
    def close(self):
        if self.close_error: raise self.close_error


class ResearchOfflineTests(unittest.TestCase):
    def make_repo(self, root):
        repo = root / "source"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "pom.xml").write_text("<project><version>1.0</version></project>")
        subprocess.run(["git", "add", "pom.xml"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@invalid",
                        "commit", "-qm", "base"], cwd=repo, check=True)
        return repo

    def test_clean_fixture_uses_commit_not_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.make_repo(root)
            (repo / "pom.xml").write_text("dirty")
            fixture = root / "fixture"
            data = MODULE.create_clean_fixture(repo, "HEAD", fixture)
            self.assertEqual("<project><version>1.0</version></project>",
                             (fixture / "pom.xml").read_text())
            self.assertEqual(40, len(data["commit"]))

    def test_rejects_uncontrolled_existing_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.make_repo(root); workspace = root / "exists"
            workspace.mkdir(); (workspace / "user-data").write_text("keep")
            with self.assertRaises(ValueError):
                MODULE.create_clean_fixture(repo, "HEAD", workspace)
            self.assertEqual("keep", (workspace / "user-data").read_text())

    def test_rejects_dirty_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.make_repo(root)
            (repo / "unexpected.txt").write_text("agent edit")
            with self.assertRaisesRegex(ValueError, "dirty or uncontrolled"):
                MODULE.require_clean_fixture(repo)

    def test_sdk_message_event_uses_llm_message(self):
        row = MODULE.serialize_event(FakeModel({"kind": "MessageEvent", "llm_message": {
            "role": "assistant", "content": [{"type": "text", "text": "answer"}]}}))
        self.assertEqual("assistant", row["observable_message"]["role"])

    def test_changed_message_event_is_preserved_with_warning(self):
        row = MODULE.serialize_event({"kind": "MessageEvent", "new_schema": {"text": "x"}})
        self.assertIn("schema_warning", row)
        self.assertEqual({"text": "x"}, row["new_schema"])

    def test_partial_event_evidence_survives_serialization_exception(self):
        class Broken:
            def model_dump(self, **_kwargs): raise RuntimeError("broken")
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "events.jsonl"
            rows = MODULE.export_events([{"kind": "ActionEvent", "tool_name": "terminal"}, Broken()], output)
            self.assertEqual(2, len(output.read_text().splitlines()))
            self.assertEqual("broken", rows[1]["serializationError"])

    def test_absent_skill_evidence_is_not_proven(self):
        result = MODULE.evidence_assessment([], configured=True, delivered=False,
                                            invoked_skills=[])
        self.assertEqual("NOT PROVEN", result["classifications"]["skillTriggeredDelivered"])
        self.assertEqual("NOT PROVEN", result["classifications"]["skillExplicitlyInvoked"])

    def test_skill_delivery_alone_is_not_explicit_invocation(self):
        events = [{"kind": "MessageEvent", "observable_message": {
            "role": "user", "content": MODULE.SKILL_NAME}}]
        result = MODULE.evidence_assessment(events, configured=True, delivered=True,
                                            invoked_skills=[])
        self.assertEqual("PROVEN", result["classifications"]["skillTriggeredDelivered"])
        self.assertEqual("NOT PROVEN", result["classifications"]["skillExplicitlyInvoked"])

    def test_action_mention_is_not_sdk_skill_invocation(self):
        events = [{"kind": "ActionEvent", "tool_name": "terminal",
                   "summary": f"read {MODULE.SKILL_NAME}"}]
        result = MODULE.evidence_assessment(events, True, True, invoked_skills=[])
        self.assertEqual("NOT PROVEN",
                         result["classifications"]["skillExplicitlyInvoked"])

    def test_sdk_invoked_skills_proves_explicit_invocation(self):
        result = MODULE.evidence_assessment([], True, True,
                                            invoked_skills=[MODULE.SKILL_NAME])
        self.assertEqual("PROVEN",
                         result["classifications"]["skillExplicitlyInvoked"])

    def test_keyword_results_are_labeled_indicators(self):
        events = [{"kind": "ObservationEvent", "text": "mvn dependency:tree"}]
        result = MODULE.evidence_assessment(events, True, True, [])
        self.assertEqual("PARTIAL",
                         result["keywordIndicators"]["dependencyBomOwnershipIndicator"])
        self.assertIn("do not prove technical correctness", result["indicatorDisclaimer"])

    def test_prompt_keywords_do_not_count_as_evidence_indicators(self):
        events = [{"kind": "MessageEvent", "observable_message": {
            "role": "user", "content": "verify compatibility with dependency:tree and OSV"}}]
        result = MODULE.evidence_assessment(events, True, True, [])
        self.assertTrue(all(value == "NOT PROVEN"
                            for value in result["keywordIndicators"].values()))

    def test_default_and_overridden_iteration_limit(self):
        with mock.patch("sys.argv", [str(MODULE.__file__), "--output-dir", "/tmp/new"]):
            self.assertEqual(15, MODULE.parse_args().max_iterations)
        with mock.patch("sys.argv", [str(MODULE.__file__), "--output-dir", "/tmp/new",
                                     "--max-iterations", "23"]):
            self.assertEqual(23, MODULE.parse_args().max_iterations)

    def test_execution_and_cleanup_errors_preserve_events_and_both_failures(self):
        event = {"kind": "MessageEvent", "llm_message": {"role": "assistant",
                                                            "content": ["partial"]}}
        conversation = FakeConversation([event], RuntimeError("run failed"),
                                        RuntimeError("close failed"), [MODULE.SKILL_NAME])
        status = {"phase": "running", "error": None, "errors": [],
                  "stopReason": None, "tokenUsage": None}
        events, invoked = MODULE.run_conversation(conversation, "prompt", status)
        self.assertEqual([event], events)
        self.assertEqual([MODULE.SKILL_NAME], invoked)
        self.assertEqual(["execution", "conversation_cleanup"],
                         [error["phase"] for error in status["errors"]])
        self.assertEqual("failed", status["phase"])

    def test_event_export_error_keeps_rows_failure_status_and_fallback(self):
        event = {"kind": "ActionEvent", "tool_name": "terminal"}
        status = {"phase": "completed", "error": None, "errors": []}
        with tempfile.TemporaryDirectory() as td:
            def fail_export(_events, _output): raise OSError("disk write failed")
            rows = MODULE.export_events_preserving_status(
                [event], Path(td), status, exporter=fail_export)
            self.assertEqual("terminal", rows[0]["tool_name"])
            self.assertTrue((Path(td) / "events-export-fallback.json").is_file())
            MODULE.write_json(Path(td) / "status.json", status)
            persisted = json.loads((Path(td) / "status.json").read_text())
            self.assertEqual("event_export", persisted["errors"][0]["phase"])
        self.assertEqual("failed", status["phase"])
        self.assertEqual("event_export", status["errors"][0]["phase"])

    def test_tree_state_detects_no_source_modification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.make_repo(root)
            before = MODULE.tree_state(repo)
            fixture = root / "fixture"
            MODULE.create_clean_fixture(repo, "HEAD", fixture)
            self.assertEqual(before, MODULE.tree_state(repo))


if __name__ == "__main__":
    unittest.main()
