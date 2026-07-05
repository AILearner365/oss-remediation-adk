from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.adk.agents import Agent

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.workflow.phase6_patch_progress_orchestrator import Phase6PatchProgressOrchestrator


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
    orchestrator = Phase6PatchProgressOrchestrator(workspace, policy=policy)
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


repository_preparation_agent = Agent(
    name="repository_preparation_agent",
    model="gemini-2.5-flash",
    description="Represents repository checkout and baseline build preparation in the OSS remediation workflow.",
    instruction=(
        "Represent the Repository Preparation stage: repository checkout and baseline build. "
        "The deterministic orchestrator executes this stage through tools; do not independently mutate repositories."
    ),
)

vulnerability_assessment_agent = Agent(
    name="vulnerability_assessment_agent",
    model="gemini-2.5-flash",
    description="Represents OSV vulnerability assessment for Maven projects.",
    instruction=(
        "Represent the Assessment stage for OSS vulnerability scanning. "
        "Severity must come from the generated vulnerability assessment artifact."
    ),
)

project_analyzer_agent = Agent(
    name="project_analyzer_agent",
    model="gemini-2.5-flash",
    description="Represents Maven project structure analysis for single-module and multi-module Spring Boot projects.",
    instruction=(
        "Represent the Maven Project Analysis stage. "
        "Analyze Maven structure, modules, dependency management, and dependency locations only through orchestrated artifacts."
    ),
)

remediation_planning_agent = Agent(
    name="remediation_planning_agent",
    model="gemini-2.5-flash",
    description="Represents dependency-only remediation planning.",
    instruction=(
        "Represent the Remediation Planning stage. "
        "Plan dependency-only Maven changes and route unsafe framework, JDK, plugin, source, or test changes to manual review."
    ),
)

patch_validation_agent = Agent(
    name="patch_validation_agent",
    model="gemini-2.5-flash",
    description="Represents patch dry run, patch application, validation, and accepted patch set creation.",
    instruction=(
        "Represent the Patch and Validation stage. "
        "Dependency patches must be dry-run, applied, validated, and accepted only when validation succeeds."
    ),
)

pull_request_delivery_agent = Agent(
    name="pull_request_delivery_agent",
    model="gemini-2.5-flash",
    description="Represents PR summary generation and GitHub Draft PR delivery.",
    instruction=(
        "Represent the Delivery stage. "
        "Create reviewer-friendly PR summaries and Draft PRs only through the policy-controlled orchestrator."
    ),
)


root_agent = Agent(
    name="oss_remediation_agent",
    model="gemini-2.5-flash",
    description="Production ADK entrypoint for the OSS remediation MVP workflow.",
    instruction=(
        "You are the OSS remediation workflow entrypoint. When the user asks to run remediation, "
        "call run_oss_remediation_workflow with the repository URL and reference branch. "
        "Delegate workflow execution to the exposed tool. The listed subagents represent workflow stages in ADK Web, "
        "but execution remains controlled by the deterministic orchestrator. "
        "For the final ADK Web answer, render the markdown text from the returned adkWebResponse field exactly. "
        "The final answer should not add manifest paths, raw progress fields, vulnerability summaries, remediation tables, "
        "or a Next Action section. Those details are available in the generated PR summary and workspace artifacts for follow-up questions."
    ),
    tools=[run_oss_remediation_workflow],
    sub_agents=[
        repository_preparation_agent,
        vulnerability_assessment_agent,
        project_analyzer_agent,
        remediation_planning_agent,
        patch_validation_agent,
        pull_request_delivery_agent,
    ],
)
