from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.workflow import FunctionNode, START, Workflow

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.phase6_patch_progress_orchestrator import Phase6PatchProgressOrchestrator


_BASELINE_FAILURE_STATE_KEY = "oss_remediation_baseline_build_failed"
_REPOSITORY_PREPARATION_RESULT_STATE_KEY = "oss_remediation_repository_preparation_result"


def run_oss_remediation_workflow(
    repository_url: str,
    reference_branch: str = "main",
    workspace_root: str | None = None,
    planning_agent_output: str | dict[str, Any] | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Run the full workflow through the deterministic, failure-gated orchestrator.

    This direct entry point remains available for non-ADK callers. The
    orchestrator stops before assessment when the baseline build fails.
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
    if result.get("status") != "SUCCESS":
        message = (
            "Workflow stopped because the repository checkout failed."
            if result.get("failureCode") == "CHECKOUT_FAILED"
            else "Workflow stopped because the baseline build did not pass."
        )
        summary = orchestrator.runtime_summary(progress, message)
        summary["stageResult"] = result
        return summary
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
    if result.get("artifactPath"):
        _record_attempt_planning_metadata(orchestrator, attempt_number, result)
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
    planning_ref = _planning_ref_for_attempt(manifest, attempt_number) or (manifest.get("planning") or {}).get("lastDecision")
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
        progress = [{"step": f"outcome_analysis_attempt_{attempt_number}", "status": result.get("status", "SUCCESS"), "artifactPath": outcome_ref}]
        return _stage_result("Outcome Analysis", workspace_root, result, progress)

    patch_plan_ref = (attempt or {}).get("patchPlan") or _planning_ref_for_attempt(manifest, attempt_number) or (manifest.get("planning") or {}).get("lastDecision")
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
        [{"step": f"outcome_analysis_attempt_{attempt_number}", "status": result.get("status", "SUCCESS"), "artifactPath": outcome_ref}],
    )


def run_replanning_loop_stage(
    workspace_root: str,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Stage 6b: continue bounded replanning after validation failure.

    ADK Web runs fixed sequential subagents. This stage bridges that fixed graph
    with the deterministic retry policy by continuing attempts after Stage 6 has
    produced outcome analysis for a failed validation attempt.
    """
    orchestrator = _orchestrator(workspace_root, policy_path)
    manifest = orchestrator.manifest_store.load()
    progress: list[dict[str, Any]] = []
    accepted = manifest.get("acceptedPatchSet") or {}
    max_attempts = _policy_max_attempts(manifest, orchestrator)
    latest_attempt = _latest_attempt(manifest)
    latest_attempt_number = _attempt_number(latest_attempt)

    if accepted.get("status") == "VALIDATED":
        result = {"status": "SKIPPED", "reason": "Validated accepted patch set already exists; replanning is not required."}
        return _stage_result("Replanning Loop", workspace_root, result, _progress_from_manifest(manifest, orchestrator.workspace.root))

    if not _requires_validation_replan(manifest, latest_attempt):
        result = {"status": "SKIPPED", "reason": "Latest workflow state does not require validation-failure replanning."}
        return _stage_result("Replanning Loop", workspace_root, result, _progress_from_manifest(manifest, orchestrator.workspace.root))

    if latest_attempt_number >= max_attempts:
        result = orchestrator.handle_max_attempts_reached()
        manifest = orchestrator.manifest_store.load()
        progress = _progress_from_manifest(manifest, orchestrator.workspace.root)
        progress.append({"step": "max_attempts_routing", "status": result.get("status"), "failureCode": result.get("failureCode")})
        return _stage_result("Replanning Loop", workspace_root, result, progress)

    next_attempt_number = latest_attempt_number + 1
    last_result: dict[str, Any] = {"status": "NOT_RUN"}

    while next_attempt_number <= max_attempts:
        source_attempt = _latest_attempt(orchestrator.manifest_store.load())
        source_attempt_number = _attempt_number(source_attempt)
        source_outcome_ref = source_attempt.get("outcomeAnalysisSummary") if source_attempt else None

        _mark_replan_required(orchestrator, source_attempt_number, next_attempt_number, source_outcome_ref)

        prepared = orchestrator.prepare_attempt_workspace(next_attempt_number)
        progress.append({"step": f"prepare_attempt_{next_attempt_number}", "status": prepared.get("status")})
        if prepared.get("status") != "SUCCESS":
            return _stage_result("Replanning Loop", workspace_root, prepared, progress)

        _mark_replan_attempt(orchestrator, next_attempt_number, source_attempt_number, source_outcome_ref)

        planning_result = orchestrator.run_planning_agent_boundary(attempt_number=next_attempt_number)
        _record_attempt_planning_metadata(orchestrator, next_attempt_number, planning_result)
        progress.append(
            {
                "step": f"remediation_planning_agent_attempt_{next_attempt_number}",
                "status": planning_result.get("status"),
                "artifactPath": planning_result.get("artifactPath"),
                "decisionType": planning_result.get("decisionType") or planning_result.get("type"),
            }
        )
        if planning_result.get("status") != "SUCCESS":
            return _stage_result("Replanning Loop", workspace_root, planning_result, progress)

        routed = orchestrator.handle_planner_result(planning_result, attempt_number=next_attempt_number)
        progress.append({"step": f"planner_result_routing_attempt_{next_attempt_number}", "status": routed.get("status"), "failureCode": routed.get("failureCode")})

        manifest = orchestrator.manifest_store.load()
        progress.extend(_attempt_progress_from_manifest(manifest, orchestrator.workspace.root, next_attempt_number))
        last_result = routed

        if routed.get("status") in {"MANUAL_REVIEW_REQUIRED", "PR_SUMMARY_CREATED", "SUCCESS"}:
            return _stage_result("Replanning Loop", workspace_root, routed, _progress_from_manifest(manifest, orchestrator.workspace.root))

        if manifest.get("status") == "OUTCOME_ANALYSIS_AGENT_INVOCATION_FAILED":
            return _stage_result("Replanning Loop", workspace_root, routed, _progress_from_manifest(manifest, orchestrator.workspace.root))

        latest_attempt = _latest_attempt(manifest)
        if _requires_validation_replan(manifest, latest_attempt) and _attempt_number(latest_attempt) < max_attempts:
            next_attempt_number = _attempt_number(latest_attempt) + 1
            continue

        if _requires_validation_replan(manifest, latest_attempt) and _attempt_number(latest_attempt) >= max_attempts:
            max_attempts_result = orchestrator.handle_max_attempts_reached()
            manifest = orchestrator.manifest_store.load()
            progress = _progress_from_manifest(manifest, orchestrator.workspace.root)
            progress.append({"step": "max_attempts_routing", "status": max_attempts_result.get("status"), "failureCode": max_attempts_result.get("failureCode")})
            return _stage_result("Replanning Loop", workspace_root, max_attempts_result, progress)

        return _stage_result("Replanning Loop", workspace_root, routed, _progress_from_manifest(manifest, orchestrator.workspace.root))

    max_attempts_result = orchestrator.handle_max_attempts_reached()
    manifest = orchestrator.manifest_store.load()
    progress = _progress_from_manifest(manifest, orchestrator.workspace.root)
    progress.append({"step": "max_attempts_routing", "status": max_attempts_result.get("status"), "failureCode": max_attempts_result.get("failureCode")})
    return _stage_result("Replanning Loop", workspace_root, max_attempts_result or last_result, progress)


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
    attempts = manifest.get("attempts", []) or []

    if baseline.get("repositoryPath"):
        progress.append({"step": "repository_checkout", "status": "SUCCESS"})

    if baseline.get("baselineBuildResult"):
        progress.append(_artifact_progress("baseline_build", workspace, baseline.get("baselineBuildResult")))

    if baseline.get("vulnerabilityAssessmentReport"):
        progress.append(_artifact_progress("vulnerability_assessment", workspace, baseline.get("vulnerabilityAssessmentReport")))

    if baseline.get("projectAnalyzerReport"):
        progress.append(_artifact_progress("project_analysis", workspace, baseline.get("projectAnalyzerReport")))

    if attempts:
        for attempt in attempts:
            attempt_number = _attempt_number(attempt) or 1
            planning_ref = attempt.get("planningDecision") or attempt.get("patchPlan")
            if planning_ref:
                progress.append(_artifact_progress(f"remediation_planning_agent_attempt_{attempt_number}", workspace, planning_ref))
            progress.extend(_attempt_progress_from_attempt(workspace, attempt, attempt_number))
    elif planning.get("lastDecision"):
        progress.append(_artifact_progress("remediation_planning_agent_attempt_1", workspace, planning.get("lastDecision")))

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
        progress.append(_artifact_progress(f"outcome_analysis_attempt_{attempt_number}", workspace, attempt.get("outcomeAnalysisSummary")))
    return progress


def _artifact_progress(step: str, workspace: Path, artifact_ref: str | None) -> dict[str, Any]:
    artifact = _read_json(workspace / str(artifact_ref)) if artifact_ref else {}
    status = artifact.get("status") or "UNKNOWN"
    if step.startswith("validation_attempt_") and status == "SUCCESS":
        status = "VALIDATION_SUCCEEDED"
    return {"step": step, "status": status, "artifactPath": artifact_ref}


def _find_attempt(manifest: dict[str, Any], attempt_number: int) -> dict[str, Any] | None:
    for attempt in manifest.get("attempts", []) or []:
        if _attempt_number(attempt) == int(attempt_number):
            return attempt
    return None


def _latest_attempt(manifest: dict[str, Any]) -> dict[str, Any]:
    attempts = manifest.get("attempts", []) or []
    if not attempts:
        return {}
    return sorted(attempts, key=_attempt_number)[-1]


def _attempt_number(attempt: dict[str, Any] | None) -> int:
    if not attempt:
        return 0
    try:
        return int(attempt.get("attemptNumber") or 0)
    except (TypeError, ValueError):
        return 0


def _policy_max_attempts(manifest: dict[str, Any], orchestrator: Phase6PatchProgressOrchestrator) -> int:
    try:
        return int((manifest.get("policy") or {}).get("maxAttempts") or orchestrator.policy.max_attempts)
    except (TypeError, ValueError):
        return int(orchestrator.policy.max_attempts)


def _requires_validation_replan(manifest: dict[str, Any], latest_attempt: dict[str, Any] | None) -> bool:
    accepted = manifest.get("acceptedPatchSet") or {}
    return (
        manifest.get("status") == "OUTCOME_ANALYSIS_COMPLETE"
        and (latest_attempt or {}).get("status") == "VALIDATION_FAILED"
        and accepted.get("status") != "VALIDATED"
    )


def _planning_ref_for_attempt(manifest: dict[str, Any], attempt_number: int) -> str | None:
    attempt = _find_attempt(manifest, attempt_number) or {}
    return attempt.get("planningDecision") or attempt.get("patchPlan")


def _record_attempt_planning_metadata(
    orchestrator: Phase6PatchProgressOrchestrator,
    attempt_number: int,
    planning_result: dict[str, Any],
) -> None:
    artifact_path = planning_result.get("artifactPath")
    if not artifact_path:
        return
    manifest = orchestrator.manifest_store.load()
    attempt = orchestrator._attempt_entry(manifest, attempt_number)
    attempt["planningDecision"] = orchestrator._relative_ref(str(artifact_path))
    attempt["planningDecisionType"] = planning_result.get("decisionType") or planning_result.get("type")
    orchestrator.manifest_store.save(manifest)


def _mark_replan_required(
    orchestrator: Phase6PatchProgressOrchestrator,
    source_attempt_number: int,
    next_attempt_number: int,
    outcome_ref: str | None,
) -> None:
    manifest = orchestrator.manifest_store.load()
    source_attempt = _find_attempt(manifest, source_attempt_number)
    if source_attempt:
        source_attempt["nextAction"] = "REPLAN_REQUIRED"
        source_attempt["nextAttemptNumber"] = next_attempt_number
        source_attempt["replanReason"] = "VALIDATION_FAILED"
        if outcome_ref:
            source_attempt["replanInput"] = outcome_ref
    orchestrator.manifest_store.save(manifest)


def _mark_replan_attempt(
    orchestrator: Phase6PatchProgressOrchestrator,
    attempt_number: int,
    source_attempt_number: int,
    outcome_ref: str | None,
) -> None:
    manifest = orchestrator.manifest_store.load()
    attempt = orchestrator._attempt_entry(manifest, attempt_number)
    attempt["replanSourceAttempt"] = source_attempt_number
    attempt["replanReason"] = "VALIDATION_FAILED"
    if outcome_ref:
        attempt["replanInputOutcomeAnalysis"] = outcome_ref
    orchestrator.manifest_store.save(manifest)


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


def _capture_repository_preparation_status(
    tool: Any,
    args: dict[str, Any],
    context: Any,
    tool_response: dict[str, Any],
) -> None:
    """Persist the Stage 1 outcome for deterministic workflow routing."""
    del tool, args
    context.state[_BASELINE_FAILURE_STATE_KEY] = tool_response.get("status") != "SUCCESS"
    context.state[_REPOSITORY_PREPARATION_RESULT_STATE_KEY] = tool_response


def _route_after_repository_preparation(ctx: Any) -> None:
    """Choose the only valid branch after repository preparation."""
    result = ctx.state.get(_REPOSITORY_PREPARATION_RESULT_STATE_KEY)
    if not isinstance(result, dict):
        ctx.route = "baseline_failed"
        return
    ctx.route = "continue" if result.get("status") == "SUCCESS" else "baseline_failed"


def _baseline_failure_response(ctx: Any) -> str:
    """Return the already formatted terminal response without invoking later stages."""
    result = ctx.state.get(_REPOSITORY_PREPARATION_RESULT_STATE_KEY, {})
    if isinstance(result, dict):
        response = result.get("adkWebResponse")
        if response:
            return str(response)
    return (
        "## OSS Remediation Workflow\n\n"
        "**Final Status:** Repository Preparation Failed\n\n"
        "Repository preparation did not return a usable result, so automated remediation was not attempted."
    )


repository_preparation_agent = LlmAgent(
    name="repository_preparation_agent",
    model="gemini-2.5-flash",
    description="Executes repository checkout and baseline build preparation.",
    instruction=(
        "Run Stage 1. Call run_repository_preparation_stage using the repository URL and reference branch from the user request. "
        "Return the tool result only."
    ),
    tools=[run_repository_preparation_stage],
    after_tool_callback=_capture_repository_preparation_status,
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

replanning_loop_agent = LlmAgent(
    name="replanning_loop_agent",
    model="gemini-2.5-flash",
    description="Continues bounded remediation attempts after validation failure and outcome analysis.",
    instruction=(
        "Run Stage 6b. Read workspaceRoot from {outcome_analysis_result}. "
        "Call run_replanning_loop_stage with that workspaceRoot. Return the tool result only."
    ),
    tools=[run_replanning_loop_stage],
    output_key="replanning_loop_result",
)

pull_request_delivery_agent = LlmAgent(
    name="pull_request_delivery_agent",
    model="gemini-2.5-flash",
    description="Executes PR summary generation and Draft PR delivery.",
    instruction=(
        "Run Stage 7. Read workspaceRoot from {replanning_loop_result}. "
        "Call run_pull_request_delivery_stage with that workspaceRoot. "
        "For the final ADK Web answer, output exactly the markdown text in the returned adkWebResponse field. "
        "Do not add vulnerability summaries, remediation tables, manifest paths, or a Next Action section."
    ),
    tools=[run_pull_request_delivery_stage],
    output_key="pull_request_delivery_result",
)


baseline_status_gate = FunctionNode(
    name="baseline_status_gate",
    func=_route_after_repository_preparation,
)

baseline_failure_response = FunctionNode(
    name="baseline_failure_response",
    func=_baseline_failure_response,
)


root_agent = Workflow(
    name="oss_remediation_agent",
    description=(
        "Executes the OSS remediation workflow through staged ADK agents. A failed repository preparation "
        "stage takes a terminal branch and prevents all later remediation stages."
    ),
    edges=[
        (START, repository_preparation_agent, baseline_status_gate),
        (
            baseline_status_gate,
            {
                "continue": vulnerability_assessment_agent,
                "baseline_failed": baseline_failure_response,
            },
        ),
        (
            vulnerability_assessment_agent,
            project_analyzer_agent,
            remediation_planning_agent,
            patch_validation_agent,
            outcome_analysis_agent,
            replanning_loop_agent,
            pull_request_delivery_agent,
        ),
    ],
)
