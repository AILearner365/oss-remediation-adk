"""Batch/report/publication boundaries. No Gemini, real target or external push."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

from native_remediation import live
from native_remediation.contract import load_task
from native_remediation.files import Blocked, digest, read, write
from tests_native.test_product import GitFixture, evaluation


class ReportTests(GitFixture):
    def setUp(self):
        super().setUp()
        self.task = load_task(dict(self.task, delivery=dict(mode="report_only")))
        self.bound.update(task=self.task, taskDigest=digest(self.task))
        write(self.state / "task.json", self.bound)
        self.invocation = dict(runId="20261022T000000Z-" + uuid.uuid4().hex,
            startedAt="2026-10-22T00:00:00+00:00", phases=[], publish=False)

    def native(self, status="finished"):
        root = self.state / "conversations" / uuid.UUID(self.bound["conversationId"]).hex
        write(root / "base_state.json", dict(execution_status=status, stats=dict(usage_to_metrics={
            "agent": dict(accumulated_cost=0.1, accumulated_token_usage=dict(prompt_tokens=20, completion_tokens=10))})))
        return root

    def success(self):
        accepted = self.accepted()
        write(self.state / "attempts/1/intent.json", dict(tree=accepted["validatedTree"]))
        write(self.state / "result.json", dict(outcome="VALIDATED", validationOutcome="PASS",
            deliveryStatus="NOT_REQUESTED", attempt=1, validatedTree=accepted["validatedTree"]))
        self.native()

    def test_success_is_bound_and_model_usage_is_numeric(self):
        self.success()
        report = live.export_report(self.state, self.invocation)
        self.assertTrue(report["reportComplete"])
        self.assertEqual(report["final"]["outcome"], "VALIDATED")
        self.assertEqual(report["final"]["delivery"], "NOT_REQUESTED")
        self.assertEqual(report["modelExecution"]["usage"]["completion_tokens"], 10)
        self.assertEqual(report["attempts"][0]["outcome"], "PASS")
        accepted = read(self.state / "attempts/1/validation.json")
        write(self.state / "attempts/1/validation.json", dict(accepted, taskDigest="invalid"))
        report = live.export_report(self.state, self.invocation)
        self.assertFalse(report["reportComplete"])
        self.assertEqual(report["final"]["outcome"], "INCONSISTENT_RESULT")

    def test_baseline_failure_uses_actual_recorded_reason_and_commands(self):
        baseline = dict(self.baseline, outcome="INCONCLUSIVE", reasons=["Unexpected OSV package identity"])
        write(self.state / "baseline.json", baseline)
        for label, code in (("build", 0), ("resolve", 0), ("scan", 1)):
            write(self.state / "baseline" / (label + ".json"), dict(exitCode=code, timedOut=False, seconds=1,
                stdout="CREDENTIAL_BEARING_LOG_MUST_NOT_LEAK"))
        report = live.export_report(self.state, self.invocation)
        self.assertEqual(report["final"]["outcome"], "BASELINE_FAILED_BEFORE_INFERENCE")
        self.assertEqual(report["modelExecution"]["status"], "NOT_EXECUTED")
        self.assertEqual(report["baseline"]["reasons"][0]["code"], "Unexpected OSV package identity")
        self.assertEqual([r["exitCode"] for r in report["baseline"]["commands"]], [0, 0, None, 1])
        self.assertNotIn("CREDENTIAL_BEARING", json.dumps(report))

    def test_stop_denial_and_interruption_are_not_success(self):
        write(self.state / "attempts/1/intent.json", dict(tree=self.baseline["tree"]))
        write(self.state / "attempts/1/validation.json", dict(outcome="FAIL", reasons=["Remaining vulnerabilities exceed acceptance policy"]))
        self.native("paused")
        report = live.export_report(self.state, self.invocation)
        self.assertEqual(report["final"]["outcome"], "STOP_DENIED")
        write(self.state / "runs/1.json", dict(state="RUN_INTENT"))
        report = live.export_report(self.state, dict(self.invocation, interrupted=True))
        self.assertEqual(report["final"]["outcome"], "INTERRUPTED")
        self.assertEqual(report["modelExecution"]["status"], "DISPATCH_CLAIMED_NO_RESPONSE_OBSERVED")

    def test_no_free_text_logs_secrets_or_private_files_are_exported(self):
        secret = "SENSITIVE_FIXTURE_1234567890"
        write(self.state / "baseline.json", dict(self.baseline, reasons=[secret]))
        root = self.native()
        write(root / "events/event-00000-12345678.json", dict(source="agent", kind="MessageEvent", text=secret))
        write(self.state / "journal/decision-1.json", dict(rationale=secret))
        write(self.state / "credential.json", dict(password=secret))
        report = live.export_report(self.state, self.invocation)
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn("credential.json", json.dumps(report))
        self.assertEqual(report["agent"]["decisions"], 1)
        self.assertEqual(report["baseline"]["reasons"][0]["code"], "PRIVATE_DIAGNOSTIC")
        (self.state / "baseline.json").unlink()
        (self.state / "baseline.json").symlink_to(self.state / "credential.json")
        report = live.export_report(self.state, self.invocation)
        self.assertFalse(report["reportComplete"])
        self.assertNotIn(secret, json.dumps(report))

    def test_report_existing_state_never_executes_or_changes_state(self):
        self.success()
        before = {str(p): p.read_bytes() for p in self.state.rglob("*.json")}
        with tempfile.TemporaryDirectory() as output, patch.object(live, "run_command") as run, redirect_stdout(StringIO()):
            code = live.main(["report", "--state", str(self.state), "--runs-dir", output])
            report = read(next(Path(output).glob("*/report.json")))
        self.assertEqual(code, 0)
        self.assertEqual(report["kind"], "EXISTING_STATE_EXPORT")
        run.assert_not_called()
        for path, data in before.items():
            self.assertEqual(Path(path).read_bytes(), data)

    def test_export_failure_is_explicit_and_preserved(self):
        with tempfile.TemporaryDirectory() as output, patch.object(live, "export_report", side_effect=ValueError("private error")), redirect_stdout(StringIO()):
            code = live.main(["report", "--state", str(self.state), "--runs-dir", output])
            report = read(next(Path(output).glob("*/report.json")))
        self.assertEqual(code, 1)
        self.assertFalse(report["reportComplete"])
        self.assertEqual(report["final"]["outcome"], "REPORT_INCOMPLETE")

    def test_live_calls_existing_cli_once_and_captures_setup_failure(self):
        task = self.state / "approved.json"
        write(task, dict(self.task, model="vertex_ai/gemini-3.8-flash"))
        seen = []
        def command(argv, job, label, phases, timeout=None):
            seen.append((argv, label))
            phases.append(dict(name=label, exitCode=0))
            if label == "preflight":
                write(job / "checks.json", dict(sdk="PASS", model="PASS"))
            if label == "execution":
                self.assertIn("--authorize-model-execution", argv)
                self.assertIn("native_remediation", argv)
                # Fixture product boundary; no real SDK/provider invocation.
                bound = dict(self.bound, task=load_task(read(task)), taskDigest=digest(load_task(read(task))))
                write(job / "state/task.json", bound)
                write(job / "state/baseline.json", dict(self.baseline, outcome="FAIL", reasons=["Maven build/tests failed; see private build evidence"]))
        with tempfile.TemporaryDirectory() as output, patch.object(live, "publishing_precheck", return_value="a" * 40), \
                patch.object(live, "publish", return_value=dict(status="PUSHED_VERIFIED")), \
                patch.object(live, "run_command", side_effect=command), redirect_stdout(StringIO()):
            args = ["live", "--task", str(task), "--authorize-model-execution", "--publish-evidence", "--runs-dir", output]
            self.assertEqual(live.main(args), 1)
            self.assertEqual([label for _, label in seen], ["setup", "preflight", "execution"])
            self.assertEqual(read(next(Path(output).glob("*/report.json")))["final"]["outcome"], "BASELINE_FAILED_BEFORE_INFERENCE")
        with tempfile.TemporaryDirectory() as output, patch.object(live, "publishing_precheck", return_value="a" * 40), \
                patch.object(live, "publish", return_value=dict(status="PUSHED_VERIFIED")), \
                patch.object(live, "run_command", side_effect=Blocked("SDK setup unavailable")), redirect_stdout(StringIO()):
            self.assertEqual(live.main(args[:-1] + [output]), 1)
            report = read(next(Path(output).glob("*/report.json")))
            self.assertEqual(report["invocation"]["failedPhase"], "setup")
            self.assertEqual(report["baseline"]["outcome"], "NOT_EXECUTED")

    def test_private_command_interrupt_cleanup_and_exit_evidence(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            phases = []
            with self.assertRaises(subprocess.TimeoutExpired):
                live.run_command([sys.executable, "-c", "import time; time.sleep(30)"],
                    Path(directory), "execution", phases, timeout=0.1)
            self.assertEqual(phases[0]["name"], "execution")
            self.assertIsNotNone(phases[0]["exitCode"])
            self.assertTrue((Path(directory) / "execution.stderr").exists())

    def test_retired_model_preflight_fails_before_adc_or_base(self):
        task = self.state / "approved.json"
        result = self.state / "checks.json"
        write(task, self.task)
        with patch("importlib.metadata.version", return_value="1.55.1"), \
                patch("native_remediation.preflight.check") as check:
            with self.assertRaisesRegex(Blocked, "retired"):
                live.prerequisite_check(task, result)
            check.assert_not_called()
        self.assertEqual(read(result), dict(sdk="PASS", model="FAIL"))

    def test_missing_model_authorization_still_reports_without_running(self):
        task = self.state / "approved.json"
        write(task, self.task)
        with tempfile.TemporaryDirectory() as output, patch.object(live, "publishing_precheck", return_value="a" * 40), \
                patch.object(live, "publish", return_value=dict(status="PUSHED_VERIFIED")) as publish, \
                patch.object(live, "run_command") as run, redirect_stdout(StringIO()):
            self.assertEqual(live.main(["live", "--task", str(task), "--publish-evidence", "--runs-dir", output]), 1)
            run.assert_not_called()
            publish.assert_called_once()
            self.assertEqual(read(next(Path(output).glob("*/report.json")))["invocation"]["failedPhase"], "authorization")

    def test_interrupted_invocation_still_exports_and_attempts_publication(self):
        task = self.state / "approved.json"
        write(task, self.task)
        with tempfile.TemporaryDirectory() as output, patch.object(live, "publishing_precheck", return_value="a" * 40), \
                patch.object(live, "publish", return_value=dict(status="PUSHED_VERIFIED")) as publish, \
                patch.object(live, "run_command", side_effect=KeyboardInterrupt), redirect_stdout(StringIO()):
            self.assertEqual(live.main(["live", "--task", str(task), "--authorize-model-execution",
                "--publish-evidence", "--runs-dir", output]), 1)
            report = read(next(Path(output).glob("*/report.json")))
            self.assertTrue(report["invocation"]["interrupted"])
            self.assertEqual(report["final"]["outcome"], "INTERRUPTED")
            publish.assert_called_once()


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "product"
        self.root.mkdir()
        self.remote = Path(self.temp.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        self.git("init", "-b", live.BRANCH)
        self.git("config", "user.name", "Offline evidence")
        self.git("config", "user.email", "offline@example.invalid")
        (self.root / "unrelated.txt").write_text("original")
        self.git("add", "unrelated.txt")
        self.git("commit", "-m", "initial")
        self.git("remote", "add", "origin", self.remote.as_uri())
        self.git("push", "origin", live.BRANCH)
        remote = patch.object(live, "REMOTES", {self.remote.as_uri()})
        remote.start()
        self.addCleanup(remote.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def report(self):
        return dict(runId="20261022T000000Z-" + uuid.uuid4().hex, reportComplete=True, final=dict(outcome="FAIL"))

    def test_isolated_staging_and_verified_local_remote_push(self):
        head = live.publishing_precheck(self.root)
        (self.root / "unrelated.txt").write_text("staged user change")
        self.git("add", "unrelated.txt")
        receipt = live.publish(self.root, self.report(), head)
        self.assertEqual(receipt["status"], "PUSHED_VERIFIED")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "unrelated.txt")
        self.assertEqual(self.git("show", "HEAD:unrelated.txt"), "original")
        self.assertEqual(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"), receipt["report"])
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/" + live.BRANCH).split()[0], receipt["commit"])

    def test_wrong_branch_remote_and_changed_head_fail_closed(self):
        head = live.publishing_precheck(self.root)
        self.git("checkout", "-b", "other")
        with self.assertRaises(Blocked):
            live.publishing_precheck(self.root)
        self.git("checkout", live.BRANCH)
        with patch.object(live, "REMOTES", set()), self.assertRaises(Blocked):
            live.publishing_precheck(self.root)
        self.git("commit", "--allow-empty", "-m", "not yet published")
        with self.assertRaises(Blocked):
            live.publish(self.root, self.report(), head)

    def test_push_failure_preserves_local_commit_and_report(self):
        head = live.publishing_precheck(self.root)
        original = live.git
        def fail_push(root, *args, **kwargs):
            if args[0] == "push":
                raise Blocked("Fixture push failure")
            return original(root, *args, **kwargs)
        with patch.object(live, "git", side_effect=fail_push), self.assertRaisesRegex(Blocked, "push failure"):
            live.publish(self.root, self.report(), head)
        self.assertNotEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/" + live.BRANCH).split()[0], head)
        self.assertTrue(list((self.root / "docs/evidence/live-runs").glob("*/report.json")))

    def test_publication_failure_receipt_is_explicit(self):
        from tests_native.test_product import task_input
        state = Path(self.temp.name) / "existing-state"
        task = load_task(task_input())
        write(state / "task.json", dict(task=task, taskDigest=digest(task)))
        original = live.git
        def fail_push(root, *args, **kwargs):
            if args[0] == "push":
                raise Blocked("Fixture push failure")
            return original(root, *args, **kwargs)
        with patch.object(live, "ROOT", self.root), patch.object(live, "git", side_effect=fail_push), redirect_stdout(StringIO()):
            output = Path(self.temp.name) / "reports"
            self.assertEqual(live.main(["report", "--state", str(state), "--publish-evidence", "--runs-dir", str(output)]), 1)
            receipt = read(next(output.glob("*/publication.json")))
            self.assertEqual(receipt["status"], "PUBLICATION_FAILED")
            self.assertTrue(list(output.glob("*/report.json")))


if __name__ == "__main__":
    unittest.main()
