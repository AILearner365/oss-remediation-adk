"""Thin native Agent Server 1.55.1 transport/configuration, not an agent loop."""
import json
from pathlib import Path
import shlex
import sys
import urllib.parse
import urllib.request

from .files import Blocked

VERSION = "1.55.1"
ENTRY = Path(__file__).with_name("__main__.py").resolve()
INSTRUCTIONS = """You are the single autonomous engineering agent for this contract.
Discover read-only before changing code. Separate facts, assumptions and uncertainty.
Use actual dependency ownership: direct, managed, imported BOM, override, transitive,
relocated or unmanaged. Investigate decision-critical unknowns with repository,
execution and current authoritative research when available. A failed tool call
does not prove absence. Consider credible whole-goal solutions, select a strategy
on evidence, then implement and reassess it; never force a Spring Boot upgrade.
Before each cycle's first material edit, record intent through the supplied record
command. Record an honest outcome and self-checks before FinishTool. Record concise
evidence and rationale, not private chain of thought. On validation feedback,
reconsider candidates and goal, carry forward evidence, and record a new bounded
cycle if a different approach is needed. Agent self-checks never authorize delivery.
Do not change the trusted task, validator, baseline, claims or evidence; do not
commit, push, create PRs or handle credentials. Trusted Stop validation captures
and tests your exact candidate tree and delivers only independent PASS. Respect
limits. If unable to satisfy the goal, report an evidence-backed bounded failure.
"""


class Native:
    def __init__(self, server, key_file):
        parsed = urllib.parse.urlsplit(server)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise Blocked("Use the existing loopback native Agent Server")
        self.server = server.rstrip("/")
        self.key = Path(key_file).read_text().strip()
        if not self.key:
            raise Blocked("Native session key file is empty")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, endpoint, body=None):
        headers = {"X-Session-API-Key": self.key, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.server + endpoint,
            data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=90) as response:
                return json.load(response)
        except Exception:
            raise Blocked("Native API operation failed or response uncertain; inspect conversation before retry") from None

    def versions(self):
        info = self.request("GET", "/server_info")
        if any(info.get(k) != VERSION for k in ("version", "sdk_version", "tools_version")):
            raise Blocked("Require native Agent Server/SDK/tools 1.55.1")
        return info


def request_config(state, bound, task):
    hook = shlex.join([sys.executable, str(ENTRY), "hook", "--state", str(state)])
    return dict(conversation_id=bound["conversationId"],
        workspace=dict(working_dir=str(state / "workspace")), worktree=False, autotitle=False,
        max_iterations=task["limits"]["max_iterations"],
        agent=dict(kind="Agent", llm=dict(model=task["model"], usage_id="oss-remediation",
            stream=False, num_retries=0, timeout=120),
            tools=[dict(name=n, params={}) for n in ("terminal", "file_editor", "task_tracker")],
            system_prompt_kwargs=dict(cli_mode=True), agent_context=dict(
                system_message_suffix=INSTRUCTIONS, load_user_skills=False,
                load_public_skills=False, load_project_skills=False, load_memory=False)),
        hook_config=dict(stop=[dict(matcher="*", hooks=[dict(type="command", command=hook,
            timeout=task["limits"]["validation_seconds"] + 300)])]),
        tags=dict(purpose="ossremediation", task=bound["conversationId"]))


def verify_effective(actual, expected):
    agent = actual.get("agent", {})
    stop = (actual.get("hook_config") or {}).get("stop", [])
    hooks = [h for group in stop for h in group["hooks"]]
    wanted = expected["hook_config"]["stop"][0]["hooks"][0]
    if (actual.get("id") != expected["conversation_id"] or len(hooks) != 1
            or any(hooks[0].get(k) != wanted[k] for k in ("type", "command", "timeout"))
            or actual.get("workspace", {}).get("working_dir") != expected["workspace"]["working_dir"]
            or actual.get("max_iterations") != expected["max_iterations"]
            or agent.get("llm", {}).get("model") != expected["agent"]["llm"]["model"]
            or agent.get("llm", {}).get("num_retries") != 0
            or [t.get("name") for t in agent.get("tools", [])] != [t["name"] for t in expected["agent"]["tools"]]):
        raise Blocked("Effective native model/tools/workspace/Stop configuration differs")


def task_message(state, bound, task, baseline):
    record = shlex.join([sys.executable, str(ENTRY), "record", "--state", str(state)])
    return ("Task and constraints (stable):\n" + json.dumps(task, indent=2)
        + "\nApproved base: " + task["base_sha"]
        + "\nDeterministic baseline evidence: " + str(state / "baseline.json")
        + "\nBaseline findings: " + json.dumps(baseline["findings"])
        + "\nResolved graphs and effective POMs are in the baseline evidence directory."
        + "\nRecord intent/outcome using: " + record + " --kind intent|outcome --document <JSON-file>"
        + "\nWrite scratch JSON outside the repository under " + str(state / "agent")
        + "\nIntent fields: facts, uncertainties, assumptions, success_criteria, candidates (list), chosen_strategy, rationale."
        + "\nOutcome fields: changes, self_checks, observations, goal_status, next_action."
        + "\nSet goal_status to candidate_ready or bounded_failure; only the trusted gate can accept success."
        + "\nUse explicit 'none established' statements when appropriate; do not invent facts."
        + "\nOptional SBRI/research references are capabilities, not a mandated strategy.")
