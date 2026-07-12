from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.agents import LLMInvocationError
from oss_remediation_agent.agents.remediation_outcome_analysis_agent import (
    build_outcome_analysis_context,
    persist_outcome_analysis_agent_output,
)
from oss_remediation_agent.workflow.phase6_orchestrator import Phase6WorkflowOrchestrator


class Phase6PatchProgressOrchestrator(Phase6WorkflowOrchestrator):
    """Phase 6 orchestrator with progress enrichment and terminal-stage guards."""

    _PRE_REMEDIATION_TERMINAL_STATUSES = {
        "CHECKOUT_FAILED",
        "BASELINE_BUILD_FAILED",
    }

    _BASELINE_FAILURE_SKIPPED_STEPS = (
        "vulnerability_assessment",
        "project_analysis",
        "remediation_planning_skipped",
        "patch_validation_skipped",
        "replanning_loop_skipped",
        "pull_request_delivery_skipped",
    )

    def run_assessment(self) -> dict:
        skipped = self._terminal_skip("vulnerability_assessment", "Vulnerability assessment")
        return skipped or super().run_assessment()

    def run_project_analysis(self) -> dict:
        skipped = self._terminal_skip("project_analysis", "Maven project analysis")
        return skipped or super().run_project_analysis()

    def run_planning_agent_boundary(
        self,
        attempt_number: int,
        planning_agent_output: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        terminal_status = self._terminal_status()
        if not terminal_status:
            return super().run_planning_agent_boundary(attempt_number, planning_agent_output)

        artifact_path = self.workspace.root / "final" / "skipped-remediation-planning.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "schemaVersion": "1.0",
            "artifactId": "skipped-remediation-planning",
            "workflowId": self.manifest_store.load().get("workflowId", "unknown"),
            "status": "SKIPPED",
            "decisionType": "MANUAL_REVIEW",
            "reason": f"Remediation planning was skipped because the workflow reached terminal status {terminal_status}.",
            "terminalStatus": terminal_status,
        }
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        manifest = self.manifest_store.load()
        manifest.setdefault("planning", {})["lastDecision"] = self._relative_ref(str(artifact_path))
        self._record_terminal_skip(manifest, "remediation_planning_skipped", terminal_status)
        self.manifest_store.save(manifest)
        return {
            "status": "SKIPPED",
            "decisionType": "MANUAL_REVIEW",
            "reason": artifact["reason"],
            "terminalStatus": terminal_status,
        }

    def prepare_attempt_workspace(self, attempt_number: int) -> dict:
        skipped = self._terminal_skip("patch_validation_skipped", "Attempt workspace preparation")
        return skipped or super().prepare_attempt_workspace(attempt_number)

    def run_patch_validation_attempt(self, attempt_number: int, patch_plan_path: str) -> dict:
        skipped = self._terminal_skip("patch_validation_skipped", "Patch application and validation")
        if skipped:
            return skipped

        result = super().run_patch_validation_attempt(attempt_number, patch_plan_path)
        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_dir = self.workspace.root / f"attempt-{attempt_number}"
        artifacts = {
            "patchDryRunResult": attempt_dir / "patch-dry-run-result.json",
            "patchApplicationProof": attempt_dir / "patch-application-proof.json",
            "patchDiff": attempt_dir / "patch.diff",
        }
        for key, path in artifacts.items():
            if path.exists():
                attempt_entry[key] = self._relative_ref(str(path))
        self._enrich_accepted_patch_set_severity(manifest)
        self.manifest_store.save(manifest)
        return result

    def handle_planner_result(self, planning_result: dict, attempt_number: int | None = None) -> dict:
        skipped = self._terminal_skip("patch_validation_skipped", "Planner-result routing")
        return skipped or super().handle_planner_result(planning_result, attempt_number)

    def handle_manual_review(self, planning_result: dict) -> dict:
        skipped = self._terminal_skip("patch_validation_skipped", "Patch application and validation")
        return skipped or super().handle_manual_review(planning_result)

    def handle_max_attempts_reached(self) -> dict:
        skipped = self._terminal_skip("replanning_loop_skipped", "Replanning")
        return skipped or super().handle_max_attempts_reached()

    def _finalize_pr_lifecycle(self, pr_type: str) -> dict:
        skipped = self._terminal_skip("pull_request_delivery_skipped", "Pull-request delivery")
        return skipped or super()._finalize_pr_lifecycle(pr_type)

    def run_outcome_analysis(
        self,
        attempt_number: int,
        patch_plan_path: str,
        patch_application_proof_path: str | None = None,
        validation_result_path: str | None = None,
        dry_run_result_path: str | None = None,
    ) -> str:
        if self._terminal_status() == "BASELINE_BUILD_FAILED":
            return self._run_baseline_failure_outcome_analysis()
        return super().run_outcome_analysis(
            attempt_number=attempt_number,
            patch_plan_path=patch_plan_path,
            patch_application_proof_path=patch_application_proof_path,
            validation_result_path=validation_result_path,
            dry_run_result_path=dry_run_result_path,
        )

    def runtime_summary(self, progress: list[dict[str, Any]], message: str) -> dict[str, Any]:
        manifest = self.manifest_store.load()
        if self._terminal_status(manifest) == "BASELINE_BUILD_FAILED":
            existing_steps = {str(item.get("step") or "") for item in progress}
            for step in self._BASELINE_FAILURE_SKIPPED_STEPS:
                if step not in existing_steps:
                    progress.append({"step": step, "status": "SKIPPED", "terminalStatus": "BASELINE_BUILD_FAILED"})
            outcome_ref = (manifest.get("final") or {}).get("outcomeAnalysisSummary")
            if outcome_ref and "baseline_failure_outcome_analysis" not in existing_steps:
                progress.append(
                    {
                        "step": "baseline_failure_outcome_analysis",
                        "status": "SUCCESS",
                        "artifactPath": outcome_ref,
                    }
                )
        return super().runtime_summary(progress, message)

    def _run_baseline_failure_outcome_analysis(self) -> str:
        manifest = self.manifest_store.load()
        final_dir = self.workspace.root / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        context_path = final_dir / "baseline-failure-outcome-analysis-context.json"
        output_path = final_dir / "outcome-analysis-summary.json"

        context = build_outcome_analysis_context(
            workspace_root=self.workspace.root,
            attempt_number=0,
        )
        context["workflowStatus"] = "BASELINE_BUILD_FAILED"
        context["analysisScope"] = {
            "failedStage": "BASELINE_BUILD",
            "remediationAttempted": False,
            "requiredConclusion": "Explain the baseline build failure and the corrective action required before remediation can run.",
        }
        context_path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        try:
            llm_output = self.llm_invoker.invoke("RemediationOutcomeAnalysisAgent", context)
            result = persist_outcome_analysis_agent_output(
                self.workspace.root,
                llm_output,
                attempt_number=0,
                output_path=output_path,
            )
            outcome_ref = self._relative_ref(result["artifactPath"]) or "final/outcome-analysis-summary.json"
        except (LLMInvocationError, ValueError) as exc:
            outcome_ref = self._relative_ref(str(context_path)) or "final/baseline-failure-outcome-analysis-context.json"
            manifest = self.manifest_store.load()
            manifest.setdefault("final", {})["outcomeAnalysisFailure"] = str(exc)

        manifest = self.manifest_store.load()
        manifest["status"] = "BASELINE_BUILD_FAILED"
        manifest.setdefault("final", {})["outcomeAnalysisSummary"] = outcome_ref
        self._record_terminal_skip(manifest, "baseline_failure_outcome_analysis", "BASELINE_BUILD_FAILED")
        self.manifest_store.save(manifest)
        return outcome_ref

    def _terminal_skip(self, step: str, label: str) -> dict[str, Any] | None:
        manifest = self.manifest_store.load()
        terminal_status = self._terminal_status(manifest)
        if not terminal_status:
            return None
        self._record_terminal_skip(manifest, step, terminal_status)
        self.manifest_store.save(manifest)
        return {
            "status": "SKIPPED",
            "reason": f"{label} was skipped because the workflow reached terminal status {terminal_status}.",
            "terminalStatus": terminal_status,
        }

    @classmethod
    def _terminal_status(cls, manifest: dict[str, Any] | None = None) -> str | None:
        if manifest is None:
            return None
        status = str(manifest.get("status") or "").upper()
        return status if status in cls._PRE_REMEDIATION_TERMINAL_STATUSES else None

    @staticmethod
    def _record_terminal_skip(manifest: dict[str, Any], step: str, terminal_status: str) -> None:
        skipped = manifest.setdefault("skippedStages", [])
        if not any(str(item.get("step") or "") == step for item in skipped):
            skipped.append({"step": step, "status": "SKIPPED", "terminalStatus": terminal_status})

    @classmethod
    def _display_steps_for_internal_step(cls, internal_step: str) -> list[str]:
        custom = {
            "remediation_planning_skipped": ["Remediation Planning"],
            "patch_validation_skipped": ["Patch Dry Run", "Dependency Patch Application", "Validation", "Accepted Patch Set"],
            "baseline_failure_outcome_analysis": ["Failure Analysis"],
            "pull_request_delivery_skipped": ["Remediation Verification Report", "PR Summary", "Draft Pull Request"],
        }
        return custom.get(internal_step, super()._display_steps_for_internal_step(internal_step))

    @classmethod
    def _normalize_step_status(cls, status: Any) -> str:
        if str(status or "").upper() == "SKIPPED":
            return "SKIPPED"
        return super()._normalize_step_status(status)

    @staticmethod
    def _aggregate_status(statuses: list[str]) -> str:
        active = [status for status in statuses if status != "SKIPPED"]
        if not active and statuses:
            return "SKIPPED"
        return Phase6WorkflowOrchestrator._aggregate_status(active)

    @staticmethod
    def _status_icon(status: str) -> str:
        if status == "SKIPPED":
            return "⏭"
        return Phase6WorkflowOrchestrator._status_icon(status)

    def _enrich_accepted_patch_set_severity(self, manifest: dict[str, Any]) -> None:
        accepted = manifest.get("acceptedPatchSet") or {}
        if accepted.get("status") != "VALIDATED":
            return
        severity_by_vulnerability = self._severity_by_vulnerability_id(manifest)
        if not severity_by_vulnerability:
            return
        for row in accepted.get("remediationSummary", []) or []:
            vulnerability_id = row.get("vulnerabilityId")
            severity = severity_by_vulnerability.get(vulnerability_id)
            if severity:
                row["severity"] = severity
        for row in accepted.get("vulnerabilityDecisions", []) or []:
            vulnerability_id = row.get("vulnerabilityId")
            severity = severity_by_vulnerability.get(vulnerability_id)
            if severity:
                row["severity"] = severity

    def _severity_by_vulnerability_id(self, manifest: dict[str, Any]) -> dict[str, str]:
        assessment_ref = (manifest.get("baseline") or {}).get("vulnerabilityAssessmentReport")
        if not assessment_ref:
            return {}
        assessment_path = Path(assessment_ref)
        if not assessment_path.is_absolute():
            assessment_path = self.workspace.root / assessment_path
        if not assessment_path.exists():
            return {}
        try:
            assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        severity_by_id: dict[str, str] = {}
        for vulnerability in assessment.get("vulnerabilities", []) or []:
            vulnerability_id = vulnerability.get("vulnerabilityId")
            severity = vulnerability.get("severity")
            if vulnerability_id and severity:
                severity_by_id[str(vulnerability_id)] = str(severity)
        return severity_by_id
