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
            pr_url = (final.get("pullRequest") or {}).get("prUrl")
            return f"Pull request created: {pr_url}" if pr_url else "Pull request created; review final.pullRequest metadata."
        if status == "PR_CREATION_FAILED":
            return "Review final/pull-request-publication.json and final.prCreationFailure, then fix the deterministic PR publishing failure."
        if status == "PR_SUMMARY_CREATED":
            return "PR summary generated only because prCreationPolicy.mode is SUMMARY_ONLY. No pull request was created by policy."
        if status == "PR_AWAITING_MANUAL_APPROVAL":
            return "PR summary generated; prCreationPolicy.mode is MANUAL_APPROVAL, so an explicit approval step is required before publishing."
        if status == "PR_CREATION_DISABLED":
            return "PR creation is disabled by policy. Review validation and summary artifacts as needed."
        if status == "VALIDATION_SUCCEEDED":
            return "Validation succeeded; Phase 6 PR policy handling should generate summary, await approval, or publish based on policy."
        return WorkflowOrchestrator._next_action(manifest)
