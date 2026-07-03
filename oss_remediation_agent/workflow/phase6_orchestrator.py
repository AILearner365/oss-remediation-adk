from __future__ import annotations

from pathlib import Path
from typing import Any

from oss_remediation_agent.tools.pr_publisher_tool import publish_pull_request
from oss_remediation_agent.workflow.orchestrator import WorkflowOrchestrator
from oss_remediation_agent.workflow.phase5_orchestrator import Phase5WorkflowOrchestrator


class Phase6WorkflowOrchestrator(Phase5WorkflowOrchestrator):
    """Policy-aware Phase 6 finalization for PR summary and publication.

    PR publication is not unconditional. The deterministic orchestrator follows
    RemediationPolicy.pr_creation_mode after a validated accepted patch set
    exists: AUTO, SUMMARY_ONLY, MANUAL_APPROVAL, or DISABLED.
    """

    def runtime_summary(self, progress: list[dict[str, Any]], message: str) -> dict[str, Any]:
        manifest = self.manifest_store.load()
        enriched_progress = self._enrich_progress(progress, manifest)
        workspace_root = Path(self.workspace.root).resolve()
        return {
            "status": manifest.get("status", "UNKNOWN"),
            "message": message,
            "workflowId": manifest.get("workflowId"),
            "workspaceRoot": str(workspace_root),
            "manifestPath": str((workspace_root / "manifest.json").resolve()),
            "progress": enriched_progress,
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
        manifest = self.manifest_store.load()
        manifest["status"] = "VALIDATION_SUCCEEDED"
        self.manifest_store.save(manifest)
        return self._finalize_pr_lifecycle("FULL_REMEDIATION")

    def handle_manual_review(self, planning_result: dict) -> dict:
        manifest = self.manifest_store.load()
        manifest["status"] = "MANUAL_REVIEW_REQUIRED"
        manifest.setdefault("planning", {})["manualReviewDecision"] = self._relative_ref(planning_result.get("artifactPath"))
        self.manifest_store.save(manifest)
        if self._has_accepted_patch_set(manifest) and self.policy.allow_partial_pr:
            return self._finalize_pr_lifecycle("PARTIAL_REMEDIATION")
        return {"status": "MANUAL_REVIEW_REQUIRED", "artifactPath": planning_result.get("artifactPath")}

    def handle_max_attempts_reached(self) -> dict:
        manifest = self.manifest_store.load()
        if self._has_accepted_patch_set(manifest) and self.policy.allow_partial_pr:
            return self._finalize_pr_lifecycle("PARTIAL_REMEDIATION")
        manifest["status"] = "FAILED_MAX_ATTEMPTS"
        self.manifest_store.save(manifest)
        return {"status": "FAILED", "failureCode": "FAILED_MAX_ATTEMPTS"}

    def _finalize_pr_lifecycle(self, pr_type: str) -> dict:
        mode = str(getattr(self.policy, "pr_creation_mode", "SUMMARY_ONLY") or "SUMMARY_ONLY").upper()
        manifest = self.manifest_store.load()
        manifest.setdefault("final", {})["prType"] = pr_type
        manifest["final"]["prCreationPolicy"] = {
            "mode": mode,
            "createDraftPr": bool(getattr(self.policy, "create_draft_pr", True)),
            "requireValidatedPatchSetForPr": bool(getattr(self.policy, "require_validated_patch_set_for_pr", True)),
            "allowManualApprovalPrCreation": bool(getattr(self.policy, "allow_manual_approval_pr_creation", False)),
        }
        self.manifest_store.save(manifest)

        if mode == "DISABLED":
            manifest = self.manifest_store.load()
            manifest["status"] = "PR_CREATION_DISABLED"
            self.manifest_store.save(manifest)
            return {"status": "PR_CREATION_DISABLED", "reason": "PR creation is disabled by policy."}

        summary_result = self.generate_final_pr_summary()

        if mode == "SUMMARY_ONLY":
            manifest = self.manifest_store.load()
            manifest["status"] = "PR_SUMMARY_CREATED"
            manifest.setdefault("final", {})["prType"] = pr_type
            self.manifest_store.save(manifest)
            return summary_result

        if mode == "MANUAL_APPROVAL":
            manifest = self.manifest_store.load()
            manifest["status"] = "PR_AWAITING_MANUAL_APPROVAL"
            manifest.setdefault("final", {})["prType"] = pr_type
            self.manifest_store.save(manifest)
            return {
                "status": "PR_AWAITING_MANUAL_APPROVAL",
                "artifactPath": summary_result.get("artifactPath"),
                "reason": "PR creation policy requires manual approval after summary generation.",
            }

        if mode != "AUTO":
            manifest = self.manifest_store.load()
            manifest["status"] = "PR_CREATION_FAILED"
            manifest.setdefault("final", {})["prCreationFailure"] = f"Unsupported prCreationPolicy.mode: {mode}"
            self.manifest_store.save(manifest)
            return {"status": "FAILED", "failureCode": "UNSUPPORTED_PR_CREATION_MODE", "mode": mode}

        manifest = self.manifest_store.load()
        if getattr(self.policy, "require_validated_patch_set_for_pr", True) and not self._has_accepted_patch_set(manifest):
            manifest["status"] = "PR_CREATION_FAILED"
            manifest.setdefault("final", {})["prCreationFailure"] = "Validated accepted patch set is required by policy."
            self.manifest_store.save(manifest)
            return {"status": "FAILED", "failureCode": "VALIDATED_PATCH_SET_REQUIRED"}

        final_dir = self.workspace.root / "final"
        publication_path = final_dir / "pull-request-publication.json"
        publish_result = publish_pull_request(
            manifest_path=str(self.workspace.root / "manifest.json"),
            pr_summary_path=str(final_dir / "pr-summary.json"),
            pr_description_path=str(final_dir / "pr-description.md"),
            output_path=str(publication_path),
            draft=bool(getattr(self.policy, "create_draft_pr", True)),
        )

        manifest = self.manifest_store.load()
        manifest.setdefault("final", {})["pullRequestPublication"] = "final/pull-request-publication.json"
        if publish_result.get("status") == "SUCCESS":
            payload = publish_result.get("payload", {})
            manifest["status"] = "PULL_REQUEST_CREATED"
            manifest["final"]["pullRequest"] = {
                "status": "CREATED",
                "branchName": payload.get("branchName"),
                "commitSha": payload.get("commitSha"),
                "prUrl": payload.get("prUrl"),
                "draft": payload.get("draft"),
            }
        else:
            manifest["status"] = "PR_CREATION_FAILED"
            manifest["final"]["prCreationFailure"] = publish_result.get("failureCode") or "PR_CREATION_FAILED"
        self.manifest_store.save(manifest)
        return publish_result

    @staticmethod
    def _next_action(manifest: dict[str, Any]) -> str:
        status = manifest.get("status")
        final = manifest.get("final", {})
        if status == "PULL_REQUEST_CREATED":
            pull_request = final.get("pullRequest") or {}
            pr_url = pull_request.get("prUrl")
            is_draft = bool(pull_request.get("draft"))
            if is_draft and pr_url:
                return f"Review the generated draft pull request, verify the dependency-only changes, and mark it ready for review when approved: {pr_url}"
            if pr_url:
                return f"Review the generated pull request and proceed with repository review/merge policy: {pr_url}"
            return "Review final.pullRequest metadata and proceed with repository review/merge policy."
        if status == "PR_CREATION_FAILED":
            return "Review final/pull-request-publication.json and final.prCreationFailure, then fix the deterministic PR publishing failure."
        if status == "PR_SUMMARY_CREATED":
            return "PR summary generated only because prCreationPolicy.mode is SUMMARY_ONLY. No pull request was created by policy."
        if status == "PR_AWAITING_MANUAL_APPROVAL":
            return "Review the generated PR summary and approve publishing if the validated patch set should be pushed as a pull request."
        if status == "PR_CREATION_DISABLED":
            return "PR creation is disabled by policy. Review validation and summary artifacts as needed."
        if status == "VALIDATION_SUCCEEDED":
            return "Validation succeeded; Phase 6 PR policy handling should generate summary, await approval, or publish based on policy."
        return WorkflowOrchestrator._next_action(manifest)

    @staticmethod
    def _enrich_progress(progress: list[dict[str, Any]], manifest: dict[str, Any]) -> list[dict[str, Any]]:
        enriched = list(progress)
        seen_steps = {item.get("step") for item in enriched}

        for attempt in manifest.get("attempts", []) or []:
            attempt_number = attempt.get("attemptNumber")
            prefix = f"attempt_{attempt_number}"
            if attempt.get("patchDryRunResult") and f"patch_dry_run_{prefix}" not in seen_steps:
                enriched.append({"step": f"patch_dry_run_{prefix}", "status": "SUCCESS", "artifactPath": attempt.get("patchDryRunResult")})
            if attempt.get("patchApplicationProof") and f"patch_apply_{prefix}" not in seen_steps:
                enriched.append({"step": f"patch_apply_{prefix}", "status": "SUCCESS", "artifactPath": attempt.get("patchApplicationProof")})
            if attempt.get("validationResult") and f"validation_{prefix}" not in seen_steps:
                enriched.append({"step": f"validation_{prefix}", "status": attempt.get("status"), "artifactPath": attempt.get("validationResult")})

        accepted = manifest.get("acceptedPatchSet", {})
        if accepted.get("status") == "VALIDATED" and "accepted_patch_set_created" not in seen_steps:
            enriched.append({
                "step": "accepted_patch_set_created",
                "status": "SUCCESS",
                "patchSetId": accepted.get("patchSetId"),
                "patchCount": len(accepted.get("patchIds", []) or []),
            })

        final = manifest.get("final", {})
        if final.get("prSummary") and "pr_summary_created" not in seen_steps:
            enriched.append({"step": "pr_summary_created", "status": "SUCCESS", "artifactPath": final.get("prSummary")})
        if final.get("pullRequestPublication") and "pull_request_published" not in seen_steps:
            pull_request = final.get("pullRequest") or {}
            enriched.append({
                "step": "pull_request_published",
                "status": "SUCCESS" if manifest.get("status") == "PULL_REQUEST_CREATED" else manifest.get("status"),
                "artifactPath": final.get("pullRequestPublication"),
                "prUrl": pull_request.get("prUrl"),
                "branchName": pull_request.get("branchName"),
            })
        return enriched
