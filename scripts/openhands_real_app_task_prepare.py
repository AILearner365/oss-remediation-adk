#!/usr/bin/env python3
"""Real multi-module Maven/OSV durable preparation; no OpenHands API or LLM.

The source is the verified real multi-module Maven application repository. Git mirroring
is confined to a fresh run root; source repository and remote GitHub untouched.
No model calls, no native conversation creation, no dispatch, no PR delivery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonomous_oss_remediation_agent.config import MavenConfig, ScannerConfig
from openhands_shared.baseline import BaselineProfile, BaselineConfig, DeterministicBaselineAssessor
from openhands_shared.contracts import TaskRequest, TaskStatus, BaselineAssessmentStatus
from openhands_shared.intelligence import IntelligenceConfig, IntelligenceProfile, SharedIntelligenceAssessor
from openhands_shared.preparation import PreparationConfig, TrustedRepository, DeterministicPreparer
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.validation import ValidationConfig

MODEL = "vertex_ai/gemini-2.5-flash"
PROFILE = "gate2-dependency-remediation-v1"
ADVISORY = None
REPO_ID = "https://github.com/AILearner365/maven-multimodule-app.git"
BUILD = "mvn -B -ntp clean verify"
SCOPE = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
# Fixed candidate is deliberately absent from all task/objective inputs.

def git(*args: str) -> str:
    return subprocess.run(["git", *args], text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=90, check=True).stdout.strip()

def prepare(source: Path, scanner: Path, run_root: Path) -> dict:
    if source.is_symlink() or scanner.is_symlink() or run_root.is_symlink():
        raise ValueError("Symlinked source, scanner or run root is not permitted")
    try:
        source, scanner = source.resolve(strict=True), scanner.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise ValueError("Required source repository or scanner does not exist") from exc
    if run_root.exists():
        raise ValueError("Run root already exists: refuse replacement or replay")
    if not source.is_dir() or not scanner.is_file():
        raise ValueError("Controlled source or scanner unavailable")
    head = git("-C", str(source), "rev-parse", "HEAD")
    if (source / "pom.xml").read_bytes() != subprocess.run(
        ["git", "-C", str(source), "show", head + ":pom.xml"],
        capture_output=True, check=True, timeout=30).stdout:
        raise ValueError("Source POM differs from exact original Git commit")
    expected_head = "9ea1b0ed5ca255db0fc7c659d050896d3ed5db78"
    if head != expected_head:
        raise ValueError("Real-app source differs from approved main-runrunning baseline")
    if git("-C", str(source), "remote", "get-url", "origin") != REPO_ID:
        raise ValueError("Source origin is not the approved real Maven repository")
    remote_head = git("ls-remote", "--exit-code", REPO_ID, "refs/heads/main-runrunning").split()[0]
    if remote_head != expected_head:
        raise ValueError("Remote reference moved; refuse unreviewed execution")
    if git("-C", str(source), "status", "--porcelain"):
        raise ValueError("Real-app source has tracked/untracked modifications")
    scanner_hash = hashlib.sha256(scanner.read_bytes()).hexdigest()
    run_root.mkdir(parents=True, mode=0o700)
    remote = run_root / "local-remote.git"
    local_source = run_root / "trusted-source"
    # Avoid connecting to the source's configured remotes or pushing anywhere.
    git("clone", "--bare", "--local", "--no-hardlinks", str(source), str(remote))
    git("clone", "--quiet", "--no-local", str(remote), str(local_source))
    if git("-C", str(local_source), "rev-parse", "HEAD") != head:
        raise ValueError("Local isolated source does not match the approved baseline")
    # Maven creates target/ during the deterministic build. Exclude ONLY
    # generated target directories in this freshly cloned local Git repository;
    # never alter the committed fixture or relax tracked-file cleanliness.
    exclude = local_source / ".git" / "info" / "exclude"
    if not exclude.is_file():
        raise ValueError("Local clone Git exclude file is missing")
    existing_excludes = exclude.read_text(encoding="utf-8")
    exclude.write_text(existing_excludes + "\n# Isolated Maven build products\ntarget/\n",
                       encoding="utf-8")
    database = run_root / "state" / "tasks.sqlite3"
    artifacts = run_root / "artifacts"
    build_profile = BaselineProfile(
        profile=PROFILE, build_commands=(BUILD,), maven=MavenConfig(mode="system"),
        scanner=ScannerConfig(backend="osv", mode="configured", executable=str(scanner),
                              version="2.6.0", sha256=scanner_hash))
    request = TaskRequest.from_dict({
        "contractVersion": "1", "idempotencyKey": "real-multimodule-" + uuid4().hex,
        "repository": {"url": REPO_ID, "baseRef": "refs/heads/main-runrunning",
                       "expectedCommit": head},
        "objective": ("Investigate and remediate all actionable Maven vulnerabilities in the real "
                      "multi-module application. Independently assess strategies, "
                      "preserve passing build and compatibility, and verify security resolution."),
        "constraints": {"javaVersionUnchanged": True,
                        "springBoot": {"allowPatch": True, "allowMinor": True,
                                       "allowMajor": False, "allowDowngrade": False},
                        "prohibitSuppressions": True,
                        "prohibitedNewSeverities": ["CRITICAL", "HIGH"]},
        "acceptance": {"buildCommands": [BUILD], "severityScope": list(SCOPE)},
        "agent": {"profile": PROFILE, "modelProfile": "vertex-gemini-2-5-flash",
                  "maxIterations": 12, "maxValidationDenials": 2},
        "intelligence": {"sbri": {"mode": "auto"}},
        "delivery": {"mode": "github_pr"}, "metadata": {"source": "experiment-client"},
    })
    with SQLiteTaskStore(database) as store:
        task_id = store.register_task(request).status.task_id
        trusted = TrustedRepository(repository_url=REPO_ID, source_path=local_source,
                                    origin_url=str(remote))
        prep = DeterministicPreparer(
            store, PreparationConfig(workspace_root=run_root / "workspaces",
                                     repositories=(trusted,))).prepare(task_id)
        workspace_exclude = Path(prep.workspace_path) / ".git" / "info" / "exclude"
        if not workspace_exclude.is_file():
            raise ValueError("Prepared task workspace lacks local Git exclude")
        workspace_exclude.write_text(
            workspace_exclude.read_text(encoding="utf-8") +
            "\n# Generated Maven outputs in disposable task workspace\ntarget/\n",
            encoding="utf-8",
        )
        baseline = DeterministicBaselineAssessor(
            store, BaselineConfig(artifact_root=artifacts, profiles=(build_profile,))).assess(task_id)
        if baseline.assessment_status is not BaselineAssessmentStatus.COMPLETED:
            raise ValueError("Durable real baseline did not complete with findings")
        intel = SharedIntelligenceAssessor(
            store, IntelligenceConfig(artifact_root=artifacts, profiles=(IntelligenceProfile(
                profile_id="real-app-sbri-v1", task_agent_profile=PROFILE,
                control_repo=ROOT, scanner=scanner, max_candidates=3),))).assess(task_id)
        if intel.outcome.value not in {"COMPLETE", "PARTIAL"}:
            raise ValueError("SBRI collector did not complete; inspect durable artifacts")
        if store.get_status(task_id).status is not TaskStatus.AGENT_RUNNING:
            raise ValueError("Task did not reach durable AGENT_RUNNING idle stage")
        stop_config = run_root / "stop-hook.json"
        stop_config.write_text(json.dumps({
            "database": str(database.resolve()), "artifactRoot": str(artifacts.resolve()),
            "profiles": [{"profileId": PROFILE, "buildCommands": [BUILD],
                          "maven": {"mode": "system"},
                          "scanner": build_profile.scanner.to_dict()}],
        }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        stop_config.chmod(0o600)
        db, config = load_stop_hook_config(stop_config)
        if db != database.resolve() or not isinstance(config, ValidationConfig):
            raise ValueError("Real Stop Hook config failed verification")
        config.profile_for(store.get_request(task_id))
        if store.get_openhands_runtime(task_id) is not None or store.get_execution_claim(task_id) is not None:
            raise ValueError("Preparation unexpectedly created a native runtime or execution claim")
        return {
            "kind": "durable-real-maven-osv-task-preparation",
            "status": "DURABLE_TASK_PREPARED_NOT_AUTHORIZED",
            "taskId": task_id, "database": str(database),
            "workspace": prep.workspace_path, "baselineCommit": baseline.baseline_commit,
            "baselineFindingCount": baseline.finding_count,
            "baselineAssessment": baseline.assessment_status.value,
            "intelligenceOutcome": intel.outcome.value,
            "validationConfig": str(stop_config),
            "model": MODEL, "nativeConversationCreated": False,
            "nativeRunCalled": False, "modelExecutionAuthorized": False,
            "nextGates": ["Inspect authoritative multi-module baseline findings and SBRI evidence",
                          "Create/verify 1.55.1 native conversation with real task and persisted hook",
                          "Verify native server Vertex extra and enforced cost bounds",
                          "Obtain explicit separate authorization for model execution"],
        }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=Path.home() / "openhands-real-app-poc/checkout-1")
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        outcome = prepare(args.source, args.scanner, args.run_root)
    except Exception as exc:
        outcome = {"kind": "durable-real-maven-osv-task-preparation",
                   "status": "BLOCKED", "errorType": type(exc).__name__,
                   "errorDetail": str(exc)[:300],
                   "nativeRunCalled": False, "modelExecutionAuthorized": False}
    print(json.dumps(outcome, sort_keys=True, indent=2))
    return 0 if outcome["status"] == "DURABLE_TASK_PREPARED_NOT_AUTHORIZED" else 1

if __name__ == "__main__":
    sys.exit(main())
