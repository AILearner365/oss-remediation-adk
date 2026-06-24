"""ADK entry point for the OSS remediation multi-agent workflow."""

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent, SequentialAgent

from oss_remediation_agent.prompts import (
    DISCOVERY_AGENT_INSTRUCTION,
    REMEDIATION_AGENT_INSTRUCTION,
    PR_CREATION_AGENT_INSTRUCTION,
)
from oss_remediation_agent.tools.workflow_tools import (
    create_pull_request_from_remediation_report,
    generate_remediation_report,
    generate_vulnerability_assessment_report,
)


# Load .env from project root when running locally with ADK.
env_path = Path(__file__).resolve().parent.parent / ".env"
if load_dotenv(dotenv_path=env_path):
    print("Successfully loaded .env file")
    print(f"GOOGLE_API_KEY loaded: {'YES' if os.getenv('GOOGLE_API_KEY') else 'NO'}")
else:
    print("Warning: .env file not found or could not be loaded")


discovery_agent = Agent(
    name="discovery_assessment_agent",
    model="gemini-2.5-flash",
    description=(
        "Agent 1. Clones a Java Spring Boot Maven repository, validates the "
        "reference branch build, runs OSV Scanner, and emits a Vulnerability "
        "Assessment Report."
    ),
    instruction=DISCOVERY_AGENT_INSTRUCTION,
    tools=[generate_vulnerability_assessment_report],
)

remediation_agent = Agent(
    name="automated_remediation_validation_agent",
    model="gemini-2.5-flash",
    description=(
        "Agent 2. Reads the Vulnerability Assessment Report, remediates Critical "
        "and High Maven dependency vulnerabilities by pom.xml version upgrades "
        "only, validates build/tests/scan, and emits a Remediation Report."
    ),
    instruction=REMEDIATION_AGENT_INSTRUCTION,
    tools=[generate_remediation_report],
)

pr_creation_agent = Agent(
    name="pull_request_creation_agent",
    model="gemini-2.5-flash",
    description=(
        "Agent 3. Reads the Remediation Report, validates PR creation conditions, "
        "commits allowed Maven dependency changes, pushes the feature branch, "
        "and creates a GitHub pull request when allowed."
    ),
    instruction=PR_CREATION_AGENT_INSTRUCTION,
    tools=[create_pull_request_from_remediation_report],
)


root_agent = SequentialAgent(
    name="oss_remediation_agent",
    description=(
        "Runs the ADK OSS vulnerability remediation workflow in sequence: "
        "Discovery & Assessment -> Automated Remediation & Validation -> "
        "Pull Request Creation."
    ),
    sub_agents=[
        discovery_agent,
        remediation_agent,
        pr_creation_agent,
    ],
)
