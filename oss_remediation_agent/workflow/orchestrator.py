from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.agents import GoogleGenAIJsonInvoker, LLMAgentInvoker, LLMInvocationError
from oss_remediation_agent.agents.remediation_outcome_analysis_agent import (
    build_outcome_analysis_context,
    persist_outcome_analysis_agent_output,
)
from oss_remediation_agent.agents.remediation_planning_agent import build_planning_context, persist_planning_agent_output
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
    """MVP workflow orchestrator.

    The orchestrator owns execution order, workflow lifecycle transitions, retry
    state, and manifest updates. AI agents remain reasoning boundaries that emit
    structured JSON contracts; deterministic tools only collect evidence or
    execute exact instructions.
    """

    def __init__(
        self,
        workspace_root: str,
        policy: RemediationPolicy | None = None,
        llm_invoker: LLMAgentInvoker | None = None,
    ):
        resolved_workspace_root = str(Path(workspace_root).resolve())
        self.workspace = WorkspaceManager(resolved_workspace_root)
        self.manifest_store = ManifestStore(Path(resolved_workspace_root) / "manifest.json")
        self.policy = policy or RemediationPolicy()
        self.llm_invoker = llm_invoker or GoogleGenAIJsonInvoker()

    def run_workflow(
        self,
        repository_url: str,
        reference_branch: str,
        planning_agent_output: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the production MVP workflow entry path.

        This method keeps ADK ``agent.py`` thin. It performs deterministic
        baseline, assessment, and project-analysis steps, then invokes the LLM
        Planning Agent boundary. ``planning_agent_output`` is retained only as a
        test/integration hook for callers that inject pre-generated structured
        JSON; production flow obtains that output through ``LLMAgentInvoker``.
        """
        progress: list[dict[str, Any]] = []

        baseline = self.checkout_and_baseline(repository_url, reference_branch)
        self._record(progress, "checkout_and_baseline", baseline)
        if baseline.get("status") != "SUCCESS":
            return self.runtime_summary(progress, "Workflow stopped because baseline build did not pass.")

        assessment = self.run_assessment()
        self._record(progress, "vulnerability_assessment", assessment)
        if assessment.get("status") != "SUCCESS":
            return self.runtime_summary(progress, "Workflow stopped because vulnerability assessment failed.")

        analysis = self.run_project_analysis()
        self._record(progress, "project_analysis", analysis)
        if analysis.get("status") not in {"SUCCESS", "PARTIAL"}:
            return self.runtime_summary(progress, "Workflow stopped because project analysis failed.")

        planning_result = self.run_planning_agent_boundary(attempt_number=1, planning_agent_output=planning_agent_output)
        self._record(progress, "remediation_planning_agent", planning_result)
        if planning_result.get("status") != "SUCCESS":
            return self.runtime_summary(progress, "Workflow stopped because the Planning Agent did not return usable structured output.")

        routed = self.handle_planner_result(planning_result, attempt_number=1)
        self._record(progress, "planner_result_routing", routed)
        return self.runtime_summary(progress, "Workflow routed the Remediation Planning Agent output.")

    def initialize(self, repository_url: str, reference_branch: str) -> dict:
        self.workspace.initialize()
        manifest = {
            "schemaVersion": "1.0",
            "artifactId": "manifest",
            "workflowId": "oss-remediation-mvp",
            "createdBy": "ADKWorkflowOrchestrator",
            "status": "INITIALIZED",
            "workspaceRoot": str(Path(self.workspace.root).resolve()),
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

    def run_planning_agent_boundary(
        self,
        attempt_number: int,
        planning_agent_output: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke the LLM Planning Agent boundary without deterministic planning."""
        manifest = self.manifest_store.load()
        context = build_planning_context(self.workspace.root, attempt_number=attempt_number)
        context_path = self.workspace.root / f"attempt-{attempt_number}" / "remediation-planning-context.json"
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest.setdefault("planning", {})["context"] = f"attempt-{attempt_number}/remediation-planning-context.json"
        manifest["planning"]["agent"] = "RemediationPlanningAgent"
        manifest["planning"]["expectedDecisionTypes"] = ["PATCH_PLAN", "MANUAL_REVIEW", "REQUEST_ADDITIONAL_EVIDENCE"]
        manifest["status"] = "PLANNING"
        self.manifest_store.save(manifest)

        try:
            llm_output = planning_agent_output if planning_agent_output is not None else self.llm_invoker.invoke("RemediationPlanningAgent", context)
            result = persist_planning_agent_output(
                self.workspace.root,
                llm_output,
                attempt_number=attempt_number,
            )
        except (LLMInvocationError, ValueError) as exc:
            manifest = self.manifest_store.load()
            manifest["status"] = "PLANNING_AGENT_INVOCATION_FAILED"
            manifest.setdefault("planning", {})["failureReason"] = str(exc)
            self.manifest_store.save(manifest)
            return {
                "status": "FAILED",
                "failureCode": "PLANNING_AGENT_INVOCATION_FAILED",
                "artifactPath": str(context_path),
                "error": str(exc),
            }

        manifest = self.manifest_store.load()
        manifest.setdefault("planning", {})["lastDecision"] = self._relative_ref(result["artifactPath"])
        manifest["status"] = "PLANNING_COMPLETE"
        self.manifest_store.save(manifest)
        return result

    def handle_planner_result(self, planning_result: dict, attempt_number: int | None = None) -> dict:
        """Route structured planner output without making remediation decisions."""
        decision_type = planning_result.get("decisionType") or planning_result.get("type")
        if decision_type == "REQUEST_ADDITIONAL_EVIDENCE":
            return self.handle_additional_investigation_request(attempt_number or 1, planning_result)
        if decision_type == "PATCH_PLAN":
            patch_plan_path = planning_result.get("patchPlanPath") or planning_result.get("artifactPath")
            if not patch_plan_path:
                return {"status": "FAILED", "failureCode": "PATCH_PLAN_ARTIFACT_MISSING"}
            result = self.run_patch_validation_attempt(attempt_number or self._next_attempt_number(), patch_plan_path)
            if result.get("status") == "SUCCESS":
                self._finalize_successful_validation()
            return result
        if decision_type == "MANUAL_REVIEW":
            manifest = self.manifest_store.load()
            manifest["status"] = "MANUAL_REVIEW_REQUIRED"
            manifest.setdefault("planning", {})["manualReviewDecision"] = self._relative_ref(planning_result.get("artifactPath"))
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
                self._finalize_successful_validation()
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
        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_entry["patchDryRunResult"] = f"attempt-{attempt_number}/patch-dry-run-result.json"
        if dry["status"] != "SUCCESS":
            attempt_entry["status"] = "PATCH_DRY_RUN_FAILED"
            manifest["status"] = "PATCH_DRY_RUN_FAILED"
            self.manifest_store.save(manifest)
            outcome_path = self.run_outcome_analysis(attempt_number, patch_plan_path, dry_run_result_path=dry_result_path)
            manifest = self.manifest_store.load()
            attempt_entry = self._attempt_entry(manifest, attempt_number)
            attempt_entry["outcomeAnalysisSummary"] = outcome_path
            self.manifest_store.save(manifest)
            return dry

        proof_path = str(attempt_dir / "patch-application-proof.json")
        diff_path = str(attempt_dir / "patch.diff")
        patch = apply_patch_plan(attempt_number, attempt_workspace, patch_plan_path, proof_path, diff_path)
        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_entry["patchApplicationProof"] = f"attempt-{attempt_number}/patch-application-proof.json"
        if patch["status"] != "SUCCESS":
            attempt_entry["status"] = "PATCH_APPLICATION_FAILED"
            manifest["status"] = "PATCH_APPLICATION_FAILED"
            self.manifest_store.save(manifest)
            outcome_path = self.run_outcome_analysis(attempt_number, patch_plan_path, patch_application_proof_path=proof_path)
            manifest = self.manifest_store.load()
            attempt_entry = self._attempt_entry(manifest, attempt_number)
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
        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_entry["validationResult"] = f"attempt-{attempt_number}/validation-result.json"
        attempt_entry["status"] = "VALIDATION_SUCCEEDED" if validation["status"] == "SUCCESS" else "VALIDATION_FAILED"
        if validation["status"] == "SUCCESS":
            manifest["acceptedPatchSet"] = self._accepted_patch_set(attempt_number, patch_plan_path, proof_path, f"attempt-{attempt_number}/validation-result.json")
            self.manifest_store.save(manifest)
        else:
            manifest["status"] = "VALIDATION_FAILED"
            self.manifest_store.save(manifest)
            outcome_path = self.run_outcome_analysis(attempt_number, patch_plan_path, patch_application_proof_path=proof_path, validation_result_path=validation_path)
            manifest = self.manifest_store.load()
            attempt_entry = self._attempt_entry(manifest, attempt_number)
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
        context = build_outcome_analysis_context(
            workspace_root=self.workspace.root,
            attempt_number=attempt_number,
            patch_plan_path=patch_plan_path,
            patch_application_proof_path=patch_application_proof_path,
            validation_result_path=validation_result_path,
            dry_run_result_path=dry_run_result_path,
        )
        context_path = self.workspace.root / f"attempt-{attempt_number}" / "outcome-analysis-context.json"
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_entry["outcomeAnalysisContext"] = f"attempt-{attempt_number}/outcome-analysis-context.json"
        manifest["status"] = "OUTCOME_ANALYSIS"
        self.manifest_store.save(manifest)

        try:
            llm_output = self.llm_invoker.invoke("RemediationOutcomeAnalysisAgent", context)
            result = persist_outcome_analysis_agent_output(
                self.workspace.root,
                llm_output,
                attempt_number=attempt_number,
            )
        except (LLMInvocationError, ValueError) as exc:
            manifest = self.manifest_store.load()
            attempt_entry = self._attempt_entry(manifest, attempt_number)
            attempt_entry["outcomeAnalysisFailure"] = str(exc)
            manifest["status"] = "OUTCOME_ANALYSIS_AGENT_INVOCATION_FAILED"
            self.manifest_store.save(manifest)
            return f"attempt-{attempt_number}/outcome-analysis-context.json"

        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_entry["outcomeAnalysisSummary"] = self._relative_ref(result["artifactPath"])
        manifest["status"] = "OUTCOME_ANALYSIS_COMPLETE"
        self.manifest_store.save(manifest)
        return self._relative_ref(result["artifactPath"]) or f"attempt-{attempt_number}/outcome-analysis-summary.json"

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

    def runtime_summary(self, progress: list[dict[str, Any]], message: str) -> dict[str, Any]:
        manifest = self.manifest_store.load()
        workspace_root = Path(self.workspace.root).resolve()
        return {
            "status": manifest.get("status", "UNKNOWN"),
            "message": message,
            "workflowId": manifest.get("workflowId"),
            "workspaceRoot": str(workspace_root),
            "manifestPath": str((workspace_root / "manifest.json").resolve()),
            "progress": progress,
            "artifacts": {
                "baseline": manifest.get("baseline", {}),
                "planning": manifest.get("planning", {}),
                "acceptedPatchSet": manifest.get("acceptedPatchSet", {}),
                "final": manifest.get("final", {}),
            },
            "nextAction": self._next_action(manifest),
        }

    def _finalize_successful_validation(self) -> dict:
        """Apply the common successful-validation lifecycle transition."""
        manifest = self.manifest_store.load()
        manifest["status"] = "VALIDATION_SUCCEEDED"
        self.manifest_store.save(manifest)
        return self.generate_final_pr_summary()

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

    def _relative_ref(self, path: str | None) -> str | None:
        if not path:
            return None
        candidate = Path(path)
        try:
            return str(candidate.relative_to(self.workspace.root))
        except ValueError:
            return str(candidate)

    @staticmethod
    def _record(progress: list[dict[str, Any]], step: str, result: dict[str, Any]) -> None:
        progress.append({
            "step": step,
            "status": result.get("status"),
            "failureCode": result.get("failureCode"),
            "decisionType": result.get("decisionType"),
            "artifactPath": result.get("artifactPath"),
        })

    @staticmethod
    def _next_action(manifest: dict[str, Any]) -> str:
        status = manifest.get("status")
        if status == "PLANNING_AGENT_INVOCATION_FAILED":
            return "Review the planning context artifact and LLM invocation error before retrying."
        if status == "PROJECT_ANALYSIS_COMPLETE":
            return "Invoke the Remediation Planning Agent with the generated assessment and project-analysis artifacts."
        if status == "PATCH_DRY_RUN_FAILED":
            return "Run Outcome Analysis for the dry-run failure before replanning."
        if status == "OUTCOME_ANALYSIS_COMPLETE":
            return "Reinvoke the Remediation Planning Agent using the outcome-analysis summary for replanning."
        if status == "VALIDATION_SUCCEEDED":
            return "Review the final PR summary artifact before creating a pull request."
        if status == "BASELINE_BUILD_FAILED":
            return "Fix the repository baseline before attempting remediation."
        if status == "FAILED_MAX_ATTEMPTS":
            return "Review outcome-analysis artifacts and decide whether manual remediation is required."
        if status == "MANUAL_REVIEW_REQUIRED":
            return "Manual review is required; automated PR creation should remain disabled."
        if status == "ADDITIONAL_INVESTIGATION_REQUESTED":
            return "Run the requested deterministic investigation through the orchestrator, then reinvoke the Planning Agent."
        if status == "OUTCOME_ANALYSIS_AGENT_INVOCATION_FAILED":
            return "Review the outcome-analysis context artifact and LLM invocation error before replanning."
        return "Review the manifest and generated artifacts for the next workflow action."

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
