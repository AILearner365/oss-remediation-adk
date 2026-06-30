from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from google.adk.agents import Agent

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.orchestrator import WorkflowOrchestrator


def run_oss_remediation_workflow(
    repository_url: str,
    reference_branch: str = "main",
    workspace_root: str | None = None,
    patch_plan_path: str | None = None,
    patch_plan_paths: list[str] | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Run the MVP OSS remediation workflow through the orchestrator.

    This is the production ADK entry capability. The ADK agent remains thin:
    it accepts user input, creates/loads runtime configuration, delegates all
    lifecycle execution to ``WorkflowOrchestrator``, and returns a compact
    progress/artifact summary. The agent does not mutate repositories directly,
    update the manifest directly, or make remediation decisions.

    When no patch plan is supplied, the workflow intentionally stops after
    baseline, vulnerability assessment, and project analysis. That is the safe
    MVP runtime boundary until the Planning Agent is wired to emit structured
    ``PATCH_PLAN`` or ``MANUAL_REVIEW`` decisions.
    """
    progress: list[dict[str, Any]] = []
    workspace = workspace_root or tempfile.mkdtemp(prefix="oss-remediation-workspace-")
    policy = RemediationPolicy.load(policy_path)
    orchestrator = WorkflowOrchestrator(workspace, policy=policy)

    def record(step: str, result: dict[str, Any]) -> None:
        progress.append({
            "step": step,
            "status": result.get("status"),
            "failureCode": result.get("failureCode"),
            "artifactPath": result.get("artifactPath"),
        })

    baseline = orchestrator.checkout_and_baseline(repository_url, reference_branch)
    record("checkout_and_baseline", baseline)
    if baseline.get("status") != "SUCCESS":
        return _runtime_summary(orchestrator, progress, "Workflow stopped because baseline build did not pass.")

    assessment = orchestrator.run_assessment()
    record("vulnerability_assessment", assessment)
    if assessment.get("status") != "SUCCESS":
        return _runtime_summary(orchestrator, progress, "Workflow stopped because vulnerability assessment failed.")

    analysis = orchestrator.run_project_analysis()
    record("project_analysis", analysis)
    if analysis.get("status") not in {"SUCCESS", "PARTIAL"}:
        return _runtime_summary(orchestrator, progress, "Workflow stopped because project analysis failed.")

    plan_paths = _normalize_patch_plan_paths(patch_plan_path, patch_plan_paths)
    if plan_paths:
        attempt_result = orchestrator.run_attempt_loop(plan_paths)
        record("attempt_loop", attempt_result)
        return _runtime_summary(orchestrator, progress, "Workflow completed attempt execution.")

    return _runtime_summary(
        orchestrator,
        progress,
        "Pre-remediation workflow completed. Planning Agent integration is required to produce a patch plan or manual-review decision.",
    )


def _normalize_patch_plan_paths(patch_plan_path: str | None, patch_plan_paths: list[str] | None) -> list[str]:
    normalized: list[str] = []
    if patch_plan_path:
        normalized.append(patch_plan_path)
    if patch_plan_paths:
        normalized.extend(path for path in patch_plan_paths if path)
    return normalized


def _runtime_summary(orchestrator: WorkflowOrchestrator, progress: list[dict[str, Any]], message: str) -> dict[str, Any]:
    manifest = orchestrator.manifest_store.load()
    workspace_root = Path(orchestrator.workspace.root)
    final = manifest.get("final", {})
    return {
        "status": manifest.get("status", "UNKNOWN"),
        "message": message,
        "workflowId": manifest.get("workflowId"),
        "workspaceRoot": str(workspace_root),
        "manifestPath": str(workspace_root / "manifest.json"),
        "progress": progress,
        "artifacts": {
            "baseline": manifest.get("baseline", {}),
            "acceptedPatchSet": manifest.get("acceptedPatchSet", {}),
            "final": final,
        },
        "nextAction": _next_action(manifest),
    }


def _next_action(manifest: dict[str, Any]) -> str:
    status = manifest.get("status")
    if status == "PROJECT_ANALYSIS_COMPLETE":
        return "Review generated assessment and project-analysis artifacts, then provide a patch plan or manual-review decision."
    if status == "VALIDATION_SUCCEEDED":
        return "Review the final PR summary artifact before creating a pull request."
    if status == "BASELINE_BUILD_FAILED":
        return "Fix the repository baseline before attempting remediation."
    if status == "FAILED_MAX_ATTEMPTS":
        return "Review outcome-analysis artifacts and decide whether manual remediation is required."
    if status == "MANUAL_REVIEW_REQUIRED":
        return "Manual review is required; automated PR creation should remain disabled."
    return "Review the manifest and generated artifacts for the next workflow action."


root_agent = Agent(
    name="oss_remediation_agent",
    model="gemini-2.5-flash",
    description="Production ADK entrypoint for the OSS remediation MVP workflow.",
    instruction=(
        "You are the OSS remediation workflow entrypoint. When the user asks to run remediation, "
        "call run_oss_remediation_workflow with the repository URL and reference branch. "
        "Do not mutate repositories directly, do not update manifests directly, and do not create pull requests. "
        "All workflow execution must be delegated to the WorkflowOrchestrator through the exposed tool. "
        "Return the workspace path, manifest path, progress steps, final status, and next action."
    ),
    tools=[run_oss_remediation_workflow],
)
