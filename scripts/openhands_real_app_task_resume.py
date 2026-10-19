#!/usr/bin/env python3
"""Resume an existing, unstarted real-app task after deterministic preparation failure.

Does not register a task, replace a workspace, dispatch an agent, or push Git.
Only continues recorded baseline/intelligence stages for exactly one task.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from openhands_real_app_task_prepare import (
    ROOT, MODEL, PROFILE, BUILD, SCOPE, REPO_ID, git,
)
from autonomous_oss_remediation_agent.config import MavenConfig, ScannerConfig
from openhands_shared.baseline import BaselineProfile, BaselineConfig, DeterministicBaselineAssessor
from openhands_shared.intelligence import IntelligenceConfig, IntelligenceProfile, SharedIntelligenceAssessor
from openhands_shared.contracts import TaskStatus, BaselineAssessmentStatus
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore

BASE_COMMIT = "9ea1b0ed5ca255db0fc7c659d050896d3ed5db78"


def resume(run_root: Path, scanner: Path) -> dict:
    if run_root.is_symlink() or scanner.is_symlink():
        raise ValueError("Symbolic-link run root or scanner is not permitted")
    run_root = run_root.resolve(strict=True)
    scanner = scanner.resolve(strict=True)
    database = run_root / "state/tasks.sqlite3"
    if not database.is_file() or not scanner.is_file():
        raise ValueError("Existing database or scanner unavailable")
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT task_id FROM tasks").fetchall()
    if len(rows) != 1:
        raise ValueError("Expected exactly one existing durable task; no new task will be created")
    task_id = rows[0][0]
    artifacts = run_root / "artifacts"
    local_source = (run_root / "trusted-source").resolve(strict=True)
    with SQLiteTaskStore(database) as store:
        request = store.get_request(task_id)
        preparation = store.get_preparation(task_id)
        status = store.get_status(task_id)
        if (request.repository.url != REPO_ID or request.repository.base_ref != "refs/heads/main-runrunning"
                or request.repository.expected_commit != BASE_COMMIT
                or request.sbri_mode != "auto" or request.delivery_mode != "github_pr"):
            raise ValueError("Existing task contract differs from approved real application")
        if preparation is None or preparation.baseline_commit != BASE_COMMIT:
            raise ValueError("Existing immutable workspace preparation is incomplete")
        if store.get_openhands_runtime(task_id) is not None or store.get_execution_claim(task_id) is not None:
            raise ValueError("Task already has native state or execution claim; refuse resume")
        if status.status not in {TaskStatus.BASELINING, TaskStatus.INTELLIGENCE, TaskStatus.AGENT_RUNNING}:
            raise ValueError("Existing task is not in a resumable pre-execution state")
        workspace = Path(preparation.workspace_path).resolve(strict=True)
        if not workspace.is_relative_to(run_root / "workspaces"):
            raise ValueError("Workspace escapes registered task run root")
        if git("-C", str(workspace), "rev-parse", "HEAD") != BASE_COMMIT:
            raise ValueError("Prepared workspace commit mismatches approved baseline")
        if git("-C", str(workspace), "status", "--porcelain"):
            raise ValueError("Prepared worktree contains unexpected changes")
        if git("-C", str(local_source), "rev-parse", "HEAD") != BASE_COMMIT:
            raise ValueError("Trusted source commit differs from approved baseline")
        common_git = Path(git("-C", str(workspace), "rev-parse", "--git-common-dir"))
        if not common_git.is_absolute():
            common_git = workspace / common_git
        common_git = common_git.resolve(strict=True)
        trusted_git = Path(git("-C", str(local_source), "rev-parse", "--git-common-dir"))
        if not trusted_git.is_absolute():
            trusted_git = local_source / trusted_git
        if common_git != trusted_git.resolve(strict=True):
            raise ValueError("Worktree is not linked to isolated trusted source")
        exclude = common_git / "info" / "exclude"
        if not exclude.is_file() or exclude.is_symlink():
            raise ValueError("Git common exclude unavailable")
        if "target/" not in exclude.read_text(encoding="utf-8").splitlines():
            with exclude.open("a", encoding="utf-8") as out:
                out.write("\n# Generated Maven files in disposable worktrees\ntarget/\n")
        scanner_hash = hashlib.sha256(scanner.read_bytes()).hexdigest()
        profile = BaselineProfile(
            profile=PROFILE, build_commands=(BUILD,), maven=MavenConfig(mode="system"),
            scanner=ScannerConfig(backend="osv", mode="configured", executable=str(scanner),
                                  version="2.6.0", sha256=scanner_hash))
        baseline = DeterministicBaselineAssessor(
            store, BaselineConfig(artifact_root=artifacts, profiles=(profile,))).assess(task_id)
        if baseline.assessment_status is not BaselineAssessmentStatus.COMPLETED:
            raise ValueError("Durable baseline did not complete; preserve evidence")
        intel = SharedIntelligenceAssessor(
            store, IntelligenceConfig(artifact_root=artifacts, profiles=(
                IntelligenceProfile(profile_id="real-app-sbri-v1",
                    task_agent_profile=PROFILE, control_repo=ROOT, scanner=scanner,
                    max_candidates=3),
            ))).assess(task_id)
        if intel.outcome.value not in {"COMPLETE", "PARTIAL"}:
            raise ValueError("Durable SBRI assessment is incomplete")
        if store.get_status(task_id).status is not TaskStatus.AGENT_RUNNING:
            raise ValueError("Task did not reach prepared idle lifecycle stage")
        config_path = run_root / "stop-hook.json"
        if config_path.exists():
            raise ValueError("Stop Hook configuration already exists; inspect instead of overwrite")
        config_path.write_text(json.dumps({
            "database": str(database.resolve()), "artifactRoot": str(artifacts.resolve()),
            "profiles": [{"profileId": PROFILE, "buildCommands": [BUILD],
                          "maven": {"mode": "system"}, "scanner": profile.scanner.to_dict()}],
        }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        config_path.chmod(0o600)
        cfg_db, config = load_stop_hook_config(config_path)
        if cfg_db != database.resolve():
            raise ValueError("Stop Hook DB identity mismatch")
        config.profile_for(request)
        return {"status": "DURABLE_TASK_PREPARED_NOT_AUTHORIZED", "taskId": task_id,
                "workspace": str(workspace), "database": str(database),
                "validationConfig": str(config_path),
                "baselineFindingCount": baseline.finding_count,
                "intelligenceOutcome": intel.outcome.value,
                "nativeConversationCreated": False, "nativeRunCalled": False,
                "modelExecutionAuthorized": False, "noPR": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--scanner", required=True, type=Path)
    a = parser.parse_args()
    try:
        result = resume(a.run_root, a.scanner)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:220], "nativeRunCalled": False,
                  "doNotRetryWithoutInspection": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "DURABLE_TASK_PREPARED_NOT_AUTHORIZED" else 1

if __name__ == "__main__":
    sys.exit(main())
