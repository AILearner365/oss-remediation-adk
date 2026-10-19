#!/usr/bin/env python3
"""Create one new idle task from immutable verified baseline evidence; no model/Maven/OSV.

Keeps the failed task, claim, conversation and evidence unchanged. Reuses their
content-addressed baseline/intelligence artifacts in the SAME durable store.
Never retries the old /run. Native attachment is a separate explicit step.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openhands_shared.contracts import (
    BaselineAssessmentStatus, IntelligenceOutcome, TaskRequest, utc_now,
)
from openhands_shared.store import SQLiteTaskStore
from openhands_real_native_idle import verify_stored

ORIGINAL = "task_93531f4571724ab183e2e2defea6def8"
DATABASE = Path("/tmp/openhands-real-durable-task-recovered-v1/state/tasks.sqlite3")
HOOK = Path("/tmp/openhands-real-durable-task-recovered-v1/stop-hook.json")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, text=True,
                          capture_output=True, timeout=60).stdout.strip()


def prepare_recovery(store: SQLiteTaskStore, original: str, hook: Path) -> dict:
    # The original attempt is dispatched, so the idle-task guard used for the\n    # NEW task must not be applied to it. Verify its immutable evidence here.\n    runtime = store.get_openhands_runtime(original)
    claim = store.get_execution_claim(original)
    if runtime is None or claim is None or claim.conversation_id != runtime.conversation_id:
        raise ValueError("Original task is not the dispatched, identified attempt")
    if claim.dispatch_status.value != "DISPATCHED":
        raise ValueError("Original dispatch claim is not DISPATCHED")
    if store.get_status(original).accepted:
        raise ValueError("Original task is already accepted")
    old = store.get_request(original)
    prep = store.get_preparation(original)
    baseline = store.get_baseline(original)
    intel = store.get_intelligence(original)
    if (prep is None or baseline is None or intel is None
            or baseline.baseline_commit != "f44f94c2b2ec553fc3276e36e6a99a0dcc4cd13a"
            or prep.baseline_commit != baseline.baseline_commit
            or old.repository.expected_commit != baseline.baseline_commit
            or baseline.finding_count != 1
            or baseline.assessment_status is not BaselineAssessmentStatus.COMPLETED
            or intel.outcome is not IntelligenceOutcome.DISABLED):
        raise ValueError("Only the exact verified completed baseline with disabled intelligence can be inherited")
    base = Path(hook).resolve(strict=True).parent
    artifacts = store.list_artifacts(original)
    config = json.loads(hook.read_text(encoding="utf-8"))
    artifact_root = Path(config["artifactRoot"]).resolve(strict=True)
    for artifact in artifacts:
        path = artifact_root / artifact.relative_path
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(artifact_root):
            raise ValueError("Original evidence artifact missing or unsafe")
        body = path.read_bytes()
        if len(body) != artifact.size_bytes or hashlib.sha256(body).hexdigest() != artifact.sha256:
            raise ValueError("Original evidence artifact checksum differs")
    report_artifact = next((a for a in artifacts if a.artifact_id == baseline.report_artifact_id), None)
    if report_artifact is None or report_artifact.sha256 != baseline.report_sha256:
        raise ValueError("Original baseline report metadata mismatch")
    report = json.loads((artifact_root / report_artifact.relative_path).read_text(encoding="utf-8"))
    findings = report.get("originalVulnerabilityFindings", [])
    if len(findings) != 1 or "GHSA-mjmj-j48q-9wg2" not in {
        findings[0].get("vulnerabilityId"), *findings[0].get("aliases", [])
    }:
        raise ValueError("Original baseline target advisory is not verified")
    source = Path(prep.source_path).resolve(strict=True)
    if git("-C", str(source), "rev-parse", "HEAD") != baseline.baseline_commit:
        raise ValueError("Trusted isolated source commit changed")
    if git("-C", str(source), "status", "--porcelain"):
        raise ValueError("Trusted isolated source worktree is not clean")
    new_contract = old.to_dict()
    new_contract["idempotencyKey"] = "recovery-" + uuid4().hex
    # correlationId is the immutable provenance link to the previous attempt.
    new_contract["metadata"]["correlationId"] = original
    new_task = TaskRequest.from_dict(new_contract)
    registered = store.register_task(new_task)
    if not registered.created:
        raise ValueError("Recovery registration unexpectedly reused a task")
    new_id = registered.status.task_id
    workspace = base / "workspaces" / new_id / "repository"
    if workspace.exists():
        raise ValueError("Recovery workspace collision")
    workspace.parent.mkdir(parents=True, exist_ok=False)
    git("clone", "--quiet", "--no-local", str(source), str(workspace))
    if git("-C", str(workspace), "rev-parse", "HEAD") != baseline.baseline_commit:
        raise ValueError("Cloned baseline differs")
    branch = "recovery-" + new_id
    git("-C", str(workspace), "checkout", "-q", "-b", branch)
    excludes = workspace / ".git" / "info" / "exclude"
    excludes.write_text(excludes.read_text(encoding="utf-8") + "\n# Maven generated files\ntarget/\n", encoding="utf-8")
    from openhands_shared.contracts import TaskStatus
    store.start_preparation(new_id)
    store.complete_preparation(replace(
        prep, task_id=new_id, workspace_path=str(workspace.resolve()),
        local_branch=branch, prepared_at=utc_now(),
    ))
    # Evidence bytes are intentionally inherited unchanged. The source report
    # identifies the original task, and correlationId preserves that provenance.
    # No claim that Maven/OSV reran for the new task is made.
    inherited = tuple(replace(a, task_id=new_id) for a in artifacts)
    baseline_ids = {baseline.report_artifact_id}
    # Baseline artifacts precede intelligence artifacts; classify by kinds using
    # original stage artifact IDs in the immutable records.
    intelligence_ids = {intel.record_artifact_id, intel.summary_artifact_id}
    baseline_artifacts = tuple(a for a in inherited if a.artifact_id not in intelligence_ids)
    intelligence_artifacts = tuple(a for a in inherited if a.artifact_id in intelligence_ids)
    if not any(a.artifact_id in baseline_ids for a in baseline_artifacts) or len(intelligence_artifacts) != 2:
        raise ValueError("Inherited baseline/intelligence evidence inventory inconsistent")
    store.complete_baseline(replace(baseline, task_id=new_id), baseline_artifacts)
    store.complete_intelligence(replace(intel, task_id=new_id), intelligence_artifacts)
    verify_stored(store, new_id, hook)
    if store.get_execution_claim(new_id) is not None or store.get_openhands_runtime(new_id) is not None:
        raise ValueError("Recovery unexpectedly has execution claim or native conversation")
    return {
        "status": "RECOVERY_IDLE_TASK_PREPARED_NOT_AUTHORIZED",
        "sourceTaskId": original, "taskId": new_id,
        "database": str(store.database_path), "hookConfig": str(hook),
        "workspace": str(workspace), "baselineEvidenceReused": True,
        "baselineReexecuted": False, "nativeRunCalled": False,
        "modelExecutionAuthorized": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, default=DATABASE)
    p.add_argument("--original-task", default=ORIGINAL)
    p.add_argument("--hook-config", type=Path, default=HOOK)
    args = p.parse_args()
    try:
        with SQLiteTaskStore(args.database) as store:
            result = prepare_recovery(store, args.original_task, args.hook_config)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:240], "doNotRetryWithoutInspection": True,
                  "nativeRunCalled": False, "modelExecutionAuthorized": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "RECOVERY_IDLE_TASK_PREPARED_NOT_AUTHORIZED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
