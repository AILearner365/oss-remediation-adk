from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.orchestrator import WorkflowOrchestrator


class PhaseBWorkflowIntegrationTests(unittest.TestCase):
    """Workflow-level integration tests for the MVP orchestrator.

    These tests keep AI/planner behavior mocked but exercise the orchestrator's
    manifest ownership, attempt lifecycle, stop conditions, outcome summary
    generation, accepted patch set generation, and final PR summary generation.
    """

    def test_successful_remediation_workflow_generates_accepted_patch_set_and_pr_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)
            orchestrator.initialize("https://example.com/repo.git", "main")
            _write_baseline_assessment(Path(tmp))
            plan_path = _write_patch_plan(Path(tmp), "plan-1.json", "patch-1", "GHSA-success", "1.33", "2.2")

            with _mock_attempt_lifecycle(validation_status_by_attempt={1: "SUCCESS"}):
                result = orchestrator.run_attempt_loop([str(plan_path)])

            self.assertEqual(result["status"], "SUCCESS")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "VALIDATION_SUCCEEDED")
            self.assertEqual(manifest["attempts"][0]["status"], "VALIDATION_SUCCEEDED")
            self.assertEqual(manifest["acceptedPatchSet"]["status"], "VALIDATED")
            self.assertEqual(manifest["acceptedPatchSet"]["sourceAttempts"], [1])
            self.assertEqual(manifest["acceptedPatchSet"]["remediationSummary"][0]["dependency"], "org.yaml:snakeyaml")
            self.assertEqual(manifest["final"]["prSummary"], "final/pr-summary.json")
            pr_summary = _read_json(Path(tmp) / "final" / "pr-summary.json")
            self.assertEqual(pr_summary["status"], "ELIGIBLE")
            self.assertEqual(pr_summary["prType"], "FULL_REMEDIATION")

    def test_baseline_build_failure_stops_before_remediation_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)
            checkout_result = {
                "status": "SUCCESS",
                "payload": {"repositoryPath": str(Path(tmp) / "repo"), "baselineCommit": "abc123"},
            }
            baseline_result = {"status": "FAILED", "failureCode": "BASELINE_BUILD_FAILED", "payload": {"exitCode": 1}}

            with patch("oss_remediation_agent.workflow.orchestrator.checkout_baseline", return_value=checkout_result), \
                 patch("oss_remediation_agent.workflow.orchestrator.run_baseline_build", return_value=baseline_result):
                result = orchestrator.checkout_and_baseline("https://example.com/repo.git", "main")

            self.assertEqual(result["status"], "FAILED")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "BASELINE_BUILD_FAILED")
            self.assertEqual(manifest.get("attempts"), [])
            self.assertEqual(manifest["baseline"]["repositoryPath"], str(Path(tmp) / "repo"))

    def test_validation_failure_generates_outcome_summary_and_stops_after_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp, policy=RemediationPolicy(max_attempts=1))
            orchestrator.initialize("https://example.com/repo.git", "main")
            _write_baseline_assessment(Path(tmp))
            plan_path = _write_patch_plan(Path(tmp), "plan-1.json", "patch-1", "GHSA-build", "1.33", "2.2")

            with _mock_attempt_lifecycle(validation_status_by_attempt={1: "FAILED"}, failed_stage="BUILD_VALIDATION"):
                result = orchestrator.run_attempt_loop([str(plan_path)])

            self.assertEqual(result["status"], "FAILED")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "FAILED_MAX_ATTEMPTS")
            self.assertEqual(manifest["attempts"][0]["status"], "VALIDATION_FAILED")
            self.assertEqual(manifest["attempts"][0]["outcomeAnalysisSummary"], "attempt-1/outcome-analysis-summary.json")
            outcome = _read_json(Path(tmp) / "attempt-1" / "outcome-analysis-summary.json")
            self.assertEqual(outcome["failureCategory"], "BUILD_FAILURE")
            self.assertEqual(manifest["acceptedPatchSet"]["status"], "EMPTY")

    def test_manual_review_workflow_generates_not_eligible_pr_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp)
            orchestrator.initialize("https://example.com/repo.git", "main")

            result = orchestrator.handle_planner_result({"decisionType": "MANUAL_REVIEW", "reason": "Unsupported upgrade path"}, attempt_number=1)

            self.assertEqual(result["status"], "SUCCESS")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "MANUAL_REVIEW_REQUIRED")
            self.assertEqual(manifest["final"]["prSummary"], "final/pr-summary.json")
            pr_summary = _read_json(Path(tmp) / "final" / "pr-summary.json")
            self.assertEqual(pr_summary["status"], "NOT_ELIGIBLE")
            self.assertFalse(pr_summary["pullRequestEligibility"]["eligible"])

    def test_retry_workflow_succeeds_on_second_attempt_after_first_validation_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = WorkflowOrchestrator(tmp, policy=RemediationPolicy(max_attempts=2))
            orchestrator.initialize("https://example.com/repo.git", "main")
            _write_baseline_assessment(Path(tmp))
            first_plan = _write_patch_plan(Path(tmp), "plan-1.json", "patch-1", "GHSA-retry", "1.33", "2.1")
            second_plan = _write_patch_plan(Path(tmp), "plan-2.json", "patch-2", "GHSA-retry", "1.33", "2.2")

            with _mock_attempt_lifecycle(validation_status_by_attempt={1: "FAILED", 2: "SUCCESS"}, failed_stage="OSV_VALIDATION"):
                result = orchestrator.run_attempt_loop([str(first_plan), str(second_plan)])

            self.assertEqual(result["status"], "SUCCESS")
            manifest = _manifest(Path(tmp))
            self.assertEqual(manifest["status"], "VALIDATION_SUCCEEDED")
            self.assertEqual(manifest["attempts"][0]["status"], "VALIDATION_FAILED")
            self.assertEqual(manifest["attempts"][0]["outcomeAnalysisSummary"], "attempt-1/outcome-analysis-summary.json")
            self.assertEqual(manifest["attempts"][1]["status"], "VALIDATION_SUCCEEDED")
            self.assertEqual(manifest["acceptedPatchSet"]["sourceAttempts"], [2])
            self.assertEqual(manifest["acceptedPatchSet"]["remediationSummary"][0]["newVersion"], "2.2")
            self.assertEqual(manifest["final"]["prSummary"], "final/pr-summary.json")


def _mock_attempt_lifecycle(validation_status_by_attempt: dict[int, str], failed_stage: str = "BUILD_VALIDATION"):
    class AttemptLifecycleContext:
        def __enter__(self):
            self.restore = patch("oss_remediation_agent.workflow.orchestrator.restore_attempt_workspace", side_effect=_restore_attempt_workspace).start()
            self.dry = patch("oss_remediation_agent.workflow.orchestrator.dry_run_patch_plan", side_effect=_dry_run_success).start()
            self.apply = patch("oss_remediation_agent.workflow.orchestrator.apply_patch_plan", side_effect=_apply_success).start()
            self.validate = patch(
                "oss_remediation_agent.workflow.orchestrator.validate_attempt",
                side_effect=lambda **kwargs: _validation_result(kwargs, validation_status_by_attempt, failed_stage),
            ).start()
            return self

        def __exit__(self, exc_type, exc, tb):
            patch.stopall()

    return AttemptLifecycleContext()


def _restore_attempt_workspace(workspace_root: str, attempt_number: int):
    attempt_workspace = Path(workspace_root) / f"attempt-{attempt_number}" / "repo"
    attempt_workspace.mkdir(parents=True, exist_ok=True)
    (attempt_workspace / "pom.xml").write_text("<project></project>", encoding="utf-8")
    return {"status": "SUCCESS", "payload": {"attemptWorkspace": str(attempt_workspace)}}


def _dry_run_success(attempt_number: int, repository_path: str, patch_plan_path: str, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    artifact = {"status": "SUCCESS", "attemptNumber": attempt_number, "patchResults": [{"patchId": _patch_id(patch_plan_path), "status": "DRY_RUN_OK"}]}
    Path(output_path).write_text(json.dumps(artifact), encoding="utf-8")
    return {"status": "SUCCESS", "artifactPath": output_path, "payload": artifact}


def _apply_success(attempt_number: int, repository_path: str, patch_plan_path: str, output_path: str, diff_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    patch_id = _patch_id(patch_plan_path)
    artifact = {
        "schemaVersion": "1.0",
        "artifactId": f"patch-application-proof-{attempt_number}",
        "workflowId": "wf-test",
        "createdBy": "IntegrationTest",
        "status": "SUCCESS",
        "attemptNumber": attempt_number,
        "filesChanged": ["pom.xml"],
        "patchResults": [{"patchId": patch_id, "status": "APPLIED", "file": "pom.xml"}],
    }
    Path(output_path).write_text(json.dumps(artifact), encoding="utf-8")
    Path(diff_path).write_text("diff --git a/pom.xml b/pom.xml\n", encoding="utf-8")
    return {"status": "SUCCESS", "artifactPath": output_path, "payload": artifact}


def _validation_result(kwargs: dict, validation_status_by_attempt: dict[int, str], failed_stage: str):
    attempt_number = kwargs["attempt_number"]
    status = validation_status_by_attempt.get(attempt_number, "FAILED")
    output_path = Path(kwargs["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schemaVersion": "1.0",
        "artifactId": f"validation-result-{attempt_number}",
        "workflowId": kwargs.get("workflow_id", "wf-test"),
        "createdBy": "IntegrationTest",
        "status": status,
        "summary": {
            "failedStage": None if status == "SUCCESS" else failed_stage,
            "failureSummary": None if status == "SUCCESS" else f"Intentional {failed_stage} failure for retry workflow test.",
        },
        "changeScopeValidation": {"status": "SUCCESS"},
        "buildValidation": {"status": "SUCCESS" if status == "SUCCESS" or failed_stage != "BUILD_VALIDATION" else "FAILED"},
        "testValidation": {"status": "SUCCESS"},
        "osvValidation": {
            "status": "SUCCESS" if status == "SUCCESS" else "FAILED",
            "remainingCriticalCount": 0,
            "remainingHighCount": 0 if status == "SUCCESS" else 1,
            "newCriticalHighIntroduced": False,
        },
    }
    output_path.write_text(json.dumps(artifact), encoding="utf-8")
    return {"status": status, "artifactPath": str(output_path), "failureCode": None if status == "SUCCESS" else "VALIDATION_FAILED", "payload": artifact}


def _write_patch_plan(root: Path, filename: str, patch_id: str, vulnerability_id: str, old_version: str, new_version: str) -> Path:
    path = root / filename
    path.write_text(json.dumps({
        "schemaVersion": "1.0",
        "artifactId": filename.replace(".json", ""),
        "workflowId": "wf-test",
        "createdBy": "IntegrationTest",
        "status": "PATCH_AVAILABLE",
        "planId": filename.replace(".json", ""),
        "vulnerabilityDecisions": [{
            "vulnerabilityId": vulnerability_id,
            "decision": "PATCH",
            "dependency": {
                "packageName": "org.yaml:snakeyaml",
                "currentVersion": old_version,
            },
            "patches": [{
                "patchId": patch_id,
                "file": "pom.xml",
                "oldText": f"<snakeyaml.version>{old_version}</snakeyaml.version>",
                "newText": f"<snakeyaml.version>{new_version}</snakeyaml.version>",
                "oldVersion": old_version,
                "newVersion": new_version,
                "expectedOccurrences": 1,
            }],
        }],
    }), encoding="utf-8")
    return path


def _patch_id(patch_plan_path: str) -> str:
    plan = _read_json(Path(patch_plan_path))
    return plan["vulnerabilityDecisions"][0]["patches"][0]["patchId"]


def _write_baseline_assessment(root: Path):
    baseline_dir = root / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "vulnerability-assessment-report.json").write_text(json.dumps({
        "schemaVersion": "1.0",
        "artifactId": "baseline-assessment",
        "workflowId": "wf-test",
        "createdBy": "IntegrationTest",
        "status": "SUCCESS",
        "vulnerabilities": [{"vulnerabilityId": "GHSA-test", "severity": "HIGH"}],
    }), encoding="utf-8")


def _manifest(root: Path) -> dict:
    return _read_json(root / "manifest.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
