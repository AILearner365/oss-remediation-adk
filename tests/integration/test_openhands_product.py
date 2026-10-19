"""Offline vertical product journeys with real Git and deterministic evidence.

Only model transport, build and scanner results are substituted. These tests
are not evidence of a Vertex run or live GitHub delivery.
"""
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from wsgiref.simple_server import make_server
import threading

from autonomous_oss_remediation_agent.models import (CommandResult, ConstraintBaseline,
    ScanReport, ScanOutcome, VulnerabilityFinding)
from openhands_shared.baseline import BaselineRunEvidence
from openhands_shared.product import Product, default_config, REAL_URL, REAL_REF, BUILD, bridge
from openhands_shared.server import ProductApi
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.validation import SharedValidationService
from tests.integration.test_openhands_shared_validation import FakeValidator, report


class NativeServer:
    def __init__(self):
        self.conversations = {}
        self.run_calls = 0
        self.lose_run_response = False

    def __call__(self, method, path, value=None, **kwargs):
        if path == "/server_info":
            return {k: "1.55.1" for k in ("version", "sdk_version", "tools_version")}
        if path == "/api/conversations?include_skills=true":
            uid = value["conversation_id"]
            self.conversations[uid] = {**copy.deepcopy(value), "id": uid, "execution_status": "idle"}
            return self.conversations[uid]
        uid = path.split("/")[3].split("?")[0]
        if path.endswith("/events"):
            assert value["run"] is False
            return {"id": "initial-message"}
        if "/events/search" in path:
            return {"items": [{"id": "initial-message", "kind": "MessageEvent"}]}
        if path.endswith("/run"):
            self.run_calls += 1
            self.conversations[uid]["execution_status"] = "running"
            if self.lose_run_response:
                raise ConnectionError("Response lost after accepted native run")
            return {}
        return self.conversations[uid]


class ProductJourneys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.git("init", "-b", "main-runrunning", str(self.seed))
        (self.seed / "pom.xml").write_text("<project><version>1.0</version></project>\n")
        self.git("-C", str(self.seed), "add", ".")
        self.git("-C", str(self.seed), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "baseline")
        self.sha = self.git("-C", str(self.seed), "rev-parse", "HEAD")
        self.remote = self.root / "remote.git"
        self.git("clone", "--bare", str(self.seed), str(self.remote))
        scanner = self.root / "scanner"
        scanner.write_text("offline scanner identity only")
        self.config = default_config(self.root / "durable")
        self.config.update(scanner=str(scanner))
        self.config["repositories"][0].update(expectedCommit=self.sha, originUrl=str(self.remote))
        self.native = NativeServer()
        self.product = Product(self.config, http=self.native)
        self.key = "k" * 48
        self.api = ProductApi(self.product, self.key)
        self.context = patch.object(bridge, "remediation_agent_context", return_value={
            "skills": [{"name": "dependency-remediation-decision"}, {"name": "maven-dependency-evidence"}],
            "system_message_suffix": "Existing guidance"})
        self.context.start()
        self.baseline = patch("openhands_shared.baseline.ExistingDeterministicBaselineRunner.run",
            return_value=BaselineRunEvidence((CommandResult([BUILD], str(self.seed), 0),),
                ScanReport(True, (VulnerabilityFinding(vulnerability_id="CVE-OFFLINE-1", aliases=(), severity="HIGH",
                    group_id="example", artifact_id="demo", package_name="example:demo", version="1.0"),),
                    None, "scan.json", outcome=ScanOutcome.COMPLETED_WITH_FINDINGS),
                ConstraintBaseline(java_versions=("21",), spring_boot_versions=("4.0.6",)),
                {"version": "2.6.0"}, {"maven": {"mode": "system"}}))
        self.baseline.start()

    def tearDown(self):
        self.product.close()
        self.context.stop()
        self.baseline.stop()
        self.temp.cleanup()

    @staticmethod
    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()

    def call(self, path="", method="GET", body=None, key="submission-1", authenticated=True):
        payload = b"" if body is None else json.dumps(body).encode()
        env = {"PATH_INFO": "/v1/remediations" + path, "REQUEST_METHOD": method,
            "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(payload)),
            "wsgi.input": io.BytesIO(payload), "HTTP_IDEMPOTENCY_KEY": key,
            "HTTP_AUTHORIZATION": "Bearer " + self.key if authenticated else ""}
        status = []
        data = self.api(env, lambda s, headers: status.append(s))
        return status[0], json.loads(b"".join(data))

    def submit(self, mode="none"):
        value = {"repository": {"url": REAL_URL, "baseRef": REAL_REF},
            "objective": "Remediate actionable Maven vulnerabilities with independent verification.",
            "intelligence": {"sbri": {"mode": "disabled"}}, "delivery": {"mode": mode, "draft": True}}
        status, result = self.call(method="POST", body=value)
        self.assertEqual(status, "202 Accepted", result)
        return result["taskId"], value

    def ready(self, mode="none"):
        task, value = self.submit(mode)
        self.product.advance(task, "QUEUED")
        self.assertEqual(self.product.status(task)["productPhase"], "AWAITING_EXECUTION_AUTHORIZATION")
        self.assertEqual(self.native.run_calls, 0)
        return task, value

    def run_task(self, task):
        offer = self.product.status(task)["executionOffer"]
        status, body = self.call("/" + task + "/execute", "POST", offer)
        self.assertEqual(status, "202 Accepted", body)
        self.product.advance(task, "AUTHORIZED")
        return self.product.store.get_openhands_runtime(task)

    def validate(self, task, passed=True, remaining=0):
        runtime = self.product.store.get_openhands_runtime(task)
        Path(runtime.workspace_path, "pom.xml").write_text("<project><version>1.1</version></project>\n")
        _, config = load_stop_hook_config(self.product.hook(task))
        return SharedValidationService(self.product.store, config,
            runner=FakeValidator([report(passed=passed, remaining=remaining)])).handle_stop(task)

    def test_api_submit_native_validation_result_restart(self):
        task, value = self.ready()
        self.assertEqual(self.call(method="POST", body=value)[1]["taskId"], task)
        runtime = self.run_task(task)
        response = self.validate(task)
        self.assertEqual(response.decision.value, "ALLOW")
        self.native.conversations[runtime.conversation_id]["execution_status"] = "finished"
        self.product.observe(task)
        status, result = self.call("/" + task + "/result")
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["task"]["productPhase"], "ACCEPTED")
        self.assertEqual(result["result"]["outcome"], "ACCEPTED")
        self.assertEqual(len(result["evidence"]["validationAttempts"]), 1)
        self.assertTrue(self.call("/" + task + "/diff")[1]["diff"])
        report_id = result["evidence"]["validationAttempts"][0]["reportArtifactId"]
        self.assertEqual(self.call("/" + task + "/artifacts/" + report_id)[0], "200 OK")
        reopened = Product(self.config, http=self.native)
        self.assertEqual(reopened.result(task), self.product.result(task))
        self.assertEqual(self.native.run_calls, 1)

    def test_failed_validation_feedback_and_bounded_outcome(self):
        task, _ = self.ready()
        runtime = self.run_task(task)
        failure = self.validate(task, passed=False, remaining=1)
        self.assertEqual(failure.decision.value, "DENY")
        self.assertIn("DETERMINISTIC_VALIDATION_FAILED", failure.additional_context)
        self.native.conversations[runtime.conversation_id]["execution_status"] = "finished"
        self.product.observe(task)
        result = self.product.result(task)
        self.assertFalse(result["task"]["validation"]["accepted"])
        self.assertEqual(result["task"]["productPhase"], "BOUNDED_FAILURE")

    def test_lost_native_response_and_restart_never_run_twice(self):
        task, _ = self.ready()
        self.native.lose_run_response = True
        self.run_task(task)
        self.product.phase(task, "DISPATCHING")
        reopened = Product(self.config, http=self.native)
        reopened.start()
        reopened.close()
        self.assertEqual(reopened.job(task)["phase"], "OBSERVING")
        reopened.observe(task)
        self.assertEqual(self.native.run_calls, 1)

    def test_unknown_dispatch_idle_requires_recovery_without_replay(self):
        task, _ = self.ready()
        self.product.store.claim_execution(task, "product-" + task)
        self.product.phase(task, "RECOVERY_REQUIRED")
        with self.assertRaises(ValueError):
            self.product.reconcile(task)
        self.assertEqual(self.native.run_calls, 0)

    def test_changed_tree_after_pass_never_finalizes(self):
        task, _ = self.ready()
        runtime = self.run_task(task)
        self.validate(task)
        Path(runtime.workspace_path, "pom.xml").write_text("changed after PASS")
        self.native.conversations[runtime.conversation_id]["execution_status"] = "finished"
        with self.assertRaisesRegex(ValueError, "validated tree"):
            self.product.observe(task)
        self.assertIsNone(self.product.store.get_result(task))

    def test_auth_input_boundary_and_no_implicit_execution(self):
        self.assertEqual(self.call(authenticated=False)[0], "401 Unauthorized")
        task, value = self.submit()
        value["objective"] += " changed"
        self.assertEqual(self.call(method="POST", body=value)[0], "409 Conflict")
        self.assertEqual(self.call("/" + task + "/execute", "POST", {"authorize": True})[0], "400 Bad Request")
        self.assertEqual(self.native.run_calls, 0)
        value["repository"]["url"] = "https://evil.example/repo.git"
        self.assertEqual(self.call(method="POST", body=value, key="other")[0], "400 Bad Request")

    def test_cli_is_http_client_of_same_api(self):
        from openhands_shared.cli import main
        key = self.root / "key"
        key.write_text(self.key)
        task, _ = self.submit()
        with make_server("127.0.0.1", 0, self.api) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with patch("sys.stdout", new_callable=io.StringIO) as output:
                    rc = main(["--url", f"http://127.0.0.1:{server.server_port}", "--key-file", str(key), "status", task])
                self.assertEqual(rc, 0)
                self.assertEqual(json.loads(output.getvalue())["taskId"], task)
            finally:
                server.shutdown()
                worker.join()

    def test_delivery_push_and_pr_response_loss_reconcile_exact_branch(self):
        import openhands_pr_delivery as delivery
        from openhands_shared.product import native
        task, _ = self.ready("github_pr")
        runtime = self.run_task(task)
        source = Path(runtime.workspace_path) / "src/main/java/Compatibility.java"
        source.parent.mkdir(parents=True)
        source.write_text("class Compatibility {}\n")
        self.git("-C", runtime.workspace_path, "add", "src/main/java/Compatibility.java")
        self.validate(task)
        self.native.conversations[runtime.conversation_id]["execution_status"] = "finished"
        self.product.observe(task)
        original_git = delivery.git
        pushes, pulls = [], []
        lose_response = [True]
        lose_push_response = [True]

        def git_local(path, *args):
            if args[0] == "push":
                pushes.append(args)
                args = tuple(str(self.remote) if a == delivery.URL else a for a in args)
                result = original_git(path, *args)
                if lose_push_response[0]:
                    lose_push_response[0] = False
                    raise ConnectionError("Git push response lost after remote accepted commit")
                return result
            return original_git(path, *args)

        def github(method, endpoint, token, data=None):
            if endpoint == "/branches/main-runrunning":
                return {"commit": {"sha": self.sha}}
            if endpoint.startswith("/branches/"):
                from urllib.parse import unquote
                branch = unquote(endpoint[len("/branches/"):])
                result = subprocess.run(["git", "--git-dir", str(self.remote), "rev-parse", "refs/heads/" + branch],
                    capture_output=True, text=True)
                if result.returncode:
                    raise ValueError("GitHub API delivery request failed with HTTP 404")
                return {"commit": {"sha": result.stdout.strip()}}
            if method == "GET" and endpoint.startswith("/pulls?"):
                return pulls
            if method == "POST" and endpoint == "/pulls":
                commit = self.git("--git-dir", str(self.remote), "rev-parse", "refs/heads/" + data["head"])
                pull = {"html_url": "https://github.com/" + delivery.REPO + "/pull/123", "number": 123,
                    "head": {"sha": commit, "ref": data["head"]},
                    "base": {"ref": delivery.BASE, "repo": {"full_name": delivery.REPO}},
                    "draft": True, "state": "open"}
                pulls.append(pull)
                if lose_response[0]:
                    lose_response[0] = False
                    raise ConnectionError("GitHub PR response lost after creation")
                return pull
            raise AssertionError(endpoint)

        with patch.object(native, "http", self.native), patch.object(delivery, "git", side_effect=git_local), \
                patch.object(delivery, "request_github", side_effect=github), patch.dict("os.environ", {"GITHUB_TOKEN": "fake-only"}):
            plan = self.product.delivery_plan(task)
            self.assertIn("src/main/java/Compatibility.java", plan["changedFiles"])
            approval = {"authorize": True, **{k: plan[k] for k in ("baseCommit", "validatedTree", "branch")}}
            self.product.authorize_delivery(task, approval)
            with self.assertRaises(ConnectionError):
                self.product.advance(task, "DELIVERY_AUTHORIZED")
            self.product.phase(task, "RECOVERY_REQUIRED")
            self.assertEqual(len(pushes), 1)
            self.assertEqual(len(pulls), 0)
            reopened = Product(self.config, http=self.native)
            reopened.authorize_delivery(task, approval)
            with self.assertRaises(ConnectionError):
                reopened.advance(task, "DELIVERY_AUTHORIZED")
            reopened.phase(task, "RECOVERY_REQUIRED")
            self.assertEqual(len(pulls), 1)
            commit = reopened.delivery_state(task)["commit_sha"]
            self.git("--git-dir", str(self.remote), "update-ref", "refs/heads/" + plan["branch"], self.sha)
            reopened.authorize_delivery(task, approval)
            with self.assertRaisesRegex(ValueError, "never overwrite"):
                reopened.advance(task, "DELIVERY_AUTHORIZED")
            self.assertEqual(len(pushes), 1)
            reopened.phase(task, "RECOVERY_REQUIRED")
            self.git("--git-dir", str(self.remote), "update-ref", "refs/heads/" + plan["branch"], commit)
            reopened.authorize_delivery(task, approval)
            reopened.advance(task, "DELIVERY_AUTHORIZED")
            self.assertEqual(reopened.status(task)["productPhase"], "DELIVERED")
            self.assertEqual(reopened.result(task)["result"]["delivery"]["pullRequestUrl"], pulls[0]["html_url"])
            self.assertEqual(len(pushes), 1)
            self.assertEqual(len(pulls), 1)
            self.assertEqual(self.git("-C", runtime.workspace_path, "rev-parse", "HEAD"), self.sha)
            self.assertEqual(self.git("--git-dir", str(self.remote), "rev-parse", REAL_REF), self.sha)

    def test_restart_during_preparation_retains_identity_and_requires_recovery(self):
        task, _ = self.submit()
        self.product.phase(task, "PREPARING")
        reopened = Product(self.config, http=self.native)
        reopened.start()
        reopened.close()
        self.assertEqual(reopened.job(task)["phase"], "RECOVERY_REQUIRED")
        self.assertEqual(len(reopened.tasks()), 1)
        self.assertEqual(self.native.run_calls, 0)

    def test_restart_gates_an_authorized_but_unclaimed_model_run(self):
        task, _ = self.ready()
        self.product.authorize_execution(task, self.product.status(task)["executionOffer"])
        reopened = Product(self.config, http=self.native)
        reopened.start()
        reopened.close()
        self.assertEqual(reopened.status(task)["productPhase"], "AWAITING_EXECUTION_AUTHORIZATION")
        self.assertEqual(reopened.job(task)["execution_authorized"], 0)
        self.assertEqual(self.native.run_calls, 0)
        self.assertIsNone(reopened.store.get_execution_claim(task))

    def test_changed_native_budget_is_blocked_before_any_execution_claim(self):
        task, _ = self.ready()
        runtime = self.product.store.get_openhands_runtime(task)
        self.native.conversations[runtime.conversation_id]["max_iterations"] = 100
        self.product.authorize_execution(task, self.product.status(task)["executionOffer"])
        with self.assertRaisesRegex(bridge.HandoffError, "iteration budget"):
            self.product.advance(task, "AUTHORIZED")
        self.assertEqual(self.native.run_calls, 0)
        self.assertIsNone(self.product.store.get_execution_claim(task))

    def test_delivery_plan_includes_independently_validated_agent_commits(self):
        from openhands_shared.product import native
        task, _ = self.ready("github_pr")
        runtime = self.run_task(task)
        workspace = runtime.workspace_path
        Path(workspace, "README.md").write_text("Compatibility explanation\n")
        self.git("-C", workspace, "add", "README.md")
        self.git("-C", workspace, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-m", "Agent compatibility change")
        self.validate(task)
        self.native.conversations[runtime.conversation_id]["execution_status"] = "finished"
        self.product.observe(task)
        with patch.object(native, "http", self.native):
            plan = self.product.delivery_plan(task)
        self.assertEqual(plan["changedFiles"], ["README.md", "pom.xml"])
        self.assertEqual(plan["baseCommit"], self.sha)

    def test_low_storage_blocks_paid_dispatch_but_keeps_status_readable(self):
        from types import SimpleNamespace
        task, _ = self.ready()
        with patch("openhands_shared.product.shutil.disk_usage", return_value=SimpleNamespace(free=1)):
            status, value = self.call("/" + task + "/execute", "POST", self.product.status(task)["executionOffer"])
        self.assertEqual(status, "409 Conflict")
        self.assertEqual(value["code"], "INSUFFICIENT_STORAGE")
        self.assertEqual(self.call("/" + task)[0], "200 OK")
        self.assertIsNone(self.product.store.get_execution_claim(task))
        self.assertEqual(self.native.run_calls, 0)


if __name__ == "__main__":
    unittest.main()
