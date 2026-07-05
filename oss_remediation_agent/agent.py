from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.phase6_patch_progress_orchestrator import Phase6PatchProgressOrchestrator


def run_oss_remediation_workflow(
    repository_url: str,
    reference_branch: str = "main",
    workspace_root: str | None = None,
    planning_agent_output: str | dict[str, Any] | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Run the full OSS remediation workflow through the deterministic orchestrator.

    This compatibility tool remains available for non-ADK-Web callers and tests.
    ADK Web uses the staged subagent tools below so the event graph shows
    meaningful stage-level execution.
    """
    workspace = workspace_root or _default_workspace_root()
    orchestrator = _orchestrator(workspace, policy_path)
    return orchestrator.run_workflow(
        repository_url=repository_url,
        reference_branch=reference_branch,
        planning_agent_output=planning_agent_output,
    )


def run_repository_preparation_stage(
    repository_url: str,
    reference_branch: str = "main",
    workspace_root: str | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Stage 1: checkout the repository and capture the baseline build."""
    workspace = workspace_root or _default_workspace_root()
    orchestrator = _orchestrator(workspace, policy_path)
    result = orchestrator.checkout_and_baseline(repository_url, reference_branch)
    progress = _progress_from_manifest(orchestrator.manifest_store.load(), orchestrator.workspace.root)
    if not progress:
        progress = [{"step": "baseline_build", "status": result.get("status")}]
    return _stage_result(
        stage="Repository Preparation",
        workspace_root=workspace,
        result=result,
        progress=progress,
    )


def run_vulnerability_assessment_stage(
    workspace_root: str,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Stage 2: generate the OSV vulnerability assessment artifact."""
    orchestrator = _orchestrator(workspace_root, policy_path)
    result = orchestrator.run_assessment()
    return _stage_result(
        stage="Vulnerability Assessment",
        workspace_root=workspace_root,
        result=result,
        progress=[{"step": "vulnerability_assessment", "status": result.get("status"), "artifactPath": result.get("artifactPath")}],
    )


def run_project_analysis_stage(
    workspace_root: str,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Stage 3: analyze Maven structure and dependency placement."""
    orchestrator = _orchestrator(workspace_root, policy_path)
    result = orchestrator.run_project_analysis()
    return _stage_result(
        stage="Maven Project Analysis",
        workspace_root=workspace_root,
        result=result,
        progress=[{"step": "project_analysis", "status": result.get("status"), "artifactPath": result.get("artifactPath")}],
    )


def run_remediation_planning_stage(
    workspace_root: str,
    attempt_number: int = 1,
    planning_agent_output: str | dict[str, Any] | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Stage 4: invoke the remediation planning agent boundary."""
    orchestrator = _orchestrator(workspace_root, policy_path)
    result = orchestrator.run_planning_agent_boundary(
        attempt_number=attempt_number,
        planning_agent_output=planning_agent_output,
    )
    return _stage_result(
        stage="Remediation Planning",
        workspace_root=workspace_root,
        result=result,
        progress=[
            {
                "step": f"remediation_planning_agent_attempt_{attempt_number}",
                "status": result.get("status"),
                "artifactPath": result.get("artifactPath"),
                "decisionType": result.get("decisionType") or result.get("type"),
            }
        ],
    )


def run_patch_validation_stage(
    workspace_root: str,
    attempt_number: int = 1,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Stage 5: route the plan, apply dependency patches, and validate."""
    orchestrator = _orchestrator(workspace_root, policy_path)
    manifest = orchestrator.manifest_store.load()
    planning_ref = (manifest.get("planning") or {}).get("lastDecision")
    if not planning_ref:
        return _stage_result(
            stage="Patch and Validation",
            workspace_root=workspace_root,
            result={"status": "FAILED", "failureCode": "PLANNING_DECISION_MISSING"},
            progress=[{"step": f"planner_result_routing_attempt_{attempt_number}", "status": "FAILED"}],
        )

    planning_path = orchestrator._resolve_workspace_ref(str(planning_ref))
    planning_result = _read_json(planning_path)
    decision_type = planning_result.get("decisionType") or planning_result.get("type")

    if decision_type == "PATCH_PLAN":
        patch_plan_path = planning_result.get("patchPlanPath") or planning_result.get("artifactPath") or str(planning_path)
        patch_plan_path = str(orchestrator._resolve_workspace_ref(str(patch_plan_path)))
        result = orchestrator.run_patch_validation_attempt(attempt_number, patch_plan_path)
        if result.get("status") == "SUCCESS":
            manifest = orchestrator.manifest_store.load()
            manifest["status"] = "VALIDATION_SUCCEEDED"
            orchestrator.manifest_store.save(manifest)
        progress = _attempt_progress_from_manifest(orchestrator.manifest_store.load(), orchestrator.workspace.root, attempt_number)
        return _stage_result(
            stage="Patch and Validation",
            workspace_root=workspace_root,
            result=result,
            progress=progress,
        )

    if decision_type == "MANUAL_REVIEW":
        result = orchestrator.handle_manual_review(planning_result)
        return _stage_result(
            stage="Patch and Validation",
            workspace_root=workspace_root,
            result=result,
            progress=[{"step": f"planner_result_routing_attempt_{attempt_number}", "status": result.get("status")}],
        )

    if decision_type == "REQUEST_ADDITIONAL_EVIDENCE":
        result = orchestrator.handle_additional_investigation_request(attempt_number, planning_result)
        return _stage_result(
            stage="Patch and Validation",
            workspace_root=workspace_root,
            result=result,
            progress=[{"step": f"planner_result_routing_attempt_{attempt_number}", "status": result.get("status")}],
        )

    return _stage_result(
        stage="Patch and Validation",
        workspace_root=workspace_root,
        result={"status": "FAILED", "failureCode": "UNKNOWN_PLANNER_RESULT"},
        progress=[{"step": f"planner_result_routing_attempt_{attempt_number}", "status": "FAILED"}],
    )


def run_outcome_analysis_stage(
    workspace_root: str,
    attempt_number: int = 1,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Stage 6: ensure evidence-backed outcome analysis exists for non-successful outcomes."""
    orchestrator = _orchestrator(workspace_root, policy_path)
    manifest = orchestrator.manifest_store.load()
    attempt = _find_attempt(manifest, attempt_number)
    accepted = manifest.get("acceptedPatchSet") or {}

    if accepted.get("status") == "VALIDATED" and manifest.get("status") in {"VALIDATION_SUCCEEDED", "PULL_REQUEST_CREATED"}:
        result = {"status": "SKIPPED", "reason": "Validated accepted patch set exists; outcome analysis is not required."}
        progress = [{"step": "outcome_analysis", "status": "SKIPPED"}]
        return _stage_result("Outcome Analysis", workspace_root, result, progress)

    outcome_ref = (attempt or {}).get("outcomeAnalysisSummary")
    if outcome_ref:
        outcome_path = orchestrator._resolve_workspace_ref(str(outcome_ref))
        result = _read_json(outcome_path)
        result.setdefault("artifactPath", str(outcome_path))
        progress = [{"step": "outcome_analysis", "status": result.get("status", "SUCCESS"), "artifactPath": outcome_ref}]
        return _stage_result("Outcome Analysis", workspace_root, result, progress)

    patch_plan_ref = (attempt or {}).get("patchPlan") or (manifest.get("planning") or {}).get("lastDecision")
    if not patch_plan_ref:
        result = {"status": "SKIPPED", "reason": "No patch plan artifact is available for outcome analysis."}
        return _stage_result("Outcome Analysis", workspace_root, result, [{"step": "outcome_analysis", "status": "SKIPPED"}])

    outcome_ref = orchestrator.run_outcome_analysis(
        attempt_number=attempt_number,
        patch_plan_path=str(orchestrator._resolve_workspace_ref(str(patch_plan_ref))),
        patch_application_proof_path=_abs_ref(orchestrator, (attempt or {}).get("patchApplicationProof")),
        validation_result_path=_abs_ref(orchestrator, (attempt or {}).get("validationResult")),
        dry_run_result_path=_abs_ref(orchestrator, (attempt or {}).get("patchDryRunResult")),
    )
    outcome_path = orchestrator._resolve_workspace_ref(str(outcome_ref))
    result = _read_json(outcome_path)
    result.setdefault("artifactPath", str(outcome_path))
    return _stage_result(
        "Outcome Analysis",
        workspace_root,
        result,
        [{"step": "outcome_analysis", "status": result.get("status", "SUCCESS"), "artifactPath": outcome_ref}],
    )


def run_pull_request_delivery_stage(
    workspace_root: str,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Stage 7: generate the PR summary and create the Draft PR when policy allows."""
    orchestrator = _orchestrator(workspace_root, policy_path)
    manifest = orchestrator.manifest_store.load()
    accepted = manifest.get("acceptedPatchSet") or {}

    if accepted.get("status") == "VALIDATED":
        delivery_result = orchestrator._finalize_pr_lifecycle("FULL_REMEDIATION")
    else:
        delivery_result = {
            "status": _user_facing_status(manifest),
            "message": "No validated accepted patch set is available for PR delivery.",
        }

    progress = _progress_from_manifest(orchestrator.manifest_store.load(), orchestrator.workspace.root)
    progress.append({"step": "pull_request_delivery_stage", "status": delivery_result.get("status")})
    summary_message = _final_summary_message(orchestrator.manifest_store.load())
    summary = orchestrator.runtime_summary(progress, summary_message)
    summary["stageResult"] = delivery_result
    return summary


def _orchestrator(workspace_root: str, policy_path: str | None = None) -> Phase6PatchProgressOrchestrator:
    policy = RemediationPolicy.load(policy_path)
    return Phase6PatchProgressOrchestrator(workspace_root, policy=policy)


def _default_workspace_root() -> str:
    """Create a visible project-local workspace path for ADK smoke tests."""
    run_id = datetime.now(timezone.utc).strftime("oss-remediation-%Y%m%d-%H%M%S")
    return str((Path.cwd() / "oss-remediation-workspaces" / run_id).resolve())


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _stage_result(
    stage: str,
    workspace_root: str,
    result: dict[str, Any],
    progress: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": result.get("status", "UNKNOWN"),
        "workspaceRoot": str(Path(workspace_root).resolve()),
        "result": result,
        "progress": progress,
    }


def _progress_from_manifest(manifest: dict[str, Any], workspace_root: str | Path) -> list[dict[str, Any]]:
    progress: list[dict[str, Any]] = []
    workspace = Path(workspace_root)
    baseline = manifest.get("baseline") or {}
    planning = manifest.get("planning") or {}

    if baseline.get("repositoryPath"):
        progress.append({"step": "repository_checkout", "status": "SUCCESS"})

    if baseline.get("baselineBuildResult"):
        progress.append(_artifact_progress("baseline_build", workspace, baseline.get("baselineBuildResult")))

    if baseline.get("vulnerabilityAssessmentReport"):
        progress.append(_artifact_progress("vulnerability_assessment", workspace, baseline.get("vulnerabilityAssessmentReport")))

    if baseline.get("projectAnalyzerReport"):
        progress.append(_artifact_progress("project_analysis", workspace, baseline.get("projectAnalyzerReport")))

    if planning.get("lastDecision"):
        progress.append(_artifact_progress("remediation_planning_agent_attempt_1", workspace, planning.get("lastDecision")))

    for attempt in manifest.get("attempts", []) or []:
        attempt_number = int(attempt.get("attemptNumber") or 1)
        progress.extend(_attempt_progress_from_attempt(workspace, attempt, attempt_number))

    return progress


def _attempt_progress_from_manifest(manifest: dict[str, Any], workspace_root: str | Path, attempt_number: int) -> list[dict[str, Any]]:
    attempt = _find_attempt(manifest, attempt_number) or {}
    return _attempt_progress_from_attempt(Path(workspace_root), attempt, attempt_number)


def _attempt_progress_from_attempt(workspace: Path, attempt: dict[str, Any], attempt_number: int) -> list[dict[str, Any]]:
    progress: list[dict[str, Any]] = []
    if attempt.get("patchDryRunResult"):
        progress.append(_artifact_progress(f"patch_dry_run_attempt_{attempt_number}", workspace, attempt.get("patchDryRunResult")))
    if attempt.get("patchApplicationProof"):
        progress.append(_artifact_progress(f"patch_apply_attempt_{attempt_number}", workspace, attempt.get("patchApplicationProof")))
    if attempt.get("validationResult"):
        progress.append(_artifact_progress(f"validation_attempt_{attempt_number}", workspace, attempt.get("validationResult")))
    if attempt.get("outcomeAnalysisSummary"):
        progress.append(_artifact_progress("outcome_analysis", workspace, attempt.get("outcomeAnalysisSummary")))
    return progress


def _artifact_progress(step: str, workspace: Path, artifact_ref: str | None) -> dict[str, Any]:
    artifact = _read_json(workspace / str(artifact_ref)) if artifact_ref else {}
    status = artifact.get("status") or "UNKNOWN"
    if step == "validation_attempt_1" and status == "SUCCESS":
        status = "VALIDATION_SUCCEEDED"
    return {"step": step, "status": status, "artifactPath": artifact_ref}


def _find_attempt(manifest: dict[str, Any], attempt_number: int) -> dict[str, Any] | None:
    for attempt in manifest.get("attempts", []) or []:
        if int(attempt.get("attemptNumber") or 0) == int(attempt_number):
            return attempt
    return None


def _abs_ref(orchestrator: Phase6PatchProgressOrchestrator, ref: str | None) -> str | None:
    if not ref:
        return None
    return str(orchestrator._resolve_workspace_ref(str(ref)))


def _user_facing_status(manifest: dict[str, Any]) -> str:
    status = str(manifest.get("status") or "UNKNOWN")
    if status == "PULL_REQUEST_CREATED":
        return "PULL_REQUEST_CREATED"
    if status == "PR_CREATION_FAILED":
        return "PR_CREATION_FAILED"
    if status == "BASELINE_BUILD_FAILED":
        return "BASELINE_BUILD_FAILED"
    if status in {"VALIDATION_FAILED", "PATCH_DRY_RUN_FAILED", "PATCH_APPLICATION_FAILED"}:
        return "VALIDATION_FAILED"
    if status in {"MANUAL_REVIEW_REQUIRED", "OUTCOME_ANALYSIS_COMPLETE", "FAILED_MAX_ATTEMPTS", "PLANNING_CONSTRAINT_VIOLATION"}:
        return "MANUAL_REVIEW_REQUIRED"
    return "MANUAL_REVIEW_REQUIRED" if status.endswith("FAILED") else status


def _final_summary_message(manifest: dict[str, Any]) -> str:
    status = _user_facing_status(manifest)
    if status == "PULL_REQUEST_CREATED":
        return "Draft pull request created after validated dependency-only remediation."
    if status == "PR_CREATION_FAILED":
        return "Validation completed, but Draft PR creation failed. Review final delivery artifacts."
    if status == "BASELINE_BUILD_FAILED":
        return "Baseline build failed. Automated remediation should not continue until the baseline build issue is reviewed."
    if status == "VALIDATION_FAILED":
        return "Validation failed after remediation attempt. No Draft PR was created because no validated accepted patch set is available."
    if status == "MANUAL_REVIEW_REQUIRED":
        return "Manual review is required. No Draft PR was created because the workflow did not reach a validated PR-ready state."
    return "Workflow completed with a non-PR terminal status. Review workspace artifacts for details."


repository_preparation_agent = LlmAgent(
    name="repository_preparation_agent",
    model="gemini-2.5-flash",
    description="Executes repository checkout and baseline build preparation.",
    instruction=(
        "Run Stage 1. Call run_repository_preparation_stage using the repository URL and reference branch from the user request. "
        "Return the tool result only."
    ),
    tools=[run_repository_preparation_stage],
    output_key="repository_preparation_result",
)

vulnerability_assessment_agent = LlmAgent(
    name="vulnerability_assessment_agent",
    model="gemini-2.5-flash",
    description="Executes OSV vulnerability assessment.",
    instruction=(
        "Run Stage 2. Read workspaceRoot from {repository_preparation_result}. "
        "Call run_vulnerability_assessment_stage with that workspaceRoot. Return the tool result only."
    ),
    tools=[run_vulnerability_assessment_stage],
    output_key="vulnerability_assessment_result",
)

project_analyzer_agent = LlmAgent(
    name="project_analyzer_agent",
    model="gemini-2.5-flash",
    description="Executes Maven project analysis.",
    instruction=(
        "Run Stage 3. Read workspaceRoot from {vulnerability_assessment_result}. "
        "Call run_project_analysis_stage with that workspaceRoot. Return the tool result only."
    ),
    tools=[run_project_analysis_stage],
    output_key="project_analysis_result",
)

remediation_planning_agent = LlmAgent(
    name="remediation_planning_agent",
    model="gemini-2.5-flash",
    description="Executes the remediation planning agent boundary.",
    instruction=(
        "Run Stage 4. Read workspaceRoot from {project_analysis_result}. "
        "Call run_remediation_planning_stage with that workspaceRoot. Return the tool result only."
    ),
    tools=[run_remediation_planning_stage],
    output_key="remediation_planning_result",
)

patch_validation_agent = LlmAgent(
    name="patch_validation_agent",
    model="gemini-2.5-flash",
    description="Executes patch dry run, dependency patch application, and validation.",
    instruction=(
        "Run Stage 5. Read workspaceRoot from {remediation_planning_result}. "
        "Call run_patch_validation_stage with that workspaceRoot. Return the tool result only."
    ),
    tools=[run_patch_validation_stage],
    output_key="patch_validation_result",
)

outcome_analysis_agent = LlmAgent(
    name="outcome_analysis_agent",
    model="gemini-2.5-flash",
    description="Ensures evidence-backed outcome analysis exists for failed or manually reviewed workflows.",
    instruction=(
        "Run Stage 6. Read workspaceRoot from {patch_validation_result}. "
        "Call run_outcome_analysis_stage with that workspaceRoot. Return the tool result only."
    ),
    tools=[run_outcome_analysis_stage],
    output_key="outcome_analysis_result",
)

pull_request_delivery_agent = LlmAgent(
    name="pull_request_delivery_agent",
    model="gemini-2.5-flash",
    description="Executes PR summary generation and Draft PR delivery.",
    instruction=(
        "Run Stage 7. Read workspaceRoot from {outcome_analysis_result}. "
        "Call run_pull_request_delivery_stage with that workspaceRoot. "
        "For the final ADK Web answer, output exactly the markdown text in the returned adkWebResponse field. "
        "Do not add vulnerability summaries, remediation tables, manifest paths, or a Next Action section."
    ),
    tools=[run_pull_request_delivery_stage],
    output_key="pull_request_delivery_result",
)


root_agent = SequentialAgent(
    name="oss_remediation_agent",
    description=(
        "Executes the OSS remediation workflow through deterministic staged ADK subagents. "
        "The subagents run in fixed order: repository preparation, vulnerability assessment, "
        "project analysis, remediation planning, patch validation, outcome analysis, and pull request delivery."
    ),
    sub_agents=[
        repository_preparation_agent,
        vulnerability_assessment_agent,
        project_analyzer_agent,
        remediation_planning_agent,
        patch_validation_agent,
        outcome_analysis_agent,
        pull_request_delivery_agent,
    ],
)
