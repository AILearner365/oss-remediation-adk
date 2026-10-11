#!/usr/bin/env python3
"""Run one bounded live OpenHands diagnostic of validate-remediation."""

from __future__ import annotations

import sys
from pathlib import Path

CONTROL_REPO = Path(__file__).resolve().parents[2]
if str(CONTROL_REPO) not in sys.path:
    sys.path.insert(0, str(CONTROL_REPO))

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import time
from typing import Any

from maven_repository_server import serve_maven_repository


DEFAULT_FIXTURE = CONTROL_REPO / "tests/fixtures/maven-multi-module"
DEFAULT_MODEL = "vertex_ai/gemini-2.5-flash"
PROMPT = """Inspect this Maven project and run the available full-project validation. Investigate the result and supporting scanner evidence. Explain whether the project passed validation, what the scanner covered, and any remaining vulnerabilities or errors. Do not modify application code.

Use `validate-remediation` from the terminal PATH for the full-project validation. Read the retained raw OSV report and Maven coverage evidence that it identifies before giving your conclusion."""

SENSITIVE = re.compile(r"(?i)(api.?key|password|secret|access.?token|authorization)")
PRIVATE_FIELDS = {"reasoning_content", "thinking_blocks", "thought", "signature", "raw_response"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-iterations", type=int, default=12)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--run-live", action="store_true")
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repository, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def tracked_state(repository: Path) -> dict[str, str]:
    return {
        relative: sha256(repository / relative)
        for relative in run_git(repository, "ls-files").splitlines()
    }


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SENSITIVE.search(str(key)) else sanitize(item)
            for key, item in value.items()
            if str(key) not in PRIVATE_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"__thought__\S+", "[OPAQUE_SIGNATURE_OMITTED]", value)
        value = re.sub(r"(?i)(Bearer\s+)[\w.\-/+=]+", r"\1[REDACTED]", value)
        return re.sub(
            r"(?i)((?:api[_-]?key|access[_-]?token|password)\s*[=:]\s*)[^\s,;]+",
            r"\1[REDACTED]", value,
        )
    return value


def serialize_events(events: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sequence, event in enumerate(events):
        try:
            raw = event.model_dump(mode="json", exclude_none=True)
        except Exception as exc:
            raw = {"kind": type(event).__name__, "serializationError": str(exc)}
        raw.setdefault("kind", type(event).__name__)
        raw["sequence"] = sequence
        rows.append(sanitize(raw))
    return rows


def final_assistant_message(rows: list[dict[str, Any]]) -> Any:
    for row in reversed(rows):
        if row.get("kind") != "MessageEvent":
            continue
        message = row.get("llm_message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            return message.get("content")
    return None


def prepare_fixture(fixture: Path, target: Path) -> str:
    shutil.copytree(fixture, target)
    subprocess.run(["git", "init", "-q", "-b", "validation-live"], cwd=target, check=True)
    subprocess.run(["git", "add", "-A"], cwd=target, check=True)
    subprocess.run(
        ["git", "-c", "user.name=OpenHands Validation Test",
         "-c", "user.email=none@example.invalid", "commit", "-qm", "fixture baseline"],
        cwd=target, check=True,
    )
    return run_git(target, "rev-parse", "HEAD")


def create_baseline(target: Path, output: Path, scanner_path: Path) -> dict[str, Any]:
    from autonomous_oss_remediation_agent.capabilities.execution import ExecutionBudget, ProcessRunner
    from autonomous_oss_remediation_agent.config import (
        ExecutionBudgetConfig, MavenConfig, OsvScannerConfig, RuntimePolicy, ScannerConfig,
    )
    from autonomous_oss_remediation_agent.deterministic.constraints import ConstraintEvaluator
    from autonomous_oss_remediation_agent.deterministic.maven import MavenService
    from autonomous_oss_remediation_agent.deterministic.scanner import create_scanner
    from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore

    root = output / "baseline-workspace"
    workspace = RunWorkspace(
        root=root, repository=target, artifacts=root / "artifacts",
        cache=root / "cache", temp=root / "temp", tools=root / "tools",
    )
    for directory in (
        workspace.artifacts, workspace.cache, workspace.temp,
        workspace.tools, workspace.investigation,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    trace = TraceStore(workspace)
    budget = ExecutionBudget(ExecutionBudgetConfig(
        max_cycles=1, max_tool_calls=20, command_timeout_seconds=600,
        overall_timeout_seconds=900, max_returned_output_chars=30000,
    ))
    policy = RuntimePolicy(
        trusted_repository=True, dedicated_runner=True,
        enable_autonomous_shell=False, allow_network=True,
    )
    runner = ProcessRunner(workspace, trace, budget, policy)
    maven = MavenConfig(mode="auto")
    config = ScannerConfig(
        backend="osv",
        osv=OsvScannerConfig(
            mode="configured", executable=str(scanner_path),
            version="2.6.0", timeout_seconds=300,
        ),
    )
    scanner = create_scanner(config, workspace, runner, trace, maven_config=maven)
    scanner.preflight(config)
    build_results = MavenService(target, runner, maven).run_baseline(("mvn clean verify",))
    if not build_results or not all(result.succeeded for result in build_results):
        raise RuntimeError("Disposable fixture baseline Maven build failed")
    scan = scanner.scan(target, ("CRITICAL", "HIGH"), "live-test-baseline")
    if not scan.succeeded:
        raise RuntimeError(f"Disposable fixture baseline scan incomplete: {scan.error}")
    constraints = ConstraintEvaluator().capture(target)
    commit = run_git(target, "rev-parse", "HEAD")
    state = {
        "experiment": "validate-remediation-controlled-live-test",
        "targetRepository": str(target),
        "origin": f"file://{target}",
        "baseBranch": "validation-live",
        "taskBranch": "validation-live",
        "baselineCommit": commit,
        "scanner": scanner.handle.to_dict() if scanner.handle else None,
        "buildResults": [result.to_dict() for result in build_results],
        "scan": scan.to_dict(),
        "constraints": constraints.to_dict(),
        "targetFindings": [finding.to_dict() for finding in scan.findings],
    }
    write_json(output / "baseline.json", state)
    return state


def create_validator_environment(output: Path) -> Path:
    """Create a durable validator interpreter isolated from the OpenHands SDK env."""
    environment = output / "validator-venv"
    python = environment / "bin/python"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(environment)],
        cwd=CONTROL_REPO,
        check=True,
    )
    subprocess.run(
        [
            "uv", "pip", "install", "--python", str(python), "--requirements",
            str(CONTROL_REPO / "autonomous_oss_remediation_agent/requirements.txt"),
        ],
        cwd=CONTROL_REPO,
        check=True,
    )
    subprocess.run(
        [str(python), "-c", "import google.adk, pydantic"],
        cwd=CONTROL_REPO,
        check=True,
    )
    return python


def main() -> int:
    args = parse_args()
    output = args.output_dir.expanduser().resolve()
    fixture = args.fixture.expanduser().resolve()
    if args.max_iterations < 4 or args.max_iterations > 20:
        raise SystemExit("--max-iterations must be between 4 and 20")
    scanner_path = Path.home() / "bin/osv-scanner"
    if not scanner_path.is_file() or not os.access(scanner_path, os.X_OK):
        raise SystemExit(f"OSV Scanner is unavailable: {scanner_path}")
    target = output / "workspace"
    state_dir = output / "harness-state"
    launcher_dir = state_dir / "scanner-bin"
    self_validation_root = state_dir / "self-validation"
    official = state_dir / "official-stop-hook"
    conversation_dir = output / "conversation"

    if args.prepare_only:
        if output.exists():
            raise SystemExit(f"Output directory already exists: {output}")
        output.mkdir(parents=True)
        status: dict[str, Any] = {
            "phase": "preparing", "model": args.model, "conversationId": None,
            "executionStatus": None, "elapsedSeconds": None, "modelUsage": None,
            "errors": [],
        }
        write_json(output / "status.json", status)
        started = time.monotonic()
        try:
            commit = prepare_fixture(fixture, target)
            baseline = create_baseline(target, output, scanner_path)
            baseline_path = output / "baseline.json"
            tracked_before = tracked_state(target)
            baseline_sha_before = sha256(baseline_path)
            launcher_dir.mkdir(parents=True)
            shutil.copyfile(CONTROL_REPO / "scripts/openhands/validate-remediation",
                            launcher_dir / "validate-remediation")
            (launcher_dir / "validate-remediation").chmod(0o700)
            shutil.copyfile(CONTROL_REPO / "scripts/openhands/openhands-osv-scanner.sh",
                            launcher_dir / "osv-scanner")
            (launcher_dir / "osv-scanner").chmod(0o700)
            official.mkdir(parents=True)
            (official / "attempt-count").write_text("0\n", encoding="utf-8")
            write_json(official / "validation.json", {"sentinel": "official-report-unchanged"})
            official_before = {
                path.name: sha256(path) for path in official.iterdir() if path.is_file()
            }
            validator_python = create_validator_environment(output)
            (output / "validator-python.txt").write_text(
                str(validator_python) + "\n", encoding="utf-8"
            )
            write_json(output / "run-manifest.json", {
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "controlCommit": run_git(CONTROL_REPO, "rev-parse", "HEAD"),
                "fixture": str(fixture), "fixtureCommit": commit,
                "model": args.model, "maxIterations": args.max_iterations,
                "prompt": PROMPT, "baselineFindingCount": len(baseline["targetFindings"]),
                "baselineSha256": baseline_sha_before,
                "expectedPoms": sorted(path.relative_to(target).as_posix()
                                       for path in target.rglob("pom.xml")),
                "officialStopHookBefore": official_before,
                "stopHookAttached": False,
            })
            write_json(output / "tracked-source-before.json", tracked_before)
            status["phase"] = "prepared"
        except BaseException as exc:
            status["phase"] = "failed"
            status["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        status["elapsedSeconds"] = round(time.monotonic() - started, 3)
        write_json(output / "status.json", status)
        print(f"PREPARATION_STATUS={status['phase']}")
        print(f"EVIDENCE_ROOT={output}")
        return 0 if status["phase"] == "prepared" else 1

    if not output.is_dir():
        raise SystemExit(f"Prepared output directory not found: {output}")
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    if status.get("phase") != "prepared":
        raise SystemExit(f"Run is not prepared: phase={status.get('phase')}")
    for name in ("VERTEXAI_PROJECT", "VERTEXAI_LOCATION"):
        if not os.environ.get(name):
            raise SystemExit(f"Missing required environment variable: {name}")
    manifest = json.loads((output / "run-manifest.json").read_text(encoding="utf-8"))
    tracked_before = json.loads((output / "tracked-source-before.json").read_text(encoding="utf-8"))
    baseline_sha_before = str(manifest["baselineSha256"])
    official_before = dict(manifest["officialStopHookBefore"])
    validator_python = (output / "validator-python.txt").read_text(encoding="utf-8").strip()
    if not Path(validator_python).is_file():
        raise SystemExit(f"Prepared validator interpreter disappeared: {validator_python}")
    status.update({"phase": "running", "model": args.model, "errors": []})
    write_json(output / "status.json", status)
    events: list[Any] = []
    conversation = None
    started = time.monotonic()
    try:
        baseline_path = output / "baseline.json"
        runner_module = runpy.run_path(
            str(CONTROL_REPO / "scripts/openhands/openhands-gate2-stop-hook-run.py"),
            run_name="validate_remediation_live_test_runner",
        )
        from openhands.sdk import Conversation, LLM

        llm = LLM(usage_id="validate-remediation-live-test", model=args.model, api_key=None)
        agent = runner_module["build_agent"](
            llm, engineering_guidance=False, task_skill=False, structured_guidance=False,
        )
        with ExitStack() as resources:
            registry_url, _requests = resources.enter_context(
                serve_maven_repository((Path.home() / ".m2/repository",))
            )
            agent = runner_module["configure_scanner_terminal"](
                agent,
                launcher_dir=launcher_dir,
                scanner_binary=scanner_path,
                registry_url=registry_url,
                validation_env={
                    "CONTROL_REPO": str(CONTROL_REPO),
                    "GATE2_TARGET_REPO": str(target),
                    "GATE2_STATE_FILE": str(baseline_path),
                    "GATE2_SCANNER_EXECUTABLE": str(scanner_path),
                    "GATE2_SELF_VALIDATION_ROOT": str(self_validation_root),
                    "GATE2_VALIDATOR_PYTHON": validator_python,
                },
            )
            conversation = Conversation(
                agent=agent, workspace=str(target),
                persistence_dir=conversation_dir, delete_on_close=False,
                max_iteration_per_run=args.max_iterations, stuck_detection=True,
            )
            conversation.send_message(PROMPT)
            conversation.run()
            status["conversationId"] = str(conversation.state.id)
            execution = conversation.state.execution_status
            status["executionStatus"] = getattr(execution, "value", str(execution))
            stats = getattr(conversation.state, "stats", None)
            status["modelUsage"] = sanitize(
                stats.model_dump(mode="json") if hasattr(stats, "model_dump") else None
            )
            events = list(conversation.state.events)
        status["phase"] = "completed"
    except BaseException as exc:
        status["phase"] = "failed"
        status["errors"].append({"type": type(exc).__name__, "message": str(exc)})
    finally:
        if conversation is not None:
            try:
                if not events:
                    events = list(conversation.state.events)
                    status["conversationId"] = str(conversation.state.id)
                stats = getattr(conversation.state, "stats", None)
                if status.get("modelUsage") is None and hasattr(stats, "model_dump"):
                    status["modelUsage"] = sanitize(stats.model_dump(mode="json"))
                conversation.close()
            except BaseException as exc:
                status["errors"].append({"type": type(exc).__name__, "message": str(exc)})
                status["phase"] = "failed"
        rows = serialize_events(events)
        with (output / "events.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        write_json(output / "final-assistant.json", {
            "content": final_assistant_message(rows),
            "present": final_assistant_message(rows) is not None,
        })
        if target.is_dir() and tracked_before and (output / "baseline.json").is_file():
            tracked_after = tracked_state(target)
            official_after = {
                path.name: sha256(path) for path in official.iterdir() if path.is_file()
            } if official.is_dir() else {}
            write_json(output / "isolation.json", {
                "trackedSourceUnchanged": tracked_after == tracked_before,
                "changedTrackedPaths": sorted(
                    path for path in set(tracked_before) | set(tracked_after)
                    if tracked_before.get(path) != tracked_after.get(path)
                ),
                "baselineUnchanged": sha256(output / "baseline.json") == baseline_sha_before,
                "officialStopHookUnchanged": official_after == official_before,
                "officialStopHookBefore": official_before,
                "officialStopHookAfter": official_after,
                "stopAttemptBefore": 0,
                "stopAttemptAfter": int((official / "attempt-count").read_text().strip()),
            })
        status["elapsedSeconds"] = round(time.monotonic() - started, 3)
        write_json(output / "status.json", status)
    print(f"LIVE_TEST_STATUS={status['phase']}")
    print(f"CONVERSATION_ID={status.get('conversationId')}")
    print(f"EXECUTION_STATUS={status.get('executionStatus')}")
    print(f"ELAPSED_SECONDS={status.get('elapsedSeconds')}")
    print(f"EVIDENCE_ROOT={output}")
    return 0 if status["phase"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
