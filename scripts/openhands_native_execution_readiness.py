#!/usr/bin/env python3
"""Read-only audit of the running OpenHands 1.55.1 Vertex and run boundaries.

No runtime restart, package installation, ADC refresh, model inference,
conversation creation, task mutation, or /run. A check of installed packages
is NOT evidence that actual paid Vertex inference works.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import openhands_native_poc as native
import openhands_native_remediation as handoff
from openhands_shared.store import SQLiteTaskStore
from openhands_shared.contracts import ExecutionStatus, OpenHandsRuntimeStatus, TaskStatus

MODEL = "vertex_ai/gemini-2.5-flash"
SERVER = "1.55.1"
DEPENDENCIES = ("openhands-sdk", "openhands-agent-server", "litellm", "google-auth",
                "google-cloud-aiplatform")


def package_versions_from_site_packages(site: Path) -> dict[str, str | None]:
    """Read wheel metadata; do not import a model provider or refresh credentials."""
    result: dict[str, str | None] = {}
    if not site.is_dir():
        return {name: None for name in DEPENDENCIES}
    for name in DEPENDENCIES:
        prefix = name.replace("-", "_") + "-"
        paths = list(site.glob(prefix + "*.dist-info/METADATA"))
        versions = []
        for path in paths:
            try:
                for line in path.read_text(encoding="utf-8").splitlines()[:60]:
                    if line.startswith("Version: "):
                        versions.append(line.split(": ", 1)[1].strip())
                        break
            except (OSError, UnicodeError):
                pass
        result[name] = versions[0] if len(versions) == 1 else None
    return result


def find_running_server_site_packages(proc_root: Path = Path("/proc")) -> tuple[Path | None, str]:
    """Identify a single uvx-installed agent-server process via its launch argv.

    A base Python /proc/PID/exe symlink is NOT sufficient to identify the uv
    virtualenv; require a venv path in process argv or an agent-server script
    located in venv/bin. Never expose argv, which can contain secrets.
    """
    matches: list[Path] = []
    try:
        process_dirs = list(proc_root.iterdir())
    except OSError:
        return None, "PROCESS_LIST_UNAVAILABLE"
    for process in process_dirs:
        if not process.name.isdecimal():
            continue
        try:
            raw = (process / "cmdline").read_bytes()
            argv = [os.fsdecode(x) for x in raw.split(b"\0") if x]
        except (OSError, UnicodeError):
            continue
        if not argv or not any("agent-server" in Path(x).name for x in argv[:3]):
            continue
        for arg in argv[:3]:
            path = Path(arg)
            if not path.is_absolute() or not path.is_file():
                continue
            if path.name != "agent-server" and not (path.name.startswith("python") and path.parent.name == "bin"):
                continue
            venv = path.parent.parent
            if not (venv / "pyvenv.cfg").is_file():
                continue
            py = venv / "lib"
            choices = list(py.glob("python*/site-packages"))
            if len(choices) == 1:
                matches.append(choices[0].resolve())
    unique = set(matches)
    if len(unique) == 1:
        return next(iter(unique)), "PROCESS_PACKAGE_PATH_FOUND"
    return None, "AMBIGUOUS_PROCESS_ENVIRONMENT" if unique else "PROCESS_ENVIRONMENT_NOT_IDENTIFIED"


def inspect_task(store: SQLiteTaskStore, task_id: str, hook_path: Path) -> dict:
    status = store.get_status(task_id)
    runtime = store.get_openhands_runtime(task_id)
    if runtime is None:
        raise ValueError("Live native conversation association is missing")
    if status.status is not TaskStatus.AGENT_RUNNING or status.accepted:
        raise ValueError("Task is not in unaccepted agent stage")
    if (status.execution_status is not ExecutionStatus.NOT_STARTED
            or runtime.runtime_status is not OpenHandsRuntimeStatus.CONTEXT_ATTACHED
            or store.get_execution_claim(task_id) is not None):
        raise ValueError("Task is not confirmed idle and unclaimed")
    request = store.get_request(task_id)
    if runtime.native_model != MODEL or request.agent.model_profile != "vertex-gemini-2-5-flash":
        raise ValueError("Task runtime model differs from approved Vertex model profile")
    native_req = handoff.build_request(
        store, task_id, hook_config=hook_path, model=MODEL,
        max_iterations=min(request.agent.max_iterations, 12),
    )
    return {"conversationId": runtime.conversation_id,
            "taskId": task_id,
            "model": MODEL,
            "iterationCapConfigured": native_req["max_iterations"],
            "validationDenialsConfigured": request.agent.max_validation_denials,
            "hardTokenCapEnforced": False,
            "hardDollarCapEnforced": False,
            "wallClockCapEnforced": False,
            "stopHookConfigured": bool(native_req["hook_config"]["stop"]),
            "taskUnstarted": True}


def audit(db: Path, task_id: str, hook: Path) -> dict:
    with SQLiteTaskStore(db) as store:
        task = inspect_task(store, task_id, hook)
    native.configure_server_version(SERVER)
    info = native.http("GET", "/server_info")
    if not all(info.get(field) == SERVER for field in ("version", "sdk_version", "tools_version")):
        raise ValueError("Native server version differs from pinned OpenHands 1.55.1")
    persisted = native.http("GET", f'/api/conversations/{task["conversationId"]}?include_skills=true')
    # validate against the immutable task handoff rather than relying on an
    # earlier operator screenshot or server_info alone.
    with SQLiteTaskStore(db) as store:
        request = handoff.build_request(
            store, task_id, hook_config=hook, model=MODEL,
            max_iterations=task["iterationCapConfigured"]
        )
        handoff.validate_native_response(persisted, request)
    site, discovery = find_running_server_site_packages()
    packages = package_versions_from_site_packages(site) if site else {x: None for x in DEPENDENCIES}
    known_versions = packages.get("openhands-sdk") == SERVER and packages.get("openhands-agent-server") == SERVER
    vertex_dependencies_detected = bool(packages.get("google-auth") and packages.get("google-cloud-aiplatform"))
    return {
        "status": "PRE_EXECUTION_CHECKED_NOT_AUTHORIZED",
        "nativeServerVerified": True, "nativeIdleHookVerified": True,
        "nativeRuntimeDiscovery": discovery,
        "nativePinnedPackagesVerified": known_versions,
        "nativeVertexDependenciesDetected": vertex_dependencies_detected,
        "installedPackageVersions": packages,
        "nativeVertexProviderFunctionallyVerified": False,
        "adcInRunningServerVerified": False,
        "actualModelTokenCostCapEnforced": False,
        "hardStopAtSpendLimitProven": False,
        "executionAuthorization": False,
        "modelRequestPerformed": False,
        "nativeRunCalled": False,
        "limits": {
            "nativeMaxIterations": task["iterationCapConfigured"],
            "maxValidationDenials": task["validationDenialsConfigured"],
            "nativeIterationCapIsNotCostCap": True,
            "hardDollarCap": None,
            "hardTokenCap": None,
            "hardElapsedTimeCap": None,
        },
        "remainingBlockers": [
            "Prove Vertex provider is usable in the actual running server without paid inference",
            "Establish externally enforceable spending/token/time hard limits or explicitly accept bounded-but-not-hard spending risk",
            "Obtain explicit authorization before /run",
            "Observe native Stop Hook event and durable independent verdict during authorized execution",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--hook-config", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = audit(args.database, args.task_id, args.hook_config)
    except Exception as exc:
        output = {
            "status": "BLOCKED", "errorType": type(exc).__name__,
            "errorDetail": str(exc)[:180],
            "executionAuthorization": False,
            "nativeRunCalled": False, "modelRequestPerformed": False
        }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] != "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
