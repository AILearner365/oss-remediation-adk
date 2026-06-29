from __future__ import annotations

from google.adk.agents import Agent


def describe_architecture() -> dict:
    return {
        "status": "READY_FOR_MVP_IMPLEMENTATION",
        "entrypoint": "agent.py",
        "orchestrator": "oss_remediation_agent.workflow.orchestrator.WorkflowOrchestrator",
        "note": "The ADK entrypoint is intentionally thin; workflow execution lives in workflow/orchestrator.py.",
    }


root_agent = Agent(
    name="oss_remediation_agent",
    model="gemini-2.5-flash",
    description="ADK entrypoint for the OSS remediation MVP architecture.",
    instruction="Use the architecture documents and deterministic workflow scaffolding. Do not perform repository mutations from the agent directly.",
    tools=[describe_architecture],
)
