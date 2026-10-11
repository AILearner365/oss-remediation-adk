import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/openhands/maven-dependency-research.py"
SPEC = importlib.util.spec_from_file_location("dependency_research", RUNNER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class FakeModel:
    def __init__(self, value): self.value = value
    def model_dump(self, **_kwargs): return self.value


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
        result = MODULE.evidence_assessment([], configured=True, delivered=False)
        self.assertEqual("NOT PROVEN", result["skillTriggeredDelivered"])
        self.assertEqual("NOT PROVEN", result["skillExplicitlyInvoked"])

    def test_skill_delivery_alone_is_not_explicit_invocation(self):
        events = [{"kind": "MessageEvent", "observable_message": {
            "role": "user", "content": MODULE.SKILL_NAME}}]
        result = MODULE.evidence_assessment(events, configured=True, delivered=True)
        self.assertEqual("PROVEN", result["skillTriggeredDelivered"])
        self.assertEqual("NOT PROVEN", result["skillExplicitlyInvoked"])

    def test_tree_state_detects_no_source_modification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = self.make_repo(root)
            before = MODULE.tree_state(repo)
            fixture = root / "fixture"
            MODULE.create_clean_fixture(repo, "HEAD", fixture)
            self.assertEqual(before, MODULE.tree_state(repo))


if __name__ == "__main__":
    unittest.main()
