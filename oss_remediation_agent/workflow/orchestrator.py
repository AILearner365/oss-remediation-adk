from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.agents.remediation_outcome_analysis_agent import create_outcome_analysis_summary
from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.tools.baseline_build_tool import run_baseline_build
from oss_remediation_agent.tools.generic_patch_apply_tool import apply as apply_patch_plan
from oss_remediation_agent.tools.generic_patch_apply_tool import dry_run as dry_run_patch_plan
from oss_remediation_agent.tools.osv_scanner_tool import generate_vulnerability_assessment
from oss_remediation_agent.tools.pr_creation_tool import create_pr_summary
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
            "workspaceRoot": str(self.workspace.root),
            "policy": self.policy.to_dict(),
            "repository": {"repositoryUrl": repository_url, "referenceBranch": reference_branch},
            "attempts": [],
            "acceptedPatchSet": {"patchIds": [], "vulnerabilityIds": [], "status": "EMPTY"},
            "additionalInvestigationRequests": [],
            "final": {},
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

    def handle_planner_result(self, planning_result: dict, attempt_number: int | None = None) -> dict:
        """Route structured planner output without making remediation decisions."""
        decision_type = planning_result.get("decisionType") or planning_result.get("type")
        if decision_type == "REQUEST_ADDITIONAL_EVIDENCE":
            return self.handle_additional_investigation_request(attempt_number or 1, planning_result)
        if decision_type == "PATCH_PLAN":
            patch_plan_path = planning_result["patchPlanPath"]
            return self.run_patch_validation_attempt(attempt_number or self._next_attempt_number(), patch_plan_path)
        if decision_type == "MANUAL_REVIEW":
            manifest = self.manifest_store.load()
            manifest["status"] = "MANUAL_REVIEW_REQUIRED"
            self.manifest_store.save(manifest)
            return self.generate_final_pr_summary()
        return {"status": "FAILED", "failureCode": "UNKNOWN_PLANNER_RESULT"}

    def handle_additional_investigation_request(self, attempt_number: int, request: dict) -> dict:
        """Record additional investigation requests per attempt and enforce the attempt-scoped limit."""
        manifest = self.manifest_store.load()
        attempt = self._attempt_entry(manifest, attempt_number)
        requests = attempt.setdefault("additionalInvestigationRequests", [])
        requests.append(request)
        manifest.setdefault("additionalInvestigationRequests", []).append({"attemptNumber": attempt_number, "request": request})
        if len(requests) > self.policy.max_additional_investigation_requests_per_attempt:
            attempt["status"] = "ADDITIONAL_INVESTIGATION_LIMIT_REACHED"
            manifest["status"] = "ADDITIONAL_INVESTIGATION_LIMIT_REACHED"
            manifest["plannerConstraint"] = "Planner must produce a patch plan or manual review decision."
        else:
            attempt["status"] = "ADDITIONAL_INVESTIGATION_REQUESTED"
            manifest["status"] = "ADDITIONAL_INVESTIGATION_REQUESTED"
        self.manifest_store.save(manifest)
        return manifest

    def run_attempt_loop(self, patch_plan_paths: list[str]) -> dict:
        """Run a bounded MVP attempt loop over provided patch-plan artifacts."""
        last_result: dict = {"status": "NOT_RUN"}
        for attempt_number, patch_plan_path in enumerate(patch_plan_paths[: self.policy.max_attempts], start=1):
            last_result = self.run_patch_validation_attempt(attempt_number, patch_plan_path)
            if last_result.get("status") == "SUCCESS":
                manifest = self.manifest_store.load()
                manifest["status"] = "VALIDATION_SUCCEEDED"
                self.manifest_store.save(manifest)
                self.generate_final_pr_summary()
                return last_result
        manifest = self.manifest_store.load()
        if manifest.get("acceptedPatchSet", {}).get("status") == "VALIDATED":
            manifest["status"] = "PARTIAL_REMEDIATION_READY_FOR_PR"
            self.manifest_store.save(manifest)
            self.generate_final_pr_summary()
        else:
            manifest["status"] = "FAILED_MAX_ATTEMPTS"
            self.manifest_store.save(manifest)
        return last_result

    def run_patch_validation_attempt(self, attempt_number: int, patch_plan_path: str) -> dict:
        manifest = self.manifest_store.load()
        restore = restore_attempt_workspace(str(self.workspace.root), attempt_number)
        attempt_workspace = restore.get("payload", {}).get("attemptWorkspace")
        attempt_dir = self.workspace.root / f"attempt-{attempt_number}"
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_entry.update({"status": "STARTED", "patchPlan": patch_plan_path})
        self.manifest_store.save(manifest)

        dry_result_path = str(attempt_dir / "patch-dry-run-result.json")
        dry = dry_run_patch_plan(attempt_number, attempt_workspace, patch_plan_path, dry_result_path)
        attempt_entry["patchDryRunResult"] = f"attempt-{attempt_number}/patch-dry-run-result.json"
        if dry["status"] != "SUCCESS":
            attempt_entry["status"] = "PATCH_DRY_RUN_FAILED"
            outcome_path = self.run_outcome_analysis(attempt_number, patch_plan_path, dry_run_result_path=dry_result_path)
            attempt_entry["outcomeAnalysisSummary"] = outcome_path
            self.manifest_store.save(manifest)
            return dry

        proof_path = str(attempt_dir / "patch-application-proof.json")
        diff_path = str(attempt_dir / "patch.diff")
        patch = apply_patch_plan(attempt_number, attempt_workspace, patch_plan_path, proof_path, diff_path)
        attempt_entry["patchApplicationProof"] = f"attempt-{attempt_number}/patch-application-proof.json"
        if patch["status"] != "SUCCESS":
            attempt_entry["status"] = "PATCH_APPLICATION_FAILED"
            outcome_path = self.run_outcome_analysis(attempt_number, patch_plan_path, patch_application_proof_path=proof_path)
            attempt_entry["outcomeAnalysisSummary"] = outcome_path
            self.manifest_store.save(manifest)
            return patch

        validation_path = str(attempt_dir / "validation-result.json")
        validation = validate_attempt(
            attempt_number=attempt_number,
            repository_path=attempt_workspace,
            patch_plan_path=patch_plan_path,
            patch_application_proof_path=proof_path,
            output_path=validation_path,
            artifact_output_dir=str(attempt_dir),
            workflow_id=manifest["workflowId"],
            severity_scope=self.policy.severity_scope,
            baseline_assessment_path=str(self.workspace.root / "baseline" / "vulnerability-assessment-report.json"),
        )
        attempt_entry["validationResult"] = f"attempt-{attempt_number}/validation-result.json"
        attempt_entry["status"] = "VALIDATION_SUCCEEDED" if validation["status"] == "SUCCESS" else "VALIDATION_FAILED"
        if validation["status"] == "SUCCESS":
            manifest["acceptedPatchSet"] = self._accepted_patch_set(attempt_number, patch_plan_path, proof_path, f"attempt-{attempt_number}/validation-result.json")
        else:
            outcome_path = self.run_outcome_analysis(attempt_number, patch_plan_path, patch_application_proof_path=proof_path, validation_result_path=validation_path)
            attempt_entry["outcomeAnalysisSummary"] = outcome_path
        self.manifest_store.save(manifest)
        return validation

    def run_outcome_analysis(
        self,
        attempt_number: int,
        patch_plan_path: str,
        patch_application_proof_path: str | None = None,
        validation_result_path: str | None = None,
        dry_run_result_path: str | None = None,
    ) -> str:
        manifest = self.manifest_store.load()
        output_path = self.workspace.root / f"attempt-{attempt_number}" / "outcome-analysis-summary.json"
        create_outcome_analysis_summary(
            attempt_number=attempt_number,
            output_path=str(output_path),
            workflow_id=manifest.get("workflowId", "unknown"),
            patch_plan_path=patch_plan_path,
            patch_application_proof_path=patch_application_proof_path,
            validation_result_path=validation_result_path,
            dry_run_result_path=dry_run_result_path,
        )
        return f"attempt-{attempt_number}/outcome-analysis-summary.json"

    def generate_final_pr_summary(self) -> dict:
        manifest = self.manifest_store.load()
        final_dir = self.workspace.root / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        result = create_pr_summary(
            manifest_path=str(self.workspace.root / "manifest.json"),
            output_path=str(final_dir / "pr-summary.json"),
            pr_description_path=str(final_dir / "pr-description.md"),
            workflow_id=manifest.get("workflowId", "unknown"),
        )
        manifest.setdefault("final", {})["prSummary"] = "final/pr-summary.json"
        manifest["final"]["prDescription"] = "final/pr-description.md"
        self.manifest_store.save(manifest)
        return result

    def _accepted_patch_set(self, attempt_number: int, patch_plan_path: str, patch_proof_path: str, validation_result_ref: str) -> dict:
        plan = self._read_json(patch_plan_path)
        proof = self._read_json(patch_proof_path)
        applied_patch_ids = {item.get("patchId") for item in proof.get("patchResults", []) if item.get("status") == "APPLIED"}
        vulnerability_ids = []
        remediation_summary = []
        accepted_decisions = []
        for decision in plan.get("vulnerabilityDecisions", []):
            patch_ids = {patch.get("patchId") for patch in decision.get("patches", [])}
            if patch_ids and patch_ids.issubset(applied_patch_ids):
                vulnerability_id = decision.get("vulnerabilityId")
                vulnerability_ids.append(vulnerability_id)
                row = self._remediation_row(decision)
                remediation_summary.append(row)
                accepted_decisions.append({
                    "vulnerabilityId": vulnerability_id,
                    "decision": decision.get("decision", "PATCH"),
                    "patchIds": sorted(item for item in patch_ids if item),
                    "dependency": row.get("dependency"),
                    "oldVersion": row.get("oldVersion"),
                    "newVersion": row.get("newVersion"),
                })
        return {
            "patchSetId": f"accepted-patch-set-{attempt_number}",
            "status": "VALIDATED",
            "sourceAttempts": [attempt_number],
            "patchIds": sorted(item for item in applied_patch_ids if item),
            "vulnerabilityIds": sorted(item for item in vulnerability_ids if item),
            "validationResult": validation_result_ref,
            "appliesOnBaselineCommit": self.manifest_store.load().get("repository", {}).get("baselineCommit"),
            "remediationSummary": remediation_summary,
            "vulnerabilityDecisions": accepted_decisions,
        }

    @staticmethod
    def _remediation_row(decision: dict[str, Any]) -> dict[str, Any]:
        dependency = decision.get("dependency") or {}
        if isinstance(dependency, dict):
            package_name = dependency.get("packageName") or _coordinate(dependency)
            old_version = dependency.get("currentVersion") or dependency.get("oldVersion")
        else:
            package_name = dependency or decision.get("packageName")
            old_version = decision.get("oldVersion")
        patches = decision.get("patches", []) or []
        new_version = decision.get("newVersion")
        if not new_version:
            for patch in patches:
                new_version = patch.get("newVersion") or patch.get("targetVersion")
                if new_version:
                    break
        if not old_version:
            for patch in patches:
                old_version = patch.get("oldVersion") or patch.get("currentVersion")
                if old_version:
                    break
        return {
            "vulnerabilityId": decision.get("vulnerabilityId"),
            "aliases": decision.get("aliases", []),
            "dependency": package_name or "UNKNOWN",
            "oldVersion": old_version,
            "newVersion": new_version,
            "status": "REMEDIATED",
            "statusReason": "Patch set validated successfully.",
        }

    def _attempt_entry(self, manifest: dict, attempt_number: int) -> dict:
        attempts = manifest.setdefault("attempts", [])
        for attempt in attempts:
            if attempt.get("attemptNumber") == attempt_number:
                return attempt
        attempt = {"attemptNumber": attempt_number, "status": "INITIALIZED"}
        attempts.append(attempt)
        return attempt

    def _next_attempt_number(self) -> int:
        manifest = self.manifest_store.load()
        return len(manifest.get("attempts", [])) + 1

    @staticmethod
    def _read_json(path: str) -> dict:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return {}


def _coordinate(dependency: dict[str, Any]) -> str | None:
    group_id = dependency.get("groupId")
    artifact_id = dependency.get("artifactId")
    if group_id and artifact_id:
        return f"{group_id}:{artifact_id}"
    return dependency.get("artifactId") or dependency.get("groupId")
