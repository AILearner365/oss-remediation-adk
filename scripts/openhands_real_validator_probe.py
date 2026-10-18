#!/usr/bin/env python3
"""Run the REAL shared independent validator on a disposable unmodified baseline.

Never invoke the native Stop Hook or claim execution against a live idle task.
Never POST /run, contact an LLM, or mutate the durable task/conversation.
An unchanged vulnerable baseline MUST NOT be validated as a success.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openhands_shared.store import SQLiteTaskStore
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.validation import (
    ExistingDeterministicValidationRunner, _validated_report, _validation_outcome
)
from openhands_shared.contracts import ExecutionStatus, TaskStatus, ValidationOutcome

ADVISORY = "GHSA-mjmj-j48q-9wg2"
COMMIT = "f44f94c2b2ec553fc3276e36e6a99a0dcc4cd13a"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], text=True, capture_output=True,
                          check=True, timeout=90).stdout.strip()


def probe(db: Path, task_id: str, config_path: Path) -> dict:
    with SQLiteTaskStore(db) as store:
        req = store.get_request(task_id)
        prep = store.get_preparation(task_id)
        base = store.get_baseline(task_id)
        status = store.get_status(task_id)
        runtime = store.get_openhands_runtime(task_id)
        if (prep is None or base is None or runtime is None
                or req.repository.expected_commit != COMMIT
                or prep.baseline_commit != COMMIT
                or base.baseline_commit != COMMIT or base.finding_count != 1):
            raise ValueError("Not the approved controlled, one-finding baseline task")
        if (status.status is not TaskStatus.AGENT_RUNNING
                or status.execution_status is not ExecutionStatus.NOT_STARTED
                or status.accepted
                or store.get_execution_claim(task_id) is not None
                or store.list_validation_attempts(task_id)):
            raise ValueError("Task must remain unstarted with no prior validation attempts")
        database, cfg = load_stop_hook_config(config_path.resolve(strict=True))
        if database != store.database_path.resolve():
            raise ValueError("Validator config not bound to task database")
        profile = cfg.profile_for(req)
        artifacts = {a.artifact_id: a for a in store.list_artifacts(task_id)}
        artifact = artifacts[base.report_artifact_id]
        report_bytes = (cfg.artifact_root / artifact.relative_path).read_bytes()
        digest = hashlib.sha256(report_bytes).hexdigest()
        if digest != artifact.sha256 or digest != base.report_sha256:
            raise ValueError("Baseline report checksum mismatch")
        report = json.loads(report_bytes)
        found = report["originalVulnerabilityFindings"]
        if len(found) != 1 or ADVISORY not in {
                found[0].get("vulnerabilityId"), *found[0].get("aliases", [])}:
            raise ValueError("Immutable baseline does not record expected advisory")
        repo = Path(prep.workspace_path).resolve(strict=True)
        if _git("-C", str(repo), "rev-parse", "HEAD") != COMMIT:
            raise ValueError("Live prepared workspace moved from baseline")
        if _git("-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("Live prepared workspace is dirty; no probe permitted")
        # Use a separate independent copy so real Maven/OSV cannot modify the
        # live task workspace. Never substitute a known fixed candidate.
        with TemporaryDirectory(prefix="openhands-real-validator-", dir="/tmp") as td:
            root = Path(td)
            cloned = root / "checkout"
            subprocess.run(["git", "clone", "--quiet", "--local", "--no-hardlinks",
                            "--no-checkout", str(repo), str(cloned)],
                           check=True, capture_output=True, timeout=90)
            _git("-C", str(cloned), "checkout", "--quiet", "--detach", COMMIT)
            if _git("-C", str(cloned), "rev-parse", "HEAD") != COMMIT:
                raise ValueError("Disposable checkout commit mismatch")
            # Maven output is untracked build evidence, not an attempted edit.
            exclude = cloned / ".git" / "info" / "exclude"
            exclude.write_text(exclude.read_text() + "\n# disposable Maven outputs\ntarget/\n")
            raw = ExistingDeterministicValidationRunner().run(
                cloned, req, profile, report, 1, root / "validator-runtime"
            )
            checked = _validated_report(raw)
            outcome = _validation_outcome(checked)
            scan = checked.get("scan") or {}
            checks = {str(c["name"]): bool(c["passed"]) for c in checked["checks"]}
            remaining = checked["remainingTargetFindings"]
            success = (
                checked["passed"] is False
                and scan.get("succeeded") is True
                and len(remaining) >= 1
                and outcome is not ValidationOutcome.PASS
            )
            return {
                "kind": "real-shared-independent-validator-probe",
                "status": "PASS_UNREMEDIATED_BASELINE_REJECTED" if success else "NOT_PROVEN",
                "validatorOutcome": outcome.value,
                "validatorPassed": checked["passed"],
                "realScannerSucceeded": scan.get("succeeded") is True,
                "remainingTargetFindings": len(remaining),
                "resolvedTargetFindings": len(checked["resolvedTargetFindings"]),
                "checks": checks,
                "liveTaskUntouched": True,
                "nativeStopHookInvoked": False,
                "nativeRunCalled": False,
                "modelExecutionAuthorized": False,
                "notProven": [
                    "Native Stop Hook invocation and durable stop-event association",
                    "Native Vertex provider within currently running server",
                    "Cost-bounded autonomous /run",
                ],
            }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True, type=Path)
    p.add_argument("--task-id", required=True)
    p.add_argument("--hook-config", required=True, type=Path)
    args = p.parse_args()
    try:
        result = probe(args.database, args.task_id, args.hook_config)
    except Exception as exc:
        result = {
            "kind": "real-shared-independent-validator-probe",
            "status": "BLOCKED", "errorType": type(exc).__name__,
            "errorDetail": str(exc)[:260],
            "nativeStopHookInvoked": False, "nativeRunCalled": False,
            "modelExecutionAuthorized": False,
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] == "PASS_UNREMEDIATED_BASELINE_REJECTED" else 1


if __name__ == "__main__":
    sys.exit(main())
