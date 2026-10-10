#!/usr/bin/env python3
"""Task-08 offline Skill loading preflight; no model calls or repo edits."""
from pathlib import Path
import ast
import hashlib

from openhands.sdk import AgentContext
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
    context = AgentContext(skills=[skill], load_public_skills=False)
    assert any(s.name == NAME for s in context.skills)
    assert context.system_message_suffix is None
    print("TASK08_SKILL_PREFLIGHT=PASS")
    print("skill_name=" + NAME)
    print("skill_sha256=" + hashlib.sha256(path.read_bytes()).hexdigest())
    print("skill_count=" + str(len(context.skills)))
    print("load_public_skills=False")
    print("sdk_loaded=True; model_read_or_adherence=NOT_TESTED")


if __name__ == "__main__":
    main()
