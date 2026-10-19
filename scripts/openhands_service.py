#!/usr/bin/env python3
"""Native OpenHands service startup, not a smoke-test or a second agent.

Keeps the official Canvas/Agent Server launcher and its /tmp package cache.
Only native state, keys and conversation storage live under persistent home.
Never creates smoke conversations, invokes /run, or pushes to GitHub.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

import openhands_native_poc as native

SERVER_VERSION = "1.55.1"
SERVICE_HOME = Path.home() / ".openhands" / "oss-remediation" / "native-1551"
MODE_MARKER = "product-native-service-v1.json"


def _private_directory(path: Path) -> Path:
    path = path.expanduser()
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError("Persistent native state directory is unsafe")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path.resolve(strict=True)


def _read_or_create_key(path: Path) -> str:
    if path.is_symlink():
        raise ValueError("Persistent native session key may not be a symlink")
    if path.exists():
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("Persistent native session key permissions are unsafe")
        secret = path.read_text(encoding="utf-8")
        if len(secret.strip()) < 40:
            raise ValueError("Persistent native session key is invalid")
        return secret
    import secrets
    secret = secrets.token_urlsafe(48)
    native.write_private(path, secret)
    return secret


def configure_persistent_environment(env: dict[str, str], home: Path) -> dict[str, str]:
    """Keep downloads in /tmp; keep small state and native conversation records in home."""
    home = _private_directory(home)
    state = _private_directory(home / "canvas")
    conversations = _private_directory(home / "conversations")
    session_key = _read_or_create_key(home / "session-key.txt")
    native.write_private(native.KEY_FILE, session_key)
    agent_config = home / "agent-server-config.json"
    if agent_config.is_symlink():
        raise ValueError("Persistent agent server config may not be a symlink")
    config = {"conversations_path": str(conversations),
              "session_api_key": session_key}
    native.write_private(agent_config, json.dumps(config, sort_keys=True) + "\n")
    updated = dict(env)
    updated.update({
        "LOCAL_BACKEND_API_KEY": session_key,
        "OH_CANVAS_SAFE_STATE_DIR": str(state),
        "OH_SECRET_KEY_PATH": str(home / "secret-key.txt"),
        "OH_SESSION_API_KEY_PATH": str(home / "canvas-session-key.txt"),
        "OPENHANDS_AGENT_SERVER_CONFIG_PATH": str(agent_config),
    })
    return updated


def serve(home: Path = SERVICE_HOME) -> dict:
    native.configure_server_version(SERVER_VERSION)
    marker = native.ROOT / MODE_MARKER
    existing = native.owned_pid()
    if existing is not None:
        if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != str(home.resolve()):
            raise ValueError("A different native smoke/test server already owns this port; do not replace it")
        native.wait_ready()
        native.wait_canvas_ready()
        return {"status": "SERVICE_RUNNING", "reused": True, "noModelRun": True,
                "url": f"http://127.0.0.1:{native.INGRESS}/"}
    native.preflight()
    env = configure_persistent_environment(native.environment(), home)
    native.canvas_install(env)
    native.warm_native_packages(env)
    native.launch(env)
    native.wait_ready()
    native.wait_canvas_ready()
    native.write_private(marker, str(home.resolve()) + "\n")
    return {"status": "SERVICE_RUNNING", "reused": False, "noModelRun": True,
            "nativeVersion": SERVER_VERSION,
            "persistentState": str(home.resolve()),
            "url": f"http://127.0.0.1:{native.INGRESS}/"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["serve"])
    parser.add_argument("--state-dir", type=Path, default=SERVICE_HOME)
    args = parser.parse_args()
    try:
        result = serve(args.state_dir)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:240], "noModelRun": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "SERVICE_RUNNING" else 1


if __name__ == "__main__":
    sys.exit(main())
