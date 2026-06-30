from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

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
        baseline, assessment, and project-analysis steps, then delegates the
        autonomous Phase 5 routing loop to the orchestrator. ``planning_agent_output``
        is retained only as a test/integration hook for callers that inject one
        pre-generated structured JSON response for the first planning invocation.
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

        return self.run_orchestration_loop(progress, first_planning_agent_output=planning_agent_output)

    def run_orchestration_loop(
        self,
        progress: list[dict[str, Any]] | None = None,
        first_planning_agent_output: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the bounded Phase 5 planning/patch/outcome/replanning loop."""
        progress = progress if progress is not None else []
        attempt_number = 1
        injected_output = first_planning_agent_output
        prepared_attempts: set[int] = set()

        while attempt_number <= self.policy.max_attempts:
            if attempt_number not in prepared_attempts:
                prepared = self.prepare_attempt_workspace(attempt_number)
                self._record(progress, f"prepare_attempt_{attempt_number}", prepared)
                if prepared.get("status") != "SUCCESS":
                    return self.runtime_summary(progress, "Workflow stopped because attempt workspace preparation failed.")
                prepared_attempts.add(attempt_number)

            planning_result = self.run_planning_agent_boundary(
                attempt_number=attempt_number,
                planning_agent_output=injected_output,
            )
            injected_output = None
            self._record(progress, f"remediation_planning_agent_attempt_{attempt_number}", planning_result)
            if planning_result.get("status") != "SUCCESS":
                return self.runtime_summary(progress, "Workflow stopped because the Planning Agent did not return usable structured output.")

            routed = self.handle_planner_result(planning_result, attempt_number=attempt_number)
            self._record(progress, f"planner_result_routing_attempt_{attempt_number}", routed)

            if routed.get("status") == "ADDITIONAL_INVESTIGATION_COMPLETE":
                continue

            if routed.get("failureCode") == "PLANNING_CONSTRAINT_VIOLATION":
                return self.runtime_summary(progress, "Workflow stopped because the Planning Agent violated the investigation-limit constraint.")

            if routed.get("status") in {"MANUAL_REVIEW_REQUIRED", "PR_SUMMARY_CREATED", "SUCCESS"}:
                return self.runtime_summary(progress, "Workflow reached a terminal routing decision.")

            manifest = self.manifest_store.load()
            if manifest.get("status") == "OUTCOME_ANALYSIS_AGENT_INVOCATION_FAILED":
                return self.runtime_summary(progress, "Workflow stopped because Outcome Analysis Agent invocation failed.")

            if manifest.get("status") == "OUTCOME_ANALYSIS_COMPLETE":
                attempt_number += 1
                continue

            if routed.get("status") == "FAILED" and routed.get("failureCode") == "PATCH_PLAN_ARTIFACT_MISSING":
                return self.runtime_summary(progress, "Workflow stopped because the Planning Agent did not provide a patch-plan artifact.")

            attempt_number += 1

        max_attempts_result = self.handle_max_attempts_reached()
        self._record(progress, "max_attempts_routing", max_attempts_result)
        return self.runtime_summary(progress, "Workflow reached the configured remediation-attempt limit.")

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

    def prepare_attempt_workspace(self, attempt_number: int) -> dict:
        """Restore clean baseline and replay the accepted patch set for an attempt."""
        manifest = self.manifest_store.load()
        restore = restore_attempt_workspace(str(self.workspace.root), attempt_number)
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_workspace = restore.get("payload", {}).get("attemptWorkspace")
        attempt_entry["attemptWorkspace"] = attempt_workspace
        attempt_entry["status"] = "ATTEMPT_WORKSPACE_PREPARED" if restore.get("status") == "SUCCESS" else "ATTEMPT_WORKSPACE_PREPARE_FAILED"
        attempt_entry["workspacePreparation"] = {
            "restoreCleanBaseline": restore,
            "acceptedPatchSetReplay": [],
        }
        self.manifest_store.save(manifest)
        if restore.get("status") != "SUCCESS":
            return restore

        replay = self.replay_accepted_patch_set(attempt_number, attempt_workspace)
        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_entry.setdefault("workspacePreparation", {})["acceptedPatchSetReplay"] = replay.get("replayResults", [])
        if replay.get("status") != "SUCCESS":
            attempt_entry["status"] = "ACCEPTED_PATCH_SET_REPLAY_FAILED"
            manifest["status"] = "ACCEPTED_PATCH_SET_REPLAY_FAILED"
            self.manifest_store.save(manifest)
            return replay
        self.manifest_store.save(manifest)
        return {"status": "SUCCESS", "attemptWorkspace": attempt_workspace, "acceptedPatchSetReplay": replay}

    def replay_accepted_patch_set(self, attempt_number: int, attempt_workspace: str | None) -> dict:
        """Replay validated accepted patches onto the clean baseline attempt workspace."""
        if not attempt_workspace:
            return {"status": "FAILED", "failureCode": "ATTEMPT_WORKSPACE_MISSING", "replayResults": []}
        manifest = self.manifest_store.load()
        accepted = manifest.get("acceptedPatchSet", {})
        if not self._has_accepted_patch_set(manifest):
            return {"status": "SUCCESS", "replayResults": [], "message": "No accepted patch set to replay."}

        replay_results: list[dict[str, Any]] = []
        for source_attempt in accepted.get("sourceAttempts", []):
            source_entry = self._find_attempt(manifest, int(source_attempt))
            patch_plan_ref = source_entry.get("patchPlan") if source_entry else None
            if not patch_plan_ref:
                replay_results.append({"status": "SKIPPED", "sourceAttempt": source_attempt, "reason": "Patch plan not found."})
                continue
            patch_plan_path = self._resolve_workspace_ref(patch_plan_ref)
            replay_dir = self.workspace.root / f"attempt-{attempt_number}" / "accepted-patch-set-replay"
            replay_dir.mkdir(parents=True, exist_ok=True)
            proof_path = str(replay_dir / f"source-attempt-{source_attempt}-patch-application-proof.json")
            diff_path = str(replay_dir / f"source-attempt-{source_attempt}.diff")
            result = apply_patch_plan(attempt_number, attempt_workspace, patch_plan_path, proof_path, diff_path)
            replay_results.append({
                "status": result.get("status"),
                "sourceAttempt": source_attempt,
                "patchPlan": self._relative_ref(patch_plan_path),
                "patchApplicationProof": self._relative_ref(proof_path),
                "diff": self._relative_ref(diff_path),
                "failureCode": result.get("failureCode"),
            })
            if result.get("status") != "SUCCESS":
                return {"status": "FAILED", "failureCode": "ACCEPTED_PATCH_SET_REPLAY_FAILED", "replayResults": replay_results}
        return {"status": "SUCCESS", "replayResults": replay_results}

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
        current_attempt = attempt_number or 1
        if decision_type == "REQUEST_ADDITIONAL_EVIDENCE":
            return self.handle_additional_investigation_request(current_attempt, planning_result)
        if decision_type == "PATCH_PLAN":
            patch_plan_path = planning_result.get("patchPlanPath") or planning_result.get("artifactPath")
            if not patch_plan_path:
                return {"status": "FAILED", "failureCode": "PATCH_PLAN_ARTIFACT_MISSING"}
            result = self.run_patch_validation_attempt(current_attempt, patch_plan_path)
            if result.get("status") == "SUCCESS":
                self._finalize_successful_validation()
            return result
        if decision_type == "MANUAL_REVIEW":
            return self.handle_manual_review(planning_result)
        return {"status": "FAILED", "failureCode": "UNKNOWN_PLANNER_RESULT"}

    def handle_additional_investigation_request(self, attempt_number: int, request: dict) -> dict:
        """Execute an LLM-requested deterministic investigation and replan in the loop."""
        manifest = self.manifest_store.load()
        attempt = self._attempt_entry(manifest, attempt_number)
        requests = attempt.setdefault("additionalInvestigationRequests", [])
        requests.append(request)
        manifest.setdefault("additionalInvestigationRequests", []).append({"attemptNumber": attempt_number, "request": request})

        limit = self.policy.max_additional_investigation_requests_per_attempt
        if len(requests) > limit:
            if manifest.get("plannerConstraint"):
                attempt["status"] = "PLANNING_CONSTRAINT_VIOLATION"
                manifest["status"] = "PLANNING_CONSTRAINT_VIOLATION"
                self.manifest_store.save(manifest)
                return {"status": "FAILED", "failureCode": "PLANNING_CONSTRAINT_VIOLATION"}
            attempt["status"] = "ADDITIONAL_INVESTIGATION_LIMIT_REACHED"
            manifest["status"] = "ADDITIONAL_INVESTIGATION_LIMIT_REACHED"
            manifest["plannerConstraint"] = "Additional investigation limit reached. Planning Agent must return PATCH_PLAN or MANUAL_REVIEW."
            self.manifest_store.save(manifest)
            return {"status": "ADDITIONAL_INVESTIGATION_COMPLETE", "limitReached": True}

        self.manifest_store.save(manifest)
        investigation_result = self.execute_additional_investigation(attempt_number, len(requests), request)
        manifest = self.manifest_store.load()
        attempt = self._attempt_entry(manifest, attempt_number)
        attempt["status"] = "ADDITIONAL_INVESTIGATION_COMPLETE"
        attempt.setdefault("additionalInvestigationArtifacts", []).append(investigation_result.get("artifactPath"))
        manifest["status"] = "ADDITIONAL_INVESTIGATION_COMPLETE"
        manifest.setdefault("additionalInvestigationArtifacts", []).append({
            "attemptNumber": attempt_number,
            "artifactPath": investigation_result.get("artifactPath"),
            "requestedTool": investigation_result.get("requestedTool"),
            "status": investigation_result.get("status"),
            "reusedArtifact": investigation_result.get("reusedArtifact", False),
        })
        self.manifest_store.save(manifest)
        return investigation_result

    def execute_additional_investigation(self, attempt_number: int, investigation_number: int, request: dict) -> dict:
        """Invoke or reuse a registered deterministic evidence tool requested by the planner."""
        requested_tool = self._requested_tool_name(request)
        if not self._force_regenerate_requested(request):
            reusable = self._find_reusable_investigation_artifact(requested_tool)
            if reusable:
                return {
                    "status": "ADDITIONAL_INVESTIGATION_COMPLETE",
                    "requestedTool": requested_tool,
                    "artifactPath": reusable,
                    "toolStatus": "SUCCESS",
                    "reusedArtifact": True,
                }

        registry = self._investigation_tool_registry()
        runner = registry.get(requested_tool)
        if runner is None:
            return self._write_investigation_result(
                attempt_number,
                investigation_number,
                requested_tool,
                {
                    "status": "FAILED",
                    "failureCode": "UNSUPPORTED_INVESTIGATION_TOOL",
                    "requestedTool": requested_tool,
                    "request": request,
                    "message": "Requested deterministic investigation tool is not registered with the orchestrator.",
                },
            )
        result = runner(attempt_number, investigation_number, request)
        return self._write_investigation_result(attempt_number, investigation_number, requested_tool, result)

    def _investigation_tool_registry(self) -> dict[str, Callable[[int, int, dict], dict]]:
        return {
            "ProjectAnalyzerTool": self._run_project_analyzer_investigation,
            "project_analyzer": self._run_project_analyzer_investigation,
            "PROJECT_ANALYZER": self._run_project_analyzer_investigation,
            "OSVScannerTool": self._run_osv_scanner_investigation,
            "osv_scanner": self._run_osv_scanner_investigation,
            "OSV_SCANNER": self._run_osv_scanner_investigation,
            "ArtifactReferenceTool": self._run_artifact_reference_investigation,
            "artifact_reference": self._run_artifact_reference_investigation,
            "ManifestArtifactReader": self._run_artifact_reference_investigation,
        }

    def _run_project_analyzer_investigation(self, attempt_number: int, investigation_number: int, request: dict) -> dict:
        manifest = self.manifest_store.load()
        repository_path = manifest.get("baseline", {}).get("repositoryPath")
        if not repository_path:
            return {"status": "FAILED", "failureCode": "BASELINE_NOT_READY", "request": request}
        artifact_dir = self.workspace.root / f"attempt-{attempt_number}" / f"investigation-{investigation_number}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return analyze_project(
            repository_path=repository_path,
            vulnerability_assessment_path=str(self.workspace.root / "baseline" / "vulnerability-assessment-report.json"),
            output_path=str(artifact_dir / "project-analyzer-report.json"),
            artifact_output_dir=str(artifact_dir),
            workflow_id=manifest["workflowId"],
        )

    def _run_osv_scanner_investigation(self, attempt_number: int, investigation_number: int, request: dict) -> dict:
        manifest = self.manifest_store.load()
        repository_path = manifest.get("baseline", {}).get("repositoryPath")
        if not repository_path:
            return {"status": "FAILED", "failureCode": "BASELINE_NOT_READY", "request": request}
        artifact_dir = self.workspace.root / f"attempt-{attempt_number}" / f"investigation-{investigation_number}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return generate_vulnerability_assessment(
            repository_path=repository_path,
            output_path=str(artifact_dir / "vulnerability-assessment-report.json"),
            raw_report_path=str(artifact_dir / "osv-report.json"),
            severity_scope=self.policy.severity_scope,
            workflow_id=manifest["workflowId"],
        )

    def _run_artifact_reference_investigation(self, attempt_number: int, investigation_number: int, request: dict) -> dict:
        manifest = self.manifest_store.load()
        return {
            "status": "SUCCESS",
            "request": request,
            "artifactReferences": {
                "manifest": str(self.workspace.root / "manifest.json"),
                "baseline": manifest.get("baseline", {}),
                "attempts": manifest.get("attempts", []),
                "acceptedPatchSet": manifest.get("acceptedPatchSet", {}),
            },
        }

    def _write_investigation_result(
        self,
        attempt_number: int,
        investigation_number: int,
        requested_tool: str | None,
        result: dict,
    ) -> dict:
        artifact_dir = self.workspace.root / f"attempt-{attempt_number}" / f"investigation-{investigation_number}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "additional-investigation-result.json"
        payload = {
            "artifactId": f"additional-investigation-{attempt_number}-{investigation_number}",
            "attemptNumber": attempt_number,
            "investigationNumber": investigation_number,
            "requestedTool": requested_tool,
            "status": result.get("status", "UNKNOWN"),
            "result": result,
        }
        artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "status": "ADDITIONAL_INVESTIGATION_COMPLETE",
            "requestedTool": requested_tool,
            "artifactPath": self._relative_ref(str(artifact_path)),
            "toolStatus": result.get("status"),
            "failureCode": result.get("failureCode"),
            "reusedArtifact": False,
        }

    def _find_reusable_investigation_artifact(self, requested_tool: str | None) -> str | None:
        manifest = self.manifest_store.load()
        for item in reversed(manifest.get("additionalInvestigationArtifacts", [])):
            if item.get("requestedTool") != requested_tool:
                continue
            artifact_ref = item.get("artifactPath")
            if not artifact_ref:
                continue
            artifact_path = self._resolve_workspace_ref(artifact_ref)
            payload = self._read_json(artifact_path)
            if payload.get("status") == "SUCCESS" and payload.get("requestedTool") == requested_tool:
                return artifact_ref
        return None

    @staticmethod
    def _force_regenerate_requested(request: dict) -> bool:
        force_keys = ("forceRegenerate", "regenerate", "refresh", "rerunTool", "ignoreCachedArtifact")
        if any(bool(request.get(key)) for key in force_keys):
            return True
        mode = str(request.get("mode") or request.get("dataRegenerationPolicy") or "").upper()
        if mode in {"REGENERATE", "REFRESH", "RERUN"}:
            return True
        reason = str(request.get("reason") or request.get("statusReason") or "").lower()
        return "corrupt" in reason or "truncated" in reason or "stale" in reason or "insufficient" in reason

    @staticmethod
    def _requested_tool_name(request: dict) -> str | None:
        requested_tool = request.get("requestedTool") or request.get("tool") or request.get("toolName")
        if isinstance(requested_tool, dict):
            return requested_tool.get("name") or requested_tool.get("toolName")
        return requested_tool

    def run_attempt_loop(self, patch_plan_paths: list[str]) -> dict:
        """Run a bounded MVP attempt loop over provided patch-plan artifacts."""
        last_result: dict = {"status": "NOT_RUN"}
        for attempt_number, patch_plan_path in enumerate(patch_plan_paths[: self.policy.max_attempts], start=1):
            self.prepare_attempt_workspace(attempt_number)
            last_result = self.run_patch_validation_attempt(attempt_number, patch_plan_path)
            if last_result.get("status") == "SUCCESS":
                self._finalize_successful_validation()
                return last_result
        return self.handle_max_attempts_reached() or last_result

    def run_patch_validation_attempt(self, attempt_number: int, patch_plan_path: str) -> dict:
        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_workspace = attempt_entry.get("attemptWorkspace")
        if not attempt_workspace:
            prepare = self.prepare_attempt_workspace(attempt_number)
            if prepare.get("status") != "SUCCESS":
                return prepare
            manifest = self.manifest_store.load()
            attempt_entry = self._attempt_entry(manifest, attempt_number)
            attempt_workspace = attempt_entry.get("attemptWorkspace")

        attempt_dir = self.workspace.root / f"attempt-{attempt_number}"
        attempt_entry.update({"status": "PATCH_EXECUTION_STARTED", "patchPlan": patch_plan_path})
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

    def handle_manual_review(self, planning_result: dict) -> dict:
        manifest = self.manifest_store.load()
        manifest["status"] = "MANUAL_REVIEW_REQUIRED"
        manifest.setdefault("planning", {})["manualReviewDecision"] = self._relative_ref(planning_result.get("artifactPath"))
        self.manifest_store.save(manifest)
        if self._has_accepted_patch_set(manifest) and self.policy.allow_partial_pr:
            result = self.generate_final_pr_summary()
            manifest = self.manifest_store.load()
            manifest["status"] = "PR_SUMMARY_CREATED"
            manifest.setdefault("final", {})["prType"] = "PARTIAL_REMEDIATION"
            self.manifest_store.save(manifest)
            return result
        return {"status": "MANUAL_REVIEW_REQUIRED", "artifactPath": planning_result.get("artifactPath")}

    def handle_max_attempts_reached(self) -> dict:
        manifest = self.manifest_store.load()
        if self._has_accepted_patch_set(manifest) and self.policy.allow_partial_pr:
            result = self.generate_final_pr_summary()
            manifest = self.manifest_store.load()
            manifest["status"] = "PR_SUMMARY_CREATED"
            manifest.setdefault("final", {})["prType"] = "PARTIAL_REMEDIATION"
            self.manifest_store.save(manifest)
            return result
        manifest["status"] = "FAILED_MAX_ATTEMPTS"
        self.manifest_store.save(manifest)
        return {"status": "FAILED", "failureCode": "FAILED_MAX_ATTEMPTS"}

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
                "additionalInvestigationArtifacts": manifest.get("additionalInvestigationArtifacts", []),
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
    def _has_accepted_patch_set(manifest: dict[str, Any]) -> bool:
        accepted = manifest.get("acceptedPatchSet", {})
        return accepted.get("status") == "VALIDATED" and bool(accepted.get("patchIds"))

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

    @staticmethod
    def _find_attempt(manifest: dict[str, Any], attempt_number: int) -> dict[str, Any] | None:
        for attempt in manifest.get("attempts", []):
            if int(attempt.get("attemptNumber", 0)) == attempt_number:
                return attempt
        return None

    def _next_attempt_number(self) -> int:
        manifest = self.manifest_store.load()
        return len(manifest.get("attempts", [])) + 1

    def _resolve_workspace_ref(self, reference: str) -> str:
        path = Path(reference)
        return str(path if path.is_absolute() else self.workspace.root / path)

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
        if status == "PR_SUMMARY_CREATED":
            return "Review the generated PR summary artifact before creating a pull request."
        if status == "VALIDATION_SUCCEEDED":
            return "Review the final PR summary artifact before creating a pull request."
        if status == "BASELINE_BUILD_FAILED":
            return "Fix the repository baseline before attempting remediation."
        if status == "FAILED_MAX_ATTEMPTS":
            return "Review outcome-analysis artifacts and decide whether manual remediation is required."
        if status == "MANUAL_REVIEW_REQUIRED":
            return "Manual review is required; automated PR creation should remain disabled because no accepted patch set exists."
        if status == "PLANNING_AGENT_INVOCATION_FAILED":
            return "Review the planning context artifact and LLM invocation error before retrying."
        if status == "OUTCOME_ANALYSIS_AGENT_INVOCATION_FAILED":
            return "Review the outcome-analysis context artifact and LLM invocation error before retrying."
        if status == "PLANNING_CONSTRAINT_VIOLATION":
            return "Review the planning decision because the Planning Agent requested additional evidence after the investigation limit was reached."
        return "Workflow completed or stopped at a terminal state; review the manifest and generated artifacts."

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
