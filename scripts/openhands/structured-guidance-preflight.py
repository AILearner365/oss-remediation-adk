#!/usr/bin/env python3
"""Offline SDK 1.50.0 prompt-delivery checks; never calls the model."""
from pathlib import Path
import ast
from openhands.sdk import AgentContext
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.skills import load_skills_from_dir

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/openhands/openhands-gate2-stop-hook-run.py"
GENERAL = ROOT / "scripts/openhands/guidance/general-engineering.md"
PROJECT = ROOT / "scripts/openhands/project-context/AGENTS.md"
SKILLS = ROOT / "scripts/openhands/skills"
TASK = ROOT / "docs/experiments/openhands/GATE2-TASK.md"
NAME = "maven-dependency-evidence"


def main():
    ast.parse(RUNNER.read_text(encoding="utf-8"))
    _, _, skills = load_skills_from_dir(SKILLS)
    assert NAME in skills and skills[NAME].trigger is not None
    general = GENERAL.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    assert general.strip() and project.strip()
    context = AgentContext(
        skills=[skills[NAME]],
        system_message_suffix=general + "\n\n<REPOSITORY_GUIDANCE>\n" + project + "\n</REPOSITORY_GUIDANCE>",
        load_public_skills=False,
    )
    system = context.get_system_message_suffix(llm_model="vertex_ai/gemini-2.5-flash")
    assert system is not None
    assert "hard constraint" in system
    assert "task-common" in system
    assert NAME in system
    assert "evidence-driven-dependency-remediation" not in system
    task_doc = TASK.read_text(encoding="utf-8")
    task = task_doc.split("## Prompt to give OpenHands", 1)[1].split("```text", 1)[1].split("```", 1)[0].strip()
    task += "\n\nUse the available maven-dependency-evidence Skill when Maven dependency or published-version facts materially affect your engineering decision."
    activated = context.get_user_message_suffix(
        Message(role="user", content=[TextContent(text=task)]), skip_skill_names=[]
    )
    assert activated is not None
    injected, triggered = activated
    assert NAME in triggered
    assert "display-parent-updates" in injected.text
    assert "engineering-judgment.md" not in system + injected.text
    print("STRUCTURED_GUIDANCE_PREFLIGHT=PASS")
    print("general_guidance=True; repository_context=True; maven_skill_triggered=True")
    print("model_api_calls=0; Maven_version_metadata_network=NOT_TESTED")


if __name__ == "__main__":
    main()
