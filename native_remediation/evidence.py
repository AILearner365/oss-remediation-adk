"""Factual phase snapshots indexing native persistence, not a second event log.

Raw SDK events remain private. No automatic publication or chain-of-thought export.
"""
import hashlib
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import shutil
import sys
import uuid

from .contract import context
from .files import digest, read, write
from .repository import git, snapshot, changed_paths


def environment(task):
    packages = {}
    for name in ("openhands-sdk", "openhands-tools"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "UNAVAILABLE"
    return dict(python=sys.executable, packages=packages,
        executables={k: shutil.which(task["tools"][k]) for k in ("maven", "osv")},
        sbri=shutil.which(task["sbri"]["executable"] or task["tools"]["sbri_reference"] or "sbri"),
        proxyVariablesPresent=[k for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy") if os.environ.get(k)],
        vertexConfiguration=dict(project=os.environ.get("VERTEXAI_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
                                 location=os.environ.get("VERTEXAI_LOCATION")),
        model=task["model"], modelRetries=0, terminal="native-subprocess-host", retention="PRIVATE_TASK_STATE")


def capture(state, stage, conversation=None):
    state, bound, task = context(state)
    native = state / "conversations" / uuid.UUID(bound["conversationId"]).hex
    rows = [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted((native / "events").glob("event-*.json"))]
    result = dict(stage=stage, conversationId=bound["conversationId"], taskDigest=bound["taskDigest"],
        approvedBase=task["base_sha"], nativePersistence=str(native.relative_to(state)),
        eventCount=len(rows), eventManifestDigest=digest(rows), environment=environment(task),
        references={name: name for name in ("task.json", "baseline.json", "preparation.json", "journal",
            "attempts", "self-validation", "sbri", "sbri-pre-edit.json", "guidance.json", "runs", "feedback.json",
            "result.json", "delivery.json") if (state / name).exists()})
    if conversation:
        result["nativeStatus"] = conversation.state.execution_status.value
        result["modelUsage"] = conversation.state.stats.model_dump(mode="json")
    workspace = state / "workspace"
    if (workspace / ".git").exists():
        try:
            tree = snapshot(workspace, task)
            result.update(candidateTree=tree, changedFiles=changed_paths(workspace, task, tree),
                gitStatus=git(workspace, "status", "--porcelain").decode(),
                gitDiff=git(workspace, "diff", "--binary", task["base_sha"], tree).decode())
        except Exception as exc:
            result["candidateCapture"] = "INCOMPLETE: " + type(exc).__name__
    path = state / "evidence" / (stage + "-" + uuid.uuid4().hex + ".json")
    write(path, result, exclusive=True)
    write(state / "evidence/latest.json", dict(path=str(path.relative_to(state)), digest=digest(result)))
    return result
