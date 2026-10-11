"""Offline regression tests for OpenHands Gate-2 evidence and scan scope."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "scripts/openhands/openhands-gate2-evidence-summary.py"
WRAPPER = ROOT / "scripts/openhands/openhands-osv-scanner.sh"


class EvidenceSummaryTests(unittest.TestCase):
    def test_reports_each_attempt_and_missing_final_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for n, resolved, remaining in ((1, 2, 24), (2, 16, 10), (3, 18, 8), (4, 26, 0)):
                result = {
                    "passed": not remaining,
                    "resolvedTargetFindings": [{}] * resolved,
                    "remainingTargetFindings": [{}] * remaining,
                    "scan": {
                        "outcome": "COMPLETED_CLEAN" if not remaining else "COMPLETED_WITH_FINDINGS",
                        "commandResult": {
                            "stderr": "Scanned /work/pom.xml file\nScanned /work/task-web/pom.xml file\n"
                        },
                    },
                    "checks": [] if not remaining else [{"name": "target_findings_resolved", "passed": False}],
                }
                (directory / f"validation-attempt-{n}.json").write_text(json.dumps(result))
            (directory / "validation.json").write_text(json.dumps({
                "passed": True, "changedFiles": ["pom.xml"]
            }))
            result = subprocess.run([sys.executable, str(SUMMARY), str(directory)],
                                    text=True, capture_output=True, check=True)
            self.assertIn("Attempt 1: FAIL - resolved 2/26", result.stdout)
            self.assertIn("Attempt 4: PASS - resolved 26/26", result.stdout)
            self.assertIn("scanned_poms=2", result.stdout)
            self.assertIn("Final independent validation: PASS", result.stdout)
            self.assertIn("WARNING: Validator reported changes", result.stdout)


class ScannerScopeTests(unittest.TestCase):
    def test_legacy_nonrecursive_reports_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "scanner"
            binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
            binary.chmod(0o700)
            env = dict(os.environ, OPENHANDS_OSV_EXECUTABLE=str(binary),
                       OPENHANDS_OSV_MAVEN_REGISTRY="http://127.0.0.1:9999/")
            result = subprocess.run(["bash", str(WRAPPER), "--format", "json", "."],
                                    env=env, text=True, capture_output=True, check=True)
            self.assertIn("OSV_LAUNCHER_SCOPE=NON_RECURSIVE", result.stderr)
            self.assertNotIn("--maven-registry", result.stdout)

    def test_recursive_uses_scoped_maven_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "scanner"
            binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
            binary.chmod(0o700)
            env = dict(os.environ, OPENHANDS_OSV_EXECUTABLE=str(binary),
                       OPENHANDS_OSV_MAVEN_REGISTRY="http://127.0.0.1:9999/")
            result = subprocess.run(["bash", str(WRAPPER), "--format", "json", "-r", "."],
                                    env=env, text=True, capture_output=True, check=True)
            self.assertIn("scan\nsource\n", result.stdout)
            self.assertIn("--data-source=native", result.stdout)
            self.assertIn("--maven-registry=http://127.0.0.1:9999/", result.stdout)


if __name__ == "__main__":
    unittest.main()
