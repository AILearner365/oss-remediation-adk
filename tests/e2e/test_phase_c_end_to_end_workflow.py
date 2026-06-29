from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.orchestrator import WorkflowOrchestrator


class PhaseCEndToEndWorkflowTests(unittest.TestCase):
    """End-to-end workflow tests for complete MVP remediation scenarios.

    Phase C exercises the orchestrator from checkout/baseline through assessment,
    project analysis, planner routing, remediation attempts, validation, outcome
    analysis, accepted patch set generation, and final PR summary generation.

    External systems are mocked so these tests remain deterministic in CI, but
    the workflow state transitions, manifest updates, and generated artifacts are
    real.
    """

    def test_e2e_successful_remediation_generates_eligible_pr_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)
            plan_path = Path(tmp) / "patch-plan-success.json"
            _write_patch_plan(plan_path, "patch-success", "GHSA-success", "1.33", "2.2")

            with _mock_pre_remediation(status="SUCCESS"), _mock_attempt_lifecycle({1: "SUCCESS"}):
                _run_pre_remediation(orchestrator)
                result = orchestrator.handle_planner_result({"decisionType": "PATCH_PLAN", "patchPlanPath": str(plan_path)}, attempt_number=1)

            self.assertEqual(result["status"], "SUCCESS")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "PROJECT_ANALYSIS_COMPLETE")
            self.assertEqual(manifest["attempts"][0]["status"], "VALIDATION_SUCCEEDED")
            self.assertEqual(manifest["acceptedPatchSet"]["status"], "VALIDATED")
            self.assertEqual(manifest["acceptedPatchSet"]["sourceAttempts"], [1])
            self.assertEqual(manifest["acceptedPatchSet"]["remediationSummary"][0]["dependency"], "org.yaml:snakeyaml")
            pr_result = orchestrator.generate_final_pr_summary()
            self.assertEqual(pr_result["status"], "SUCCESS")
            pr_summary = _read_json(Path(tmp) / "final" / "pr-summary.json")
            self.assertEqual(pr_summary["status"], "ELIGIBLE")
            self.assertEqual(pr_summary["prType"], "FULL_REMEDIATION")

    def test_e2e_baseline_build_failure_stops_before_assessment_and_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)

            with _mock_pre_remediation(status="BASELINE_FAILED"):
                result = orchestrator.checkout_and_baseline("https://example.com/repo.git", "main")

            self.assertEqual(result["status"], "FAILED")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "BASELINE_BUILD_FAILED")
            self.assertEqual(manifest["attempts"], [])
            self.assertNotIn("vulnerabilityAssessmentReport", manifest.get("baseline", {}))
            self.assertEqual(manifest["acceptedPatchSet"]["status"], "EMPTY")

    def test_e2e_manual_review_required_generates_not_eligible_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)

            with _mock_pre_remediation(status="SUCCESS"):
                _run_pre_remediation(orchestrator)
                result = orchestrator.handle_planner_result({"decisionType": "MANUAL_REVIEW", "reason": "Spring Boot major migration requires manual review."}, attempt_number=1)

            self.assertEqual(result["status"], "SUCCESS")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "MANUAL_REVIEW_REQUIRED")
            self.assertEqual(manifest["attempts"], [])
            self.assertEqual(manifest["acceptedPatchSet"]["status"], "EMPTY")
            pr_summary = _read_json(Path(tmp) / "final" / "pr-summary.json")
            self.assertEqual(pr_summary["status"], "NOT_ELIGIBLE")
            self.assertFalse(pr_summary["pullRequestEligibility"]["eligible"])

    def test_e2e_retry_then_success_uses_second_attempt_as_accepted_patch_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp, policy=RemediationPolicy(max_attempts=2))
            first_plan = Path(tmp) / "patch-plan-attempt-1.json"
            second_plan = Path(tmp) / "patch-plan-attempt-2.json"
            _write_patch_plan(first_plan, "patch-attempt-1", "GHSA-retry", "1.33", "2.1")
            _write_patch_plan(second_plan, "patch-attempt-2", "GHSA-retry", "1.33", "2.2")

            with _mock_pre_remediation(status="SUCCESS"), _mock_attempt_lifecycle({1: "FAILED", 2: "SUCCESS"}, failed_stage="OSV_VALIDATION"):
                _run_pre_remediation(orchestrator)
                result = orchestrator.run_attempt_loop([str(first_plan), str(second_plan)])

            self.assertEqual(result["status"], "SUCCESS")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "VALIDATION_SUCCEEDED")
            self.assertEqual(manifest["attempts"][0]["status"], "VALIDATION_FAILED")
            self.assertEqual(manifest["attempts"][0]["outcomeAnalysisSummary"], "attempt-1/outcome-analysis-summary.json")
            self.assertEqual(manifest["attempts"][1]["status"], "VALIDATION_SUCCEEDED")
            self.assertEqual(manifest["acceptedPatchSet"]["sourceAttempts"], [2])
            self.assertEqual(manifest["acceptedPatchSet"]["remediationSummary"][0]["newVersion"], "2.2")
            pr_summary = _read_json(Path(tmp) / "final" / "pr-summary.json")
            self.assertEqual(pr_summary["status"], "ELIGIBLE")

    def test_e2e_max_attempts_reached_without_accepted_patch_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp, policy=RemediationPolicy(max_attempts=3))
            plans = []
            for attempt in range(1, 4):
                plan_path = Path(tmp) / f"patch-plan-attempt-{attempt}.json"
                _write_patch_plan(plan_path, f"patch-attempt-{attempt}", "GHSA-max", "1.33", f"2.{attempt}")
                plans.append(str(plan_path))

            with _mock_pre_remediation(status="SUCCESS"), _mock_attempt_lifecycle({1: "FAILED", 2: "FAILED", 3: "FAILED"}, failed_stage="BUILD_VALIDATION"):
                _run_pre_remediation(orchestrator)
                result = orchestrator.run_attempt_loop(plans)

            self.assertEqual(result["status"], "FAILED")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "FAILED_MAX_ATTEMPTS")
            self.assertEqual(len(manifest["attempts"]), 3)
            self.assertTrue(all(attempt["status"] == "VALIDATION_FAILED" for attempt in manifest["attempts"]))
            self.assertEqual(manifest["acceptedPatchSet"]["status"], "EMPTY")
            self.assertNotIn("prSummary", manifest.get("final", {}))

    def test_e2e_unsafe_change_scope_is_rejected_and_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp, policy=RemediationPolicy(max_attempts=1))
            plan_path = Path(tmp) / "patch-plan-unsafe-scope.json"
            _write_patch_plan(plan_path, "patch-unsafe", "GHSA-unsafe", "1.33", "2.2", file_name="src/main/java/App.java")

            with _mock_pre_remediation(status="SUCCESS"), _mock_attempt_lifecycle({1: "FAILED"}, failed_stage="CHANGE_SCOPE_VALIDATION"):
                _run_pre_remediation(orchestrator)
                result = orchestrator.run_attempt_loop([str(plan_path)])

            self.assertEqual(result["status"], "FAILED")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["acceptedPatchSet"]["status"], "EMPTY")
            validation = _read_json(Path(tmp) / "attempt-1" / "validation-result.json")
            self.assertEqual(validation["summary"]["failedStage"], "CHANGE_SCOPE_VALIDATION")
            outcome = _read_json(Path(tmp) / "attempt-1" / "outcome-analysis-summary.json")
            self.assertEqual(outcome["failureCategory"], "CHANGE_SCOPE_FAILURE")

    def test_e2e_new_critical_or_high_vulnerability_introduced_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp, policy=RemediationPolicy(max_attempts=1))
            plan_path = Path(tmp) / "patch-plan-new-high.json"
            _write_patch_plan(plan_path, "patch-new-high", "GHSA-new-high", "1.33", "2.2")

            with _mock_pre_remediation(status="SUCCESS"), _mock_attempt_lifecycle({1: "FAILED"}, failed_stage="OSV_VALIDATION", new_critical_high=True):
                _run_pre_remediation(orchestrator)
                result = orchestrator.run_attempt_loop([str(plan_path)])

            self.assertEqual(result["status"], "FAILED")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["acceptedPatchSet"]["status"], "EMPTY")
            validation = _read_json(Path(tmp) / "attempt-1" / "validation-result.json")
            self.assertTrue(validation["osvValidation"]["newCriticalHighIntroduced"])
            outcome = _read_json(Path(tmp) / "attempt-1" / "outcome-analysis-summary.json")
            self.assertEqual(outcome["failureCategory"], "OSV_VALIDATION_FAILURE")


def _run_pre_remediation(orchestrator: WorkflowOrchestrator) -> None:
    baseline = orchestrator.checkout_and_baseline("https://example.com/repo.git", "main")
    assert baseline["status"] == "SUCCESS"
    assessment = orchestrator.run_assessment()
    assert assessment["status"] == "SUCCESS"
    analysis = orchestrator.run_project_analysis()
    assert analysis["status"] == "SUCCESS"


def _mock_pre_remediation(status: str = "SUCCESS"):
    class PreRemediationContext:
        def __enter__(self):
            checkout = {"status": "SUCCESS", "payload": {"repositoryPath": "mock-repo", "baselineCommit": "abc123"}}
            baseline = {"status": "SUCCESS", "artifactPath": "baseline/baseline-build-result.json", "payload": {"exitCode": 0}}
            if status == "BASELINE_FAILED":
                baseline = {"status": "FAILED", "failureCode": "BASELINE_BUILD_FAILED", "payload": {"exitCode": 1}}
            self.patchers = [
                patch("oss_remediation_agent.workflow.orchestrator.checkout_baseline", return_value=checkout),
                patch("oss_remediation_agent.workflow.orchestrator.run_baseline_build", side_effect=lambda repository_path, workflow_id, output_path, log_file: _write_baseline_result(output_path, log_file, baseline)),
                patch("oss_remediation_agent.workflow.orchestrator.generate_vulnerability_assessment", side_effect=_write_assessment_result),
                patch("oss_remediation_agent.workflow.orchestrator.analyze_project", side_effect=_write_project_analysis_result),
            ]
            for patcher in self.patchers:
                patcher.start()
            return self

        def __exit__(self, exc_type, exc, tb):
            for patcher in reversed(self.patchers):
                patcher.stop()

    return PreRemediationContext()


def _mock_attempt_lifecycle(validation_status_by_attempt: dict[int, str], failed_stage: str = "BUILD_VALIDATION", new_critical_high: bool = False):
    class AttemptLifecycleContext:
        def __enter__(self):
            self.patchers = [
                patch("oss_remediation_agent.workflow.orchestrator.restore_attempt_workspace", side_effect=_restore_attempt_workspace),
                patch("oss_remediation_agent.workflow.orchestrator.dry_run_patch_plan", side_effect=_dry_run_success),
                patch("oss_remediation_agent.workflow.orchestrator.apply_patch_plan", side_effect=_apply_success),
                patch(
                    "oss_remediation_agent.workflow.orchestrator.validate_attempt",
                    side_effect=lambda **kwargs: _validation_result(kwargs, validation_status_by_attempt, failed_stage, new_critical_high),
                ),
            ]
            for patcher in self.patchers:
                patcher.start()
            return self

        def __exit__(self, exc_type, exc, tb):
            for patcher in reversed(self.patchers):
                patcher.stop()

    return AttemptLifecycleContext()


def _write_baseline_result(output_path: str, log_file: str, result: dict) -> dict:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps({"status": result["status"], "payload": result.get("payload", {})}), encoding="utf-8")
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(log_file).write_text("mock baseline build log", encoding="utf-8")
    return result


def _write_assessment_result(repository_path: str, output_path: str, raw_report_path: str, severity_scope: str, workflow_id: str) -> dict:
    artifact = {
        "schemaVersion": "1.0",
        "artifactId": "vulnerability-assessment-report",
        "workflowId": workflow_id,
        "createdBy": "E2ETest",
        "status": "SUCCESS",
        "vulnerabilities": [{"vulnerabilityId": "GHSA-test", "severity": "HIGH", "dependency": "org.yaml:snakeyaml"}],
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact), encoding="utf-8")
    Path(raw_report_path).write_text(json.dumps({"results": []}), encoding="utf-8")
    return {"status": "SUCCESS", "artifactPath": output_path, "payload": artifact}


def _write_project_analysis_result(repository_path: str, vulnerability_assessment_path: str, output_path: str, artifact_output_dir: str, workflow_id: str) -> dict:
    artifact = {
        "schemaVersion": "1.0",
        "artifactId": "project-analyzer-report",
        "workflowId": workflow_id,
        "createdBy": "E2ETest",
        "status": "SUCCESS",
        "projectFacts": {"projectType": "MAVEN", "rootPom": "pom.xml", "pomFiles": ["pom.xml"]},
        "dependencyResolutionEvidence": [{"dependency": "org.yaml:snakeyaml", "resolvedVersion": "1.33"}],
    }
    output_dir = Path(artifact_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact), encoding="utf-8")
    return {"status": "SUCCESS", "artifactPath": output_path, "payload": artifact}


def _restore_attempt_workspace(workspace_root: str, attempt_number: int):
    attempt_workspace = Path(workspace_root) / f"attempt-{attempt_number}" / "repo"
    attempt_workspace.mkdir(parents=True, exist_ok=True)
    (attempt_workspace / "pom.xml").write_text("<project></project>", encoding="utf-8")
    (attempt_workspace / "src/main/java").mkdir(parents=True, exist_ok=True)
    (attempt_workspace / "src/main/java/App.java").write_text("class App {}", encoding="utf-8")
    return {"status": "SUCCESS", "payload": {"attemptWorkspace": str(attempt_workspace)}}


def _dry_run_success(attempt_number: int, repository_path: str, patch_plan_path: str, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    artifact = {"status": "SUCCESS", "attemptNumber": attempt_number, "patchResults": [{"patchId": _patch_id(patch_plan_path), "status": "DRY_RUN_OK"}]}
    Path(output_path).write_text(json.dumps(artifact), encoding="utf-8")
    return {"status": "SUCCESS", "artifactPath": output_path, "payload": artifact}


def _apply_success(attempt_number: int, repository_path: str, patch_plan_path: str, output_path: str, diff_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plan = _read_json(Path(patch_plan_path))
    patch_item = plan["vulnerabilityDecisions"][0]["patches"][0]
    artifact = {
        "schemaVersion": "1.0",
        "artifactId": f"patch-application-proof-{attempt_number}",
        "workflowId": "wf-e2e",
        "createdBy": "E2ETest",
        "status": "SUCCESS",
        "attemptNumber": attempt_number,
        "filesChanged": [patch_item["file"]],
        "patchResults": [{"patchId": patch_item["patchId"], "status": "APPLIED", "file": patch_item["file"]}],
    }
    Path(output_path).write_text(json.dumps(artifact), encoding="utf-8")
    Path(diff_path).write_text(f"diff --git a/{patch_item['file']} b/{patch_item['file']}\n", encoding="utf-8")
    return {"status": "SUCCESS", "artifactPath": output_path, "payload": artifact}


def _validation_result(kwargs: dict, validation_status_by_attempt: dict[int, str], failed_stage: str, new_critical_high: bool):
    attempt_number = kwargs["attempt_number"]
    status = validation_status_by_attempt.get(attempt_number, "FAILED")
    output_path = Path(kwargs["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schemaVersion": "1.0",
        "artifactId": f"validation-result-{attempt_number}",
        "workflowId": kwargs.get("workflow_id", "wf-e2e"),
        "createdBy": "E2ETest",
        "status": status,
        "summary": {
            "failedStage": None if status == "SUCCESS" else failed_stage,
            "failureSummary": None if status == "SUCCESS" else f"Intentional {failed_stage} failure for end-to-end workflow test.",
        },
        "changeScopeValidation": {"status": "SUCCESS" if status == "SUCCESS" or failed_stage != "CHANGE_SCOPE_VALIDATION" else "FAILED"},
        "buildValidation": {"status": "SUCCESS" if status == "SUCCESS" or failed_stage != "BUILD_VALIDATION" else "FAILED"},
        "testValidation": {"status": "SUCCESS" if status == "SUCCESS" or failed_stage != "TEST_VALIDATION" else "FAILED"},
        "osvValidation": {
            "status": "SUCCESS" if status == "SUCCESS" else "FAILED",
            "remainingCriticalCount": 0,
            "remainingHighCount": 0 if status == "SUCCESS" else 1,
            "newCriticalHighIntroduced": bool(new_critical_high),
        },
    }
    output_path.write_text(json.dumps(artifact), encoding="utf-8")
    return {"status": status, "artifactPath": str(output_path), "failureCode": None if status == "SUCCESS" else failed_stage, "payload": artifact}


def _write_patch_plan(path: Path, patch_id: str, vulnerability_id: str, old_version: str, new_version: str, file_name: str = "pom.xml") -> None:
    path.write_text(json.dumps({
        "schemaVersion": "1.0",
        "artifactId": path.stem,
        "workflowId": "wf-e2e",
        "createdBy": "E2ETest",
        "status": "PATCH_AVAILABLE",
        "planId": path.stem,
        "vulnerabilityDecisions": [{
            "vulnerabilityId": vulnerability_id,
            "decision": "PATCH",
            "dependency": {
                "packageName": "org.yaml:snakeyaml",
                "currentVersion": old_version,
            },
            "patches": [{
                "patchId": patch_id,
                "file": file_name,
                "oldText": f"<snakeyaml.version>{old_version}</snakeyaml.version>",
                "newText": f"<snakeyaml.version>{new_version}</snakeyaml.version>",
                "oldVersion": old_version,
                "newVersion": new_version,
                "expectedOccurrences": 1,
            }],
        }],
    }), encoding="utf-8")


def _patch_id(patch_plan_path: str) -> str:
    plan = _read_json(Path(patch_plan_path))
    return plan["vulnerabilityDecisions"][0]["patches"][0]["patchId"]


def _manifest(root: Path) -> dict:
    return _read_json(root / "manifest.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
