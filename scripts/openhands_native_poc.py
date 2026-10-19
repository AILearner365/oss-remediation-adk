#!/usr/bin/env python3
"""Disposable OpenHands Canvas 1.27.1 / Agent Server 1.54.0 or 1.55.1 smoke.

One command: python3 scripts/openhands_native_poc.py run
No model execution, build, scanner, git push, custom task API or SQLite.
Published Canvas starts its own matching Agent Server and Automation backend.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

CANVAS = "1.27.1"
SERVER = "1.54.0"  # default; CLI may opt into 1.55.1
CANVAS_DEFAULT_SERVER = "1.54.0"  # published Canvas 1.27.1 default
SUPPORTED_SERVERS = ("1.54.0", "1.55.1")
POC_LITELLM_PIN = "1.105.1"
AUTOMATION = "1.19.3"  # Canvas 1.27.1's own published default
ROOT = Path(os.environ.get("OH_POC_TMP", "/tmp/openhands-native-poc-1271")).resolve()
RESULT_DIR = Path(os.environ.get("OH_POC_REPORTS", str(Path.home() / "openhands-native-poc-reports"))).expanduser().resolve()
INGRESS = int(os.environ.get("OH_POC_PORT", "8090"))
BACKEND = int(os.environ.get("OH_POC_BACKEND_PORT", "18900"))
AUTOMATION_PORT = int(os.environ.get("OH_POC_AUTOMATION_PORT", "18901"))
FRONTEND_PORT = int(os.environ.get("OH_POC_FRONTEND_PORT", "18902"))
BIN = ROOT / "npm" / "bin" / "agent-canvas"
PID_FILE = ROOT / "launcher.pid"
KEY_FILE = ROOT / "session-key.txt"
IDENTITIES = ROOT / "identities.json"
REPORT = RESULT_DIR / "native-integration-smoke.json"
LOG_FILE = ROOT / "canvas.log"
LOOPBACK = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def configure_server_version(version: str) -> None:
    """Select a fully separate disposable stack before performing any operation.

    Keep 1.54.0's existing /tmp paths, ports and published report unchanged.
    The 1.55.1 test uses a different native state, conversation IDs, ports,
    credentials and report; it never opens 1.54.0's persisted conversations.
    """
    global SERVER, ROOT, INGRESS, BACKEND, AUTOMATION_PORT, FRONTEND_PORT
    global BIN, PID_FILE, KEY_FILE, IDENTITIES, REPORT, LOG_FILE
    if version not in SUPPORTED_SERVERS:
        raise ValueError(f"Unsupported server version: {version}")
    SERVER = version
    newer = version == "1.55.1"
    ROOT = Path(os.environ.get(
        "OH_POC_TMP", "/tmp/openhands-native-poc-1271-server-1551" if newer
        else "/tmp/openhands-native-poc-1271"
    )).resolve()
    INGRESS = int(os.environ.get("OH_POC_PORT", "8091" if newer else "8090"))
    BACKEND = int(os.environ.get("OH_POC_BACKEND_PORT", "18910" if newer else "18900"))
    AUTOMATION_PORT = int(os.environ.get("OH_POC_AUTOMATION_PORT", "18911" if newer else "18901"))
    FRONTEND_PORT = int(os.environ.get("OH_POC_FRONTEND_PORT", "18912" if newer else "18902"))
    BIN = ROOT / "npm" / "bin" / "agent-canvas"
    PID_FILE = ROOT / "launcher.pid"
    KEY_FILE = ROOT / "session-key.txt"
    IDENTITIES = ROOT / "identities.json"
    REPORT = RESULT_DIR / ("native-integration-smoke-1.55.1.json" if newer
                           else "native-integration-smoke.json")
    LOG_FILE = ROOT / "canvas.log"


class Failure(Exception):
    pass


def log(message: str) -> None:
    print("[poc] " + message, flush=True)


def write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)


def record(data: dict) -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT.with_suffix(".tmp")
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(path, REPORT)
    log("Report: " + str(REPORT))


def command(args: list[str], *, env: dict | None = None) -> str:
    if Path(args[0]).name in {"npm", "uvx"}:
        # Installation may be long on Cloud Shell: keep detailed output on /tmp,
        # but print a small heartbeat rather than appear stuck for 10 minutes.
        install_log = ROOT / "install.log"
        ROOT.mkdir(parents=True, exist_ok=True)
        with install_log.open("ab") as logfile:
            proc = subprocess.Popen(args, stdout=logfile, stderr=subprocess.STDOUT,
                                    env=env, stdin=subprocess.DEVNULL)
            started = time.monotonic()
            last_update = started
            while proc.poll() is None:
                if time.monotonic() - started >= 900:
                    proc.terminate()
                    raise Failure(f"{args[0]} installation exceeded 15 minutes; see {install_log}")
                time.sleep(3)
                if time.monotonic() - last_update > 30:
                    log(f"{args[0]} preparing temporary dependencies ... {int(time.monotonic() - started)}s")
                    last_update = time.monotonic()
            if proc.returncode:
                raise Failure(f"{args[0]} exited {proc.returncode}; see {install_log}")
        return ""
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, timeout=900, check=False)
    if result.returncode:
        raise Failure(f"{args[0]} exited {result.returncode}; see local terminal or temporary logs")
    return result.stdout.strip()


def preflight() -> None:
    for name in ("python3", "node", "npm", "uvx"):
        if not shutil.which(name):
            raise Failure(f"{name} not installed. Check Cloud Shell prerequisites before continuing")
    node = command(["node", "--version"])
    if int(node.lstrip("v").split(".")[0]) < 24:
        raise Failure(f"Node >=24 required by Canvas {CANVAS}; found {node}")
    ports = (INGRESS, BACKEND, AUTOMATION_PORT, FRONTEND_PORT, BACKEND + 1000)
    if len(set(ports)) != len(ports) or any(not (1024 <= p <= 65535) for p in ports):
        raise Failure("Invalid/conflicting POC ports")
    usage = shutil.disk_usage("/tmp")
    log(f"/tmp free: {usage.free // 1024**2} MiB; /home free: {shutil.disk_usage(str(Path.home())).free // 1024**2} MiB")
    if usage.free < 2 * 1024**3 and not BIN.exists():
        raise Failure("Need about 2 GiB free on /tmp for first-time package installation")
    if Path("/proc/meminfo").exists():
        info = Path("/proc/meminfo").read_text(encoding="utf-8")
        available = int(next(x.split()[1] for x in info.splitlines() if x.startswith("MemAvailable:"))) // 1024
        log(f"Memory available: {available} MiB")
        if available < 1100:
            raise Failure("Less than 1100 MiB memory available; stop unrelated processes first")


def environment() -> dict[str, str]:
    ROOT.mkdir(parents=True, exist_ok=True)
    if not KEY_FILE.is_file():
        write_private(KEY_FILE, secrets.token_urlsafe(36))
    env = dict(os.environ)
    if SERVER == "1.55.1":
        constraint = ROOT / "litellm-constraint.txt"
        constraint.write_text(f"litellm=={POC_LITELLM_PIN}\n", encoding="utf-8")
        env["UV_CONSTRAINT"] = str(constraint)
    else:
        env.pop("UV_CONSTRAINT", None)
    env.update({
        "UV_CACHE_DIR": str(ROOT / "uv-cache"),
        "UV_TOOL_DIR": str(ROOT / "uv-tools"),
        "UV_TOOL_BIN_DIR": str(ROOT / "uv-tool-bin"),
        "npm_config_cache": str(ROOT / "npm-cache"),
        "npm_config_prefix": str(ROOT / "npm"),
        "XDG_CACHE_HOME": str(ROOT / "cache"),
        "OH_CANVAS_SAFE_STATE_DIR": str(ROOT / "state"),
        "OH_SECRET_KEY_PATH": str(ROOT / "secret-key.txt"),
        "OH_SESSION_API_KEY_PATH": str(ROOT / "session-key-persisted.txt"),
        "LOCAL_BACKEND_API_KEY": KEY_FILE.read_text(encoding="utf-8"),
        "OH_AGENT_SERVER_VERSION": SERVER,
        "OH_AUTOMATION_VERSION": AUTOMATION,
        "OH_CANVAS_SAFE_BACKEND_PORT": str(BACKEND),
        "OH_CANVAS_SAFE_AUTOMATION_PORT": str(AUTOMATION_PORT),
        "OH_CANVAS_SAFE_VITE_PORT": str(FRONTEND_PORT),
        "OH_TELEMETRY_EXPORTER": "none",
        "DO_NOT_TRACK": "1",
        "NO_COLOR": "1",
    })
    # An old test's custom source or Git ref must not override official versions.
    for item in ("OH_AGENT_SERVER_GIT_REF", "OH_AGENT_SERVER_LOCAL_PATH", "OH_AUTOMATION_GIT_REF", "OH_AUTOMATION_LOCAL_PATH"):
        env.pop(item, None)
    install_vertex_uvx_wrapper(env)
    return env


def install_vertex_uvx_wrapper(env: dict[str, str]) -> None:
    """Inject the Vertex extra into Canvas's *actual* pinned Agent Server uvx.

    Canvas 1.27.1 builds its own uvx command, independent of our prewarm.
    Do not patch its installed source or affect Automation/other uvx calls.
    """
    if SERVER != "1.55.1":
        return
    real_uvx = shutil.which("uvx", path=env.get("PATH"))
    if not real_uvx:
        raise Failure("uvx unavailable for pinned Vertex Agent Server")
    wrapper_dir = ROOT / "vertex-uvx-bin"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    wrapper = wrapper_dir / "uvx"
    script = (
        "#!/bin/sh\n"
        "for arg do\n"
        "  if [ \"$arg\" = 'openhands-agent-server==1.55.1' ]; then\n"
        f"    exec {shlex.quote(real_uvx)} --with 'openhands-sdk[vertex]==1.55.1' \"$@\"\n"
        "  fi\n"
        "done\n"
        f"exec {shlex.quote(real_uvx)} \"$@\"\n"
    )
    write_private(wrapper, script)
    wrapper.chmod(0o700)
    env["PATH"] = str(wrapper_dir) + os.pathsep + env.get("PATH", "")


def canvas_install(env: dict[str, str]) -> None:
    package = ROOT / "npm" / "lib" / "node_modules" / "@openhands" / "agent-canvas" / "package.json"
    if package.is_file():
        try:
            if json.loads(package.read_text(encoding="utf-8")).get("version") == CANVAS and BIN.exists():
                log(f"Reusing temporary published Canvas {CANVAS}")
                return
        except (ValueError, OSError):
            pass
    log(f"Installing prebuilt @openhands/agent-canvas@{CANVAS} into /tmp (may take a few minutes)")
    command(["npm", "install", "--global", "--prefix", str(ROOT / "npm"), "--no-audit", "--no-fund", f"@openhands/agent-canvas@{CANVAS}"], env=env)
    if not BIN.exists() or command([str(BIN), "--version"], env=env) != CANVAS:
        raise Failure("Canvas version verification failed")
    # Source of truth is the package, not our expectation.
    defaults = json.loads((package.parent / "config" / "defaults.json").read_text(encoding="utf-8"))
    if defaults.get("versions", {}).get("agentServer") != CANVAS_DEFAULT_SERVER or defaults.get("versions", {}).get("automation") != AUTOMATION:
        raise Failure("Upstream Canvas default versions changed; inspect before proceeding")
    log("Verified official Canvas launcher and matched default backend versions")


def owned_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        if stat.rsplit(") ", 1)[1].startswith("Z"):
            PID_FILE.unlink(missing_ok=True)
            return None
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
        if "agent-canvas" not in cmdline or str(BIN) not in cmdline:
            raise Failure("Stored PID refers to a different process; refusing to stop or reuse")
        return pid
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return None


def assert_ports_free() -> None:
    for port in (INGRESS, BACKEND, AUTOMATION_PORT, FRONTEND_PORT, BACKEND + 1000):
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                raise Failure(f"Port {port} already in use (not owned by this POC). Do not disrupt existing services")


def warm_native_packages(env: dict[str, str]) -> None:
    """Official CLI waits only 60s for backend readiness; prewarm exact uvx deps."""
    stamp = ROOT / "packages-ready.txt"
    fingerprint = f"{SERVER}|{AUTOMATION}|{POC_LITELLM_PIN if SERVER == '1.55.1' else 'unconstrained'}|{'vertex-extra-1' if SERVER == '1.55.1' else 'standard'}"
    if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == fingerprint:
        return
    log("Preparing pinned SDK/Agent Server and Automation in /tmp before Canvas startup")
    command(["uvx", "--from", f"openhands-agent-server=={SERVER}",
             "--with", f"openhands-sdk=={SERVER}", "--with", f"openhands-tools=={SERVER}",
             "--with", f"openhands-workspace=={SERVER}", "--with", "posthog>=6,<7",
             "agent-server", "--help"], env=env)
    if SERVER == "1.55.1":
        # Use exactly the same uvx package requirements as the official
        # launcher. Verify dependency resolution before opening the server.
        command(["uvx", "--from", f"openhands-agent-server=={SERVER}",
                 "--with", f"openhands-sdk=={SERVER}",
                 "--with", f"openhands-tools=={SERVER}",
                 "--with", f"openhands-workspace=={SERVER}",
                 "--with", "posthog>=6,<7",
                 "python", "-c",
                 "from importlib.metadata import version; "
                 "assert version('litellm') == '1.105.1', version('litellm'); "
                 "import litellm; import mcp.types"], env=env)
        log("Verified pinned LiteLLM import preflight with Vertex extra requested for Agent Server")
    command(["uvx", "--from", f"openhands-automation=={AUTOMATION}",
             "uvicorn", "--help"], env=env)
    stamp.write_text(fingerprint + "\n", encoding="utf-8")


def launch(env: dict[str, str]) -> None:
    if owned_pid() is not None:
        log("Reusing already-running POC launcher")
        return
    assert_ports_free()
    log(f"Starting official Canvas {CANVAS} stack on loopback {INGRESS}; server {SERVER}")
    with LOG_FILE.open("ab") as f:
        p = subprocess.Popen([str(BIN), "--port", str(INGRESS), "--host", "127.0.0.1"],
                             cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT, env=env,
                             start_new_session=True, stdin=subprocess.DEVNULL)
    write_private(PID_FILE, str(p.pid))


def http(method: str, path: str, payload: dict | None = None, *, timeout: int = 15) -> dict:
    headers = {"Accept": "application/json", "X-Session-API-Key": KEY_FILE.read_text(encoding="utf-8")}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{BACKEND}{path}", data=data,
                                 method=method, headers=headers)
    try:
        with LOOPBACK.open(req, timeout=timeout) as resp:
            result = json.load(resp)
        if not isinstance(result, dict):
            raise Failure(f"Unexpected API response type for {path}")
        return result
    except urllib.error.HTTPError as exc:
        # API error responses may expose environment details; keep raw body out of persisted reports.
        raise Failure(f"Native API {method} {path} returned HTTP {exc.code}. Inspect temporary Canvas log") from exc
    except urllib.error.URLError as exc:
        raise Failure(f"Native API unreachable for {path}: {type(exc.reason).__name__}") from exc


def wait_ready() -> dict:
    deadline = time.monotonic() + 600  # uvx may install SDK on first launch
    last = "not ready"
    while time.monotonic() < deadline:
        if owned_pid() is None:
            raise Failure("Canvas launcher stopped unexpectedly; inspect " + str(LOG_FILE))
        try:
            info = http("GET", "/server_info", timeout=4)
            if info.get("version") != SERVER or info.get("sdk_version") != SERVER:
                raise Failure(f"Version mismatch: Agent Server={info.get('version')}, SDK={info.get('sdk_version')}; expected {SERVER}")
            return info
        except Failure as exc:
            if "Version mismatch" in str(exc):
                raise
            last = str(exc)
        time.sleep(4)
    raise Failure("Timed out waiting for Agent Server: " + last + "; see " + str(LOG_FILE))


def wait_canvas_ready() -> None:
    """Wait for the official launcher to serve Canvas after Agent Server starts.

    The Agent Server /server_info endpoint can become available before the
    ingress proxy and static frontend are ready, especially after a restart.
    """
    deadline = time.monotonic() + 120
    last = "not ready"
    request = urllib.request.Request(
        f"http://127.0.0.1:{INGRESS}/", headers={"Accept": "text/html"}
    )
    while time.monotonic() < deadline:
        if owned_pid() is None:
            raise Failure("Canvas launcher exited while waiting for HTTP ingress")
        try:
            with LOOPBACK.open(request, timeout=5) as response:
                body = response.read(16384)
                if response.status == 200 and b"<html" in body.lower():
                    return
                last = f"HTTP {response.status}, HTML missing"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise Failure(
        "Canvas ingress did not become ready within 120s after Agent Server; "
        f"last observation: {last}. Inspect {LOG_FILE}"
    )


def create_fixture(kind: str, conv_id: str) -> Path:
    workspace = ROOT / "fixtures" / kind
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text(f"# {kind} smoke workspace\nNo real remediation.\n", encoding="utf-8")
    if kind == "remediation":
        report = {"status": "SIMULATED_BASELINE", "targetFindings": 2, "note": "Not an OSV scan"}
        (workspace / "baseline.json").write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    return workspace


def hook_command() -> str:
    # Trusted hook fixture logic resides in this same POC script. Never use it in production.
    import shlex
    return " ".join(shlex.quote(x) for x in [sys.executable, str(Path(__file__).resolve()), "hook", "--verdict", str(ROOT / "synthetic-verdict.json")])


def smoke_hook() -> dict:
    verdict_file = ROOT / "synthetic-verdict.json"
    out = {}
    for passed in (False, True):
        verdict_file.write_text(json.dumps({"simulatedPass": passed}) + "\n", encoding="utf-8")
        run = subprocess.run([sys.executable, str(Path(__file__).resolve()), "hook", "--verdict", str(verdict_file)],
                             input='{"event_type":"Stop"}', capture_output=True, text=True, timeout=10)
        try:
            payload = json.loads(run.stdout)
        except ValueError as exc:
            raise Failure("Synthetic Stop Hook output not JSON") from exc
        expected = (0, "allow") if passed else (2, "deny")
        if (run.returncode, payload.get("decision")) != expected:
            raise Failure("Synthetic Stop Hook verdict did not match expected native protocol")
        out["mockPass" if passed else "mockFail"] = "PASS"
    verdict_file.unlink(missing_ok=True)  # hook must DENY if someone accidentally runs it
    return out


def main_probe() -> dict:
    report = {"canvasVersion": CANVAS, "expectedAgentServer": SERVER,
              "checks": {}, "notProven": ["Canvas browser rendering", "Native /run executing Stop Hook", "Real Maven/OSV baseline", "Vertex ADC", "Real remediation and delivery"]}
    info = http("GET", "/server_info")
    if any(info.get(x) != SERVER for x in ("version", "sdk_version", "tools_version")):
        raise Failure("Unexpected native Agent Server/SDK/tools versions")
    report["checks"]["nativeServerSdkVersion"] = "PASS"
    # Verify that published Canvas serves an HTML frontend on ingress; browser
    # rendering itself must still be verified manually.
    request = urllib.request.Request(f"http://127.0.0.1:{INGRESS}/", headers={"Accept": "text/html"})
    try:
        with LOOPBACK.open(request, timeout=10) as response:
            body = response.read(16384)
            if response.status != 200 or b"<html" not in body.lower():
                raise Failure("Canvas ingress responded without an HTML frontend")
    except urllib.error.URLError as exc:
        raise Failure("Canvas UI ingress is unavailable") from exc
    report["checks"]["canvasStaticFrontendHttp"] = "PASS"
    report["serverCapabilities"] = [x for x in info.get("capabilities", []) if x in ("idempotent_conversation_create_v1", "canvas_app_backend_bridge_v1")]
    report["checks"]["hookProtocolStandalone"] = smoke_hook()
    if IDENTITIES.is_file():
        ids = json.loads(IDENTITIES.read_text(encoding="utf-8"))
    else:
        ids = {"normal": str(uuid.uuid4()), "remediation": str(uuid.uuid4())}
        write_private(IDENTITIES, json.dumps(ids))

    for kind in ("normal", "remediation"):
        uid = ids[kind]
        workspace = create_fixture(kind, uid)
        req = {
            "conversation_id": uid,
            "workspace": {"working_dir": str(workspace)},
            "worktree": False,
            "autotitle": False,
            "max_iterations": 3,
            "tags": {"smoke": "native", "scenario": kind},
            "agent": {"kind": "Agent", "llm": {"model": "openai/gpt-4o-mini", "api_key": "poc-local-dummy-not-real", "base_url": "http://127.0.0.1:12999/v1", "usage_id": "openhands-native-poc"}},
        }
        if kind == "remediation":
            req["hook_config"] = {"stop": [{"matcher": "*", "hooks": [{"type": "command", "command": hook_command(), "timeout": 15}]}]}
        current = None
        try:
            current = http("GET", f"/api/conversations/{uid}?include_skills=true")
        except Failure as exc:
            if "HTTP 404" not in str(exc):
                raise
        if current is None:
            current = http("POST", "/api/conversations?include_skills=true", req, timeout=75)
            report["checks"][f"{kind}ConversationCreated"] = "PASS"
        elif str(current.get("id", current.get("conversation_id"))) != uid:
            raise Failure("Existing conversation id mismatch")
        else:
            report["checks"][f"{kind}ConversationReused"] = "PASS"
        if str(current.get("id", current.get("conversation_id"))) != uid:
            raise Failure(f"{kind} native conversation id mismatch")
        # No initial_message: SDK 1.50+ otherwise may start a run automatically.
        if kind == "remediation":
            events = http("GET", f"/api/conversations/{uid}/events/search?limit=50&sort_order=TIMESTAMP")
            items = events.get("items", [])
            if not isinstance(items, list):
                raise Failure("Native event listing changed shape")
            # Trigger lazy native hook initialization, but never execute the agent.
            if not any("NATIVE_POC_CONTEXT" in json.dumps(item) for item in items):
                http("POST", f"/api/conversations/{uid}/events", {
                    "role": "user", "content": [{"type": "text", "text": "NATIVE_POC_CONTEXT: synthetic pre-agent baseline saved. This is an idle integration smoke only; do not run the agent."}],
                    "run": False,
                })
            current = http("GET", f"/api/conversations/{uid}?include_skills=true")
            stop = current.get("hook_config", {}).get("stop", []) if isinstance(current.get("hook_config"), dict) else []
            commands = [h.get("command") for matcher in stop if isinstance(matcher, dict) for h in matcher.get("hooks", []) if isinstance(h, dict)]
            if hook_command() not in commands:
                raise Failure("Effective Stop Hook not visible; do not run this conversation")
            report["checks"]["nativeStopHookAttached"] = "PASS"
            events = http("GET", f"/api/conversations/{uid}/events/search?limit=50&sort_order=TIMESTAMP")
            if not events.get("items"):
                raise Failure("Native events missing")
            report["checks"]["nativeEventsReadable"] = "PASS"
        if current.get("execution_status") != "idle":
            raise Failure(f"{kind} conversation unexpectedly executed: {current.get('execution_status')}")
        report["checks"][f"{kind}IdleNoModelCall"] = "PASS"
        report[kind + "ConversationId"] = uid
        report[kind + "CanvasUrl"] = f"http://127.0.0.1:{INGRESS}/conversations/{uid}"
    report["verdict"] = "NATIVE_API_SMOKE_PASSED__BROWSER_AND_NATIVE_HOOK_RUN_NOT_PROVEN"
    return report


def stop() -> None:
    pid = owned_pid()
    if pid is None:
        log("No owned launcher running")
        return
    log(f"Stopping only the owned launcher PID {pid}")
    os.kill(pid, signal.SIGTERM)
    for _ in range(25):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            PID_FILE.unlink(missing_ok=True)
            return
        time.sleep(0.2)
    log("Launcher still shutting down. Inspect PID before retry; no force kill performed")


def run() -> None:
    preflight()
    env = environment()
    canvas_install(env)
    if owned_pid() is None:
        warm_native_packages(env)
    launch(env)
    wait_ready()
    wait_canvas_ready()
    log("Native server and Canvas ingress ready; verifying idle integration (NO LLM RUN)")
    result = main_probe()
    record(result)
    log("API smoke PASSED for Server/SDK " + SERVER + ". Open Canvas via Cloud Shell Web Preview on port " + str(INGRESS))
    log("Remediation conversation: " + result["remediationCanvasUrl"])
    log("Normal conversation: " + result["normalCanvasUrl"])
    log("To test persistence: run 'stop', then 'run' again within the same Cloud Shell session")


def hook(verdict_file: str) -> int:
    """Synthetic protocol fixture ONLY; not an independent security validator."""
    try:
        payload = json.loads(Path(verdict_file).read_text(encoding="utf-8"))
        if payload.get("simulatedPass") is True:
            print(json.dumps({"decision": "allow"}))
            return 0
    except (OSError, ValueError, AttributeError):
        pass
    print(json.dumps({"decision": "deny", "reason": "Synthetic POC validation has not passed", "additionalContext": "This is only a protocol fixture, not a real validator."}))
    return 2


def publish() -> None:
    """Explicit opt-in: publish ONLY sanitized result JSON to the integration branch."""
    if not REPORT.exists():
        raise Failure("No result report exists. Run POC first")
    repo = Path(__file__).resolve().parent.parent
    branch = command(["git", "-C", str(repo), "branch", "--show-current"])
    if branch != "openhands-service-integration":
        raise Failure("Publish allowed only from openhands-service-integration")
    origin = command(["git", "-C", str(repo), "remote", "get-url", "origin"])
    if "AILearner365/oss-remediation-adk" not in origin:
        raise Failure("Unexpected git origin; refusing publish")
    if command(["git", "-C", str(repo), "diff", "--cached", "--name-only"]):
        raise Failure("Already staged changes detected; refusing to mix them with evidence")
    published = repo / "docs" / "experiments" / "openhands" / "evidence"
    published.mkdir(parents=True, exist_ok=True)
    name = time.strftime("native-smoke-%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3) + ".json"
    destination = published / name
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    # Selectively publish only expected, credential-free diagnostic keys.
    keys = ("canvasVersion", "expectedAgentServer", "checks", "notProven", "serverCapabilities",
            "normalConversationId", "remediationConversationId", "verdict", "failure")
    if data.get("expectedAgentServer") != SERVER:
        raise Failure("Report version mismatch; run the selected server test before publishing")
    sanitized = {k: data[k] for k in keys if k in data}
    destination.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    relative = str(destination.relative_to(repo))
    command(["git", "-C", str(repo), "add", "--", relative])
    command(["git", "-C", str(repo), "commit", "-m", "Record native OpenHands disposable integration smoke evidence", "--", relative])
    command(["git", "-C", str(repo), "push", "origin", "HEAD:openhands-service-integration"])
    log("Evidence committed and pushed: " + relative)


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "probe", "stop", "status", "hook", "publish"))
    parser.add_argument("--verdict", default=None)
    parser.add_argument("--server-version", choices=SUPPORTED_SERVERS,
                        default="1.54.0", help="Server/SDK pin; 1.55.1 uses separate ports and temporary state")
    args = parser.parse_args()
    configure_server_version(args.server_version)
    if args.action == "hook":
        if not args.verdict:
            parser.error("hook requires --verdict")
        return hook(args.verdict)
    try:
        if args.action == "publish":
            publish()
        elif args.action == "stop":
            stop()
        elif args.action == "status":
            print("Launcher running:", bool(owned_pid()))
            if REPORT.exists():
                print("Last report:", REPORT)
                print(REPORT.read_text(encoding="utf-8"))
        elif args.action == "probe":
            record(main_probe())
        else:
            run()
        return 0
    except (Failure, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        message = str(exc).replace(KEY_FILE.read_text(encoding="utf-8") if KEY_FILE.exists() else "<unused>", "[redacted]")
        print("ERROR:", message, file=sys.stderr)
        if args.action in ("run", "probe"):
            record({"verdict": "FAILED", "failure": message, "canvasVersion": CANVAS, "expectedAgentServer": SERVER,
                    "logFile": str(LOG_FILE), "note": "No paid model calls are made by this script"})
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
