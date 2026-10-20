"""P1 regressions on local fixtures only; no inference, target or live delivery."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import time
import unittest
from unittest.mock import patch

from native_remediation import capabilities, native, runtime, validation
from native_remediation.contract import load_task
from native_remediation.files import Blocked, digest, read, write
from tests_native.test_product import GitFixture, OfflineConversation, evaluation, task_input


BOOT = "org.springframework.boot:spring-boot"


def boot_evaluation(modules):
    result = evaluation("fixture")
    inventory = result["inventory"]
    inventory.update(modules=sorted(modules), properties={m: {"java.version": "21"} for m in modules}, graphs=[])
    packages = set()
    for module, versions in modules.items():
        group, artifact = module.split(":")
        versions = (versions,) if isinstance(versions, str) else versions
        packages.update((BOOT, v) for v in versions)
        inventory["graphs"].append(dict(path=artifact + "/target/" + validation.TREE_FILE,
            graph=dict(groupId=group, artifactId=artifact, version="1", children=[dict(
                groupId="org.springframework.boot", artifactId="spring-boot", version=v) for v in versions])))
    inventory["packages"] = [dict(name=n, version=v) for n, v in sorted(packages)]
    result["coverage"].update(expected=len(packages), scanned=len(packages))
    return result


class BootPolicyTests(unittest.TestCase):
    def setUp(self):
        self.before = boot_evaluation({"app:a": "4.0.6", "app:b": "4.1.1"})
        self.policy = load_task(task_input())["policy"]

    def outcome(self, modules):
        return validation.compare(self.before, boot_evaluation(modules), self.policy)["outcome"]

    def test_identical_multiple_versions_have_no_artificial_movement(self):
        self.assertEqual(self.outcome({"app:a": "4.0.6", "app:b": "4.1.1"}), "PASS")
        after = deepcopy(self.before)
        self.before["inventory"]["graphs"] = after["inventory"]["graphs"] = []
        self.assertEqual(validation.compare(self.before, after, self.policy)["outcome"], "PASS")

    def test_module_owned_patch_upgrades_are_not_cross_paired(self):
        self.assertEqual(self.outcome({"app:a": "4.0.8", "app:b": "4.1.2"}), "PASS")
        self.policy["spring_boot"]["patch"] = False
        self.assertEqual(self.outcome({"app:a": "4.0.8", "app:b": "4.1.1"}), "FAIL")

    def test_root_controller_and_module_override_are_compared_independently(self):
        self.before["inventory"]["spring_boot"] = "4.0.6"
        after = boot_evaluation({"app:a": "4.0.8", "app:b": "4.1.1"})
        after["inventory"]["spring_boot"] = "4.0.8"
        self.assertEqual(validation.compare(self.before, after, self.policy)["outcome"], "PASS")
        # Root patch approval must not conceal a module's explicit downgrade.
        overridden = boot_evaluation({"app:a": "4.0.8", "app:b": "4.1.0"})
        overridden["inventory"]["spring_boot"] = "4.0.8"
        self.assertEqual(validation.compare(self.before, overridden, self.policy)["outcome"], "FAIL")
        # Controller policy applies even when modules pin the old resolved versions.
        pinned = deepcopy(self.before)
        pinned["inventory"]["spring_boot"] = "5.0.0"
        self.assertEqual(validation.compare(self.before, pinned, self.policy)["outcome"], "FAIL")

    def test_real_and_mixed_downgrades_fail_even_when_global_sets_match(self):
        for modules in ({"app:a": "4.0.5", "app:b": "4.1.1"},
                        {"app:a": "4.0.8", "app:b": "4.1.0"},
                        {"app:a": "4.1.1", "app:b": "4.0.6"}):
            with self.subTest(modules=modules):
                self.assertEqual(self.outcome(modules), "FAIL")
        self.policy["spring_boot"]["downgrade"] = True
        self.assertEqual(self.outcome({"app:a": "4.0.5", "app:b": "4.1.1"}), "PASS")

    def test_module_minor_and_major_permissions_remain_enforced(self):
        self.policy["spring_boot"]["minor"] = False
        self.assertEqual(self.outcome({"app:a": "4.1.1", "app:b": "4.1.1"}), "FAIL")
        self.assertEqual(self.outcome({"app:a": "5.0.0", "app:b": "4.1.1"}), "FAIL")
        self.policy["spring_boot"]["major"] = True
        self.assertEqual(self.outcome({"app:a": "5.0.0", "app:b": "4.1.1"}), "PASS")

    def test_ambiguous_changed_sets_or_invalid_ownership_never_pass(self):
        after = boot_evaluation({"app:a": "4.0.8", "app:b": "4.1.2"})
        self.before["inventory"]["graphs"] = after["inventory"]["graphs"] = []
        self.assertEqual(validation.compare(self.before, after, self.policy)["outcome"], "INCONCLUSIVE")
        self.before = boot_evaluation({"app:a": ("4.0.6", "4.1.1")})
        after = boot_evaluation({"app:a": ("4.0.8", "4.1.2")})
        self.assertEqual(validation.compare(self.before, after, self.policy)["outcome"], "INCONCLUSIVE")
        after["inventory"]["graphs"][0]["graph"]["artifactId"] = "unknown"
        self.assertEqual(validation.compare(self.before, after, self.policy)["outcome"], "INCONCLUSIVE")


class PreparedFixture(GitFixture):
    def bind(self, **changes):
        self.task = load_task(dict(self.task, **changes))
        self.bound.update(task=self.task, taskDigest=digest(self.task))
        write(self.state / "task.json", self.bound)

    def prepared(self, baseline=None):
        baseline = baseline or self.baseline
        self.bound["executionFramework"] = "standalone-sdk-1.55.1"
        write(self.state / "task.json", self.bound)
        write(self.state / "baseline.json", baseline)
        write(self.state / "preparation.json", dict(outcome="COMPLETE", conversationId=self.bound["conversationId"],
            taskDigest=self.bound["taskDigest"], repository=self.task["repository"], baseCommit=self.task["base_sha"],
            baseTree=self.baseline["tree"], baselineDigest=digest(baseline), completedAt=time.time()))


class StrictBaselineTests(PreparedFixture):
    def test_expired_task_blocks_dispatch_and_recovery_before_authority_or_sdk(self):
        self.prepared()
        self.bound["createdAt"] = time.time() - self.task["limits"]["task_seconds"] - 1
        write(self.state / "task.json", self.bound)
        for reason in (None, "simulated restart after deadline"):
            with self.subTest(reason=reason), patch.object(runtime, "require_independent_authority",
                    side_effect=AssertionError("Expired task reached authority gate")):
                with self.assertRaises(Blocked):
                    runtime.dispatch(self.state, resume_reason=reason,
                        factory=lambda *a: self.fail("Expired task must not initialize or run"))
        self.assertFalse((self.state / "runs").exists())

    def test_invalid_baselines_block_before_authority_or_dispatch(self):
        mutations = [lambda b: b.update(outcome="FAIL"), lambda b: b.update(outcome="INCONCLUSIVE"),
            lambda b: b.update(reasons=["Required check failed"]), lambda b: b.update(tests=0),
            lambda b: b["coverage"].update(complete=False), lambda b: b["coverage"].update(scanned=0),
            lambda b: b["coverage"].update(expected=True),
            lambda b: b["inventory"].update(graphs=[]), lambda b: b["inventory"].update(modules=[]),
            lambda b: b["inventory"].update(packages=[]), lambda b: b.pop("findings"),
            lambda b: b["inventory"]["graphs"][0]["graph"]["children"].clear()]
        for mutate in mutations:
            baseline = deepcopy(self.baseline)
            mutate(baseline)
            self.prepared(baseline)
            with self.subTest(mutate=mutate), patch.object(runtime, "require_independent_authority",
                    side_effect=AssertionError("Invalid baseline reached authority gate")):
                with self.assertRaises(Blocked):
                    runtime.dispatch(self.state, factory=lambda *a: self.fail("No model initialization"))
        self.prepared()
        runtime.require_preparation(self.state)
        with self.assertRaisesRegex(Blocked, "authority separation"):
            runtime.dispatch(self.state)

    def test_incomplete_baseline_never_creates_complete_receipt(self):
        destination = self.state / "failed-baseline"
        conversation = OfflineConversation()
        def preparer(state, task):
            shutil.copytree(self.workspace, state / "workspace")
            return state / "workspace"
        broken = deepcopy(self.baseline)
        broken["inventory"]["graphs"] = []
        with self.assertRaises(Blocked):
            runtime.prepare_task(self.task, destination, factory=lambda *a: conversation,
                preparer=preparer, evaluator=lambda *a, **kw: broken)
        self.assertFalse((destination / "preparation.json").exists())
        self.assertEqual(conversation.runs, 0)
        self.assertFalse(conversation.state.events)

    def test_configured_checks_are_required_on_baseline_and_candidate(self):
        self.bind(tools=dict(checks=[["required-health-check"]]),
                  constraints=[dict(description="Required invariant", check=["required-invariant"])])
        def runner(argv, source, timeout, output):
            result = dict(exitCode=0, timedOut=False, stdout="", stderr="")
            target = source / "target"
            target.mkdir(exist_ok=True)
            if "clean" in argv:
                reports = target / "surefire-reports"
                reports.mkdir()
                (reports / "TEST-fixture.xml").write_text('<testsuite tests="2"/>')
            elif validation.DEPENDENCY_GOAL in argv:
                write(target / validation.TREE_FILE, self.baseline["inventory"]["graphs"][0]["graph"])
                effective = Path(next(a.split("=", 1)[1] for a in argv if a.startswith("-Doutput=")))
                effective.write_text('<project><groupId>app</groupId><artifactId>root</artifactId><version>1</version></project>')
            elif "--version" in argv:
                result["stdout"] = "osv-scanner version: 2.6.0"
            elif "scan" in argv:
                result["stdout"] = json.dumps(dict(results=[dict(packages=[dict(package=dict(
                    name="org.example:library", version="1.0.0", ecosystem="Maven"))])]))
            elif argv[0] == "required-invariant":
                result["exitCode"] = 1
            write(output, result)
            return result
        for phase in ("baseline", "candidate"):
            result = validation.evaluate(self.workspace, self.baseline["tree"], self.task,
                self.state / phase, deadline=time.time() + 30, runner=runner)
            self.assertEqual(result["outcome"], "FAIL")
            self.assertEqual(result["commands"][-1]["name"], "acceptance-check-1")
            with self.assertRaises(Blocked):
                validation.require_baseline(result, self.baseline["tree"], self.task)


class SbriCorrectionTests(PreparedFixture):
    def setUp(self):
        super().setUp()
        (self.workspace / "pom.xml").write_text('<project><parent><groupId>org.springframework.boot</groupId>'
            '<artifactId>spring-boot-starter-parent</artifactId><version>4.0.6</version></parent></project>')
        self.git("add", "pom.xml")
        self.git("commit", "-m", "SBRI local fixture baseline")
        self.baseline["tree"] = self.git("rev-parse", "HEAD^{tree}")
        self.baseline["inventory"]["spring_boot"] = "4.0.6"
        write(self.state / "baseline.json", self.baseline)
        self.backend = self.state / "sbri-fixture"
        self.backend.write_text("#!/bin/sh\nexit 0\n")
        self.backend.chmod(0o700)
        self.bind(base_sha=self.git("rev-parse", "HEAD"), sbri=dict(mode="on", executable=str(self.backend), versions=["4.0.8"], cache_seconds=100,
                            retry_seconds=2), tools=dict(profiles=["integration", "compat"]),
                  limits=dict(max_sbri_calls=8))
        self.calls = []

    def response(self, argv):
        versions = argv[argv.index("--releases") + 1].split(",") if "--releases" in argv else ["4.1.1"]
        return dict(schema_version="1.0", status="SUCCESS", errors=[],
            releases=[dict(version=v, assessment_status="COMPLETE", rank=1) for v in ["4.0.6", *versions]],
            execution=dict(profiles=argv[argv.index("--profiles") + 1].split(","),
                scopes=argv[argv.index("--scopes") + 1].split(","),
                release_selection=dict(resolved_candidates=versions)))

    def runner(self, argv, source, timeout, output):
        self.calls.append(argv)
        destination = Path(argv[argv.index("--output") + 1])
        write(destination / "result.json", self.response(argv))
        return dict(exitCode=0, timedOut=False)

    def test_profiles_settings_cache_reuse_and_agent_interface(self):
        first = capabilities.sbri(self.state, scopes=["runtime"], runner=self.runner)
        self.assertEqual(first["status"], "COMPLETE")
        self.assertEqual(first["request"]["profiles"], ["integration", "compat"])
        self.assertEqual(self.calls[0][self.calls[0].index("--profiles") + 1], "integration,compat")
        self.assertIn("--timeout", self.calls[0])
        self.assertTrue(capabilities.sbri(self.state, scopes=["runtime"], runner=self.runner)["reused"])
        self.assertEqual(len(self.calls), 1)

    def test_generated_argv_against_actual_historical_cli_with_fixture_evaluator(self):
        # Actual retained CLI parser/forwarding, NOT a live SBRI backend proof.
        import contextlib
        import io
        import sys
        from types import ModuleType
        historical = subprocess.run(["git", "show",
            "e5d160cb6080e5c6ed8fef16ca4ba42ab6106c8f:spring_boot_release_intelligence/sbri_cli.py"],
            cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True)
        if historical.returncode:
            self.skipTest("Pinned historical CLI source not available in this checkout")
        modules = {name: ModuleType(name) for name in ("sbri_contract_fixture", "sbri_contract_fixture.report",
            "sbri_contract_fixture.release_selection", "sbri_contract_fixture.standalone")}
        seen, active = {}, {}
        class Evaluator:
            def __init__(self, project, releases, output, **kwargs):
                seen.update(kwargs)
                self.output = output
            def evaluate(inner):
                inner.output.mkdir(parents=True)
                return self.response(active["argv"])
        modules["sbri_contract_fixture.report"].write_report = lambda *a: None
        modules["sbri_contract_fixture.release_selection"].select_candidates = lambda baseline, **kw: (
            kw["versions"].split(","), dict(resolved_candidates=kw["versions"].split(",")))
        modules["sbri_contract_fixture.release_selection"].validate_resolved_selection = lambda *a: self.fail("Unused selection")
        modules["sbri_contract_fixture.standalone"].Evaluator = Evaluator
        modules["sbri_contract_fixture.standalone"].discover_boot_version = lambda *a: dict(version="4.0.6")
        namespace = dict(__name__="sbri_contract_fixture.cli", __package__="sbri_contract_fixture")
        with patch.dict(sys.modules, modules):
            exec(compile(historical.stdout, "pinned-historical-sbri-cli.py", "exec"), namespace)
            def actual_cli(argv, source, timeout, output):
                active["argv"] = argv
                with contextlib.redirect_stdout(io.StringIO()):
                    code = namespace["main"](argv[1:])
                return dict(exitCode=code, timedOut=False)
            result = capabilities.sbri(self.state, runner=actual_cli)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(seen["profiles"], self.task["tools"]["profiles"])
        self.assertEqual(seen["scopes"], self.task["sbri"]["scopes"])
        self.assertEqual(seen["timeout"], self.task["limits"]["command_seconds"])

    def test_ordinary_failures_and_malformed_responses_are_retained(self):
        def invalid(payload, code=0, timed_out=False):
            def run(argv, cwd, timeout, output):
                destination = Path(argv[argv.index("--output") + 1])
                destination.mkdir(parents=True)
                (destination / "result.json").write_text(payload)
                return dict(exitCode=code, timedOut=timed_out)
            return run
        runners = [invalid("not-json"), invalid("[]"), invalid('{}'), invalid('{"status":"SUCCESS","releases":[]}'),
                   invalid('{}', code=2), invalid('{}', timed_out=True)]
        for runner in runners:
            result = capabilities.sbri(self.state, refresh=True, runner=runner)
            self.assertEqual(result["status"], "INCONCLUSIVE")
            self.assertTrue(result["reasons"])
            self.assertTrue((self.state / result["evidence"] / "result.json").is_file())

    def test_missing_backend_execution_and_missing_report_are_bounded(self):
        def vanished(*a):
            raise FileNotFoundError("fixture disappeared")
        self.assertEqual(capabilities.sbri(self.state, runner=vanished)["status"], "UNAVAILABLE")
        result = capabilities.sbri(self.state, refresh=True, runner=lambda *a: dict(exitCode=0, timedOut=False))
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIn("missing", result["reasons"][0])

    def test_real_fixture_command_failure_preserves_private_output_and_safe_feedback(self):
        from native_remediation.files import command
        self.backend.write_text("#!/bin/sh\nprintf 'sbri: Maven profile dependency unavailable; api_key=fixture-secret\\n' >&2\nexit 2\n")
        result = capabilities.sbri(self.state, runner=command)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        private = read(self.state / result["commandEvidence"])
        self.assertEqual(private["exitCode"], 2)
        self.assertIn("Maven profile dependency unavailable", private["stderr"])
        self.assertIn("fixture-secret", private["stderr"])
        self.assertNotIn("fixture-secret", str(result["reasons"]))
        try:
            import openhands.sdk
        except ImportError:
            pass  # Without SDK, feedback points to private evidence, not raw text.
        else:
            self.assertIn("Maven profile dependency unavailable", str(result["reasons"]))
        self.assertEqual((self.state / result["commandEvidence"]).stat().st_mode & 0o777, 0o600)

    def test_exception_diagnostic_retains_actual_reason(self):
        def vanished(*args):
            raise FileNotFoundError("SBRI fixture launcher disappeared")
        result = capabilities.sbri(self.state, runner=vanished)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(read(self.state / result["executionErrorEvidence"]),
            dict(type="FileNotFoundError", message="SBRI fixture launcher disappeared"))
        self.assertIsNone(result["commandEvidence"])

    def test_partial_or_wrong_profiles_and_scopes_never_mean_complete(self):
        for field in ("partial", "profiles", "scopes", "missing-release"):
            def run(argv, cwd, timeout, output):
                payload = self.response(argv)
                if field == "partial":
                    payload["releases"][-1]["assessment_status"] = "FAILED"
                elif field == "missing-release":
                    payload["releases"] = payload["releases"][:1]
                else:
                    payload["execution"][field] = []
                write(Path(argv[argv.index("--output") + 1]) / "result.json", payload)
                return dict(exitCode=0, timedOut=False)
            self.assertEqual(capabilities.sbri(self.state, refresh=True, runner=run)["status"], "INCONCLUSIVE")

    def test_cache_expiry_known_failure_retry_and_operator_refresh(self):
        with patch("native_remediation.capabilities.time.time", return_value=1000):
            first = capabilities.sbri(self.state, runner=self.runner)
        with patch("native_remediation.capabilities.time.time", return_value=1001):
            self.assertTrue(capabilities.sbri(self.state, runner=self.runner)["reused"])
        with patch("native_remediation.capabilities.time.time", return_value=1101):
            second = capabilities.sbri(self.state, runner=self.runner)
        self.assertNotEqual(first["evidence"], second["evidence"])
        third = capabilities.sbri(self.state, refresh=True, runner=lambda *a: dict(exitCode=2, timedOut=False))
        self.assertEqual(third["status"], "INCONCLUSIVE")
        self.assertTrue(capabilities.sbri(self.state, runner=self.runner)["reused"])
        with patch("native_remediation.capabilities.time.time", return_value=third["completedAt"] + 3):
            self.assertEqual(capabilities.sbri(self.state, runner=self.runner)["status"], "COMPLETE")

    def test_tree_requests_profiles_scanner_and_backend_identity_invalidate_cache(self):
        results = [capabilities.sbri(self.state, runner=self.runner)]
        results.append(capabilities.sbri(self.state, ranges=["4.1.x"], runner=self.runner))
        results.append(capabilities.sbri(self.state, scopes=["test"], runner=self.runner))
        self.backend.write_text("#!/bin/sh\n# changed backend\nexit 0\n")
        results.append(capabilities.sbri(self.state, runner=self.runner))
        (self.workspace / "pom.xml").write_text((self.workspace / "pom.xml").read_text() + "\n<!-- changed -->")
        results.append(capabilities.sbri(self.state, runner=self.runner))
        self.bind(tools=dict(profiles=["other"], osv="/missing/scanner"))
        results.append(capabilities.sbri(self.state, runner=self.runner))
        self.assertEqual(len({r["evidence"] for r in results}), len(results))

    def test_interrupted_claim_is_not_replayed_and_integrity_errors_block(self):
        def interrupted(*a):
            raise RuntimeError("Simulated process interruption")
        with self.assertRaises(RuntimeError):
            capabilities.sbri(self.state, runner=interrupted)
        result = capabilities.sbri(self.state, refresh=True, runner=lambda *a: self.fail("No duplicate execution"))
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIn("Interrupted", result["reason"])
        claim = self.state / result["evidence"] / "intent.json"
        write(claim, dict(read(claim), request={}))
        with self.assertRaisesRegex(Blocked, "checksum"):
            capabilities.sbri(self.state, runner=self.runner)

    def test_cached_result_raw_evidence_and_authority_failures_still_block(self):
        result = capabilities.sbri(self.state, runner=self.runner)
        write(self.state / result["resultPath"], dict(status="tampered"))
        with self.assertRaisesRegex(Blocked, "canonical result changed"):
            capabilities.sbri(self.state, runner=self.runner)
        with self.assertRaisesRegex(Blocked, "authority separation"):
            capabilities.sbri(self.state)

    def test_summary_tampering_and_task_identity_mismatch_block(self):
        result = capabilities.sbri(self.state, runner=self.runner)
        summary = self.state / result["evidence"] / "result.json"
        write(summary, dict(read(summary), tree="tampered"))
        with self.assertRaisesRegex(Blocked, "integrity"):
            capabilities.sbri(self.state, runner=self.runner)
        bound = read(self.state / "task.json")
        bound["taskDigest"] = "tampered"
        write(self.state / "task.json", bound)
        with self.assertRaisesRegex(Blocked, "digest"):
            capabilities.sbri(self.state, runner=self.runner)

    def test_source_and_binding_changes_during_execution_block(self):
        def source_changed(argv, cwd, timeout, output):
            result = self.runner(argv, cwd, timeout, output)
            (self.workspace / "pom.xml").write_text((self.workspace / "pom.xml").read_text() + "\n<!-- drift -->")
            return result
        with self.assertRaisesRegex(Blocked, "Source changed"):
            capabilities.sbri(self.state, runner=source_changed)
        def binding_changed(argv, cwd, timeout, output):
            result = self.runner(argv, cwd, timeout, output)
            write(self.state / "task.json", dict(read(self.state / "task.json"), createdAt=0))
            return result
        with self.assertRaisesRegex(Blocked, "Task binding changed"):
            capabilities.sbri(self.state, runner=binding_changed)

    def test_uncertain_timeout_never_replays_but_completed_failures_can_retry(self):
        def unknown(*a):
            raise subprocess.TimeoutExpired("fixture", 1)
        result = capabilities.sbri(self.state, runner=unknown)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertFalse(result["retryable"])
        with patch("native_remediation.capabilities.time.time", return_value=result["completedAt"] + 1000):
            repeated = capabilities.sbri(self.state, refresh=True, runner=lambda *a: self.fail("Uncertain execution cannot replay"))
        self.assertTrue(repeated["reused"])

    def test_call_budget_is_bounded_optional_intelligence_not_acceptance(self):
        self.bind(limits=dict(max_sbri_calls=1))
        capabilities.sbri(self.state, runner=self.runner)
        result = capabilities.sbri(self.state, refresh=True, runner=lambda *a: self.fail("Budget exhausted"))
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIn("budget exhausted", result["reason"])
        self.assertFalse((self.state / "attempts").exists())
        self.assertFalse((self.state / "delivery.json").exists())

    def test_pre_edit_and_agent_use_same_profiled_result_without_model(self):
        destination = self.state / "prepared"
        conversation = OfflineConversation()
        def prepare(state, task):
            shutil.copytree(self.workspace, state / "workspace")
            return state / "workspace"
        original = capabilities.sbri
        # Fixture execution seam only, not a replacement production authority check.
        with patch.object(capabilities, "sbri", side_effect=lambda state: original(state, runner=self.runner)):
            runtime.prepare_task(self.task, destination, factory=lambda *a: conversation,
                preparer=prepare, evaluator=lambda *a, **kw: self.baseline)
        runtime.require_preparation(destination)
        self.assertEqual(read(destination / "sbri-pre-edit.json")["status"], "COMPLETE")
        self.assertTrue(original(destination, runner=self.runner)["reused"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(conversation.runs, 0)

    def test_optional_bad_report_does_not_prevent_strict_preparation(self):
        destination = self.state / "prepared-failure"
        def malformed(argv, source, timeout, output):
            path = Path(argv[argv.index("--output") + 1])
            path.mkdir(parents=True)
            (path / "result.json").write_text("broken JSON")
            return dict(exitCode=0, timedOut=False)
        def prepare(state, task):
            shutil.copytree(self.workspace, state / "workspace")
            return state / "workspace"
        original = capabilities.sbri
        with patch.object(capabilities, "sbri", side_effect=lambda state: original(state, runner=malformed)):
            runtime.prepare_task(self.task, destination, factory=lambda *a: OfflineConversation(),
                preparer=prepare, evaluator=lambda *a, **kw: self.baseline)
        runtime.require_preparation(destination)
        self.assertEqual(read(destination / "sbri-pre-edit.json")["status"], "INCONCLUSIVE")
        with self.assertRaisesRegex(Blocked, "authority separation"):
            runtime.dispatch(destination)


class TerminalPolicyTests(PreparedFixture):
    def setUp(self):
        super().setUp()
        self.prepared()
        self.event = dict(event_type="PreToolUse", tool_name="terminal", session_id=self.bound["conversationId"],
            working_dir=str(self.workspace), tool_input=dict(command="printf FIXTURE", timeout=1))

    def test_finite_timeouts_required_and_bounded(self):
        self.assertEqual(runtime.terminal_hook(self.state, self.event)["decision"], "allow")
        for timeout in (None, 0, -1, float("nan"), float("inf"), 999999, "1", True):
            self.event["tool_input"]["timeout"] = timeout
            self.assertEqual(runtime.terminal_hook(self.state, self.event)["decision"], "deny")

    def test_remaining_admission_budget_expiry_and_control_input(self):
        with patch("native_remediation.runtime.time.time", return_value=self.bound["createdAt"] + 7199.5):
            self.assertEqual(runtime.terminal_hook(self.state, self.event)["decision"], "deny")
        self.bound["createdAt"] -= 7201
        write(self.state / "task.json", self.bound)
        with self.assertRaises(Blocked):
            runtime.terminal_hook(self.state, self.event)
        self.event["tool_input"] = dict(command="C-c", is_input=True)
        self.assertEqual(runtime.terminal_hook(self.state, self.event)["decision"], "allow")

    def test_identity_and_baseline_failures_cannot_allow_new_commands(self):
        self.event["session_id"] = "wrong-conversation"
        with self.assertRaisesRegex(Blocked, "identity"):
            runtime.terminal_hook(self.state, self.event)
        self.event["session_id"] = self.bound["conversationId"]
        (self.state / "preparation.json").unlink()
        with self.assertRaises(Blocked):
            runtime.terminal_hook(self.state, self.event)

    def test_cli_returns_explicit_deny_not_infrastructure_success(self):
        import sys
        self.event["tool_input"]["timeout"] = 999999
        result = subprocess.run([sys.executable, "-m", "native_remediation", "terminal-hook", "--state", str(self.state)],
            input=json.dumps(self.event), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["decision"], "deny")


if __name__ == "__main__":
    unittest.main()
