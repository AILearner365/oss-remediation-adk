from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.adk.agents import Agent

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.phase6_orchestrator import Phase6WorkflowOrchestrator


def run_oss_remediation_workflow(
    repository_url: str,
    reference_branch: str = "main",
    workspace_root: str | None = None,
    planning_agent_output: str | dict[str, Any] | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    """Run the OSS remediation workflow through the orchestrator.

    This is the ADK entry capability. The ADK agent stays intentionally thin:
    it accepts user/runtime inputs, loads policy, creates the orchestrator, and
    delegates the full lifecycle to ``WorkflowOrchestrator.run_workflow``.

    The agent does not sequence workflow steps, mutate repositories, update the
    manifest, make remediation decisions, apply patches, run validation, or
    create pull requests directly. Phase 6 PR behavior is delegated to the
    deterministic orchestrator and controlled by policy.
    """
    workspace = workspace_root or _default_workspace_root()
    policy = RemediationPolicy.load(policy_path)
    orchestrator = Phase6WorkflowOrchestrator(workspace, policy=policy)
    return orchestrator.run_workflow(
        repository_url=repository_url,
        reference_branch=reference_branch,
        planning_agent_output=planning_agent_output,
    )


def _default_workspace_root() -> str:
    """Create a visible project-local workspace path for ADK smoke tests.

    ``workspace_root`` can still be supplied explicitly to use /tmp or another
    external location, but the default should be easy to inspect from Cloud Shell
    Editor and local IDE explorers.
    """
    run_id = datetime.now(timezone.utc).strftime("oss-remediation-%Y%m%d-%H%M%S")
    return str((Path.cwd() / "oss-remediation-workspaces" / run_id).resolve())


root_agent = Agent(
    name="oss_remediation_agent",
    model="gemini-2.5-flash",
    description="Production ADK entrypoint for the OSS remediation MVP workflow.",
    instruction=(
        "You are the OSS remediation workflow entrypoint. When the user asks to run remediation, "
        "call run_oss_remediation_workflow with the repository URL and reference branch. "
        "Do not mutate repositories directly, do not update manifests directly, do not apply patches directly, "
        "and do not create pull requests directly. All workflow execution, including policy-controlled Phase 6 "
        "PR handling, must be delegated to WorkflowOrchestrator.run_workflow through the exposed tool. "
        "Return the workspace path, manifest path, progress steps, final status, artifacts, and next action."
    ),
    tools=[run_oss_remediation_workflow],
)
