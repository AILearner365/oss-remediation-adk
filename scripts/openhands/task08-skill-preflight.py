#!/usr/bin/env python3
"""Task-08 offline Skill loading preflight; no model calls or repo edits."""
from pathlib import Path
import ast
import hashlib

from openhands.sdk import AgentContext
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.skills import load_skills_from_dir

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/openhands/openhands-gate2-stop-hook-run.py"
SKILL_ROOT = ROOT / "scripts/openhands/skills"
NAME = "evidence-driven-dependency-remediation"


def main() -> None:
    ast.parse(RUNNER.read_text(encoding="utf-8"))
    path = SKILL_ROOT / NAME / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: " + NAME in text
    assert all(
        title in text for title in (
            "Establish the actual system",
            "Choose a defensible strategy",
            "Use failures as evidence",
            "Implement with continuity",
            "Validate the whole goal",
        )
    )
    _, _, agent_skills = load_skills_from_dir(SKILL_ROOT)
    assert NAME in agent_skills, sorted(agent_skills)
    skill = agent_skills[NAME]
    assert skill.is_agentskills_format
    assert skill.trigger is not None, "Task-08 Skill must be auto-injected by a task keyword"
    task_text = (ROOT / "docs/experiments/openhands/GATE2-TASK.md").read_text(encoding="utf-8").lower()
    for keyword in ("vulnerability", "remediation", "dependency"):
        assert keyword in task_text
    context = AgentContext(skills=[skill], load_public_skills=False)
    assert any(s.name == NAME for s in context.skills)
    assert context.system_message_suffix is None
    # Exercise the same SDK methods used to compose model-facing context.
    task_document = (ROOT / "docs/experiments/openhands/GATE2-TASK.md").read_text(
        encoding="utf-8"
    )
    marker = "## Prompt to give OpenHands"
    assert marker in task_document
    section = task_document.split(marker, 1)[1]
    task_prompt = section.split("```text", 1)[1].split("```", 1)[0].strip()
    message = Message(role="user", content=[TextContent(text=task_prompt)])
    available = context.get_system_message_suffix(llm_model="vertex_ai/gemini-2.5-flash")
    assert available is not None and NAME in available
    assert "engineering-judgment.md" not in available
    activated = context.get_user_message_suffix(message, skip_skill_names=[])
    assert activated is not None, "Task text did not activate the Skill"
    injected, triggered_names = activated
    assert NAME in triggered_names, triggered_names
    assert "Establish the actual system" in injected.text
    assert "Use failures as evidence" in injected.text
    assert "engineering-judgment.md" not in injected.text
    print("TASK08_SKILL_ACTIVATION=PASS")
    print("system_advertisement=True; task_keyword_injection=True")
    print("legacy_suffix_absent=True; model_api_calls=0")
    print("TASK08_SKILL_PREFLIGHT=PASS")
    print("skill_name=" + NAME)
    print("skill_sha256=" + hashlib.sha256(path.read_bytes()).hexdigest())
    print("skill_count=" + str(len(context.skills)))
    print("load_public_skills=False")
    print("sdk_loaded=True; model_read_or_adherence=NOT_TESTED")


if __name__ == "__main__":
    main()
