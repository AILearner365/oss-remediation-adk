"""Focused historical-parity contracts. Fixtures are not live remediation proof."""
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import uuid

from native_remediation import capabilities, evidence, journal, runtime, validation
from native_remediation.contract import load_task
from native_remediation.files import Blocked, digest, read, write
from tests_native.test_product import GitFixture, task_input, evaluation


class ConfigurationParityTests(unittest.TestCase):
    def test_safe_default_precedence_and_legacy_destination_not_authorization(self):
        value = task_input()
        value.pop("delivery")
        task = load_task(value)
        self.assertEqual(task["delivery"], {"mode": "report_only"})
        self.assertFalse(task["policy"]["java"]["allow_change"])
        explicit = load_task(dict(value, limits=dict(max_iterations=250),
            policy=dict(java=dict(allow_change=True), spring_boot=dict(major=True))))
        self.assertEqual(explicit["limits"]["max_iterations"], 250)
        self.assertTrue(explicit["policy"]["java"]["allow_change"])
        self.assertTrue(explicit["policy"]["spring_boot"]["major"])
        legacy = load_task(dict(value, delivery=dict(repository=value["repository"],
            base_branch=value["base_branch"], draft=True)))
        self.assertFalse(legacy["delivery"]["authorized"])

    def test_reject_unverified_scanner_ambiguous_skills_or_candidate_scope(self):
        bad = [dict(scanner=dict(type="other")), dict(scanner=dict(version="9.0")),
            dict(sbri=dict(versions=["4.0.8"], ranges=["4.1.x"])),
            dict(sbri=dict(versions=["4.0.8; echo unsafe"])), dict(sbri=dict(scopes=["unknown"])),
            dict(guidance=dict(skills=["evidence-driven-dependency-remediation", "dependency-remediation-decision"])),
            dict(policy=dict(java=dict(allow_change="yes")))]
        for override in bad:
            with self.subTest(override=override), self.assertRaises(Blocked):
                load_task(dict(task_input(), **override))

    def test_java_and_boot_movement_are_independent_approved_constraints(self):
        before, after = evaluation("base", True), evaluation("candidate")
        before["inventory"]["properties"]["app:root"]["java.version"] = "17"
        after["inventory"]["properties"]["app:root"]["java.version"] = "21"
        policy = load_task(task_input())["policy"]
        self.assertEqual(validation.compare(before, after, policy)["outcome"], "FAIL")
        policy["java"] = dict(allow_change=True, allowed_versions=["21"])
        self.assertEqual(validation.compare(before, after, policy)["outcome"], "PASS")
        before["inventory"]["spring_boot"] = "4.0.6"
        for current, permission in (("4.0.8", "patch"), ("4.1.1", "minor"), ("5.0.0", "major"), ("4.0.5", "downgrade")):
            after["inventory"]["spring_boot"] = current
            policy["spring_boot"][permission] = False
            self.assertEqual(validation.compare(before, after, policy)["outcome"], "FAIL")
            policy["spring_boot"][permission] = True
            self.assertEqual(validation.compare(before, after, policy)["outcome"], "PASS")


class CapabilityParityTests(GitFixture):
    def bind(self, **changes):
        self.task = load_task(dict(self.task, **changes))
        self.bound.update(task=self.task, taskDigest=digest(self.task))
        write(self.state / "task.json", self.bound)

    def prepared(self):
        self.bound["executionFramework"] = "standalone-sdk-1.55.1"
        write(self.state / "task.json", self.bound)
        write(self.state / "preparation.json", dict(outcome="COMPLETE", conversationId=self.bound["conversationId"],
            taskDigest=self.bound["taskDigest"], repository=self.task["repository"], baseCommit=self.task["base_sha"],
            baseTree=self.baseline["tree"], baselineDigest=digest(self.baseline), completedAt=time.time()))

    def test_self_validation_does_not_accept_deliver_or_consume_stop_attempts(self):
        self.prepared()
        result = capabilities.self_validate(self.state, evaluator=lambda *a, **kw: evaluation(self.baseline["tree"]))
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["authority"], "AGENT_SELF_CHECK_ONLY")
        self.assertFalse(result["stopAttemptConsumed"])
        for name in ("attempts", "feedback.json", "result.json", "delivery.json"):
            self.assertFalse((self.state / name).exists())
        with patch("native_remediation.capabilities.require_independent_authority", side_effect=Blocked("host authority")):
            with self.assertRaises(Blocked):
                capabilities.self_validate(self.state)
        self.assertEqual(len(list((self.state / "self-validation").glob("*/intent.json"))), 1)

    def test_report_only_pass_never_delivers_and_missing_questionnaire_is_not_acceptance(self):
        self.bind(delivery=dict(mode="report_only"))
        event = dict(event_type="Stop", session_id=self.bound["conversationId"],
                     working_dir=str(self.workspace), metadata=dict(reason="agent_finished"))
        response = runtime.hook(self.state, event, evaluator=lambda *a, **kw: evaluation(self.baseline["tree"]),
                                delivery=lambda *a: self.fail("report_only must not deliver"))
        self.assertEqual(response["decision"], "allow")
        self.assertEqual(read(self.state / "result.json")["outcome"], "VALIDATED")
        self.assertEqual(read(self.state / "feedback.json")["outcome"], "PASS")
        self.assertFalse((self.state / "delivery.json").exists())
        self.assertFalse((self.state / "journal").exists())
        self.assertIn("VALIDATED", runtime.status(self.state)["result"]["outcome"])

    def test_report_only_failure_returns_feedback_and_authorization_is_not_inferred(self):
        self.bind(delivery=dict(mode="report_only"))
        tree = self.candidate()
        event = dict(event_type="Stop", session_id=self.bound["conversationId"],
                     working_dir=str(self.workspace), metadata=dict(reason="agent_finished"))
        response = runtime.hook(self.state, event, evaluator=lambda *a, **kw: evaluation(tree, True),
                                delivery=lambda *a: self.fail("must not deliver"))
        self.assertEqual(response["decision"], "deny")
        self.assertEqual(read(self.state / "feedback.json")["outcome"], "FAIL")
        self.assertFalse((self.state / "result.json").exists())
        self.bind(delivery=dict(mode="draft_pr", repository=self.task["repository"],
            base_branch=self.task["base_branch"], draft=True, authorized=False))
        (self.workspace / "pom.xml").write_text("<project><!-- revised candidate --></project>")
        from native_remediation.repository import snapshot
        tree = snapshot(self.workspace, self.task)
        journal.record(self.state, "outcome", dict(summary="Revised candidate", goal_status="candidate_ready"))
        with self.assertRaisesRegex(Blocked, "not explicitly authorized"):
            runtime.hook(self.state, event, evaluator=lambda *a, **kw: evaluation(tree),
                         delivery=lambda *a: self.fail("unauthorized draft must not deliver"))
        self.assertEqual(read(self.state / "feedback.json")["outcome"], "PASS")
        self.assertFalse((self.state / "delivery.json").exists())

    def test_decisions_are_material_optional_and_recovery_refs_are_retained(self):
        result = journal.record(self.state, "decision", dict(strategy="Assess BOM and targeted candidates",
            rationale="Owned dependency evidence changed the premise", evidence_refs=["baseline.json"]))
        (self.workspace / "pom.xml").write_text("<project><!-- normal debugging edit --></project>")
        outcome = journal.record(self.state, "outcome", dict(summary="Self-check incomplete", goal_status="candidate_ready",
            remaining_uncertainty="Runtime compatibility", evidence_refs=["baseline.json"]))
        self.assertEqual(journal.final_outcome(self.state, outcome["tree"]), outcome)
        self.assertEqual(result["taskDigest"], self.bound["taskDigest"])
        with self.assertRaises(Blocked):
            journal.record(self.state, "decision", dict(strategy="x", rationale="y", evidence_refs=["../outside"]))

    def test_automatic_native_and_git_evidence_capture_without_agent_report(self):
        path = self.state / "conversations" / uuid.UUID(self.bound["conversationId"]).hex / "events"
        write(path / "event-00000-fixture.json", dict(kind="ObservationEvent", observation="fixture"))
        (self.workspace / "pom.xml").write_text("<project><!-- candidate --></project>")
        result = evidence.capture(self.state, "offline-fixture")
        self.assertEqual(result["eventCount"], 1)
        self.assertIn("candidate", result["gitDiff"])
        self.assertIn("baseline.json", result["references"])
        self.assertNotIn("observation", result)  # Native raw events remain native, not duplicated.

    def test_sbri_availability_candidates_scope_cache_and_source_identity(self):
        self.assertEqual(capabilities.sbri(self.state)["status"], "NOT_APPLICABLE")
        (self.workspace / "pom.xml").write_text("<project><parent><groupId>org.springframework.boot</groupId>"
            "<artifactId>spring-boot-starter-parent</artifactId><version>4.0.6</version></parent></project>")
        self.bind(sbri=dict(mode="on", executable="/missing/sbri"))
        self.assertEqual(capabilities.sbri(self.state)["status"], "UNAVAILABLE")
        tool = self.state / "sbri-fixture"
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o700)
        self.bind(sbri=dict(mode="on", executable=str(tool), versions=["4.0.8"]))
        calls = []
        def runner(argv, cwd, timeout, output):
            calls.append(argv)
            destination = Path(argv[argv.index("--output") + 1])
            write(destination / "result.json", dict(status="SUCCESS", releases=[dict(version="4.0.8",
                  assessment_status="COMPLETE", rank=1)], execution=dict(release_selection=dict(mode="explicit"))))
            return dict(exitCode=0, timedOut=False)
        first = capabilities.sbri(self.state, scopes=["test"], runner=runner)
        self.assertEqual(first["status"], "COMPLETE")
        self.assertTrue(first["rankIsNotStrategy"])
        self.assertIn("--releases", calls[0])
        self.assertIn("test", calls[0])
        again = capabilities.sbri(self.state, scopes=["test"], runner=runner)
        self.assertTrue(again["reused"])
        self.assertEqual(len(calls), 1)
        changed = capabilities.sbri(self.state, ranges=["4.1.x"], runner=runner)
        self.assertNotEqual(first["evidence"], changed["evidence"])
        self.assertIn("--range", calls[-1])
        def incomplete(argv, cwd, timeout, output):
            destination = Path(argv[argv.index("--output") + 1])
            write(destination / "result.json", dict(status="SUCCESS", releases=[]))
            return dict(exitCode=0, timedOut=False)
        self.assertEqual(capabilities.sbri(self.state, versions=["4.0.9"],
                         runner=incomplete)["status"], "INCONCLUSIVE")
        self.assertFalse((self.state / "attempts").exists())


if __name__ == "__main__":
    unittest.main()
