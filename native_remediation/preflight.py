"""Read-only native environment checks. Never call an LLM or install/restart services."""
import json
from pathlib import Path
import subprocess
import urllib.parse

from .delivery import GitHub
from .files import Blocked


def vertex_adc(native):
    port = str(urllib.parse.urlsplit(native.server).port or 80).encode()
    matches = []
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            args = path.read_bytes().split(b"\0")
            if len(args) > 1 and args[1].endswith(b"/bin/agent-server") and port in args:
                matches.append((path, args))
        except OSError:
            continue
    if len(matches) != 1:
        raise Blocked("Cannot identify the exact native server Python/environment for ADC preflight")
    path, args = matches[0]
    env = {k.decode(): v.decode() for k, v in (row.split(b"=", 1) for row in
        path.with_name("environ").read_bytes().split(b"\0") if b"=" in row)}
    # No token/credential values printed, even on failure.
    code = """
import json, os
from datetime import datetime, timezone
import google.auth
from google.auth.transport.requests import Request
try:
    c, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    for _ in range(2): c.refresh(Request())
    expiry = c.expiry
    if expiry and expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
    seconds = int((expiry-datetime.now(timezone.utc)).total_seconds()) if expiry else 0
    configured = os.environ.get('VERTEXAI_PROJECT') or os.environ.get('GOOGLE_CLOUD_PROJECT')
    assert configured and os.environ.get('VERTEXAI_LOCATION')
    assert c.token and c.valid and seconds >= 300 and (not project or project == configured)
    print(json.dumps(dict(source=type(c).__module__, project=project, remainingSeconds=seconds, passed=True)))
except Exception as exc:
    print(json.dumps(dict(passed=False, errorType=type(exc).__name__)))
    raise SystemExit(1)
"""
    result = subprocess.run([args[0].decode(), "-c", code], env=env,
                            capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise Blocked("Native runtime ADC refresh failed; verify discovery/source and >=300s lifetime")
    return json.loads(result.stdout)


def check(native, task):
    native.versions()
    report = dict(nativeVersion="1.55.1")
    if task["model"].startswith("vertex_ai/"):
        report["adc"] = vertex_adc(native)
    gh = GitHub(task["repository"])
    repo = gh.request("GET", "")
    if not repo or not repo.get("permissions", {}).get("push"):
        raise Blocked("Existing GitHub credentials lack target repository push access")
    report["githubPushAccess"] = True
    return report
