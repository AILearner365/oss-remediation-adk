import os
from pathlib import Path
from dotenv import load_dotenv
from google.adk.agents import Agent, SequentialAgent

from oss_remediation_agent.prompts import (
    SCANNER_AGENT_INSTRUCTION,
    REMEDIATION_AGENT_INSTRUCTION,
    VALIDATION_AGENT_INSTRUCTION,
)

from oss_remediation_agent.tools.scanner_tools import scan_repository
from oss_remediation_agent.tools.remediation_tools import apply_remediation
from oss_remediation_agent.tools.validation_tools import validate_repository


# Load .env from project root: ~/oss-remediation-adk/.env
env_path = Path(__file__).resolve().parent.parent / ".env"

if load_dotenv(dotenv_path=env_path):
    print("Successfully loaded .env file")
    print(f"GOOGLE_API_KEY loaded: {'YES' if os.getenv('GOOGLE_API_KEY') else 'NO'}")
else:
    print("Warning: .env file not found or could not be loaded")


scanner_agent = Agent(
    name="scanner_agent",
    model="gemini-2.5-flash",
    description="Scans the repository for OSS vulnerabilities.",
    instruction=SCANNER_AGENT_INSTRUCTION,
    tools=[scan_repository],
)

remediation_agent = Agent(
    name="remediation_agent",
    model="gemini-2.5-flash",
    description="Plans and applies dependency remediation changes.",
    instruction=REMEDIATION_AGENT_INSTRUCTION,
    tools=[apply_remediation],
)

validation_agent = Agent(
    name="validation_agent",
    model="gemini-2.5-flash",
    description="Validates the repository after remediation.",
    instruction=VALIDATION_AGENT_INSTRUCTION,
    tools=[validate_repository],
)


root_agent = SequentialAgent(
    name="oss_remediation_agent",
    description="Runs OSS scan, remediation, and validation in sequence.",
    sub_agents=[
        scanner_agent,
        remediation_agent,
        validation_agent,
    ],
)