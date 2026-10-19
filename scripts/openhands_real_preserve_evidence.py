#!/usr/bin/env python3
"""Preserve verified remediation evidence without running the agent or validator.

Archive excludes credentials, raw environment, unrestricted tool transcripts,
and backend session state. A SQLite consistent backup stays local, private,
and is NOT part of the shareable evidence bundle.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from openhands_real_run_audit import TASK, HOOK, audit
from openhands_shared.stop_hook import load_stop_hook_config
from openhands_shared.store import SQLiteTaskStore


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def preserve(task_id: str, hook: Path, destination: Path, *, check_native: bool = True) -> dict:
    # Fail before making copies if task/result identity is not verified.
    summary = audit(task_id, hook, check_native=check_native)
    db, config = load_stop_hook_config(hook.resolve(strict=True))
    dest = destination.expanduser().resolve()
    if dest.exists() or dest.is_symlink():
        raise ValueError("Destination exists; never overwrite preservation evidence")
    if dest == Path.home() or dest == Path("/"):
        raise ValueError("Unsafe archive destination")
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.mkdir(dest, 0o700)
    try:
        share = dest / "shareable"
        private = dest / "private"
        share.mkdir(mode=0o700)
        private.mkdir(mode=0o700)
        source_report = Path(summary["validationReportPath"])
        copied = share / "validation-report.json"
        shutil.copyfile(source_report, copied)
        if digest(copied) != summary["validationReportSha256"]:
            raise ValueError("Validation report checksum changed while copying")
        # Durable task metadata is useful for forensics, but SQLite may contain
        # raw event payloads; retain it ONLY under the private directory.
        backup = private / "tasks.sqlite3"
        src = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(backup)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        os.chmod(backup, 0o600)
        with SQLiteTaskStore(db) as store:
            prep = store.get_preparation(task_id)
            if prep is None:
                raise ValueError("Workspace preparation disappeared")
            workspace = Path(prep.workspace_path)
            changes = subprocess.run(["git", "diff", "--binary", "HEAD", "--"], cwd=workspace,
                                     check=True, capture_output=True, timeout=30).stdout
            patch = private / "working-tree.patch"
            patch.write_bytes(changes)
            os.chmod(patch, 0o600)
            # Immutable original baseline report is separately checksum-verified.
            baseline = store.get_baseline(task_id)
            artifacts = {a.artifact_id: a for a in store.list_artifacts(task_id)}
            original = artifacts[baseline.report_artifact_id]
            original_path = config.artifact_root / original.relative_path
            if original_path.is_symlink() or digest(original_path) != original.sha256:
                raise ValueError("Inherited baseline report checksum mismatch")
            shutil.copyfile(original_path, share / "baseline-report.json")
            manifest = {
                "status": "EVIDENCE_PRESERVED",
                "audit": summary,
                "sourceTaskId": store.get_request(task_id).correlation_id,
                "files": {
                    "shareable/validation-report.json": digest(copied),
                    "shareable/baseline-report.json": digest(share / "baseline-report.json"),
                    "private/tasks.sqlite3": digest(backup),
                    "private/working-tree.patch": digest(patch),
                },
                "warning": "Private SQLite and patch may contain sensitive content. Do not publish them.",
                "nativeEventTranscriptArchived": False,
            }
        (share / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return {"status": "EVIDENCE_PRESERVED", "directory": str(dest),
                "manifest": str(share / "manifest.json"),
                "privateDatabaseBackup": str(backup),
                "nativeEventTranscriptArchived": False,
                "noModelRun": True}
    except BaseException:
        # Do not silently remove partial forensic evidence.
        raise


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task-id", default=TASK)
    p.add_argument("--hook-config", type=Path, default=HOOK)
    p.add_argument("--destination", type=Path,
                   default=Path.home() / "openhands-native-poc-reports" / ("accepted-evidence-" + TASK))
    p.add_argument("--skip-native-check", action="store_true")
    args = p.parse_args()
    try:
        result = preserve(args.task_id, args.hook_config, args.destination,
                          check_native=not args.skip_native_check)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:220], "doNotRetryWithoutInspection": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "EVIDENCE_PRESERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
