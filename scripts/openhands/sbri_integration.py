#!/usr/bin/env python3
"""Bounded pre-edit SBRI evidence for the existing OpenHands Gate-2 runner."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from spring_boot_release_intelligence.standalone import BOOT_METADATA, discover_boot_version


SECURITY_TERMS = ("vulnerability", "vulnerabilities", "security", "cve", "remediation")
DEPENDENCY_TERMS = ("dependency", "dependencies", "spring boot", "maven", "oss")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _tree_size(path: Path, pattern: str | None = None) -> tuple[int, int]:
    files = [item for item in path.rglob(pattern or "*") if item.is_file()] if path.exists() else []
    return len(files), sum(item.stat().st_size for item in files)


def _execute_sbri(command: list[str], *, cwd: Path, env: dict[str, str],
                  timeout: int, log: Path) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    peak_rss = 0
    while process.poll() is None:
        if time.monotonic() - started > timeout:
            process.kill(); process.wait()
            output = process.stdout.read() if process.stdout else ""
            log.write_text(output, encoding="utf-8")
            return {"exitCode": 124, "wallSeconds": time.monotonic() - started,
                    "peakProcessTreeRssKib": peak_rss, "timedOut": True}
        listing = subprocess.run(["ps", "-eo", "pid=,ppid=,rss="], text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        rows = []
        for line in listing.stdout.splitlines():
            try:
                rows.append(tuple(map(int, line.split())))
            except ValueError:
                continue
        descendants = {process.pid}
        changed = True
        while changed:
            changed = False
            for pid, parent, _rss in rows:
                if parent in descendants and pid not in descendants:
                    descendants.add(pid); changed = True
        peak_rss = max(peak_rss, sum(rss for pid, _parent, rss in rows if pid in descendants))
        time.sleep(0.1)
    output = process.stdout.read() if process.stdout else ""
    log.write_text(output, encoding="utf-8")
    return {"exitCode": process.returncode, "wallSeconds": time.monotonic() - started,
            "peakProcessTreeRssKib": peak_rss, "timedOut": False}


def applicability(project: Path, task: str) -> dict[str, Any]:
    lowered = task.lower()
    task_relevant = any(term in lowered for term in SECURITY_TERMS) and any(
        term in lowered for term in DEPENDENCY_TERMS
    )
    if not task_relevant:
        return {"applicable": False, "reason": "task is not Maven security remediation"}
    try:
        discovery = discover_boot_version(project)
    except Exception as error:
        return {"applicable": False, "reason": f"Spring Boot controller not discovered: {error}"}
    return {"applicable": True, "reason": "Spring Boot Maven security remediation",
            "baseline": discovery["version"], "controller": discovery["controller"]}


def discover_patch_candidates(baseline: str, *, limit: int = 3) -> tuple[list[str], dict]:
    """Discover bounded forward stable patches from current Maven Central metadata."""
    with urllib.request.urlopen(BOOT_METADATA, timeout=30) as response:
        raw = response.read()
    root = ET.fromstring(raw)
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", baseline)
    if not match:
        raise ValueError(f"baseline is not a stable numeric release: {baseline}")
    major, minor, patch = map(int, match.groups())
    eligible = []
    for node in root.findall(".//version"):
        candidate = node.text or ""
        parsed = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", candidate)
        if not parsed:
            continue
        values = tuple(map(int, parsed.groups()))
        if values[:2] == (major, minor) and values[2] > patch:
            eligible.append((values, candidate))
    selected = [value for _, value in sorted(eligible)[-limit:]]
    return selected, {"source": BOOT_METADATA, "sha256": hashlib.sha256(raw).hexdigest(),
                      "policy": f"latest {limit} stable forward patches in {major}.{minor}.x"}


def project_fingerprint(project: Path, request: dict) -> tuple[str, dict]:
    poms = sorted(project.rglob("pom.xml"))
    pom_hashes = {path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in poms if ".git" not in path.parts and "target" not in path.parts}
    state = {"head": _git(project, "rev-parse", "HEAD"), "status": _git(project, "status", "--porcelain"),
             "poms": pom_hashes, "request": request}
    digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    return digest, state


def _totals(counts: dict | None) -> dict | None:
    return None if counts is None else {name: sum(values.values()) for name, values in counts.items()}


def build_summary(result: dict, output: Path, *, max_changes: int = 12,
                  max_advisories: int = 10) -> tuple[str, dict]:
    baseline = result["application"]["original_spring_boot_version"]
    releases = []
    for release in result["releases"]:
        releases.append({"version": release["version"],
                         "assessmentStatus": release["assessment_status"],
                         "rank": release.get("rank"), "counts": _totals(release.get("counts")),
                         "remainingCriticalHigh": (None if release.get("counts", {}).get("remaining") is None else
                             release["counts"]["remaining"].get("CRITICAL", 0) +
                             release["counts"]["remaining"].get("HIGH", 0))})
    ranked = sorted((item for item in releases if item["rank"] is not None), key=lambda item: item["rank"])
    preferred = ranked[0]["version"] if ranked else None
    baseline_deps = {item["coordinate"]: item for item in result["dependencies"] if item["release"] == baseline}
    candidate_deps = {item["coordinate"]: item for item in result["dependencies"] if item["release"] == preferred}
    changes = []
    if preferred:
        for coordinate in sorted(set(baseline_deps) | set(candidate_deps)):
            before, after = baseline_deps.get(coordinate), candidate_deps.get(coordinate)
            before_version = before.get("selected_version") if before else None
            after_version = after.get("selected_version") if after else None
            if before_version != after_version or (after and after.get("ownership") in
                                                    {"BOOT_MANAGED_OVERRIDDEN", "OWNERSHIP_UNKNOWN"}):
                changes.append({"coordinate": coordinate, "baseline": before_version,
                                "candidate": after_version,
                                "ownership": (after or before).get("ownership"),
                                "override": (after or before).get("override_source")})
    advisories = [{"package": item["package"], "id": item["advisory_id"],
                   "severity": item["severity"], "fixed": item.get("fixed_versions", []),
                   "evidence": item.get("evidence_reference")}
                  for item in result["findings"]
                  if item["release"] == (preferred or baseline) and
                  item["severity"] in {"CRITICAL", "HIGH"}][:max_advisories]
    bounded = {"status": result["status"], "baseline": baseline,
               "evaluated": result["execution"]["evaluated_releases"], "releases": releases,
               "securityRankOne": preferred, "rankIsSecurityEvidenceOnly": True,
               "dependencyChanges": changes[:max_changes],
               "dependencyChangesOmitted": max(0, len(changes) - max_changes),
               "criticalHighAdvisorySample": advisories,
               "errors": result.get("errors", []),
               "artifacts": {"result": str(output / "result.json"),
                             "report": str(output / "report.html"),
                             "evidence": str(output / "evidence")}}
    lines = ["SBRI pre-edit release intelligence (security evidence; not an upgrade instruction)",
             f"Status: {bounded['status']}; baseline Spring Boot: {baseline}"]
    for item in releases:
        if item["counts"] is None:
            lines.append(f"- {item['version']}: {item['assessmentStatus']}; not ranked")
        else:
            count = item["counts"]
            lines.append(f"- {item['version']}: {item['assessmentStatus']}; rank={item['rank']}; "
                         f"original={count['original']}, addressed={count['addressed']}, "
                         f"remaining={count['remaining']}, new={count['new']}, total={count['total']}; "
                         f"remaining Critical+High={item['remainingCriticalHigh']}")
    if changes:
        lines.append("Relevant selected-version/ownership changes for security rank 1:")
        lines.extend(f"- {item['coordinate']}: {item['baseline']} -> {item['candidate']}; "
                     f"ownership={item['ownership']}" +
                     (f"; override={item['override']}" if item["override"] else "")
                     for item in changes[:max_changes])
    lines.extend([f"Full JSON: {bounded['artifacts']['result']}",
                  f"HTML: {bounded['artifacts']['report']}",
                  f"Raw evidence: {bounded['artifacts']['evidence']}",
                  "Use this with Maven/application compatibility evidence and consider credible targeted, "
                  "framework, override, or combined strategies. Independent validation remains authoritative."])
    return "\n".join(lines), bounded


def run_pre_edit_intelligence(*, control_repo: Path, project: Path, task: str,
                              state_dir: Path, scanner: Path | None = None,
                              config: Path | None = None, enabled: bool = True,
                              timeout: int = 2400) -> dict[str, Any]:
    started = time.monotonic()
    root = state_dir / "sbri"
    root.mkdir(parents=True, exist_ok=True)
    applicable = applicability(project, task)
    if not enabled or not applicable["applicable"]:
        record = {"status": "DISABLED" if not enabled else "NOT_APPLICABLE",
                  "applicability": applicable, "invoked": False, "reused": False}
        (root / "latest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return record
    try:
        candidates, discovery = discover_patch_candidates(applicable["baseline"])
    except Exception as error:
        candidates, discovery = [], {"error": str(error)}
    if not candidates:
        record = {"status": "NO_FORWARD_PATCH_CANDIDATES", "applicability": applicable,
                  "candidateDiscovery": discovery, "invoked": False, "reused": False,
                  "message": "No eligible forward stable patch was discovered; no upgrade was invented."}
        (root / "latest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return record
    request = {"baseline": applicable["baseline"], "releases": candidates,
               "scanner": str(scanner) if scanner else "osv-scanner",
               "config": str(config) if config else None, "candidateDiscovery": discovery}
    fingerprint, before = project_fingerprint(project, request)
    run_dir = root / fingerprint
    output = run_dir / "output"
    execution_path = run_dir / "execution.json"
    if execution_path.is_file() and (output / "result.json").is_file():
        record = json.loads(execution_path.read_text())
        record.update({"reused": True, "duplicateExecutionAvoided": True})
        (root / "latest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return record
    run_dir.mkdir(parents=True, exist_ok=True)
    command = [str(control_repo / "sbri"), "evaluate", "--project", str(project),
               "--releases", ",".join(candidates), "--output", str(output)]
    if scanner:
        command.extend(["--scanner", str(scanner)])
    if config:
        command.extend(["--config", str(config)])
    measurement = _execute_sbri(command, cwd=control_repo,
        env={**os.environ, "PYTHONPATH": str(control_repo)}, timeout=timeout,
        log=run_dir / "command.log")
    exit_code = measurement["exitCode"]
    after_fingerprint, after = project_fingerprint(project, request)
    result = json.loads((output / "result.json").read_text()) if (output / "result.json").is_file() else None
    summary_text, summary = build_summary(result, output) if result else (
        f"SBRI failed before producing usable result.json (exit {exit_code}). "
        f"Evidence: {run_dir / 'command.log'}", {"errors": []})
    (run_dir / "agent-summary.txt").write_text(summary_text + "\n", encoding="utf-8")
    (run_dir / "agent-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    cache_files, cache_bytes = _tree_size(output / "evidence/maven-repository")
    jar_count, jar_bytes = _tree_size(output / "evidence/maven-repository", "*.jar")
    output_files, output_bytes = _tree_size(output)
    record = {"status": ({0: "COMPLETE", 3: "PARTIAL", 2: "FAILED"}.get(exit_code,
                         "FAILED")), "applicability": applicable, "invoked": True, "reused": False,
              "duplicateExecutionAvoided": False, "exitCode": exit_code,
              "fingerprint": fingerprint, "request": request, "command": command,
              "elapsedSeconds": time.monotonic() - started, "measurement": measurement,
              "outputFiles": output_files, "outputBytes": output_bytes,
              "mavenCacheFiles": cache_files, "mavenCacheBytes": cache_bytes,
              "mavenCacheJarCount": jar_count, "mavenCacheJarBytes": jar_bytes,
              "sourceUnchanged": fingerprint == after_fingerprint and before == after,
              "sourceBefore": before, "sourceAfter": after,
              "summaryPath": str(run_dir / "agent-summary.txt"),
              "summaryJsonPath": str(run_dir / "agent-summary.json"),
              "resultPath": str(output / "result.json"), "reportPath": str(output / "report.html"),
              "evidencePath": str(output / "evidence"), "commandLog": str(run_dir / "command.log"),
              "agentContextCharacters": len(summary_text),
              "agentContextApproxTokens": (len(summary_text) + 3) // 4,
              "deliveredBeforeAgentRun": exit_code in (0, 3),
              "observedConsideredBeforeFirstDependencyEdit": "NOT_YET_OBSERVABLE",
              "rankForcedAsStrategy": False}
    execution_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    (root / "latest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def agent_message(record: dict) -> str:
    if not record.get("deliveredBeforeAgentRun"):
        reason = record.get("message") or record.get("applicability", {}).get("reason") or record["status"]
        return ("SBRI pre-edit intelligence is unavailable or not applicable: " + str(reason) +
                ". This is not evidence that Spring Boot upgrades are impossible; continue with other "
                "task-permitted investigation methods.")
    summary = Path(record["summaryPath"]).read_text(encoding="utf-8").strip()
    return (summary + "\n\nThis evidence was generated before your first action. Inspect the referenced "
            "artifacts as needed and make the remediation decision yourself; do not treat security rank 1 "
            "as a mandatory upgrade.")


def retain_review_bundle(latest: Path, destination: Path) -> None:
    """Copy bounded durable evidence while excluding caches and materialized workspaces."""
    record = json.loads(latest.read_text(encoding="utf-8"))
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(latest, destination / "latest.json")
    for key in ("summaryPath", "summaryJsonPath", "commandLog"):
        source = Path(record[key]) if record.get(key) else None
        if source and source.is_file():
            shutil.copy2(source, destination / source.name)
    result_path = Path(record["resultPath"]) if record.get("resultPath") else None
    if not result_path or not result_path.is_file():
        return
    source_output = result_path.parent
    target_output = destination / "output"
    target_output.mkdir(exist_ok=True)
    for name in ("result.json", "report.html"):
        source = source_output / name
        if source.is_file():
            shutil.copy2(source, target_output / name)
    source_evidence = source_output / "evidence"
    target_evidence = target_output / "evidence"
    for source in source_evidence.rglob("*") if source_evidence.exists() else []:
        relative = source.relative_to(source_evidence)
        if any(part in {"maven-repository", "work", "http-cache"} for part in relative.parts):
            continue
        if source.is_file() and source.stat().st_size:
            target = target_evidence / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
