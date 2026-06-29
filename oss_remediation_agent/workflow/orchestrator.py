from __future__ import annotations

from pathlib import Path

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.tools.baseline_build_tool import run_baseline_build
from oss_remediation_agent.tools.generic_patch_apply_tool import apply as apply_patch_plan
from oss_remediation_agent.tools.generic_patch_apply_tool import dry_run as dry_run_patch_plan
from oss_remediation_agent.tools.osv_scanner_tool import generate_vulnerability_assessment
from oss_remediation_agent.tools.project_analyzer_tool import analyze_project
from oss_remediation_agent.tools.repo_checkout_tool import checkout_baseline, restore_attempt_workspace
from oss_remediation_agent.tools.validation_tool import validate_attempt
from oss_remediation_agent.workspace import ManifestStore, WorkspaceManager


class WorkflowOrchestrator:
    """MVP orchestration skeleton.

    The orchestrator owns execution order and manifest updates. AI planning and
    outcome analysis remain integration points for the ADK application layer.
    """

    def __init__(self, workspace_root: str, policy: RemediationPolicy | None = None):
        self.workspace = WorkspaceManager(workspace_root)
        self.manifest_store = ManifestStore(Path(workspace_root) / "manifest.json")
        self.policy = policy or RemediationPolicy()

    def initialize(self, repository_url: str, reference_branch: str) -> dict:
        self.workspace.initialize()
        manifest = {
            "schemaVersion": "1.0",
            "artifactId": "manifest",
            "workflowId": "oss-remediation-mvp",
            "createdBy": "ADKWorkflowOrchestrator",
            "status": "INITIALIZED",
            "policy": self.policy.to_dict(),
            "repository": {"repositoryUrl": repository_url, "referenceBranch": reference_branch},
            "attempts": [],
            "acceptedPatchSet": {"patchIds": [], "vulnerabilityIds": [], "status": "EMPTY"},
        }
        self.manifest_store.save(manifest)
        return manifest

    def checkout_and_baseline(self, repository_url: str, reference_branch: str) -> dict:
        manifest = self.initialize(repository_url, reference_branch)
        checkout = checkout_baseline(repository_url, reference_branch, str(self.workspace.root))
        if checkout["status"] != "SUCCESS":
            manifest["status"] = "CHECKOUT_FAILED"
            self.manifest_store.save(manifest)
            return checkout

        repository_path = checkout["payload"]["repositoryPath"]
        manifest["repository"]["baselineCommit"] = checkout["payload"].get("baselineCommit")
        baseline = run_baseline_build(
            repository_path,
            workflow_id=manifest["workflowId"],
            output_path=str(self.workspace.root / "baseline" / "baseline-build-result.json"),
            log_file=str(self.workspace.root / "baseline" / "baseline-build.log"),
        )
        manifest["status"] = "BASELINE_BUILD_PASSED" if baseline["status"] == "SUCCESS" else "BASELINE_BUILD_FAILED"
        manifest["baseline"] = {
            "repositoryPath": repository_path,
            "baselineBuildResult": "baseline/baseline-build-result.json",
        }
        self.manifest_store.save(manifest)
        return baseline

    def run_assessment(self) -> dict:
        manifest = self.manifest_store.load()
        repository_path = manifest.get("baseline", {}).get("repositoryPath")
        if not repository_path:
            return {"status": "FAILED", "failureCode": "BASELINE_NOT_READY"}
        assessment = generate_vulnerability_assessment(
            repository_path=repository_path,
            output_path=str(self.workspace.root / "baseline" / "vulnerability-assessment-report.json"),
            raw_report_path=str(self.workspace.root / "baseline" / "osv-report.json"),
            severity_scope=self.policy.severity_scope,
            workflow_id=manifest["workflowId"],
        )
        manifest.setdefault("baseline", {})["vulnerabilityAssessmentReport"] = "baseline/vulnerability-assessment-report.json"
        manifest["status"] = "SCANNING_COMPLETE" if assessment["status"] == "SUCCESS" else "SCANNING_FAILED"
        self.manifest_store.save(manifest)
        return assessment

    def run_project_analysis(self) -> dict:
        manifest = self.manifest_store.load()
        repository_path = manifest.get("baseline", {}).get("repositoryPath")
        if not repository_path:
            return {"status": "FAILED", "failureCode": "BASELINE_NOT_READY"}
        result = analyze_project(
            repository_path=repository_path,
            vulnerability_assessment_path=str(self.workspace.root / "baseline" / "vulnerability-assessment-report.json"),
            output_path=str(self.workspace.root / "baseline" / "project-analyzer-report.json"),
            artifact_output_dir=str(self.workspace.root / "baseline"),
            workflow_id=manifest["workflowId"],
        )
        manifest.setdefault("baseline", {})["projectAnalyzerReport"] = "baseline/project-analyzer-report.json"
        manifest["status"] = "PROJECT_ANALYSIS_COMPLETE" if result["status"] in {"SUCCESS", "PARTIAL"} else "PROJECT_ANALYSIS_FAILED"
        self.manifest_store.save(manifest)
        return result

    def run_patch_validation_attempt(self, attempt_number: int, patch_plan_path: str) -> dict:
        manifest = self.manifest_store.load()
        restore = restore_attempt_workspace(str(self.workspace.root), attempt_number)
        attempt_workspace = restore.get("payload", {}).get("attemptWorkspace")
        attempt_dir = self.workspace.root / f"attempt-{attempt_number}"
        attempt_entry = {"attemptNumber": attempt_number, "status": "STARTED", "patchPlan": patch_plan_path}
        manifest.setdefault("attempts", []).append(attempt_entry)
        self.manifest_store.save(manifest)

        dry = dry_run_patch_plan(attempt_number, attempt_workspace, patch_plan_path, str(attempt_dir / "patch-dry-run-result.json"))
        attempt_entry["patchDryRunResult"] = f"attempt-{attempt_number}/patch-dry-run-result.json"
        if dry["status"] != "SUCCESS":
            attempt_entry["status"] = "PATCH_DRY_RUN_FAILED"
            self.manifest_store.save(manifest)
            return dry

        proof_path = str(attempt_dir / "patch-application-proof.json")
        diff_path = str(attempt_dir / "patch.diff")
        patch = apply_patch_plan(attempt_number, attempt_workspace, patch_plan_path, proof_path, diff_path)
        attempt_entry["patchApplicationProof"] = f"attempt-{attempt_number}/patch-application-proof.json"
        if patch["status"] != "SUCCESS":
            attempt_entry["status"] = "PATCH_APPLICATION_FAILED"
            self.manifest_store.save(manifest)
            return patch

        validation = validate_attempt(
            attempt_number=attempt_number,
            repository_path=attempt_workspace,
            patch_plan_path=patch_plan_path,
            patch_application_proof_path=proof_path,
            output_path=str(attempt_dir / "validation-result.json"),
            artifact_output_dir=str(attempt_dir),
            workflow_id=manifest["workflowId"],
            severity_scope=self.policy.severity_scope,
            baseline_assessment_path=str(self.workspace.root / "baseline" / "vulnerability-assessment-report.json"),
        )
        attempt_entry["validationResult"] = f"attempt-{attempt_number}/validation-result.json"
        attempt_entry["status"] = "VALIDATION_SUCCEEDED" if validation["status"] == "SUCCESS" else "VALIDATION_FAILED"
        if validation["status"] == "SUCCESS":
            manifest["acceptedPatchSet"] = {"status": "VALIDATED", "patchIds": [], "vulnerabilityIds": []}
        self.manifest_store.save(manifest)
        return validation
