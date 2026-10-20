"""Agent evidence capabilities reuse the existing validator and SBRI CLI.

Neither path writes Stop feedback/acceptance, consumes Stop attempts or delivers.
"""
from pathlib import Path
import shutil
import time
import uuid
import xml.etree.ElementTree as ET

from .contract import context
from .files import Blocked, command, digest, lock, read, write, require_independent_authority
from .repository import export, snapshot
from .validation import compare, evaluate


def self_validate(state, *, evaluator=None):
    if evaluator is None:
        require_independent_authority()
    from .runtime import require_preparation
    state, bound, task = require_preparation(state)
    with lock(state):
        root = state / "self-validation"
        if len(list(root.glob("*/intent.json"))) >= task["limits"]["max_self_validations"]:
            raise Blocked("Self-validation budget exhausted; Stop attempts remain independent")
        tree = snapshot(state / "workspace", task)
        attempt = root / uuid.uuid4().hex
        write(attempt / "intent.json", dict(tree=tree, at=time.time()), exclusive=True)
    candidate = (evaluator or evaluate)(state / "workspace", tree, task, attempt / "candidate",
        deadline=min(bound["createdAt"] + task["limits"]["task_seconds"],
                     time.time() + task["limits"]["validation_seconds"]))
    result = dict(compare(read(state / "baseline.json"), candidate, task["policy"]),
        conversationId=bound["conversationId"], taskDigest=bound["taskDigest"], tree=tree,
        authority="AGENT_SELF_CHECK_ONLY", evaluation=candidate,
        evidence=str(attempt.relative_to(state)), stopAttemptConsumed=False)
    write(attempt / "result.json", result, exclusive=True)
    return result


def discover_boot(project):
    """Root parent/imported BOM discovery adapted from the retained SBRI helper.

    Ambiguous or unresolved ownership is unknown, not proof of non-applicability.
    """
    root = ET.parse(Path(project) / "pom.xml").getroot()
    props = {p.tag.split("}")[-1]: p.text or "" for p in root.findall("{*}properties/*")}
    values = []
    for node in [root.find("{*}parent"), *root.findall("{*}dependencyManagement/{*}dependencies/{*}dependency")]:
        if node is not None and node.findtext("{*}groupId") == "org.springframework.boot" and node.findtext(
                "{*}artifactId") in ("spring-boot-starter-parent", "spring-boot-dependencies"):
            version = node.findtext("{*}version", "")
            version = props.get(version[2:-1], version) if version.startswith("${") else version
            values.append(version)
    if not values:
        return None
    if len(set(values)) != 1 or "${" in values[0]:
        raise Blocked("Spring Boot controller is ambiguous/unresolved; investigate ownership")
    return values[0]


def sbri(state, *, versions=None, ranges=None, scopes=None, runner=None):
    state, bound, task = context(state)
    config = dict(task["sbri"])
    if versions is not None or ranges is not None:
        config.update(versions=versions or [], ranges=ranges or [])
    if scopes is not None:
        config["scopes"] = scopes
    # Use the task schema for agent candidate arguments too; never accept argv.
    from .contract import load_task
    config = load_task(dict(task, sbri=config))["sbri"]
    if config["mode"] == "off":
        return dict(status="DISABLED", authority="OPTIONAL_INTELLIGENCE_ONLY")
    try:
        boot = discover_boot(state / "workspace")
    except (ET.ParseError, OSError, Blocked) as exc:
        return dict(status="INCONCLUSIVE", reason=str(exc), applicability="UNKNOWN")
    if boot is None:
        return dict(status="NOT_APPLICABLE", reason="No root Boot parent/imported BOM discovered; not exhaustive reactor discovery")
    executable = config["executable"] or task["tools"]["sbri_reference"] or shutil.which("sbri")
    resolved = shutil.which(str(executable)) if executable else None
    if not resolved:
        return dict(status="UNAVAILABLE", reason="Existing SBRI CLI not found; no release/security conclusion", baseline=boot)
    if runner is None:
        require_independent_authority()
    tree = snapshot(state / "workspace", task)
    request = dict(config=config, tree=tree, taskDigest=bound["taskDigest"], executable=str(Path(resolved).resolve()),
                   executableStat=Path(resolved).stat().st_mtime_ns, scanner=task["scanner"],
                   maven=task["tools"]["maven"], osv=task["tools"]["osv"])
    key = digest(request)
    with lock(state):
        root = state / "sbri"
        attempt = root / key
        if (attempt / "result.json").exists():
            return dict(read(attempt / "result.json"), reused=True)
        if (attempt / "intent.json").exists():
            raise Blocked("Interrupted SBRI claim; inspect evidence, no automatic duplicate execution")
        if len(list(root.glob("*/intent.json"))) >= task["limits"]["max_sbri_calls"]:
            raise Blocked("SBRI investigation budget exhausted")
        write(attempt / "intent.json", request, exclusive=True)
    source = attempt / "source"
    export(state / "workspace", tree, source)
    output = attempt / "output"
    argv = [resolved, "evaluate", "--project", str(source), "--output", str(output),
            "--max-candidates", str(config["max_candidates"]), "--scopes", ",".join(config["scopes"]),
            "--maven", task["tools"]["maven"], "--scanner", task["tools"]["osv"]]
    if config["versions"]:
        argv += ["--releases", ",".join(config["versions"])]
    if config["ranges"]:
        argv += ["--range", ",".join(config["ranges"])]
    remaining = min(task["limits"]["validation_seconds"],
                    int(bound["createdAt"] + task["limits"]["task_seconds"] - time.time()))
    if remaining <= 0:
        raise Blocked("SBRI task time budget exhausted")
    execution = (runner or command)(argv, source, remaining, attempt / "command.json")
    raw = read(output / "result.json") if (output / "result.json").is_file() else {}
    selection = raw.get("execution", {}).get("release_selection", {})
    releases = raw.get("releases", [])
    complete = (execution["exitCode"] == 0 and not execution.get("timedOut")
        and raw.get("status") == "SUCCESS" and isinstance(releases, list) and bool(releases)
        and all(isinstance(r, dict) and r.get("assessment_status") == "COMPLETE" for r in releases)
        and set(config["versions"]) <= {r.get("version") for r in releases}
        and not raw.get("errors"))
    result = dict(status="COMPLETE" if complete else "INCONCLUSIVE", sourceStatus=raw.get("status"),
        authority="OPTIONAL_INTELLIGENCE_ONLY", tree=tree, taskDigest=bound["taskDigest"], request=request,
        baseline=boot, scopes=config["scopes"], selection=selection,
        releases=releases, errors=raw.get("errors", []),
        evidence=str(attempt.relative_to(state)), resultPath=str((output / "result.json").relative_to(state)),
        compatibility="NOT_ASSESSED", candidateCoverage="Only recorded successfully assessed releases/scopes",
        rankIsNotStrategy=True, reused=False)
    if snapshot(state / "workspace", task) != tree:
        raise Blocked("Source changed during SBRI; evidence cannot be associated with this candidate")
    write(attempt / "result.json", result, exclusive=True)
    return result
