"""Offline boundary tests. Test doubles are not live remediation evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from native_remediation import delivery, journal, native, repository, runtime, validation
from native_remediation.contract import load_task
from native_remediation.files import Blocked, digest, read, write


def task_input(sha="a" * 40):
    return dict(repository="AILearner365/maven-multimodule-app", base_branch="main-runrunning", base_sha=sha,
        goal="Resolve baseline vulnerabilities without regressions", policy=dict(minimum_tests=1),
        delivery=dict(repository="AILearner365/maven-multimodule-app", base_branch="main-runrunning", draft=True))


def evaluation(tree, vulnerable=False):
    return dict(tree=tree, outcome="COMPLETE", reasons=[], tests=2,
        inventory=dict(modules=["app:root"], properties={"app:root": {"java.version": "21"}},
            packages=[dict(name="org.example:library", version="1.0.0" if vulnerable else "1.0.1")], graphs=[]),
        coverage=dict(expected=1, scanned=1, complete=True),
        findings=[dict(package="org.example:library", version="1.0.0", ids=["GHSA-test", "CVE-test"])] if vulnerable else [])


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.workspace = self.state / "workspace"
        self.workspace.mkdir()
        self.git("init")
        self.git("config", "user.name", "Offline Check")
        self.git("config", "user.email", "offline@example.invalid")
        self.git("remote", "add", "origin", "https://github.com/AILearner365/maven-multimodule-app.git")
        (self.workspace / "pom.xml").write_text("<project/>\n")
        self.git("add", "pom.xml")
        self.git("commit", "-m", "baseline")
        self.task = load_task(task_input(self.git("rev-parse", "HEAD")))
        self.bound = dict(task=self.task, taskDigest=digest(self.task),
            conversationId="05f7716a-90bc-4ec5-a90e-01b7a4de5fa0", createdAt=time.time())
        write(self.state / "task.json", self.bound)
        self.baseline = evaluation(self.git("rev-parse", "HEAD^{tree}"), True)
        write(self.state / "baseline.json", self.baseline)

    def git(self, *args):
        return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-C", str(self.workspace),
                                        *args], stderr=subprocess.DEVNULL).decode().strip()

    def candidate(self):
        journal.record(self.state, "intent", {k: ["supported alternative"] if k == "candidates" else "recorded evidence"
                                             for k in journal.INTENT_FIELDS})
        (self.workspace / "pom.xml").write_text("<project><!-- candidate --></project>\n")
        journal.record(self.state, "outcome", {k: "candidate_ready" if k == "goal_status" else "recorded checks"
                                              for k in journal.OUTCOME_FIELDS})
        return repository.snapshot(self.workspace, self.task)

    def accepted(self):
        tree = self.candidate()
        candidate = evaluation(tree)
        accepted = dict(validation.compare(self.baseline, candidate, self.task["policy"]),
            conversationId=self.bound["conversationId"], baseCommit=self.task["base_sha"],
            taskDigest=self.bound["taskDigest"], validatedTree=tree, attempt=1, changedFiles=["pom.xml"])
        write(self.state / "attempts/1/evaluation.json", candidate)
        write(self.state / "attempts/1/validation.json", accepted)
        write(self.state / "feedback.json", accepted)
        return accepted


class ContractTests(unittest.TestCase):
    def test_defaults_are_product_limits_not_smoke_recipe(self):
        task = load_task(task_input())
        self.assertEqual(task["limits"]["max_iterations"], 40)
        self.assertIsNone(task["tools"]["sbri_reference"])
        self.assertNotIn("spring_boot_version", task["policy"])

    def test_reject_bad_identity_delivery_secrets_and_unverifiable_constraints(self):
        cases = []
        for key, value in (("base_sha", "main"), ("repository", "https://evil.invalid/x"),
                           ("delivery", {"draft": False}), ("goal", "refresh_token=secret"),
                           ("constraints", ["Never change runtime behavior"])):
            task = task_input()
            task[key] = value
            cases.append(task)
        for task in cases:
            with self.subTest(task=task), self.assertRaises(Blocked):
                load_task(task)


class RepositoryTests(GitFixture):
    def test_snapshot_captures_committed_staged_untracked_without_index_changes(self):
        (self.workspace / "pom.xml").write_text("committed\n")
        self.git("add", "pom.xml")
        self.git("commit", "-m", "agent edit")
        (self.workspace / "another.xml").write_text("untracked\n")
        index = self.git("write-tree")
        tree = repository.snapshot(self.workspace, self.task)
        self.assertEqual(self.git("write-tree"), index)
        self.assertEqual(set(repository.changed_paths(self.workspace, self.task, tree)), {"pom.xml", "another.xml"})
        with self.assertRaises(Blocked):
            repository.check_paths(self.workspace, self.task, tree)
        destination = self.state / "isolated"
        repository.export(self.workspace, tree, destination)
        (self.workspace / "pom.xml").write_text("later mutation")
        self.assertEqual((destination / "pom.xml").read_text(), "committed\n")

    def test_symlink_candidate_cannot_escape_export(self):
        (self.workspace / "link").symlink_to("/etc/passwd")
        with self.assertRaises(Blocked):
            repository.export(self.workspace, repository.snapshot(self.workspace, self.task), self.state / "export")

    def test_export_attributes_cannot_hide_files_from_validation(self):
        (self.workspace / ".gitattributes").write_text("pom.xml export-ignore\n")
        tree = repository.snapshot(self.workspace, self.task)
        repository.export(self.workspace, tree, self.state / "export")
        self.assertEqual((self.state / "export/pom.xml").read_bytes(), (self.workspace / "pom.xml").read_bytes())

    def test_cycle_intent_must_precede_first_change(self):
        (self.workspace / "pom.xml").write_text("too late")
        with self.assertRaises(Blocked):
            journal.record(self.state, "intent", {k: "evidence" for k in journal.INTENT_FIELDS})


class ScannerTests(unittest.TestCase):
    def test_clean_requires_exact_package_coverage(self):
        packages = [dict(name="org.example:library", version="1.0")]
        payload = dict(results=[dict(packages=[dict(package=dict(packages[0], ecosystem="Maven"))])])
        self.assertTrue(validation.scan_result(payload, packages, 0, "")["coverage"]["complete"])
        for body, code, stderr in ((dict(results=[]), 0, ""), (payload, 1, ""),
                                    (payload, 2, ""), (payload, 0, "error: incomplete extraction")):
            with self.assertRaises(Blocked):
                validation.scan_result(body, packages, code, stderr)

    def test_findings_aliases_and_new_findings(self):
        old = evaluation("base", True)
        new = evaluation("new", True)
        policy = load_task(task_input())["policy"]
        policy["max_remaining_findings"] = 1
        policy["target_ids"] = ["CVE-test"]
        self.assertEqual(validation.compare(old, new, policy)["outcome"], "FAIL")
        new["findings"][0]["ids"] = ["CVE-new"]
        self.assertTrue(validation.compare(old, new, policy)["introduced"])

    def test_build_scan_module_dependency_and_test_unknowns_never_pass(self):
        old = evaluation("base", True)
        policy = load_task(task_input())["policy"]
        for mutate in (lambda n: n.update(outcome="INCONCLUSIVE"),
                       lambda n: n["inventory"].update(packages=[]),
                       lambda n: n["inventory"].update(modules=[]), lambda n: n.update(tests=0)):
            new = evaluation("candidate")
            mutate(new)
            self.assertNotEqual(validation.compare(old, new, policy)["outcome"], "PASS")

    def test_policy_has_no_forced_upgrade_but_enforces_authorized_movement(self):
        old, new = evaluation("base", True), evaluation("candidate")
        policy = load_task(task_input())["policy"]
        new["inventory"]["packages"][0]["version"] = "2.0.0"
        self.assertEqual(validation.compare(old, new, policy)["outcome"], "FAIL")
        policy["allow_major_upgrades"] = True
        self.assertEqual(validation.compare(old, new, policy)["outcome"], "PASS")
        new["inventory"]["packages"][0]["version"] = "2.0.0-RC1"
        self.assertEqual(validation.compare(old, new, policy)["outcome"], "INCONCLUSIVE")


class MavenPipelineTests(GitFixture):
    def test_real_export_with_controlled_maven_osv_process_outputs(self):
        # Offline process-boundary fixture; not proof of live Maven or OSV service.
        calls = []
        def runner(argv, source, timeout, output):
            calls.append(argv)
            result = dict(exitCode=0, timedOut=False, stdout="", stderr="")
            target = source / "target"
            target.mkdir(exist_ok=True)
            if "clean" in argv:
                reports = target / "surefire-reports"
                reports.mkdir()
                (reports / "TEST-unit.xml").write_text('<testsuite tests="2" skipped="0" failures="0" errors="0"/>')
            if validation.DEPENDENCY_GOAL in argv:
                (target / validation.TREE_FILE).write_text(json.dumps(dict(groupId="app", artifactId="root", version="1",
                    children=[dict(groupId="org.example", artifactId="library", version="1.0.1", scope="compile")])) )
                effective = Path(next(a.split("=", 1)[1] for a in argv if a.startswith("-Doutput=")))
                effective.write_text('<project><groupId>app</groupId><artifactId>root</artifactId><version>1</version>'
                    '<properties><java.version>21</java.version></properties></project>')
            if "--version" in argv:
                result["stdout"] = "osv-scanner version: 2.6.0\n"
            if "scan" in argv:
                result["stdout"] = json.dumps(dict(results=[dict(packages=[dict(package=dict(
                    name="org.example:library", version="1.0.1", ecosystem="Maven"))])]))
            write(output, result)
            return result
        result = validation.evaluate(self.workspace, self.baseline["tree"], self.task,
            self.state / "evaluation", deadline=time.time() + 60, runner=runner)
        self.assertEqual(result["outcome"], "COMPLETE", result)
        self.assertEqual(result["tests"], 2)
        self.assertTrue(result["coverage"]["complete"])
        self.assertTrue((self.state / "evaluation/bom.cdx.json").is_file())
        self.assertFalse((self.workspace / "target").exists())
        self.assertIn("-Dverbose=false", calls[1])


class OfflineGitHub:
    """Remote boundary double. No credentials/network are ever consulted."""
    def __init__(self, task, uid):
        self.task, self.uid = task, uid
        self.ref, self.prs, self.posts = None, [], 0
    def request(self, method, endpoint, body=None):
        if endpoint.startswith("/branches/"):
            return dict(commit=dict(sha=self.task["base_sha"]))
        if endpoint.startswith("/git/ref/"):
            return self.ref
        if method == "GET":
            return self.prs
        self.posts += 1
        pr = dict(draft=True, state="open", head=dict(sha=self.ref["object"]["sha"],
            ref=body["head"], repo=dict(full_name=self.task["repository"])),
            base=dict(ref=body["base"], sha=self.task["base_sha"], repo=dict(full_name=self.task["repository"])),
            html_url="https://github.com/" + self.task["repository"] + "/pull/123")
        self.prs = [pr]
        return pr


class DeliveryTests(GitFixture):
    def setUp(self):
        super().setUp()
        self.acceptance = self.accepted()
        self.remote = OfflineGitHub(self.task, self.bound["conversationId"])
        real_text = delivery.text
        def fake_push(repo, *args, **kwargs):
            if args[0] == "push":
                self.assertIn("--force-with-lease=refs/heads/openhands/remediate-" + self.bound["conversationId"] + ":", args)
                self.remote.ref = dict(object=dict(sha=args[-1].split(":")[0]))
                return ""
            return real_text(repo, *args, **kwargs)
        self.patcher = patch.object(delivery, "text", side_effect=fake_push)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_exact_pass_delivers_once_then_reconciles(self):
        first = delivery.deliver(self.state, self.acceptance, github=self.remote)
        second = delivery.deliver(self.state, self.acceptance, github=self.remote)
        self.assertEqual(first, second)
        self.assertEqual(self.remote.posts, 1)
        self.assertEqual(self.git("show", "-s", "--format=%T", first["commit"]), self.acceptance["validatedTree"])
        self.assertEqual(self.git("show", "-s", "--format=%P", first["commit"]), self.task["base_sha"])

    def test_workspace_drift_blocks_before_remote_mutation(self):
        (self.workspace / "pom.xml").write_text("drift")
        with self.assertRaises(Blocked):
            delivery.deliver(self.state, self.acceptance, github=self.remote)
        self.assertEqual(self.remote.posts, 0)

    def test_uncertain_pr_post_does_not_repeat(self):
        delivery.deliver(self.state, self.acceptance, github=self.remote)
        claim = read(self.state / "delivery.json")
        claim["state"] = "PR_POST_STARTED"
        write(self.state / "delivery.json", claim)
        self.remote.prs = []
        with self.assertRaisesRegex(Blocked, "uncertain"):
            delivery.deliver(self.state, self.acceptance, github=self.remote)
        self.assertEqual(self.remote.posts, 1)


class OfflineConversation:
    """Local SDK boundary double only; never live execution evidence."""
    def __init__(self):
        from types import SimpleNamespace
        self.state = SimpleNamespace(execution_status=SimpleNamespace(value="idle"), events=[],
            stats=SimpleNamespace(model_dump=lambda **kw: {}))
        self.runs, self.closed = 0, False
    def send_message(self, text):
        from types import SimpleNamespace
        MessageEvent = type("MessageEvent", (), {})
        event = MessageEvent()
        event.source, event.text = "user", text
        event.llm_message = SimpleNamespace(content=[SimpleNamespace(text=text)])
        self.state.events.append(event)
    def run(self):
        self.runs += 1
        self.state.execution_status.value = "paused"
    def close(self):
        self.closed = True


class RuntimeTests(GitFixture):
    def prepared(self):
        self.bound["executionFramework"] = "standalone-sdk-1.55.1"
        write(self.state / "task.json", self.bound)
        write(self.state / "preparation.json", dict(outcome="COMPLETE",
            conversationId=self.bound["conversationId"], taskDigest=self.bound["taskDigest"],
            repository=self.task["repository"], baseCommit=self.task["base_sha"],
            baseTree=self.baseline["tree"], baselineDigest=digest(self.baseline), completedAt=time.time()))

    def test_missing_incomplete_stale_or_tampered_preparation_blocks_run(self):
        factory = lambda *a: self.fail("No SDK run/restore before evidence gate")
        for mode in ("missing", "incomplete", "stale", "tampered", "wrong_identity", "coverage"):
            self.prepared()
            if mode == "missing":
                (self.state / "preparation.json").unlink()
            elif mode == "tampered":
                write(self.state / "baseline.json", dict(self.baseline, tests=999))
            elif mode == "stale":
                write(self.state / "preparation.json", dict(read(self.state / "preparation.json"), completedAt=0))
            elif mode == "coverage":
                broken = dict(self.baseline, coverage=dict(expected=1, scanned=0, complete=False))
                write(self.state / "baseline.json", broken)
                write(self.state / "preparation.json", dict(read(self.state / "preparation.json"), baselineDigest=digest(broken)))
            else:
                key = "outcome" if mode == "incomplete" else "conversationId"
                write(self.state / "preparation.json", dict(read(self.state / "preparation.json"), **{key: "wrong"}))
            with self.subTest(mode=mode), self.assertRaises((Blocked, FileNotFoundError)):
                runtime.dispatch(self.state, factory=factory)
            write(self.state / "baseline.json", self.baseline)

    def test_preparation_creates_conversation_first_and_never_sends_or_runs(self):
        import shutil
        events = []
        conversation = OfflineConversation()
        def factory(*args):
            events.append("initialize")
            return conversation
        def prepare(state, task):
            events.append("prepare")
            shutil.copytree(self.workspace, state / "workspace")
            return state / "workspace"
        def evaluate(*args, **kwargs):
            events.append("baseline")
            return self.baseline
        destination = self.state / "new"
        runtime.prepare_task(self.task, destination, factory=factory, preparer=prepare,
                             evaluator=evaluate, sandbox_check=lambda task: None)
        self.assertEqual(events, ["initialize", "prepare", "baseline"])
        self.assertEqual(conversation.runs, 0)
        self.assertFalse(conversation.state.events)
        runtime.require_preparation(destination)
        with patch.object(runtime, "verify_base"), patch("native_remediation.sandbox.check"), patch("native_remediation.sandbox.stop_agent"):
            runtime.dispatch(destination, factory=lambda *a: conversation, preflight=lambda task: {})
        self.assertEqual(conversation.runs, 1)
        with self.assertRaises(FileExistsError):
            runtime.prepare_task(self.task, destination, factory=factory)
        broken = self.state / "failed"
        failed_conversation = OfflineConversation()
        with self.assertRaises(Blocked):
            runtime.prepare_task(self.task, broken, factory=lambda *a: failed_conversation, preparer=prepare,
                evaluator=lambda *a, **kw: dict(self.baseline, outcome="INCONCLUSIVE"),
                sandbox_check=lambda task: None)
        self.assertFalse((broken / "preparation.json").exists())
        with self.assertRaises(Blocked):
            runtime.dispatch(broken, factory=lambda *a: self.fail("Must not restore or run"))
        self.assertEqual(failed_conversation.runs, 0)

    def test_successful_gate_dispatches_once_and_recovery_rechecks_receipt(self):
        self.prepared()
        conversation = OfflineConversation()
        with patch.object(runtime, "verify_base"), patch("native_remediation.sandbox.check"), patch("native_remediation.sandbox.stop_agent"):
            runtime.dispatch(self.state, factory=lambda *a: conversation, preflight=lambda task: {})
            self.assertEqual(conversation.runs, 1)
            self.assertEqual(len(conversation.state.events), 1)
            with self.assertRaises(Blocked):
                runtime.dispatch(self.state, factory=lambda *a: conversation)
            # Simulated process restoration uses the persisted native history.
            runtime.dispatch(self.state, resume_reason="offline recovery", factory=lambda *a: conversation,
                             preflight=lambda task: {})
            self.assertEqual(conversation.runs, 2)
            self.assertEqual(len(conversation.state.events), 2)
            (self.state / "preparation.json").unlink()
            with self.assertRaises(Blocked):
                runtime.dispatch(self.state, resume_reason="must block", factory=lambda *a: conversation)
            self.assertEqual(conversation.runs, 2)

    def test_hook_command_returns_explicit_deny_on_invalid_event(self):
        proc = subprocess.run([sys.executable, "-S", "-m", "native_remediation", "hook", "--state", str(self.state)],
                              input="{}", capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["decision"], "deny")

    def test_honest_bounded_failure_terminates_without_validation_or_delivery(self):
        journal.record(self.state, "intent", {k: ["investigated alternative"] if k == "candidates" else "recorded unknown"
                                             for k in journal.INTENT_FIELDS})
        journal.record(self.state, "outcome", {k: "bounded_failure" if k == "goal_status" else "evidence-backed limitation"
                                              for k in journal.OUTCOME_FIELDS})
        event = dict(event_type="Stop", session_id=self.bound["conversationId"],
                     working_dir=str(self.workspace), metadata=dict(reason="agent_finished"))
        result = runtime.hook(self.state, event,
            evaluator=lambda *a, **k: self.fail("Failure must not invoke validation"),
            delivery=lambda *a, **k: self.fail("Failure must not deliver"))
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(read(self.state / "result.json")["outcome"], "BOUNDED_FAILURE")


    def test_hook_pass_and_deny_have_distinct_authority(self):
        tree = self.candidate()
        event = dict(event_type="Stop", session_id=self.bound["conversationId"],
                     working_dir=str(self.workspace), metadata=dict(reason="agent_finished"))
        delivered = []
        def delivery_stub(state, accepted):
            self.assertEqual(accepted["outcome"], "PASS")
            self.assertEqual(accepted["validatedTree"], tree)
            delivered.append(accepted)
            return dict(prUrl="offline-boundary-only", state="DELIVERED")
        response = runtime.hook(self.state, event,
            evaluator=lambda *a, **k: evaluation(tree, True), delivery=delivery_stub)
        self.assertEqual(response["decision"], "deny")
        self.assertFalse(delivered)
        # A repeated Finish in the same cycle reuses failure feedback, not scans.
        cached = runtime.hook(self.state, event,
            evaluator=lambda *a, **k: self.fail("Repeated candidate was rescanned"), delivery=delivery_stub)
        self.assertEqual(cached["decision"], "deny")
        journal.record(self.state, "intent", {k: ["reassessed candidate"] if k == "candidates" else "new investigation"
                                             for k in journal.INTENT_FIELDS})
        journal.record(self.state, "outcome", {k: "candidate_ready" if k == "goal_status" else "new checks"
                                              for k in journal.OUTCOME_FIELDS})
        response = runtime.hook(self.state, event,
            evaluator=lambda *a, **k: evaluation(tree), delivery=delivery_stub)
        self.assertEqual(response["decision"], "allow")
        self.assertEqual(len(delivered), 1)

    def test_native_finished_alone_is_not_product_success(self):
        class Finished:
            def __init__(self):
                from types import SimpleNamespace
                self.state = SimpleNamespace(execution_status=SimpleNamespace(value="finished"),
                    stats=SimpleNamespace(model_dump=lambda **kw: {}))
        self.assertEqual(runtime.status(self.state, Finished())["result"]["outcome"], "BLOCKED")
