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
               "command_seconds": 900, "validation_seconds": 2400, "task_seconds": 7200,
               "max_decisions": 12, "max_self_validations": 4, "max_sbri_calls": 3},
    "policy": {"allowed_paths": ["pom.xml", "**/pom.xml"], "protected_paths": [],
               "protected_properties": [], "allowed_removed_dependencies": [],
               "allow_major_upgrades": False, "allow_downgrades": False,
               "max_remaining_findings": 0, "target_ids": [], "minimum_tests": 0,
               "java": {"allow_change": False, "allowed_versions": []},
               "spring_boot": {"patch": True, "minor": True, "major": False, "downgrade": False}},
    "tools": {"maven": "mvn", "osv": "osv-scanner", "profiles": [], "checks": [],
              "sbri_reference": None, "research_reference": None},
    "guidance": {"skills": ["dependency-remediation-decision", "maven-dependency-evidence"],
                 "project_context": ""},
    "scanner": {"type": "osv", "version": "2.6.0"},
    "sbri": {"mode": "auto", "pre_edit": True, "executable": None,
             "versions": [], "ranges": [], "scopes": ["compile", "runtime"], "max_candidates": 12},
    "delivery": {"mode": "report_only"},
}


def load_task(value):
    task = deepcopy(DEFAULTS)
    if not isinstance(value, dict) or set(value) - {"repository", "base_branch", "base_sha",
            "goal", "constraints", "model", "limits", "policy", "tools", "delivery",
            "guidance", "scanner", "sbri"}:
        raise Blocked("Unknown task fields")
    for key, item in value.items():
        if key in ("limits", "policy", "tools", "guidance", "scanner", "sbri"):
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
    delivery = task["delivery"]
    if delivery == {"repository": task["repository"], "base_branch": branch, "draft": True}:
        # Previously approved destination syntax is retained, not silently authorized.
        delivery = dict(delivery, mode="draft_pr", authorized=False)
        task["delivery"] = delivery
    if delivery != {"mode": "report_only"}:
        if (not isinstance(delivery, dict) or set(delivery) != {"mode", "repository", "base_branch", "draft", "authorized"}
                or delivery["mode"] != "draft_pr" or delivery["repository"] != task["repository"]
                or delivery["base_branch"] != branch or delivery["draft"] is not True
                or type(delivery["authorized"]) is not bool):
            raise Blocked("Require report_only or an explicitly authorized same-repository/base draft policy")
    for name, number in task["limits"].items():
        if type(number) is not int or not 1 <= number <= 86400:
            raise Blocked("Invalid resource limit: " + name)
    if task["limits"]["max_cycles"] > 10 or task["limits"]["max_runs"] > 5 or task["limits"]["max_iterations"] > 1000:
        raise Blocked("Task exceeds bounded agent limits")
    p = task["policy"]
    for section in ("java", "spring_boot"):
        explicit = value.get("policy", {}).get(section, {})
        if not isinstance(explicit, dict) or set(explicit) - set(DEFAULTS["policy"][section]):
            raise Blocked("Unknown " + section + " policy")
        p[section] = dict(DEFAULTS["policy"][section], **explicit)
    if (type(p["java"]["allow_change"]) is not bool
            or not isinstance(p["java"]["allowed_versions"], list)
            or any(not isinstance(v, str) or not re.fullmatch(r"\d+(?:\.\d+)*", v) for v in p["java"]["allowed_versions"])
            or any(type(v) is not bool for v in p["spring_boot"].values())):
        raise Blocked("Invalid Java/Spring Boot movement policy")
    if task["scanner"] != DEFAULTS["scanner"]:
        raise Blocked("Only the verified OSV 2.6.0 adapter is supported; no unverified scanner substitution")
    guidance = task["guidance"]
    names = DEFAULTS["guidance"]["skills"] + ["evidence-driven-dependency-remediation"]
    if (not isinstance(guidance["skills"], list) or not all(n in names for n in guidance["skills"])
            or len(set(guidance["skills"])) != len(guidance["skills"])
            or not isinstance(guidance["project_context"], str)):
        raise Blocked("Invalid native guidance selection")
    if "evidence-driven-dependency-remediation" in guidance["skills"] and "dependency-remediation-decision" in guidance["skills"]:
        raise Blocked("Select one remediation decision Skill, not overlapping workflows")
    sbri = task["sbri"]
    if (sbri["mode"] not in ("off", "auto", "on") or type(sbri["pre_edit"]) is not bool
            or type(sbri["max_candidates"]) is not int or not 1 <= sbri["max_candidates"] <= 50
            or sbri["executable"] is not None and (not isinstance(sbri["executable"], str) or not sbri["executable"])
            or not isinstance(sbri["scopes"], list) or not sbri["scopes"]
            or not all(s in ("compile", "runtime", "test", "provided", "system") for s in sbri["scopes"])):
        raise Blocked("Invalid SBRI mode/executable/scopes/budget")
    for key, pattern in (("versions", r"\d+\.\d+\.\d+"), ("ranges", r"\d+\.\d+\.x")):
        if not isinstance(sbri[key], list) or any(not isinstance(v, str) or not re.fullmatch(pattern, v) for v in sbri[key]):
            raise Blocked("Invalid SBRI " + key)
    if sbri["versions"] and sbri["ranges"] or len(sbri["versions"]) > sbri["max_candidates"]:
        raise Blocked("SBRI versions/ranges are exclusive and candidate count is bounded")
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
