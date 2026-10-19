"""Small offline checks: real local Git, no native server, credentials or network."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import openhands_native_wiring_hook as hook
import openhands_native_wiring_submit as submit


class NativeWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "workspace"
        self.workspace.mkdir()
        def git(*args):
            return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null",
                "-c", "user.name=Offline Check", "-c", "user.email=offline@example.invalid",
                "-C", str(self.workspace), *args], stderr=subprocess.DEVNULL, text=True).strip()
        self.git = git
        git("init")
        git("remote", "add", "origin", hook.URL)
        (self.workspace / "README").write_text("baseline\n")
        git("add", "README")
        git("commit", "-m", "offline baseline")
        self.contract = dict(conversationId="05f7716a-90bc-4ec5-a90e-01b7a4de5fa0",
            workspace=str(self.workspace), baseCommit=git("rev-parse", "HEAD"),
            repository=hook.REPO, base=hook.BASE)
        (self.workspace / hook.FILE).write_bytes(hook.MESSAGE)

    def test_exact_tree_and_delivery_commit_without_mutating_head(self):
        tree = hook.validate(self.contract)
        self.assertEqual(self.git("diff", "--name-status", self.contract["baseCommit"], tree),
                         "A\t" + hook.FILE)
        commit = hook.delivery_commit(self.workspace, dict(self.contract, validatedTree=tree))
        self.assertEqual(self.git("show", "-s", "--format=%T", commit), tree)
        self.assertEqual(self.git("show", "-s", "--format=%P", commit), self.contract["baseCommit"])
        self.assertEqual(self.git("rev-parse", "HEAD"), self.contract["baseCommit"])

    def test_reject_extra_file_wrong_content_and_executable(self):
        extra = self.workspace / "unexpected"
        extra.write_text("no\n")
        with self.assertRaises(ValueError):
            hook.validate(self.contract)
        extra.unlink()
        target = self.workspace / hook.FILE
        target.write_bytes(hook.MESSAGE.rstrip(b"\n"))
        with self.assertRaises(ValueError):
            hook.validate(self.contract)
        target.write_bytes(hook.MESSAGE)
        target.chmod(0o755)
        with self.assertRaises(ValueError):
            hook.validate(self.contract)

    def test_conversation_mismatch_blocks_before_delivery(self):
        state = Path(self.temp.name) / "evidence"
        state.mkdir()
        (state / "contract.json").write_text(json.dumps(self.contract))
        with self.assertRaisesRegex(ValueError, "conversation mismatch"):
            hook.run(state, dict(session_id="wrong"))
        self.assertFalse((state / "validation.json").exists())

    def test_native_request_and_evidence(self):
        request = submit.build_request(self.contract, Path(self.temp.name))
        self.assertEqual(request["agent"]["llm"]["model"], "vertex_ai/gemini-2.5-flash")
        self.assertEqual(request["max_iterations"], 3)
        self.assertEqual(request["agent"]["llm"]["num_retries"], 0)
        self.assertFalse(request["autotitle"])
        self.assertEqual(len(request["hook_config"]["stop"][0]["hooks"]), 1)
        evidence = json.loads((SCRIPTS.parent / "docs/experiments/openhands/evidence/"
                               "native-wiring-20261019.json").read_text())
        self.assertEqual(evidence["conversationId"], self.contract["conversationId"])
        self.assertEqual(evidence["hook"]["decision"], "allow")
        self.assertEqual(evidence["delivery"]["validatedTree"], evidence["validation"]["validatedTree"])


if __name__ == "__main__":
    unittest.main()
