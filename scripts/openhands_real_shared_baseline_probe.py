#!/usr/bin/env python3
"""Exercise the REAL shared deterministic Maven/OSV baseline on a disposable clone.

Not an OpenHands task launcher. No native /run, no model calls, no fixed-version
hints. Never mutates the user's baseline or existing Maven/OSV evidence.
"""
from __future__ import annotations

import argparse
from tempfile import TemporaryDirectory
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autonomous_oss_remediation_agent.config import MavenConfig, ScannerConfig
from openhands_shared.baseline import BaselineProfile, ExistingDeterministicBaselineRunner
from openhands_shared.contracts import TaskRequest

MODEL = "vertex_ai/gemini-2.5-flash"
KNOWN_ADVISORY = "GHSA-mjmj-j48q-9wg2"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        timeout=30, check=True
    )
    return result.stdout.strip()


def probe(base: Path, scanner: Path) -> dict:
    base = base.expanduser()
    scanner = scanner.expanduser()
    if base.is_symlink() or scanner.is_symlink():
        raise ValueError("Base repository and scanner may not be symbolic links")
    base, scanner = base.resolve(strict=True), scanner.resolve(strict=True)
    if not scanner.is_file() or not base.is_dir():
        raise ValueError("Scanner must be file and base repository a directory")
    head = git(base, "rev-parse", "--verify", "HEAD")
    original = (base / "pom.xml").read_bytes()
    committed = subprocess.run(
        ["git", "-C", str(base), "show", f"{head}:pom.xml"],
        capture_output=True, timeout=30, check=True
    ).stdout
    if original != committed:
        raise ValueError("Baseline POM is not identical to immutable commit")
    expected_scanner_sha = hashlib.sha256(scanner.read_bytes()).hexdigest()
    with TemporaryDirectory(prefix="openhands-real-shared-osv-", dir="/tmp") as td:
        root = Path(td)
        disposable = root / "repo"
        subprocess.run(
            ["git", "clone", "--quiet", "--local", "--no-hardlinks",
             "--no-checkout", str(base), str(disposable)],
            capture_output=True, timeout=60, check=True
        )
        subprocess.run(
            ["git", "-C", str(disposable), "checkout", "--quiet", "--detach", head],
            capture_output=True, timeout=30, check=True
        )
        if git(disposable, "rev-parse", "HEAD") != head:
            raise ValueError("Disposable checkout commit differs from approved baseline")
        task = TaskRequest.from_dict({
            "contractVersion": "1",
            "idempotencyKey": "shared-probe-no-agent",
            "repository": {
                "url": "https://example.invalid/disposable-snakeyaml.git",
                "baseRef": "refs/heads/main",
                "expectedCommit": head,
            },
            "objective": "Remediate the vulnerable dependency while preserving the Maven build.",
            "constraints": {
                "javaVersionUnchanged": True,
                "springBoot": {
                    "allowPatch": True, "allowMinor": True,
                    "allowMajor": False, "allowDowngrade": False
                },
                "prohibitSuppressions": True,
                "prohibitedNewSeverities": ["CRITICAL", "HIGH"],
            },
            "acceptance": {
                "buildCommands": ["mvn -B -ntp clean verify"],
                "severityScope": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
            },
            "agent": {
                "profile": "gate2-dependency-remediation-v1",
                "modelProfile": "vertex-gemini-2-5-flash",
                "maxIterations": 12,
                "maxValidationDenials": 2,
            },
            "intelligence": {"sbri": {"mode": "disabled"}},
            "delivery": {"mode": "none"},
            "metadata": {"source": "experiment-client"},
        })
        profile = BaselineProfile(
            profile=task.agent.profile,
            build_commands=task.acceptance.build_commands,
            maven=MavenConfig(mode="system"),
            scanner=ScannerConfig(
                backend="osv", mode="configured",
                executable=str(scanner), version="2.6.0", sha256=expected_scanner_sha
            ),
        )
        data = ExistingDeterministicBaselineRunner().run(
            disposable, task, profile, root / "runtime"
        )
        build_ok = bool(data.build_results) and all(x.succeeded for x in data.build_results)
        scan_ok = data.scan is not None and data.scan.succeeded
        observed = []
        if scan_ok:
            for finding in data.scan.findings:
                # ScanReport finding is typed; do not export original object or
                # full advisory payload to a diagnostic console.
                observed.append(finding.vulnerability_id)
        checks = {
            "disposableExactCommit": git(disposable, "rev-parse", "HEAD") == head,
            "mavenBuildPassed": build_ok,
            "realOsvScannerPassed": scan_ok,
            "targetAdvisoryFound": KNOWN_ADVISORY in observed or any(
                KNOWN_ADVISORY in getattr(f, "aliases", ())
                for f in (data.scan.findings if scan_ok else ())
            ),
        }
        return {
            "kind": "real-shared-baseline-runner-probe",
            "status": "PASS" if all(checks.values()) else "NOT_PROVEN",
            "checks": checks, "findingCount": len(observed),
            "scannerVersionExpected": "2.6.0",
            "noModelExecution": True, "noNativeRun": True,
            "notProven": [
                "Durable shared task registration, assessment and artifacts",
                "Actual validator Stop Hook on native server",
                "Native agent-produced remediation",
                "Cost-enforced Vertex run",
            ],
        }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-repository", type=Path,
                   default=Path("/tmp/openhands-real-remediation-snakeyaml-v1"))
    p.add_argument("--scanner", type=Path, required=True)
    args = p.parse_args()
    try:
        result = probe(args.baseline_repository, args.scanner)
    except Exception as exc:
        result = {"kind": "real-shared-baseline-runner-probe", "status": "BLOCKED",
                  "errorType": type(exc).__name__, "noModelExecution": True,
                  "noNativeRun": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
