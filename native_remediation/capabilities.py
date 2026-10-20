"""Agent evidence capabilities reuse the existing validator and SBRI CLI.

Neither path writes Stop feedback/acceptance, consumes Stop attempts or delivers.
"""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess
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


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def diagnostic_text(value):
    """Bound optional-tool feedback using the installed SDK's secret redactor.

    Full command output stays in private evidence, never in task prompts.
    This redactor is best-effort, not an authority/isolation boundary.
    """
    try:
        from openhands.sdk.utils.redact import redact_text_secrets
    except ImportError:
        return "Inspect private evidence (SDK diagnostic redactor unavailable)"
    return redact_text_secrets(str(value))[-2000:]


def executable_identity(executable):
    resolved = shutil.which(str(executable))
    if not resolved:
        return dict(path=str(executable), available=False)
    path = Path(resolved).resolve()
    return dict(path=str(path), sha256=file_sha256(path),
                mtimeNs=path.stat().st_mtime_ns)


def cached_sbri(state, attempt, request):
    """Checksums detect accidental/observed tampering, not host-user isolation."""
    path = attempt / "result.json"
    if not path.exists() or not (attempt / "result-digest.json").exists():
        return None
    try:
        result = read(path)
        if (read(attempt / "result-digest.json")["sha256"] != digest(result)
                or result["request"] != request):
            raise Blocked("SBRI cached evidence integrity mismatch")
        raw = attempt / "output/result.json"
        if result["rawSha256"] != (file_sha256(raw) if raw.exists() else None):
            raise Blocked("SBRI canonical result changed after capture")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Blocked("SBRI cache evidence is invalid or inaccessible") from exc
    return result


def sbri(state, *, versions=None, ranges=None, scopes=None, refresh=False, runner=None):
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
    tree = snapshot(state / "workspace", task)
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
    try:
        request = dict(config=config, tree=tree, taskDigest=bound["taskDigest"],
            conversationId=bound["conversationId"], executable=executable_identity(resolved),
            scanner=task["scanner"], profiles=task["tools"]["profiles"],
            maven=executable_identity(task["tools"]["maven"]), osv=executable_identity(task["tools"]["osv"]))
    except OSError:
        return dict(status="UNAVAILABLE", reason="SBRI/tool executable identity cannot be read", tree=tree)
    key = digest(request)
    with lock(state):
        root = state / "sbri"
        claims = list(root.glob("*/intent.json"))
        matching = []
        for claim in claims:
            try:
                intent = read(claim)
                if "cacheKey" in intent and intent["cacheKey"] != digest(intent["request"]):
                    raise Blocked("SBRI claim evidence checksum mismatch")
                if intent.get("cacheKey") == key:
                    if intent["request"] != request:
                        raise Blocked("SBRI claim identity mismatch")
                    matching.append((intent["at"], claim.parent))
            except (ValueError, KeyError, TypeError) as exc:
                raise Blocked("SBRI claim evidence is invalid") from exc
        if matching:
            _, previous = max(matching)
            result = cached_sbri(state, previous, request)
            if result is None:
                return dict(status="INCONCLUSIVE", reason="Interrupted/in-flight SBRI claim; no automatic duplicate execution",
                            tree=tree, evidence=str(previous.relative_to(state)))
            if result.get("retryable") is False:
                return dict(result, reused=True, reason="Execution termination is uncertain; no automatic or refresh replay")
            age = time.time() - result["completedAt"]
            lifetime = config["cache_seconds"] if result["status"] == "COMPLETE" else config["retry_seconds"]
            if not refresh and 0 <= age < lifetime:
                return dict(result, reused=True, retryAfterSeconds=max(0, int(lifetime - age)))
        if len(claims) >= task["limits"]["max_sbri_calls"]:
            return dict(status="INCONCLUSIVE", reason="SBRI investigation budget exhausted; use other evidence",
                        tree=tree, evidence="sbri")
        attempt = root / (key if not matching else key + "-" + str(len(claims) + 1))
        write(attempt / "intent.json", dict(cacheKey=key, request=request, at=time.time()), exclusive=True)
    source = attempt / "source"
    export(state / "workspace", tree, source)
    output = attempt / "output"
    argv = [resolved, "evaluate", "--project", str(source), "--output", str(output),
            "--max-candidates", str(config["max_candidates"]), "--scopes", ",".join(config["scopes"]),
            "--maven", task["tools"]["maven"], "--scanner", task["tools"]["osv"]]
    if task["tools"]["profiles"]:
        argv += ["--profiles", ",".join(task["tools"]["profiles"])]
    if config["versions"]:
        argv += ["--releases", ",".join(config["versions"])]
    if config["ranges"]:
        argv += ["--range", ",".join(config["ranges"])]
    remaining = min(task["limits"]["validation_seconds"],
                    int(bound["createdAt"] + task["limits"]["task_seconds"] - time.time()))
    if remaining <= 0:
        remaining = 0
    argv += ["--timeout", str(max(1, min(task["limits"]["command_seconds"], remaining)))]
    raw, raw_sha, failure, execution = {}, None, [], {}
    raw_path = output / "result.json"
    unavailable, retryable = False, True
    try:
        if remaining == 0:
            failure.append("SBRI task admission budget exhausted")
        else:
            execution = (runner or command)(argv, source, remaining, attempt / "command.json")
            if raw_path.is_file():
                raw_sha = file_sha256(raw_path)
                raw = read(raw_path)
            else:
                failure.append("SBRI result.json is missing")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        write(attempt / "execution-error.json", dict(type=type(exc).__name__, message=str(exc)))
        failure.append("Optional SBRI execution/report failure: " + type(exc).__name__
                       + ": " + diagnostic_text(exc))
        unavailable = isinstance(exc, (FileNotFoundError, PermissionError))
        retryable = not isinstance(exc, subprocess.TimeoutExpired)
    if execution and (execution.get("exitCode") != 0 or execution.get("timedOut")):
        failure.append("SBRI command exitCode=" + str(execution.get("exitCode"))
                       + ", timedOut=" + str(execution.get("timedOut")) + ": "
                       + diagnostic_text(execution.get("stderr") or execution.get("stdout") or "No command output"))
    if raw_sha is None and raw_path.is_file():
        try:
            raw_sha = file_sha256(raw_path)
        except OSError:
            failure.append("SBRI raw evidence is inaccessible")
    if not isinstance(raw, dict):
        raw = {}
        failure.append("SBRI result is not an object")
    details = raw.get("execution") if isinstance(raw.get("execution"), dict) else {}
    selection = details.get("release_selection") if isinstance(details.get("release_selection"), dict) else {}
    releases = raw.get("releases") if isinstance(raw.get("releases"), list) else []
    selected = selection.get("resolved_candidates", [])
    complete = (not failure and execution.get("exitCode") == 0 and not execution.get("timedOut")
        and raw.get("schema_version") == "1.0" and raw.get("status") == "SUCCESS" and bool(releases)
        and details.get("profiles") == task["tools"]["profiles"] and details.get("scopes") == config["scopes"]
        and isinstance(selected, list) and bool(selected) and all(isinstance(v, str) for v in selected)
        and len(selected) <= config["max_candidates"]
        and all(isinstance(r, dict) and isinstance(r.get("version"), str) and re.fullmatch(r"\d+\.\d+\.\d+", r["version"])
                and r.get("assessment_status") == "COMPLETE" for r in releases)
        and {boot, *selected} == {r["version"] for r in releases}
        and len(releases) == len({r["version"] for r in releases})
        and (not config["versions"] or set(config["versions"]) == set(selected))
        and isinstance(raw.get("errors", []), list) and not raw.get("errors"))
    if not complete and not failure:
        failure.append("SBRI execution, release evaluations, profiles/scopes or result schema are incomplete")
    result = dict(status="COMPLETE" if complete else "UNAVAILABLE" if unavailable else "INCONCLUSIVE", sourceStatus=raw.get("status"),
        authority="OPTIONAL_INTELLIGENCE_ONLY", tree=tree, taskDigest=bound["taskDigest"], request=request,
        baseline=boot, scopes=config["scopes"], selection=selection,
        releases=releases, errors=raw.get("errors", []), reasons=failure,
        execution={k: execution.get(k) for k in ("exitCode", "timedOut", "seconds")},
        commandEvidence=(str((attempt / "command.json").relative_to(state))
                         if (attempt / "command.json").is_file() else None),
        executionErrorEvidence=(str((attempt / "execution-error.json").relative_to(state))
                                if (attempt / "execution-error.json").is_file() else None),
        evidence=str(attempt.relative_to(state)), resultPath=str((output / "result.json").relative_to(state)),
        compatibility="NOT_ASSESSED", candidateCoverage="Only recorded successfully assessed releases/scopes",
        rankIsNotStrategy=True, reused=False, retryable=retryable, rawSha256=raw_sha, completedAt=time.time())
    if snapshot(state / "workspace", task) != tree:
        raise Blocked("Source changed during SBRI; evidence cannot be associated with this candidate")
    # Recheck task binding as well as the source before retaining reusable evidence.
    if context(state)[1] != bound:
        raise Blocked("Task binding changed during SBRI")
    with lock(state):
        write(attempt / "result.json", result, exclusive=True)
        write(attempt / "result-digest.json", dict(sha256=digest(result)), exclusive=True)
    return result
