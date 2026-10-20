"""Pinned local SKILL.md files loaded using the SDK, not another Skill registry."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def general():
    return (ROOT / "guidance/general-engineering.md").read_text().strip()


def load(task):
    from openhands.sdk.skills import load_skills_from_dir
    repo, knowledge, agentskills = load_skills_from_dir(ROOT / "skills")
    available = {**repo, **knowledge, **agentskills}
    return [available[name] for name in task["guidance"]["skills"]]


def delivery_evidence(agent_context, task_text):
    from openhands.sdk import Message, TextContent
    suffix = agent_context.get_user_message_suffix(
        Message(role="user", content=[TextContent(text=task_text)]), skip_skill_names=[])
    return dict(available=[s.name for s in agent_context.skills],
                systemSuffixSha256=hashlib.sha256(agent_context.system_message_suffix.encode()).hexdigest(),
                triggered=suffix[1] if suffix else [],
                renderedSuffixSha256=hashlib.sha256((suffix[0].text if suffix else "").encode()).hexdigest(),
                sourceSha256={s.name: hashlib.sha256(Path(s.source).read_bytes()).hexdigest()
                              for s in agent_context.skills},
                status="SDK_RENDERED_NOT_MODEL_USE", observedEngineeringUse="NOT_PROVEN")
