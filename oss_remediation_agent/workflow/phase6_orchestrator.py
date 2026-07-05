from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.tools.pr_publisher_tool import publish_pull_request
from oss_remediation_agent.workflow.orchestrator import WorkflowOrchestrator
from oss_remediation_agent.workflow.phase5_orchestrator import Phase5WorkflowOrchestrator


class Phase6WorkflowOrchestrator(Phase5WorkflowOrchestrator):
    """Policy-aware Phase 6 finalization for PR summary and publication."""

    WORKFLOW_STAGES: list[dict[str, Any]] = [
        {"name": "Repository Preparation", "steps": ["Repository Checkout", "Baseline Build"]},
        {"name": "Assessment", "steps": ["OSS Vulnerability Assessment", "Maven Project Analysis"]},
        {"name": "Remediation", "steps": ["Remediation Planning", "Patch Dry Run", "Dependency Patch Application"]},
        {"name": "Validation", "steps": ["Validation", "Accepted Patch Set"]},
        {"name": "Outcome Analysis", "steps": ["Failure Analysis"]},
        {"name": "Delivery", "steps": ["PR Summary", "Draft Pull Request"]},
    ]

    SUCCESS_STATUSES = {
        "SUCCESS",
        "PARTIAL",
        "VALIDATED",
        "VALIDATION_SUCCEEDED",
        "PULL_REQUEST_CREATED",
        "PR_SUMMARY_CREATED",
        "COMPLETED",
        "SKIPPED",
    }

    FAILURE_STATUSES = {
        "FAILED",
        "CHECKOUT_FAILED",
        "BASELINE_BUILD_FAILED",
        "SCANNING_FAILED",
        "PROJECT_ANALYSIS_FAILED",
        "PATCH_DRY_RUN_FAILED",
        "PATCH_APPLICATION_FAILED",
        "VALIDATION_FAILED",
        "PR_CREATION_FAILED",
        "FAILED_MAX_ATTEMPTS",
    }

    USER_FACING_FINAL_STATUSES = {
        "PULL_REQUEST_CREATED",
        "PR_CREATION_FAILED",
        "VALIDATION_FAILED",
        "BASELINE_BUILD_FAILED",
        "MANUAL_REVIEW_REQUIRED",
    }

    ARTIFACT_LABELS: dict[tuple[str, str], str] = {
        ("baseline", "baselineBuildResult"): "Baseline Build Result",
        ("baseline", "vulnerabilityAssessmentReport"): "Vulnerability Assessment Report",
        ("baseline", "projectAnalyzerReport"): "Project Analyzer Report",
        ("planning", "lastDecision"): "Remediation Patch Plan",
        ("final", "prSummary"): "PR Summary",
        ("final", "prDescription"): "PR Description",
        ("final", "pullRequestPublication"): "Pull Request Publication Result",
    }

    def runtime_summary(self, progress: list[dict[str, Any]], message: str) -> dict[str, Any]:
        manifest = self.manifest_store.load()
        enriched_progress = self._enrich_progress(progress, manifest)
        workflow_stages = self._workflow_stages(enriched_progress)
        workspace_root = Path(self.workspace.root).resolve()
        pr_info = self._pull_request_info(manifest)
        artifact_summary = self._artifact_summary(manifest)
        display_status = self._user_facing_final_status(manifest)
        display_message = self._summary_message(manifest, message)
        adk_web_response = self._format_adk_web_response(
            manifest=manifest,
            display_status=display_status,
            message=display_message,
            workspace_root=workspace_root,
            workflow_stages=workflow_stages,
            artifacts=artifact_summary,
            pull_request=pr_info,
        )
        return {
            "status": display_status,
            "internalStatus": manifest.get("status", "UNKNOWN"),
            "message": display_message,
            "workflowId": manifest.get("workflowId"),
            "workspaceRoot": str(workspace_root),
            "manifestPath": str((workspace_root / "manifest.json").resolve()),
            "adkWebResponse": adk_web_response,
            "workflowStages": workflow_stages,
            "progress": enriched_progress,
            "artifacts": {
                "baseline": manifest.get("baseline", {}),
                "planning": manifest.get("planning", {}),
                "acceptedPatchSet": manifest.get("acceptedPatchSet", {}),
                "final": manifest.get("final", {}),
                "additionalInvestigationArtifacts": manifest.get("additionalInvestigationArtifacts", []),
            },
            "pullRequest": pr_info,
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
            manifest["status"] = "PR_CREATION_FAILED"
            manifest.setdefault("final", {})["prCreationFailure"] = "PR creation is disabled by policy."
            self.manifest_store.save(manifest)
            return {"status": "PR_CREATION_FAILED", "reason": "PR creation is disabled by policy."}

        summary_result = self.generate_final_pr_summary()

        if mode == "SUMMARY_ONLY":
            manifest = self.manifest_store.load()
            manifest["status"] = "PR_CREATION_FAILED"
            manifest.setdefault("final", {})["prType"] = pr_type
            manifest["final"]["prCreationFailure"] = "PR creation policy is SUMMARY_ONLY."
            self.manifest_store.save(manifest)
            return {"status": "PR_CREATION_FAILED", "artifactPath": summary_result.get("artifactPath"), "reason": "PR creation policy is SUMMARY_ONLY."}

        if mode == "MANUAL_APPROVAL":
            manifest = self.manifest_store.load()
            manifest["status"] = "MANUAL_REVIEW_REQUIRED"
            manifest.setdefault("final", {})["prType"] = pr_type
            self.manifest_store.save(manifest)
            return {
                "status": "MANUAL_REVIEW_REQUIRED",
                "artifactPath": summary_result.get("artifactPath"),
                "reason": "PR creation policy requires manual approval after summary generation.",
            }

        if mode != "AUTO":
            manifest = self.manifest_store.load()
            manifest["status"] = "PR_CREATION_FAILED"
            manifest.setdefault("final", {})["prCreationFailure"] = f"Unsupported prCreationPolicy.mode: {mode}"
            self.manifest_store.save(manifest)
            return {"status": "PR_CREATION_FAILED", "failureCode": "UNSUPPORTED_PR_CREATION_MODE", "mode": mode}

        manifest = self.manifest_store.load()
        if getattr(self.policy, "require_validated_patch_set_for_pr", True) and not self._has_accepted_patch_set(manifest):
            manifest["status"] = "PR_CREATION_FAILED"
            manifest.setdefault("final", {})["prCreationFailure"] = "Validated accepted patch set is required by policy."
            self.manifest_store.save(manifest)
            return {"status": "PR_CREATION_FAILED", "failureCode": "VALIDATED_PATCH_SET_REQUIRED"}

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
                return f"Draft pull request created for dependency-only review: {pr_url}"
            if pr_url:
                return f"Pull request created for repository review: {pr_url}"
            return "Pull request metadata was created in final.pullRequest."
        if status == "PR_CREATION_FAILED":
            return "PR creation failed. Review final/pull-request-publication.json and final.prCreationFailure."
        if status == "VALIDATION_SUCCEEDED":
            return "Validation succeeded; Phase 6 PR policy handling completed according to policy."
        return WorkflowOrchestrator._next_action(manifest)

    @classmethod
    def _workflow_stages(cls, progress: list[dict[str, Any]]) -> list[dict[str, Any]]:
        step_statuses = cls._display_step_statuses(progress)
        stages: list[dict[str, Any]] = []
        for stage in cls.WORKFLOW_STAGES:
            steps = []
            for step_name in stage["steps"]:
                steps.append({"name": step_name, "status": step_statuses.get(step_name, "NOT_RUN")})
            stage_status = cls._aggregate_status([step["status"] for step in steps])
            stages.append({"name": stage["name"], "status": stage_status, "steps": steps})
        return stages

    @classmethod
    def _display_step_statuses(cls, progress: list[dict[str, Any]]) -> dict[str, str]:
        statuses: dict[str, str] = {}
        for item in progress:
            internal_step = str(item.get("step") or "")
            status = cls._normalize_step_status(item.get("status"))
            for display_step in cls._display_steps_for_internal_step(internal_step):
                statuses[display_step] = cls._merge_status(statuses.get(display_step), status)
        return statuses

    @staticmethod
    def _display_steps_for_internal_step(internal_step: str) -> list[str]:
        if internal_step == "checkout_and_baseline":
            return ["Repository Checkout", "Baseline Build"]
        if internal_step == "repository_checkout":
            return ["Repository Checkout"]
        if internal_step == "baseline_build":
            return ["Baseline Build"]
        if internal_step == "vulnerability_assessment":
            return ["OSS Vulnerability Assessment"]
        if internal_step == "project_analysis":
            return ["Maven Project Analysis"]
        if internal_step.startswith("remediation_planning_agent"):
            return ["Remediation Planning"]
        if internal_step.startswith("patch_dry_run"):
            return ["Patch Dry Run"]
        if internal_step.startswith("patch_apply"):
            return ["Dependency Patch Application"]
        if internal_step.startswith("validation"):
            return ["Validation"]
        if internal_step == "accepted_patch_set_created":
            return ["Accepted Patch Set"]
        if internal_step == "outcome_analysis":
            return ["Failure Analysis"]
        if internal_step == "pr_summary_created":
            return ["PR Summary"]
        if internal_step == "pull_request_published":
            return ["Draft Pull Request"]
        return []

    @classmethod
    def _normalize_step_status(cls, status: Any) -> str:
        normalized = str(status or "UNKNOWN").upper()
        if normalized in cls.SUCCESS_STATUSES:
            return "SUCCESS"
        if normalized in cls.FAILURE_STATUSES or normalized.endswith("FAILED"):
            return "FAILED"
        if normalized in {"MANUAL_REVIEW_REQUIRED", "PR_AWAITING_MANUAL_APPROVAL"}:
            return "ATTENTION_REQUIRED"
        return "UNKNOWN"

    @staticmethod
    def _merge_status(existing: str | None, candidate: str) -> str:
        if existing == "FAILED" or candidate == "FAILED":
            return "FAILED"
        if existing == "ATTENTION_REQUIRED" or candidate == "ATTENTION_REQUIRED":
            return "ATTENTION_REQUIRED"
        if existing == "SUCCESS" or candidate == "SUCCESS":
            return "SUCCESS"
        return candidate or existing or "UNKNOWN"

    @staticmethod
    def _aggregate_status(statuses: list[str]) -> str:
        if any(status == "FAILED" for status in statuses):
            return "FAILED"
        if any(status == "ATTENTION_REQUIRED" for status in statuses):
            return "ATTENTION_REQUIRED"
        if all(status == "SUCCESS" for status in statuses):
            return "SUCCESS"
        if any(status == "SUCCESS" for status in statuses):
            return "IN_PROGRESS"
        return "NOT_RUN"

    @staticmethod
    def _status_icon(status: str) -> str:
        if status == "SUCCESS":
            return "✅"
        if status == "FAILED":
            return "❌"
        if status == "ATTENTION_REQUIRED":
            return "⚠️"
        if status == "IN_PROGRESS":
            return "⏳"
        return "▫️"

    @classmethod
    def _display_status(cls, status: str) -> str:
        display_status = cls._normalize_final_status(status)
        labels = {
            "PULL_REQUEST_CREATED": "Draft Pull Request Created",
            "PR_CREATION_FAILED": "PR Creation Failed",
            "VALIDATION_FAILED": "Validation Failed",
            "BASELINE_BUILD_FAILED": "Baseline Build Failed",
            "MANUAL_REVIEW_REQUIRED": "Manual Review Required",
        }
        return labels.get(display_status, display_status.replace("_", " ").title())

    @classmethod
    def _normalize_final_status(cls, status: str) -> str:
        status = str(status or "UNKNOWN")
        if status in cls.USER_FACING_FINAL_STATUSES:
            return status
        if status in {"PATCH_DRY_RUN_FAILED", "PATCH_APPLICATION_FAILED"}:
            return "VALIDATION_FAILED"
        if status in {"OUTCOME_ANALYSIS_COMPLETE", "FAILED_MAX_ATTEMPTS", "PLANNING_CONSTRAINT_VIOLATION", "PR_AWAITING_MANUAL_APPROVAL"}:
            return "MANUAL_REVIEW_REQUIRED"
        if status in {"PR_SUMMARY_CREATED", "PR_CREATION_DISABLED"}:
            return "PR_CREATION_FAILED"
        if status.endswith("FAILED"):
            return "MANUAL_REVIEW_REQUIRED"
        return status

    def _user_facing_final_status(self, manifest: dict[str, Any]) -> str:
        status = str(manifest.get("status") or "UNKNOWN")
        if status == "OUTCOME_ANALYSIS_COMPLETE":
            outcome = self._latest_outcome_analysis(manifest)
            outcome_status = str(outcome.get("recommendedDisposition") or outcome.get("status") or "").upper()
            if outcome_status in self.USER_FACING_FINAL_STATUSES:
                return outcome_status
            if outcome.get("failedStage") or outcome.get("whatHappened"):
                return "VALIDATION_FAILED"
            return "MANUAL_REVIEW_REQUIRED"
        return self._normalize_final_status(status)

    def _summary_message(self, manifest: dict[str, Any], fallback_message: str) -> str:
        if str(manifest.get("status") or "UNKNOWN") != "OUTCOME_ANALYSIS_COMPLETE":
            return fallback_message

        outcome = self._latest_outcome_analysis(manifest)
        if not outcome:
            return fallback_message

        parts: list[str] = []
        what_happened = outcome.get("whatHappened") if isinstance(outcome.get("whatHappened"), dict) else {}
        root_cause = outcome.get("rootCauseAnalysis") if isinstance(outcome.get("rootCauseAnalysis"), dict) else {}
        recommended_focus = outcome.get("recommendedFocusForPlanner")

        failed_stage = what_happened.get("failedStage")
        failure_summary = what_happened.get("failureSummary")
        if failure_summary:
            if failed_stage:
                parts.append(f"{failed_stage.replace('_', ' ').title()}: {failure_summary}")
            else:
                parts.append(str(failure_summary))

        primary_cause = root_cause.get("primaryCause")
        if primary_cause:
            parts.append(str(primary_cause))

        if recommended_focus:
            focus_items = recommended_focus if isinstance(recommended_focus, list) else [recommended_focus]
            focus_text = next((str(item).strip() for item in focus_items if str(item).strip()), "")
            if focus_text:
                parts.append(f"Recommended next step: {focus_text}")

        if not parts:
            return fallback_message

        pr_note = "No Draft PR was created because the workflow did not reach a validated PR-ready state."
        return "\n\n".join(parts + [pr_note])

    def _latest_outcome_analysis(self, manifest: dict[str, Any]) -> dict[str, Any]:
        for attempt in reversed(manifest.get("attempts", []) or []):
            ref = attempt.get("outcomeAnalysisSummary")
            if not ref:
                continue
            artifact = self._read_artifact(ref)
            if artifact:
                return artifact
        return {}

    def _read_artifact(self, artifact_ref: str | None) -> dict[str, Any]:
        if not artifact_ref:
            return {}
        path = Path(artifact_ref)
        if not path.is_absolute():
            path = self.workspace.root / path
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _pull_request_info(manifest: dict[str, Any]) -> dict[str, Any]:
        pull_request = (manifest.get("final") or {}).get("pullRequest") or {}
        return {
            "url": pull_request.get("prUrl"),
            "branchName": pull_request.get("branchName"),
            "draft": pull_request.get("draft"),
            "status": pull_request.get("status"),
        }

    @classmethod
    def _artifact_summary(cls, manifest: dict[str, Any]) -> list[dict[str, str]]:
        artifacts: list[dict[str, str]] = []
        seen_paths: set[str] = set()
        for (section_name, key), label in cls.ARTIFACT_LABELS.items():
            artifact_ref = (manifest.get(section_name) or {}).get(key)
            if artifact_ref and artifact_ref not in seen_paths:
                artifacts.append({"name": label, "path": str(artifact_ref)})
                seen_paths.add(str(artifact_ref))
        for attempt in manifest.get("attempts", []) or []:
            for key, label in (
                ("patchDryRunResult", "Patch Dry Run Result"),
                ("patchApplicationProof", "Patch Application Proof"),
                ("validationResult", "Validation Result"),
                ("outcomeAnalysisSummary", "Outcome Analysis Summary"),
            ):
                artifact_ref = attempt.get(key)
                if artifact_ref and artifact_ref not in seen_paths:
                    artifacts.append({"name": label, "path": str(artifact_ref)})
                    seen_paths.add(str(artifact_ref))
        accepted = manifest.get("acceptedPatchSet") or {}
        validation_ref = accepted.get("validationResult")
        if accepted.get("status") == "VALIDATED" and validation_ref:
            artifacts.append({"name": "Accepted Patch Set", "path": "manifest.acceptedPatchSet"})
        return artifacts

    @classmethod
    def _format_adk_web_response(
        cls,
        manifest: dict[str, Any],
        display_status: str,
        message: str,
        workspace_root: Path,
        workflow_stages: list[dict[str, Any]],
        artifacts: list[dict[str, str]],
        pull_request: dict[str, Any],
    ) -> str:
        lines = [
            "## OSS Remediation Workflow",
            "",
            f"**Final Status:** {cls._display_status(display_status)}",
            f"**Workspace:** `{workspace_root.name}`",
            "",
            "### Summary",
            "",
            message,
            "",
            "### Workflow Progress",
            "",
        ]
        for index, stage in enumerate(workflow_stages, start=1):
            stage_icon = cls._status_icon(stage["status"])
            lines.append(f"#### {stage_icon} Stage {index} — {stage['name']}")
            for step in stage["steps"]:
                lines.append(f"- {cls._status_icon(step['status'])} {step['name']}")
            lines.append("")

        pr_url = pull_request.get("url")
        if pr_url:
            draft_label = "Draft Pull Request" if pull_request.get("draft") is not False else "Pull Request"
            lines.extend([f"### {draft_label}", "", str(pr_url), ""])

        if artifacts:
            lines.extend(["### Artifacts", ""])
            for artifact in artifacts:
                lines.append(f"- **{artifact['name']}**: `{artifact['path']}`")
            lines.append("")

        return "\n".join(lines).strip()

    def _artifact_status(self, artifact_ref: str | None, fallback: str = "SUCCESS") -> str:
        if not artifact_ref:
            return fallback
        artifact = self._read_artifact(artifact_ref)
        return str(artifact.get("status") or fallback)

    def _enrich_progress(self, progress: list[dict[str, Any]], manifest: dict[str, Any]) -> list[dict[str, Any]]:
        enriched = list(progress)
        seen_steps = {item.get("step") for item in enriched}

        for attempt in manifest.get("attempts", []) or []:
            attempt_number = attempt.get("attemptNumber")
            prefix = f"attempt_{attempt_number}"
            if attempt.get("patchDryRunResult") and f"patch_dry_run_{prefix}" not in seen_steps:
                enriched.append({"step": f"patch_dry_run_{prefix}", "status": self._artifact_status(attempt.get("patchDryRunResult")), "artifactPath": attempt.get("patchDryRunResult")})
            if attempt.get("patchApplicationProof") and f"patch_apply_{prefix}" not in seen_steps:
                enriched.append({"step": f"patch_apply_{prefix}", "status": self._artifact_status(attempt.get("patchApplicationProof")), "artifactPath": attempt.get("patchApplicationProof")})
            if attempt.get("validationResult") and f"validation_{prefix}" not in seen_steps:
                enriched.append({"step": f"validation_{prefix}", "status": self._artifact_status(attempt.get("validationResult"), attempt.get("status", "UNKNOWN")), "artifactPath": attempt.get("validationResult")})
            if attempt.get("outcomeAnalysisSummary") and "outcome_analysis" not in seen_steps:
                enriched.append({"step": "outcome_analysis", "status": self._artifact_status(attempt.get("outcomeAnalysisSummary")), "artifactPath": attempt.get("outcomeAnalysisSummary")})

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
            enriched.append({"step": "pr_summary_created", "status": self._artifact_status(final.get("prSummary")), "artifactPath": final.get("prSummary")})
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
