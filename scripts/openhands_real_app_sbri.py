#!/usr/bin/env python3
"""Run existing SBRI collector against verified real-app baseline; no OpenHands/model/PR.

Output directory is unique. This invokes Maven/OSV for evaluated release candidates,
which may download dependencies and use network resources. Does not edit source.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from openhands_real_app_prepare import REPOSITORY, REFERENCE, SHA, MODULES, run_git

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.openhands.sbri_integration import run_pre_edit_intelligence

OBJECTIVE = ("Investigate and remediate security vulnerabilities in a Spring Boot Maven "
             "multimodule dependency graph; compare credible release and independent "
             "dependency strategies while preserving application compatibility.")


def assess(project: Path, original: Path, osv: Path, output: Path, expected: str,
           scanner: Path, releases: str | None, ranges: str | None, max_candidates: int) -> dict:
    if not SHA.fullmatch(expected):
        raise ValueError("Exact source commit is required")
    if output.exists() or output.is_symlink():
        raise ValueError("SBRI destination already exists")
    project, original, osv, scanner = (
        project.resolve(strict=True), original.resolve(strict=True),
        osv.resolve(strict=True), scanner.resolve(strict=True))
    if not scanner.is_file() or scanner.is_symlink():
        raise ValueError("Scanner binary unavailable")
    source = json.loads((original / "summary.json").read_text(encoding="utf-8"))
    finding = json.loads((osv / "summary.json").read_text(encoding="utf-8"))
    if (source.get("commit") != expected or source.get("repository") != REPOSITORY
            or source.get("runs", {}).get("maven", {}).get("status") != "BUILD_PASSED"
            or finding.get("commit") != expected or finding.get("repository") != REPOSITORY
            or finding.get("osvStatus") != "REPORT_RECORDED_REQUIRES_FINDING_REVIEW"):
        raise ValueError("Maven/OSV baseline metadata incomplete or mismatched")
    for file, digest in ((original / "maven.stdout", source["runs"]["maven"]["stdoutSha256"]),
                         (original / "maven.stderr", source["runs"]["maven"]["stderrSha256"]),
                         (osv / "osv.stdout", finding["osvStdoutSha256"]),
                         (osv / "osv.stderr", finding["osvStderrSha256"])):
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError("Original baseline evidence checksum mismatch")
    if (run_git("-C", str(project), "rev-parse", "HEAD") != expected
            or run_git("-C", str(project), "status", "--porcelain")
            or run_git("-C", str(project), "remote", "get-url", "origin") != REPOSITORY):
        raise ValueError("Project identity or clean source verification failed")
    if run_git("ls-remote", "--exit-code", REPOSITORY, "refs/heads/" + REFERENCE).split()[0] != expected:
        raise ValueError("Remote branch changed since baseline")
    for file in ("pom.xml", *(module + "/pom.xml" for module in MODULES)):
        if not (project / file).is_file():
            raise ValueError("Maven reactor structure changed")
    output.mkdir(parents=True, mode=0o700)
    record = run_pre_edit_intelligence(
        control_repo=ROOT, project=project, task=OBJECTIVE, state_dir=output,
        scanner=scanner, release_versions=releases, release_ranges=ranges,
        max_candidates=max_candidates, enabled=True)
    summary = {"status": record.get("status"), "applicability": record.get("applicability"),
               "exitCode": record.get("exitCode"), "sourceUnchanged": record.get("sourceUnchanged"),
               "resultPath": record.get("resultPath"), "summaryPath": record.get("summaryPath"),
               "releaseSelection": record.get("releaseSelection"),
               "baselineCommit": expected, "modelInvoked": False,
               "pullRequestCreated": False, "durableTaskRegistered": False}
    (output / "assessment-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--maven-evidence", type=Path, required=True)
    p.add_argument("--osv-evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--expected-commit", required=True)
    p.add_argument("--scanner", type=Path, required=True)
    selection = p.add_mutually_exclusive_group()
    selection.add_argument("--releases")
    selection.add_argument("--range", dest="ranges")
    p.add_argument("--max-candidates", type=int, default=6)
    args = p.parse_args()
    try:
        result = assess(args.project, args.maven_evidence, args.osv_evidence, args.output,
                        args.expected_commit, args.scanner, args.releases, args.ranges,
                        args.max_candidates)
    except Exception as exc:
        result = {"status": "BLOCKED", "errorType": type(exc).__name__,
                  "errorDetail": str(exc)[:180], "noModelRun": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"COMPLETE", "PARTIAL"} else 1

if __name__ == "__main__":
    sys.exit(main())
