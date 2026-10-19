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
import subprocess
import time
import urllib.request
import urllib.error

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
    # Canvas 1.27.1 supplies OH_CONVERSATIONS_PATH from this exact directory.
    conversations = _private_directory(state / "dev_conversations")
    session_key = _read_or_create_key(home / "session-key.txt")
    native.write_private(native.KEY_FILE, session_key)
    agent_config = home / "agent-server-config.json"
    if agent_config.is_symlink():
        raise ValueError("Persistent agent server config may not be a symlink")
    config = {"conversations_path": str(conversations),
              "session_api_keys": [session_key]}
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


def native_environment(env: dict[str, str]) -> dict[str, str]:
    """Pass runtime settings and Vertex ADC location, not operator API tokens."""
    allowed = {
        "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
        "TERM", "TMPDIR", "TMP", "TEMP", "XDG_CACHE_HOME", "SSL_CERT_FILE", "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NO_PROXY", "UV_CACHE_DIR", "UV_TOOL_DIR",
        "UV_TOOL_BIN_DIR", "UV_CONSTRAINT", "UV_PYTHON", "UV_PYTHON_INSTALL_DIR",
        "npm_config_cache", "npm_config_prefix", "LOCAL_BACKEND_API_KEY",
        "OPENHANDS_AGENT_SERVER_CONFIG_PATH", "OH_CANVAS_SAFE_STATE_DIR", "OH_SECRET_KEY_PATH",
        "OH_SESSION_API_KEY_PATH", "OH_AGENT_SERVER_VERSION", "OH_AUTOMATION_VERSION",
        "OH_CANVAS_SAFE_BACKEND_PORT", "OH_CANVAS_SAFE_AUTOMATION_PORT", "OH_CANVAS_SAFE_VITE_PORT",
        "OH_TELEMETRY_EXPORTER", "DO_NOT_TRACK", "NO_COLOR", "VERTEXAI_PROJECT", "VERTEXAI_LOCATION",
        "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_QUOTA_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS",
        "CLOUDSDK_CONFIG", "DEVSHELL_CLIENT_PORT", "CLOUD_SHELL",
    }
    return {k: v for k, v in env.items() if k in allowed}


def serve(home: Path = SERVICE_HOME) -> dict:
    native.configure_server_version(SERVER_VERSION)
    marker = native.ROOT / MODE_MARKER
    existing = native.owned_pid()
    if existing is not None:
        if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != str(home.resolve()):
            raise ValueError("A different native smoke/test server already owns this port; do not replace it")
        configure_persistent_environment(native.environment(), home)
        native.wait_ready()
        native.wait_canvas_ready()
        return {"status": "SERVICE_RUNNING", "reused": True, "noModelRun": True,
                "url": f"http://127.0.0.1:{native.INGRESS}/"}
    native.preflight()
    env = configure_persistent_environment(native.environment(), home)
    native.canvas_install(env)
    native.warm_native_packages(env)
    native.assert_ports_free()
    # Record ownership before launch: readiness can fail after a successful
    # spawn, and retry must recognize its own partially started service.
    native.write_private(marker, str(home.resolve()) + "\n")
    native.launch(native_environment(env))
    native.wait_ready()
    native.wait_canvas_ready()
    return {"status": "SERVICE_RUNNING", "reused": False, "noModelRun": True,
            "nativeVersion": SERVER_VERSION,
            "persistentState": str(home.resolve()),
            "url": f"http://127.0.0.1:{native.INGRESS}/"}


PRODUCT_HOME = Path.home() / ".openhands/oss-remediation/product"


def ensure_node() -> None:
    """Reuse Node >=24, or provision one verified official Linux x64 release."""
    import hashlib
    import platform
    import shutil
    import tarfile
    existing = shutil.which("node")
    if existing:
        version = native.command([existing, "--version"])
        if int(version.lstrip("v").split(".")[0]) >= 24:
            return
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ValueError("Install Node >=24 for this platform before startup")
    directory = Path("/tmp/node-v24.13.0-linux-x64")
    archive = Path(str(directory) + ".tar.xz")
    expected = "e798599612f4bb71333a3397ab0d095fd62214e115aea45aa858a145fc72d67e"
    if not (directory / "bin/node").is_file():
        if not archive.is_file():
            native.log("Downloading pinned Node 24 prerequisite to /tmp")
            with urllib.request.urlopen("https://nodejs.org/dist/v24.13.0/" + archive.name, timeout=60) as response:
                with archive.open("wb") as output:
                    shutil.copyfileobj(response, output)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise ValueError("Official Node archive checksum mismatch; remove corrupt download")
        with tarfile.open(archive) as bundle:
            bundle.extractall("/tmp", filter="data")
    os.environ["PATH"] = str(directory / "bin") + os.pathsep + os.environ.get("PATH", "")


def _product_start(config_path: Path, port: int = 8080) -> dict:
    """Start official Canvas and one thin product worker; never run a model."""
    # Delay application imports until the repository path is established.
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository))
    from openhands_shared.product import default_config
    config_path = config_path.expanduser().resolve()
    if not config_path.exists():
        native.write_private(config_path, json.dumps(default_config(config_path.parent), indent=2) + "\n")
    config = json.loads(config_path.read_text())
    home = _private_directory(Path(config["stateDir"]))
    import shutil
    for name in ("git", "java", "mvn", "uvx"):
        if not shutil.which(name):
            raise ValueError(name + " is a required installed prerequisite")
    if not Path(config["scanner"]).expanduser().is_file():
        raise ValueError("Configure a pinned OSV scanner executable before startup")
    ensure_node()
    check = subprocess.run(["/usr/bin/python3", "-c",
        "import sys;sys.path.insert(0," + repr(str(repository)) + ");import openhands_shared.stop_hook"],
        capture_output=True, timeout=15)
    if check.returncode:
        raise ValueError("Stable system Python validator dependencies unavailable")
    api_key = _read_or_create_key(home / "api-key.txt").strip()
    native_result = serve(home / "native")
    env = configure_persistent_environment(native.environment(), home / "native")
    # Native coding tools need Vertex ADC, but never delivery/API credentials.
    # Product credentials are read by the separate control process below.
    key_file = home / "api-key.txt"
    url = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url + "/health", headers={"Authorization": "Bearer " + api_key})

    def ready():
        try:
            with opener.open(request, timeout=3) as response:
                value = json.load(response)
                return value.get("status") == "ready" and value.get("nativeVersion") == SERVER_VERSION
        except (OSError, ValueError):
            return False

    if not ready():
        import socket
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise ValueError("Product port already occupied by a different or unhealthy service")
        command = ["uvx", "--with", "openhands-sdk[vertex]==1.55.1",
            "--from", "openhands-agent-server==1.55.1", "--with", "openhands-sdk==1.55.1",
            "--with", "openhands-tools==1.55.1", "--with", "openhands-workspace==1.55.1",
            "--with", "posthog>=6,<7", "python", "-m", "openhands_shared.server",
            "--config", str(config_path), "--port", str(port)]
        with (home / "product.log").open("ab") as log:
            process = subprocess.Popen(command, cwd=repository, env=env, stdout=log,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        native.write_private(home / "product.pid", str(process.pid))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if ready():
                break
            if process.poll() is not None:
                raise ValueError("Product service exited; inspect private product.log")
            time.sleep(1)
        else:
            raise ValueError("Product readiness timed out; inspect existing process before retry")
    return {"status": "PRODUCT_RUNNING", "ui": url, "api": url + "/v1/remediations",
        "canvas": native_result["url"], "keyFile": str(key_file), "state": str(home),
        "config": str(config_path), "noModelRun": True, "noSmokeConversation": True}


def product_start(config_path: Path, port: int = 8080) -> dict:
    import fcntl
    parent = _private_directory(config_path.expanduser().parent)
    with (parent / "startup.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another product startup is already in progress") from None
        return _product_start(config_path, port)


def product_stop(config_path: Path):
    """Stop only the owned product and official launcher; retain all state."""
    import signal
    config = json.loads(config_path.expanduser().read_text())
    home = Path(config["stateDir"]).expanduser().resolve()
    pid_file = home / "product.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text())
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
            if b"openhands_shared.server" not in cmdline or str(config_path.expanduser().resolve()).encode() not in cmdline:
                raise ValueError("Product PID belongs to another process; refusing to stop it")
            os.kill(pid, signal.SIGTERM)
        except (FileNotFoundError, ProcessLookupError):
            pass
    native.configure_server_version(SERVER_VERSION)
    marker = native.ROOT / MODE_MARKER
    if native.owned_pid() is not None:
        if not marker.is_file() or marker.read_text().strip() != str(home / "native"):
            raise ValueError("Native launcher belongs to another deployment")
        native.stop()
    return {"status": "STOP_REQUESTED", "stateRetained": str(home), "noModelRun": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "restart", "serve"])
    parser.add_argument("--state-dir", type=Path, default=SERVICE_HOME)
    parser.add_argument("--config", type=Path, default=PRODUCT_HOME / "config.json")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        if args.action in {"stop", "restart"}:
            result = product_stop(args.config)
            if args.action == "restart":
                time.sleep(2)
        if args.action in {"start", "restart"}:
            result = product_start(args.config, args.port)
        elif args.action == "serve":
            result = serve(args.state_dir)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:240], "noModelRun": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"SERVICE_RUNNING", "PRODUCT_RUNNING", "STOP_REQUESTED"} else 1


if __name__ == "__main__":
    sys.exit(main())
