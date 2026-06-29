from __future__ import annotations

from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "remediation_outcome_analysis_agent.md"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")
