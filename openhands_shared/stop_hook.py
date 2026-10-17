"""Deployment-owned command boundary for the native OpenHands Stop Hook."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autonomous_oss_remediation_agent.config import MavenConfig, ScannerConfig

from .contracts import StopHookDecision, reject_sensitive_input
from .store import SQLiteTaskStore
from .validation import (
    SharedValidationService,
    StopHookResponse,
    ValidationConfig,
    ValidationProfile,
)


def load_stop_hook_config(path: Path) -> tuple[Path, ValidationConfig]:
    """Load the credential-free deployment configuration fail closed."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("configuration must be an object")
    reject_sensitive_input(value, "stopHookConfig")
    if set(value) != {"database", "artifactRoot", "profiles"}:
        raise ValueError("configuration fields are invalid")
    profiles = []
    if not isinstance(value["profiles"], list) or not value["profiles"]:
        raise ValueError("at least one validation profile is required")
    for item in value["profiles"]:
        if not isinstance(item, dict) or set(item) != {"profileId", "buildCommands", "maven", "scanner"}:
            raise ValueError("validation profile fields are invalid")
        profiles.append(
            ValidationProfile(
                profile_id=str(item["profileId"]),
                build_commands=tuple(str(command) for command in item["buildCommands"]),
                maven=MavenConfig(**dict(item["maven"])),
                scanner=ScannerConfig.from_dict(dict(item["scanner"])),
            )
        )
    database = Path(value["database"]).expanduser().resolve()
    return database, ValidationConfig(
        artifact_root=Path(value["artifactRoot"]), profiles=tuple(profiles)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run shared deterministic Stop Hook validation")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args(argv)
    store = None
    try:
        database, config = load_stop_hook_config(args.config.expanduser().resolve())
        store = SQLiteTaskStore(database)
        response = SharedValidationService(store, config).handle_stop(
            args.task_id, workspace_argument=args.workspace
        )
    except Exception:
        # Pinned 1.50.0 falls open for command failures. Emit an explicit ALLOW
        # solely to terminate, never an acceptance verdict; product recovery
        # observes that no complete PASS attempt exists.
        response = StopHookResponse(
            decision=StopHookDecision.ALLOW,
            reason=(
                "Shared validator transport failed; native termination is allowed only "
                "for fail-closed recovery. Deterministic acceptance has NOT passed."
            ),
        )
    finally:
        if store is not None:
            store.close()
    sys.stdout.write(json.dumps(response.to_native_dict(), sort_keys=True) + "\n")
    return response.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
