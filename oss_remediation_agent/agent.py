from __future__ import annotations

import tempfile
from typing import Any

from google.adk.agents import Agent

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.orchestrator import WorkflowOrchestrator


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
    create pull requests.
    """
    workspace = workspace_root or tempfile.mkdtemp(prefix="oss-remediation-workspace-")
    policy = RemediationPolicy.load(policy_path)
    orchestrator = WorkflowOrchestrator(workspace, policy=policy)
    return orchestrator.run_workflow(
        repository_url=repository_url,
        reference_branch=reference_branch,
        planning_agent_output=planning_agent_output,
    )


root_agent = Agent(
    name="oss_remediation_agent",
    model="gemini-2.5-flash",
    description="Production ADK entrypoint for the OSS remediation MVP workflow.",
    instruction=(
        "You are the OSS remediation workflow entrypoint. When the user asks to run remediation, "
        "call run_oss_remediation_workflow with the repository URL and reference branch. "
        "Do not mutate repositories directly, do not update manifests directly, do not apply patches directly, "
        "and do not create pull requests. All workflow execution must be delegated to "
        "WorkflowOrchestrator.run_workflow through the exposed tool. If the workflow returns "
        "AWAITING_PLANNING_AGENT_OUTPUT, report the planning context artifact path and next action. "
        "Return the workspace path, manifest path, progress steps, final status, artifacts, and next action."
    ),
    tools=[run_oss_remediation_workflow],
)
