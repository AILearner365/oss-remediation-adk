"""Explicit, replaceable task inputs. Credentials are file references, never values."""
from copy import deepcopy
from pathlib import Path
import re

from .files import Blocked, digest, read

SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
DEFAULTS = {
    "model": "vertex_ai/gemini-2.5-flash",
    "limits": {"max_iterations": 40, "max_cycles": 3, "max_runs": 2,
               "command_seconds": 900, "validation_seconds": 2400, "task_seconds": 7200},
    "policy": {"allowed_paths": ["pom.xml", "**/pom.xml"], "protected_paths": [],
               "protected_properties": [], "allowed_removed_dependencies": [],
               "allow_major_upgrades": False, "allow_downgrades": False,
               "max_remaining_findings": 0, "target_ids": [], "minimum_tests": 0},
    "tools": {"maven": "mvn", "osv": "osv-scanner", "profiles": [], "checks": [],
              "sbri_reference": None, "research_reference": None},
    "sandbox": {"image": None},
}


def load_task(value):
    task = deepcopy(DEFAULTS)
    if not isinstance(value, dict) or set(value) - {"repository", "base_branch", "base_sha",
            "goal", "constraints", "model", "limits", "policy", "tools", "delivery", "sandbox"}:
        raise Blocked("Unknown task fields")
    for key, item in value.items():
        if key in ("limits", "policy", "tools", "sandbox"):
            if not isinstance(item, dict) or set(item) - set(task[key]):
                raise Blocked("Unknown " + key + " fields")
            task[key].update(item)
        else:
            task[key] = item
    if not REPO.fullmatch(task.get("repository", "")) or not SHA.fullmatch(task.get("base_sha", "")):
        raise Blocked("Require GitHub owner/repo and approved immutable base SHA")
    branch = task.get("base_branch", "")
    if not branch or branch.startswith("-") or any(c in branch for c in " ~^:?*[\\\n\r") or ".." in branch:
        raise Blocked("Invalid base branch")
    if not isinstance(task.get("goal"), str) or not task["goal"].strip():
        raise Blocked("A remediation goal is required")
    if task.get("delivery") != {"repository": task["repository"], "base_branch": branch, "draft": True}:
        raise Blocked("Delivery must explicitly authorize a draft in the same repository/base")
    for name, number in task["limits"].items():
        if type(number) is not int or not 1 <= number <= 86400:
            raise Blocked("Invalid resource limit: " + name)
    if task["limits"]["max_cycles"] > 10 or task["limits"]["max_runs"] > 5 or task["limits"]["max_iterations"] > 200:
        raise Blocked("Task exceeds bounded agent limits")
    p = task["policy"]
    for key in ("allowed_paths", "protected_paths", "protected_properties", "allowed_removed_dependencies", "target_ids"):
        if not isinstance(p[key], list) or not all(isinstance(x, str) and x for x in p[key]):
            raise Blocked("Invalid policy list: " + key)
    if not p["allowed_paths"] or any(x.startswith("/") or ".." in Path(x).parts
                                     for x in p["allowed_paths"] + p["protected_paths"]):
        raise Blocked("Require bounded relative change paths")
    for key in ("allow_major_upgrades", "allow_downgrades"):
        if type(p[key]) is not bool:
            raise Blocked("Invalid policy boolean")
    for key in ("max_remaining_findings", "minimum_tests"):
        if type(p[key]) is not int or p[key] < 0:
            raise Blocked("Invalid acceptance count")
    tools = task["tools"]
    image = task["sandbox"]["image"]
    if image is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise Blocked("Sandbox requires an immutable local Docker image ID (sha256:...), not a tag")
    if (not isinstance(tools["profiles"], list) or not all(re.fullmatch(r"[\w.-]+", x) for x in tools["profiles"])
            or not isinstance(tools["checks"], list) or not all(isinstance(c, list) and c
                and all(isinstance(x, str) and x for x in c) for c in tools["checks"])):
        raise Blocked("Tool profiles/checks must be explicit argument lists")
    for key in ("maven", "osv"):
        if not isinstance(tools[key], str) or not tools[key] or tools[key].startswith("-"):
            raise Blocked("Tool executable is required")
    for key in ("sbri_reference", "research_reference"):
        if tools[key] is not None and (not isinstance(tools[key], str) or not tools[key]):
            raise Blocked("Optional capability must be a non-secret reference or null")
    if not isinstance(task["model"], str) or not task["model"]:
        raise Blocked("Explicit model required")
    task.setdefault("constraints", [])
    if (not isinstance(task["constraints"], list) or not all(isinstance(x, dict)
            and set(x) == {"description", "check"} and isinstance(x["description"], str)
            and x["description"] and isinstance(x["check"], list) and x["check"]
            and all(isinstance(arg, str) and arg for arg in x["check"]) for x in task["constraints"])):
        raise Blocked("Each additional hard constraint needs description and deterministic check argv")
    # Reject credential-bearing inputs rather than accidentally putting them in prompts.
    text = str(task)
    if re.search(r"(?i)(refresh_token|private_key|client_secret|api_key|gh[pousr]_[A-Za-z0-9]{20})", text):
        raise Blocked("Use credential references, never secrets in task inputs")
    return task


def context(state):
    state = Path(state).resolve(strict=True)
    bound = read(state / "task.json")
    task = load_task(bound["task"])
    if bound["taskDigest"] != digest(task):
        raise Blocked("Task contract digest mismatch")
    return state, bound, task
