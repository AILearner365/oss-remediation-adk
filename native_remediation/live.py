"""Cloud Shell batch entry point: bootstrap, call the product CLI once, report.

No agent loop or alternate product execution. Public evidence is a strict data
projection, not arbitrary log text with best-effort credential redaction.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import uuid

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from native_remediation.contract import load_task
from native_remediation.files import Blocked, digest, read, write
from native_remediation.scanners import SCANNERS

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "autonomous-oss-remediation"
REMOTES = {"https://github.com/AILearner365/oss-remediation-adk.git",
           "https://github.com/AILearner365/oss-remediation-adk",
           "git@github.com:AILearner365/oss-remediation-adk.git"}
OUTCOMES = {"COMPLETE", "PASS", "FAIL", "INCONCLUSIVE", "UNAVAILABLE", "DISABLED", "NOT_APPLICABLE",
            "VALIDATED", "DELIVERED", "BOUNDED_FAILURE", "BLOCKED", "PENDING", "NOT_REQUESTED", "CONFIRMED"}
REASONS = {
    "Unexpected OSV package identity", "Maven build/tests failed; see private build evidence",
    "Maven dependency resolution/effective model failed", "Executed tests below the configured minimum",
    "OSV error/incomplete extraction; absence of findings is not PASS",
    "OSV exit/report disagreement or incomplete resolved-package coverage",
    "Missing reactor dependency graphs or zero external dependencies",
    "Remaining vulnerabilities exceed acceptance policy", "New vulnerabilities introduced",
    "Requested vulnerability identifiers remain", "Additional acceptance check failed",
    "Resolved dependency/scanner coverage is incomplete", "Baseline/candidate evidence incomplete",
    "Candidate already rejected in this cycle", "Native terminal without trusted acceptance/delivery result",
}
CHECKS = {"sdk", "model", "tools", "adc_and_delivery", "base"}


class GitFailure(Blocked):
    def __init__(self, operation, detail):
        super().__init__("Evidence Git operation failed: " + operation)
        self.detail = detail  # Private only, possibly credential-bearing.


def utc():
    return datetime.now(timezone.utc).isoformat()


def enum(value, allowed, missing="NOT_EXECUTED"):
    return value if isinstance(value, str) and value in allowed else missing


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def public_vulnerabilities(groups):
    """Structured finding facts only: never scanner prose, logs or arbitrary URLs."""
    def versions(values):
        return [v for v in values if isinstance(v, str) and re.fullmatch(r'[0-9][A-Za-z0-9_.+\-]{0,99}', v)]
    def ids(values):
        return [v for v in values if isinstance(v, str) and re.fullmatch(r'(?:CVE|GHSA|OSV|XRAY|JFROG)-[A-Za-z0-9-]{1,100}', v)]
    def coordinate(value):
        return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+', value)
    result = {}
    for category in ('resolved', 'remaining', 'introduced', 'unknown'):
        rows = []
        for finding in groups.get(category, []):
            if not coordinate(finding.get('package')):
                rows.append(dict(identity='UNPROVEN_OR_PRIVATE', ids=ids(finding.get('ids', []))))
                continue
            row = dict(package=finding['package'], ids=ids(finding.get('ids', [])))
            for key in ('baselineVersions', 'candidateVersions', 'baselineDependencyVersions', 'candidateDependencyVersions'):
                row[key] = versions(finding.get(key, []))
            for side in ('baseline', 'candidate'):
                source = finding.get(side + 'Findings', [])
                fixed = {v for f in source for v in versions(f.get('fixedVersions', []))}
                fixed.update({v for f in source for a in f.get('affected', [])
                    if a.get('package', {}).get('name') == finding['package']
                    for r in a.get('ranges', []) for event in r.get('events', []) for v in versions([event.get('fixed')])})
                row[side + 'FixedVersions'] = sorted(fixed)
                row[side + 'Severity'] = [dict(type=s['type'], score=s['score']) for f in source for s in f.get('severity', [])
                    if isinstance(s, dict) and s.get('type') in ('CVSS_V2', 'CVSS_V3', 'CVSS_V4')
                    and re.fullmatch(r'[A-Za-z0-9:/._-]{1,300}', str(s.get('score', '')))]
            paths = finding.get('dependencyPaths', {})
            row['dependencyPaths'] = {side: [path for path in paths.get(side, [])
                if isinstance(path, list) and all(isinstance(v, str) and '@' in v
                    and coordinate(v.rsplit('@', 1)[0]) and versions([v.rsplit('@', 1)[1]]) for v in path)]
                for side in ('baseline', 'candidate')}
            row['sourceEvidence'] = ['scan.json', 'resolved.json']
            rows.append(row)
        result[category] = rows
    return result


class Projection:
    def __init__(self, state):
        self.state = Path(state).resolve()
        self.references = {}
        self.issues = []

    def get(self, name):
        path = self.state / name
        if not path.exists() and not path.is_symlink():
            return {}
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(self.state) or path.stat().st_size > 20_000_000:
                raise ValueError("Unsafe/oversized evidence")
            data = path.read_bytes()
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("Expected object")
            self.references[name] = hashlib.sha256(data).hexdigest()
            return result
        except (OSError, ValueError):
            self.issues.append("UNREADABLE_OR_UNSAFE_ARTIFACT")
            return {}

    def reasons(self, rows):
        if not isinstance(rows, list):
            self.issues.append("INVALID_REASON_RECORD")
            return []
        return [dict(code=text if text in REASONS else "PRIVATE_DIAGNOSTIC",
                     sha256=digest(text)) for text in rows if isinstance(text, str)]

    def evaluation(self, name):
        row = self.get(name)
        inventory = row.get("inventory", {})
        coverage = row.get("coverage", {})
        commands = []
        for label in ("build", "resolve", "scanner-version", "scan"):
            prefix = Path("baseline") if name == "baseline.json" else Path(name).parent
            record = self.get(str(prefix / label) + ".json")
            commands.append(dict(command=label, status="RECORDED" if record else "NOT_EXECUTED",
                exitCode=number(record.get("exitCode")), timedOut=record.get("timedOut") is True,
                seconds=number(record.get("seconds"))))
        findings = row.get("findings")
        ids = sorted({v for f in (findings or []) if isinstance(f, dict) for v in f.get("ids", [])
            if isinstance(v, str) and re.fullmatch(r"(?:CVE-\d{4}-\d{4,}|GHSA-[23456789cfghjmpqrvwx]{4}(?:-[23456789cfghjmpqrvwx]{4}){2})", v)})
        scan = self.get(str(prefix / "scan.json"))
        try:
            raw = json.loads(scan.get("stdout", "{}"))
            packages = [p.get("package", {}) for r in raw.get("results", []) for p in r.get("packages", [])]
            observed = {(p.get("name"), p.get("version")) for p in packages if p.get("ecosystem") == "Maven"}
            expected = {(p["name"], p["version"]) for p in inventory.get("packages", [])}
            raw_scan = dict(reportedPackages=len(packages), identityMatch=bool(expected) and observed == expected,
                unexpectedPackages=len(observed - expected)) if scan else None
        except (ValueError, TypeError, AttributeError):
            raw_scan = dict(status="MALFORMED_PRIVATE_SCANNER_RESPONSE")
        comparison = {}
        if isinstance(findings, list):
            # Same-tree comparison normalizes duplicate aliases for baseline evidence.
            from native_remediation.validation import finding_comparison
            comparison = public_vulnerabilities(finding_comparison(row, row, coverage.get('complete') is True))
        return dict(outcome=enum(row.get("outcome"), OUTCOMES), reasons=self.reasons(row.get("reasons", [])),
            tests=number(row.get("tests")), resolvedPackages=len(inventory["packages"]) if "packages" in inventory else None,
            modules=len(inventory["modules"]) if "modules" in inventory else None, commands=commands,
            scanner=dict(type=enum(row.get('scanner', {}).get('type', 'osv'), SCANNERS),
                version=row.get('scanner', {}).get('version') if re.fullmatch(r'[0-9][A-Za-z0-9_.+-]{0,80}', str(row.get('scanner', {}).get('version'))) else None,
                coverageComplete=coverage.get('complete') is True,
                status=enum(row.get('status'), {'COMPLETE', 'INCONCLUSIVE', 'FAILED'}),
                expected=number(coverage.get('expected')), scanned=number(coverage.get('scanned')),
                findingRecords=len(findings) if isinstance(findings, list) else None), vulnerabilities=comparison,
            osv=dict(coverageComplete=coverage.get("complete") is True,
                expected=number(coverage.get("expected")), scanned=number(coverage.get("scanned")),
                findings=len(findings) if isinstance(findings, list) else None,
                findingsStatus="NORMALIZED" if isinstance(findings, list) else "NOT_ASSESSED",
                rawInventory=raw_scan, publicFindingIds=ids))


def export_report(state, invocation):
    """Read-only on state. Never publish task prose, logs, argv, files or secrets."""
    p = Projection(state)
    bound = p.get("task.json")
    task = load_task(bound["task"]) if bound.get("task") else None
    if not task and invocation.get("task"):
        task = load_task(invocation["task"])
    if task and bound and bound.get("taskDigest") != digest(task):
        p.issues.append("TASK_IDENTITY_MISMATCH")
    baseline = p.evaluation("baseline.json")
    prep = p.get("preparation.json")
    prep_intent = p.get("preparation-intent.json")
    result = p.get("result.json")
    sbri = p.get("sbri-pre-edit.json")
    attempts = []
    for path in sorted((p.state / "attempts").glob("*/intent.json")):
        if not path.parent.name.isdecimal():
            continue
        prefix = "attempts/" + path.parent.name
        p.get(prefix + "/intent.json")
        accepted = p.get(prefix + "/validation.json")
        attempts.append(dict(attempt=int(path.parent.name), outcome=enum(accepted.get("outcome"), OUTCOMES, "INTERRUPTED"),
            reasons=p.reasons(accepted.get("reasons", [])), evaluation=p.evaluation(prefix + "/candidate/evaluation.json"),
            summary={key: number(accepted.get('summary', {}).get(key)) for key in ('baseline', 'resolved', 'remaining', 'introduced', 'unknown')},
            vulnerabilities=public_vulnerabilities(accepted.get('vulnerabilities', {})),
            checks={key: enum(value, {'PASS', 'FAIL', 'INCONCLUSIVE'}) for key, value in accepted.get('checks', {}).items()
                if key in {'build', 'tests', 'scanCoverage', 'remediation', 'newVulnerabilities', 'springBootPolicy', 'javaPolicy', 'dependencyPolicy', 'evidenceIntegrity', 'taskChecks'}},
            tree=accepted.get("validatedTree") if re.fullmatch(r"[0-9a-f]{40}", str(accepted.get("validatedTree"))) else None))
    events = []
    status, usage = "NOT_INITIALIZED", {}
    cid = bound.get("conversationId")
    try:
        cid = str(uuid.UUID(cid))
    except (ValueError, TypeError, AttributeError):
        cid = None
    if cid:
        native = "conversations/" + uuid.UUID(cid).hex
        native_state = p.get(native + "/base_state.json")
        status = enum(native_state.get("execution_status"), {"idle", "running", "paused", "finished", "stuck", "error"}, "UNKNOWN")
        for metric in native_state.get("stats", {}).get("usage_to_metrics", {}).values():
            for key in ("accumulated_cost",):
                usage[key] = usage.get(key, 0) + (number(metric.get(key)) or 0)
            for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cache_read_tokens", "cache_write_tokens"):
                usage[key] = usage.get(key, 0) + (number((metric.get("accumulated_token_usage") or {}).get(key)) or 0)
        for path in sorted((p.state / native / "events").glob("event-*.json")):
            if re.fullmatch(r"event-\d{5,}-[0-9a-fA-F-]{8,}\.json", path.name):
                events.append(p.get(native + "/events/" + path.name))
    claimed = bool(list((p.state / "runs").glob("*.json")))
    responses = sum(e.get("source") == "agent" and e.get("kind") in ("ActionEvent", "MessageEvent") for e in events)
    final = enum(result.get("outcome"), OUTCOMES, "NO_PRODUCT_RESULT")
    if final == "NO_PRODUCT_RESULT":
        if baseline["outcome"] in ("FAIL", "INCONCLUSIVE"):
            final = "BASELINE_FAILED_BEFORE_INFERENCE" if not claimed else "BASELINE_FAILED"
        elif invocation.get("interrupted"):
            final = "INTERRUPTED"
        elif attempts and attempts[-1]["outcome"] in ("FAIL", "INCONCLUSIVE"):
            final = "STOP_DENIED"
        elif invocation.get("failedPhase"):
            final = "INVOCATION_FAILED"
        elif status in ("running", "error", "paused", "stuck") or claimed:
            final = "INTERRUPTED_OR_UNACCEPTED"
    if final in ("VALIDATED", "DELIVERED"):
        attempt = result.get("attempt", p.get("feedback.json").get("attempt"))
        if type(attempt) is not int or attempt < 1:
            attempt = 0
        acceptance = p.get("attempts/" + str(attempt) + "/validation.json")
        candidate = p.get("attempts/" + str(attempt) + "/evaluation.json")
        if (acceptance.get("outcome") != "PASS" or acceptance.get("taskDigest") != bound.get("taskDigest")
                or acceptance.get("conversationId") != cid or acceptance.get("validatedTree") != result.get("validatedTree")
                or acceptance.get("candidateDigest") != digest(candidate)
                or acceptance.get("baselineDigest") != digest(p.get("baseline.json"))):
            final = "INCONSISTENT_RESULT"
            p.issues.append("RESULT_WITHOUT_BOUND_ACCEPTANCE")
        elif status != "finished":
            final += "_AWAITING_NATIVE_FINISH"
    records = []
    for path in sorted((p.state / "journal").glob("*.json")):
        if re.fullmatch(r"(?:decision-\d+|outcome-\d+|\d+\.(?:intent|outcome))\.json", path.name):
            record = p.get("journal/" + path.name)
            records.append(dict(reference="journal/" + path.name, cycle=number(record.get("cycle")),
                goalStatus=enum(record.get("document", {}).get("goal_status"), {"candidate_ready", "bounded_failure"}, "NOT_RECORDED")))
    intelligence = []
    for path in sorted((p.state / "sbri").glob("*/result.json")):
        if re.fullmatch(r"[0-9a-f]{64}(?:-\d+)?", path.parent.name):
            record = p.get("sbri/" + path.parent.name + "/result.json")
            intelligence.append(dict(reference="sbri/" + path.parent.name + "/result.json",
                outcome=enum(record.get("status"), OUTCOMES), reasons=p.reasons(record.get("reasons", [])),
                assessedReleases=sum(r.get("assessment_status") == "COMPLETE" for r in record.get("releases", []))))
    claim = p.get("delivery.json")
    pr_url = result.get("prUrl") or claim.get("prUrl")
    if not task or not isinstance(pr_url, str) or not re.fullmatch("https://github.com/" + re.escape(task["repository"]) + r"/pull/\d+", pr_url):
        pr_url = None
    checks = invocation.get("checks", {})
    report = dict(schemaVersion=1, runId=invocation["runId"], timestamp=invocation["startedAt"],
        kind="EXISTING_STATE_EXPORT" if invocation.get("reportOnly") else "REAL_PRODUCT_INVOCATION",
        taskIdentity=dict(digest=digest(task) if task else None, repository=task["repository"] if task else None,
            baseSha=task["base_sha"] if task else None, baseBranch=task["base_branch"] if task else None,
            model=(task["model"] if task and re.fullmatch(r"vertex_ai/gemini-[a-z0-9.-]{1,100}", task["model"]) else None)), conversationId=cid,
        prerequisites={k: enum(checks.get(k), {"PASS", "FAIL", "NOT_CHECKED"}, "NOT_CHECKED") for k in sorted(CHECKS)},
        predictionAvailability="NOT_PROVEN_BY_PREFLIGHT", baseline=baseline,
        preparation=enum(prep.get("outcome"), OUTCOMES, "FAILED_OR_INTERRUPTED" if prep_intent else "NOT_EXECUTED"),
        sbri=dict(preEdit=enum(sbri.get("status"), OUTCOMES),
            retainedCalls=len(list((p.state / "sbri").glob("*/intent.json"))), results=intelligence),
        modelExecution=dict(nativeStatus=status, dispatchClaimed=claimed, observedResponseEvents=responses,
            status="RESPONSE_OBSERVED" if responses else "DISPATCH_CLAIMED_NO_RESPONSE_OBSERVED" if claimed else "NOT_EXECUTED", usage=usage),
        agent=dict(nativeEvents=len(events), decisions=len(list((p.state / "journal").glob("decision-*.json"))),
            outcomes=len(list((p.state / "journal").glob("*outcome*.json"))),
            records=records, narrative="PRIVATE_ONLY_NOT_AUTOMATICALLY_PUBLISHED"), attempts=attempts,
        final=dict(outcome=final, remediationSuccess=not p.issues and final in ("VALIDATED", "DELIVERED"),
            validation=enum(result.get("validationOutcome"), OUTCOMES), delivery=enum(result.get("deliveryStatus"), OUTCOMES),
            deliveryClaim=enum(claim.get("state"), {"CLAIMED", "PUSH_STARTED", "PR_POST_STARTED", "DELIVERED"}), prUrl=pr_url),
        invocation=dict(failedPhase=enum(invocation.get("failedPhase"), {"authorization", "task", "publication_precheck", "setup", "preflight", "execution"}, "NONE"),
            interrupted=invocation.get("interrupted") is True,
            phases=[dict(name=enum(r.get("name"), {"setup", "preflight", "execution"}, "UNKNOWN"),
                exitCode=number(r.get("exitCode"))) for r in invocation.get("phases", [])]),
        privateEvidence=dict(artifacts=p.references, retention="COMPLETE_PRIVATE_STATE_NOT_COPIED_TO_GIT"),
        reportComplete=not p.issues, reportIssues=p.issues,
        publication="REQUESTED_RECEIPT_STORED_PRIVATELY" if invocation.get("publish") else "NOT_AUTHORIZED",
        exclusions=["credentials", "raw logs/argv", "task/agent free text", "workspace snapshots", "private dependency names"])
    return report


def git(root, *args, env=None, input=None):
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        input=input, capture_output=True, text=True, env=env, timeout=120)
    if result.returncode:
        raise GitFailure(args[0], result.stderr)
    return result.stdout.strip()


def publishing_precheck(root):
    if git(root, "branch", "--show-current") != BRANCH:
        raise Blocked("Evidence publication requires autonomous-oss-remediation")
    for args in (("remote", "get-url", "--all", "origin"), ("remote", "get-url", "--push", "--all", "origin")):
        if git(root, *args) not in REMOTES:
            raise Blocked("Evidence remote is not the authorized product repository")
    head = git(root, "rev-parse", "HEAD")
    remote = git(root, "ls-remote", "--heads", "origin", "refs/heads/" + BRANCH).split()
    if not remote or remote[0] != head:
        raise Blocked("Product local/remote HEAD differ; publish existing work explicitly first")
    git(root, "var", "GIT_AUTHOR_IDENT")
    git(root, "var", "GIT_COMMITTER_IDENT")
    return head


def publish(root, report, expected_head):
    """Isolated index + compare-and-set branch; never stage unrelated user edits."""
    root = Path(root).resolve()
    if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{32}", report["runId"]):
        raise Blocked("Invalid evidence run identity")
    directory = root / "docs/evidence/live-runs" / report["runId"]
    if not directory.resolve().is_relative_to(root) or any(p.is_symlink() for p in (directory, *directory.parents) if p != root.parent):
        raise Blocked("Unsafe public evidence destination")
    directory.mkdir(parents=True, exist_ok=False)
    write(directory / "report.json", report, exclusive=True)
    relative = str((directory / "report.json").relative_to(root))
    gitdir = Path(git(root, "rev-parse", "--absolute-git-dir"))
    with (gitdir / "oss-evidence.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if publishing_precheck(root) != expected_head:
            raise Blocked("Product HEAD changed during run; evidence retained, no automatic merge/retry")
        with tempfile.TemporaryDirectory(prefix="oss-evidence-index-") as temp:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"))
            git(root, "read-tree", expected_head, env=env)
            # Hash canonical generated data directly: no user .gitattributes
            # clean filters may inject credential-bearing bytes into this blob.
            payload = json.dumps(report, sort_keys=True, indent=2) + "\n"
            blob = git(root, "hash-object", "-w", "--stdin", input=payload)
            git(root, "update-index", "--add", "--cacheinfo", "100644," + blob + "," + relative, env=env)
            tree = git(root, "write-tree", env=env)
            commit = git(root, "-c", "commit.gpgsign=false", "commit-tree", tree, "-p", expected_head,
                input="Sanitized remediation evidence " + report["runId"] + "\n")
            git(root, "update-ref", "refs/heads/" + BRANCH, commit, expected_head)
        # Synchronize just our new path in the user's index; unrelated staged
        # entries and worktree files remain untouched.
        git(root, "update-index", "--add", "--cacheinfo", "100644," + blob + "," + relative)
        git(root, "push", "origin", commit + ":refs/heads/" + BRANCH)
        observed = git(root, "ls-remote", "--heads", "origin", "refs/heads/" + BRANCH).split()
        if not observed or observed[0] != commit:
            raise Blocked("Evidence push not positively confirmed; do not blindly repeat")
    return dict(status="PUSHED_VERIFIED", commit=commit, report=relative)


def prerequisite_check(task_file, result_file):
    """Runs in the pinned SDK runtime; no inference or target writes."""
    from importlib.metadata import version
    import shutil
    from native_remediation import preflight, repository
    task = load_task(read(task_file))
    results, phase = {}, "sdk"
    try:
        if not version("openhands-sdk") == version("openhands-tools") == "1.55.1":
            raise Blocked("SDK and Tools must both be 1.55.1")
        results["sdk"] = "PASS"
        phase = "model"
        if not task["model"].startswith("vertex_ai/gemini-"):
            raise Blocked("Live entry requires the configured Vertex Gemini model")
        # A lifecycle date is not an inference availability probe. Keep the
        # approved model; only an actual provider response proves availability.
        results["model"] = "PASS"
        phase = "tools"
        for key in (("maven", "osv") if task['scanner']['type'] == 'osv' else ("maven",)):
            if not shutil.which(task["tools"][key]):
                raise Blocked("Configured tool executable unavailable: " + key)
        result = subprocess.run([task["tools"]["maven"], "--version"], capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise Blocked("Configured Maven/Java runtime is unavailable")
        if task['scanner']['type'] == 'osv':
            result = subprocess.run([task["tools"]["osv"], "--version"], capture_output=True, text=True, timeout=15)
            if result.returncode or 'osv-scanner version: ' + task['scanner']['version'] not in result.stdout:
                raise Blocked("Configured OSV scanner version mismatch")
        results["tools"] = "PASS"
        phase = "adc_and_delivery"
        preflight.check(task)
        results["adc_and_delivery"] = "PASS"
        phase = "base"
        repository.verify_base(task)
        results["base"] = "PASS"
    except Exception:
        results[phase] = "FAIL"
        raise
    finally:
        write(result_file, results)


def run_command(argv, job, label, phases, timeout=None):
    """Private logs; product retains its own lifecycle, budgets and recovery."""
    with (job / (label + ".stdout")).open("xb") as out, (job / (label + ".stderr")).open("xb") as err:
        with subprocess.Popen(argv, cwd=ROOT, stdout=out, stderr=err, start_new_session=True) as process:
            try:
                code = process.wait(timeout=timeout)
            except BaseException:
                for sig, wait in ((signal.SIGINT, 10), (signal.SIGTERM, 5), (signal.SIGKILL, 5)):
                    if process.poll() is not None:
                        break
                    os.killpg(process.pid, sig)
                    try:
                        process.wait(timeout=wait)
                    except subprocess.TimeoutExpired:
                        pass
                phases.append(dict(name=label, exitCode=process.returncode))
                raise
    phases.append(dict(name=label, exitCode=code))
    if code:
        raise Blocked(label + " failed; inspect private logs")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("live", "report"))
    parser.add_argument("--task", type=Path)
    parser.add_argument("--state", type=Path, help="Existing state, report only; never rerun")
    parser.add_argument("--authorize-model-execution", action="store_true")
    parser.add_argument("--publish-evidence", action="store_true")
    parser.add_argument("--runs-dir", type=Path, default=Path.home() / ".local/state/oss-remediation/live")
    args = parser.parse_args(argv)
    os.umask(0o077)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
    job = args.runs_dir.expanduser().resolve() / run_id
    job.mkdir(parents=True, exist_ok=False, mode=0o700)
    state = args.state.resolve() if args.action == "report" and args.state else job / "state"
    invocation = dict(runId=run_id, startedAt=utc(), reportOnly=args.action == "report", publish=args.publish_evidence, phases=[])
    phase, expected_head, receipt = "authorization", None, dict(status="NOT_AUTHORIZED")
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    old_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.action == "live" and (not args.authorize_model_execution or not args.task or args.state or not args.publish_evidence):
            raise Blocked("live requires --task, --authorize-model-execution and --publish-evidence, never --state")
        if args.action == "report" and (not args.state or not state.is_dir()):
            raise Blocked("report requires an existing --state; no execution occurs")
        phase = "task"
        task = load_task(read(args.task)) if args.action == "live" else load_task(read(state / "task.json")["task"])
        invocation["task"] = task
        write(job / "task-input.json", task, exclusive=True)
        if args.publish_evidence:
            phase = "publication_precheck"
            expected_head = publishing_precheck(ROOT)
        if args.action == "live":
            phase = "setup"
            run_command(["bash", str(ROOT / "scripts/openhands/sdk-cloudshell-setup.sh"), "prepare"], job, phase, invocation["phases"], 900)
            py = Path(os.environ.get("OPENHANDS_RUNTIME_ROOT", "/tmp/openhands-sdk-1.55.1")) / "venv/bin/python"
            phase = "preflight"
            run_command([str(py), "-c", "import sys; from native_remediation.live import prerequisite_check; prerequisite_check(sys.argv[1],sys.argv[2])",
                         str(job / "task-input.json"), str(job / "checks.json")], job, phase, invocation["phases"], 180)
            phase = "execution"
            run_command([str(py), "-m", "native_remediation", "start", "--task", str(job / "task-input.json"),
                         "--state", str(state), "--authorize-model-execution"], job, phase, invocation["phases"])
    except (Exception, KeyboardInterrupt) as exc:
        invocation.update(failedPhase=phase, interrupted=isinstance(exc, KeyboardInterrupt), errorType=type(exc).__name__)
        # Full details remain private; never serialize arbitrary exception text to Git.
        write(job / "failure.json", dict(errorType=type(exc).__name__, message=str(exc), gitDiagnostic=getattr(exc, "detail", None)))
    finally:
        try:
            invocation["checks"] = read(job / "checks.json") if (job / "checks.json").exists() else {}
        except (OSError, ValueError):
            invocation["checks"] = {}
            invocation["captureIncomplete"] = True
        write(job / "invocation.json", invocation)
        try:
            report = export_report(state, invocation)
            if invocation.get("captureIncomplete"):
                report["reportComplete"] = False
                report["reportIssues"].append("PREREQUISITE_EVIDENCE_UNREADABLE")
        except Exception as exc:
            report = dict(schemaVersion=1, runId=run_id, timestamp=invocation["startedAt"], reportComplete=False,
                          reportIssues=["EXPORT_FAILED"], final=dict(outcome="REPORT_INCOMPLETE"))
            write(job / "export-error.json", dict(errorType=type(exc).__name__))
        write(job / "report.json", report, exclusive=True)
        if args.publish_evidence:
            try:
                if expected_head is None:
                    expected_head = publishing_precheck(ROOT)
                receipt = publish(ROOT, report, expected_head)
            except Exception as exc:
                receipt = dict(status="PUBLICATION_FAILED", errorType=type(exc).__name__)
                write(job / "publication-error.json", dict(errorType=type(exc).__name__, message=str(exc), gitDiagnostic=getattr(exc, "detail", None)))
        write(job / "publication.json", receipt)
        signal.signal(signal.SIGTERM, old_term)
    print(json.dumps(dict(runId=run_id, privateRun=str(job), privateState=str(state), report=str(job / "report.json"),
                          outcome=report["final"]["outcome"], reportComplete=report["reportComplete"], publication=receipt)))
    return 0 if (report["reportComplete"] and report["final"]["outcome"] in ("VALIDATED", "DELIVERED")
                 and (not args.publish_evidence or receipt["status"] == "PUSHED_VERIFIED")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
