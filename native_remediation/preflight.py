"""Read-only native environment checks. Never call an LLM or install/restart services."""
import json
import subprocess
import os
import sys

from .delivery import GitHub
from .files import Blocked


def vertex_adc():
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
    result = subprocess.run([sys.executable, "-c", code], env=dict(os.environ),
                            capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise Blocked("Native runtime ADC refresh failed; verify discovery/source and >=300s lifetime")
    return json.loads(result.stdout)


def check(task):
    from importlib.metadata import version
    if version("openhands-sdk") != "1.55.1":
        raise Blocked("Require standalone SDK 1.55.1")
    report = dict(sdkVersion="1.55.1")
    if task["model"].startswith("vertex_ai/"):
        report["adc"] = vertex_adc()
    if task["delivery"]["mode"] == "report_only":
        report["githubDelivery"] = "NOT_REQUESTED"
        return report
    if not task["delivery"]["authorized"]:
        raise Blocked("Draft delivery policy is not explicitly authorized")
    gh = GitHub(task["repository"])
    repo = gh.request("GET", "")
    if not repo or not repo.get("permissions", {}).get("push"):
        raise Blocked("Existing GitHub credentials lack target repository push access")
    report["githubPushAccess"] = True
    return report
