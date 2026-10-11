#!/usr/bin/env python3
"""Run an investigation-only OpenHands Maven dependency research experiment.

The non-SDK helpers are intentionally importable by offline tests. OpenHands is
imported only after the evidence directory and baseline manifest exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from typing import Any


CONTROL_REPO = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = Path.home() / "maven-multimodule-app"
DEFAULT_BASELINE_REF = "origin/main-runrunning"
DEFAULT_MODEL = "vertex_ai/gemini-2.5-flash"
GENERAL_GUIDANCE = CONTROL_REPO / "scripts/openhands/guidance/general-engineering.md"
PROJECT_GUIDANCE = CONTROL_REPO / "scripts/openhands/project-context/AGENTS.md"
SKILLS_DIR = CONTROL_REPO / "scripts/openhands/skills"
SKILL_NAME = "maven-dependency-evidence"
SKILL_FILE = SKILLS_DIR / SKILL_NAME / "SKILL.md"

PROMPT = """Investigate this Maven repository's dependency situation and provide an evidence-based recommendation. This is investigation-only: do not modify any repository file or perform remediation.

Inspect the actual parent/BOM ownership and identify relevant direct and transitive dependencies. Verify that candidate versions are published and resolvable, evaluate vulnerability evidence where it is available, and consider compatibility and downstream impact. Clearly distinguish observed evidence from assumptions. Do not claim that a candidate fixes a vulnerability unless the evidence covers it. Make a conditional recommendation, or explicitly defer selection when evidence is insufficient.

Use the available maven-dependency-evidence Skill when Maven dependency or published-version facts materially affect the decision. Report commands and sources used, material uncertainties, and the final recommendation."""


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")


def create_clean_fixture(source: Path, baseline_ref: str, workspace: Path) -> dict[str, Any]:
    """Export exactly one Git commit without reading files from the worktree."""
    if workspace.exists():
        raise ValueError(f"workspace already exists: {workspace}")
    if run_git(source, "rev-parse", "--is-inside-work-tree") != "true":
        raise ValueError(f"not a Git repository: {source}")
    commit = run_git(source, "rev-parse", f"{baseline_ref}^{{commit}}")
    workspace.mkdir(parents=True)
    archive = subprocess.Popen(["git", "archive", "--format=tar", commit], cwd=source,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert archive.stdout is not None
    try:
        with tarfile.open(fileobj=archive.stdout, mode="r|") as stream:
            stream.extractall(workspace, filter="data")
    finally:
        archive.stdout.close()
    stderr = archive.stderr.read().decode() if archive.stderr else ""
    if archive.stderr:
        archive.stderr.close()
    if archive.wait():
        shutil.rmtree(workspace)
        raise RuntimeError(f"git archive failed: {stderr.strip()}")
    # Give the agent Git inspection without linking this fixture to a user worktree.
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(["git", "-c", "user.name=OpenHands Evidence Test",
                    "-c", "user.email=none@example.invalid", "commit", "-qm", "baseline"],
                   cwd=workspace, check=True)
    return {"requestedRef": baseline_ref, "commit": commit,
            "sourceRepository": str(source.resolve())}


def tree_state(workspace: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            state[str(path.relative_to(workspace))] = sha256(path)
    return state


def require_clean_fixture(workspace: Path) -> None:
    if run_git(workspace, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError(f"fixture is dirty or uncontrolled: {workspace}")


def initial_poms(workspace: Path) -> list[dict[str, Any]]:
    rows = []
    pattern = re.compile(r"<(?:version|artifactId)>([^<]+)</(?:version|artifactId)>")
    for path in sorted(workspace.rglob("pom.xml")):
        text = path.read_text(encoding="utf-8")
        rows.append({"path": str(path.relative_to(workspace)), "sha256": sha256(path),
                     "declaredValues": pattern.findall(text)})
    return rows


SENSITIVE = re.compile(r"(?i)(api.?key|password|secret|access.?token|authorization)")
PRIVATE_FIELDS = {"reasoning_content", "thinking_blocks", "thought", "signature", "raw_response"}


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if SENSITIVE.search(str(k)) else sanitize(v))
                for k, v in value.items() if str(k) not in PRIVATE_FIELDS}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(Bearer\s+)[\w.\-/+=]+", r"\1[REDACTED]", value)
        return re.sub(r"(?i)((?:api[_-]?key|access[_-]?token|password)\s*[=:]\s*)[^\s,;]+",
                      r"\1[REDACTED]", value)
    return value


def serialize_event(event: Any) -> dict[str, Any]:
    """Serialize SDK 1.50 events without assuming MessageEvent.message."""
    if hasattr(event, "model_dump"):
        raw = event.model_dump(mode="json", exclude_none=True)
    elif isinstance(event, dict):
        raw = dict(event)
    else:
        raw = {"kind": type(event).__name__, "representation": repr(event)}
    kind = raw.get("kind", type(event).__name__)
    raw.setdefault("kind", kind)
    if kind == "MessageEvent":
        message = raw.get("llm_message")
        if isinstance(message, dict):
            raw["observable_message"] = {k: message[k] for k in ("role", "content") if k in message}
        else:
            raw["schema_warning"] = "MessageEvent has no llm_message mapping"
    return sanitize(raw)


def evidence_assessment(events: list[dict[str, Any]], configured: bool,
                        delivered: bool, invoked_skills: list[str]) -> dict[str, Any]:
    evidence_rows = [
        row for row in events
        if row.get("kind") != "SystemPromptEvent"
        and not (
            row.get("kind") == "MessageEvent"
            and isinstance(row.get("observable_message"), dict)
            and row["observable_message"].get("role") == "user"
        )
    ]
    text = json.dumps(evidence_rows).lower()
    classifications = {
        "skillConfigured": "PROVEN" if configured else "NOT PROVEN",
        "skillTriggeredDelivered": "PROVEN" if delivered else "NOT PROVEN",
        "skillExplicitlyInvoked": "PROVEN" if SKILL_NAME in invoked_skills else "NOT PROVEN",
    }
    indicators = {
        "skillInstructionsVisiblyAppliedIndicator": "PARTIAL" if any(x in text for x in ("dependency:tree", "effective-pom", "dependency management")) else "NOT PROVEN",
        "publishedVersionVerificationIndicator": "PARTIAL" if any(x in text for x in ("maven-metadata", "dependency:get", "versions:display")) else "NOT PROVEN",
        "dependencyBomOwnershipIndicator": "PARTIAL" if any(x in text for x in ("effective-pom", "dependency:tree", "bom")) else "NOT PROVEN",
        "vulnerabilityCoverageIndicator": "PARTIAL" if any(x in text for x in ("osv", "cve-", "ghsa-")) else "NOT PROVEN",
        "compatibilityAssessmentIndicator": "PARTIAL" if "compatib" in text else "NOT PROVEN",
        "decisionQualityIndicator": "PARTIAL" if "recommend" in text else "NOT PROVEN",
        "unresolvedUncertaintiesIndicator": "PARTIAL" if any(x in text for x in ("uncertain", "insufficient", "unknown")) else "NOT PROVEN",
    }
    return {
        "classifications": classifications,
        "keywordIndicators": indicators,
        "sdkInvokedSkills": invoked_skills,
        "indicatorDisclaimer": (
            "Keyword indicators locate evidence for human review only. They do not prove "
            "technical correctness, evidence coverage, decision quality, or successful Skill application."
        ),
        "skillEvidenceDisclaimer": (
            "Configuration and trigger delivery do not prove use. Explicit invocation is PROVEN "
            "only when SDK 1.50.0 conversation state records the Skill in invoked_skills."
        ),
    }


def export_events(events: list[Any], output: Path) -> list[dict[str, Any]]:
    rows = serialize_events(events)
    with output.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
    return rows


def serialize_events(events: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for sequence, event in enumerate(events):
        try:
            row = serialize_event(event)
        except Exception as exc:
            row = {"kind": type(event).__name__, "serializationError": str(exc)}
        row["sequence"] = sequence
        rows.append(row)
    return rows


def record_error(status: dict[str, Any], phase: str, exc: BaseException) -> None:
    status["phase"] = "failed"
    status.setdefault("errors", []).append({
        "phase": phase, "type": type(exc).__name__, "message": str(exc),
    })
    if status.get("error") is None:
        status["error"] = status["errors"][0]


def export_events_preserving_status(events: list[Any], output: Path,
                                    status: dict[str, Any],
                                    exporter: Any = export_events) -> list[dict[str, Any]]:
    try:
        return exporter(events, output / "events.jsonl")
    except BaseException as exc:
        record_error(status, "event_export", exc)
        rows = serialize_events(events)
        try:
            write_json(output / "events-export-fallback.json", rows)
        except BaseException as fallback_exc:
            record_error(status, "event_export_fallback", fallback_exc)
        return rows


def run_conversation(conversation: Any, prompt: str,
                     status: dict[str, Any]) -> tuple[list[Any], list[str]]:
    """Run and close a conversation while retaining each observable failure."""
    events: list[Any] = []
    invoked_skills: list[str] = []
    try:
        conversation.send_message(prompt)
        conversation.run()
        status["phase"] = "completed"
    except BaseException as exc:
        record_error(status, "execution", exc)
    finally:
        try:
            state = conversation.state
            events = list(state.events)
            invoked_skills = list(getattr(state, "invoked_skills", []))
            execution_status = getattr(state, "execution_status", None)
            status["stopReason"] = getattr(execution_status, "value", str(execution_status))
            stats = getattr(state, "stats", None)
            status["tokenUsage"] = sanitize(
                stats.model_dump(mode="json") if hasattr(stats, "model_dump") else None)
        except BaseException as exc:
            record_error(status, "state_capture", exc)
        try:
            conversation.close()
        except BaseException as exc:
            record_error(status, "conversation_cleanup", exc)
    return events, invoked_skills


def final_assistant_message(events: list[dict[str, Any]]) -> Any:
    for row in reversed(events):
        message = row.get("observable_message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            return message.get("content")
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-iterations", type=int, default=15)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source_repo.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    if output == source or source in output.parents:
        raise SystemExit("Output directory must be outside the source repository")
    if output.exists():
        raise SystemExit(f"Output directory must not already exist: {output}")
    output.mkdir(parents=True)
    workspace = output / "workspace"
    status: dict[str, Any] = {"phase": "preparing", "error": None, "errors": [],
                              "stopReason": None, "tokenUsage": None}
    write_json(output / "status.json", status)
    events: list[Any] = []
    invoked_skills: list[str] = []
    delivered = False
    triggered_names: list[str] = []
    try:
        baseline = create_clean_fixture(source, args.baseline_ref, workspace)
        require_clean_fixture(workspace)
        source_status_before = run_git(source, "status", "--porcelain=v1", "--untracked-files=all")
        before = tree_state(workspace)
        manifest = {
            "sdk": "openhands-sdk[vertex]==1.50.0", "tools": "openhands-tools==1.50.0",
            "model": args.model, "prompt": PROMPT, "baseline": baseline,
            "sourceStatusBefore": source_status_before.splitlines(),
            "initialPoms": initial_poms(workspace),
            "instructions": {
                "generalGuidance": {"path": str(GENERAL_GUIDANCE), "sha256": sha256(GENERAL_GUIDANCE)},
                "projectGuidance": {"path": str(PROJECT_GUIDANCE), "sha256": sha256(PROJECT_GUIDANCE)},
                "mavenSkill": {"name": SKILL_NAME, "path": str(SKILL_FILE), "sha256": sha256(SKILL_FILE)},
            },
        }
        write_json(output / "run-manifest.json", manifest)
        write_json(output / "workspace-before.json", before)
        status["phase"] = "running"
        write_json(output / "status.json", status)

        from openhands.sdk import AgentContext, Conversation, LLM
        from openhands.sdk.llm import Message, TextContent
        from openhands.sdk.skills import load_skills_from_dir
        from openhands.tools.preset.default import get_default_agent

        _, _, skills = load_skills_from_dir(SKILLS_DIR)
        if SKILL_NAME not in skills:
            raise RuntimeError(f"missing Skill: {SKILL_NAME}")
        context = AgentContext(
            skills=[skills[SKILL_NAME]], load_public_skills=False,
            system_message_suffix=GENERAL_GUIDANCE.read_text() +
            "\n\n<REPOSITORY_GUIDANCE>\n" + PROJECT_GUIDANCE.read_text() +
            "\n</REPOSITORY_GUIDANCE>",
        )
        activation = context.get_user_message_suffix(
            Message(role="user", content=[TextContent(text=PROMPT)]), skip_skill_names=[])
        delivered = bool(activation and SKILL_NAME in activation[1])
        triggered_names = sorted(str(x) for x in activation[1]) if activation else []
        write_json(output / "skill-delivery.json", {
            "configured": True, "triggeredDelivered": delivered,
            "triggeredNames": triggered_names,
            "explicitInvocation": "NOT PROVEN",
        })
        llm = LLM(usage_id="maven-dependency-research", model=args.model, api_key=None)
        agent = get_default_agent(llm=llm, cli_mode=True).model_copy(update={"agent_context": context})
        conversation = Conversation(agent=agent, workspace=str(workspace),
                                    persistence_dir=output / "conversation", delete_on_close=False,
                                    max_iteration_per_run=args.max_iterations, stuck_detection=True)
        events, invoked_skills = run_conversation(conversation, PROMPT, status)
    except BaseException as exc:
        record_error(status, "setup", exc)
    finally:
        rows = export_events_preserving_status(events, output, status)
        write_json(output / "skill-delivery.json", {
            "configured": True, "triggeredDelivered": delivered,
            "triggeredNames": triggered_names,
            "sdkInvokedSkills": invoked_skills,
            "explicitInvocation": "PROVEN" if SKILL_NAME in invoked_skills else "NOT PROVEN",
        })
        write_json(output / "final-assistant.json", {
            "content": final_assistant_message(rows),
            "status": "PROVEN" if final_assistant_message(rows) is not None else "NOT PROVEN",
        })
        if workspace.exists():
            after = tree_state(workspace)
            write_json(output / "workspace-after.json", after)
            changes = sorted(set(before) | set(after)) if "before" in locals() else []
            changes = [p for p in changes if before.get(p) != after.get(p)] if "before" in locals() else changes
        else:
            changes = []
        try:
            source_status_after = run_git(source, "status", "--porcelain=v1", "--untracked-files=all")
        except Exception as exc:
            source_status_after = f"STATUS_CHECK_FAILED: {exc}"
        source_unchanged = ("source_status_before" in locals()
                            and source_status_after == source_status_before)
        if status["phase"] == "completed" and (changes or not source_unchanged):
            record_error(status, "workspace_integrity", RuntimeError(
                "isolated workspace or source worktree changed during investigation"))
        write_json(output / "workspace-integrity.json", {
            "workspaceUnchanged": not changes, "changedPaths": changes,
            "sourceWorktreeUnchanged": source_unchanged,
            "sourceStatusAfter": source_status_after.splitlines(),
        })
        write_json(output / "assessment.json", evidence_assessment(
            rows, True, delivered, invoked_skills))
        write_json(output / "status.json", status)
    if status["phase"] != "completed" or changes or not source_unchanged:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
