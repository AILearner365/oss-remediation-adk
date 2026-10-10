"""Offline tests for the OpenHands session-scoped OSV launcher."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parents[2] / "scripts/openhands/openhands-osv-scanner.sh"


class OpenHandsOsvLauncherTests(unittest.TestCase):
    def test_scan_uses_native_maven_registry_without_mutating_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "fake-osv"
            fake.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
            fake.chmod(0o755)
            env = dict(os.environ, OPENHANDS_OSV_EXECUTABLE=str(fake),
                       OPENHANDS_OSV_MAVEN_REGISTRY="http://127.0.0.1:8765/")
            result = subprocess.run(
                ["bash", str(LAUNCHER), "scan", "source", "-r", ".", "--format", "json"],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                ["scan", "source", "-r", ".", "--format", "json",
                 "--data-source=native", "--maven-registry=http://127.0.0.1:8765/"],
                json.loads(result.stdout),
            )

    def test_scan_fails_closed_when_registry_missing(self):
        env = dict(os.environ)
        env.pop("OPENHANDS_OSV_MAVEN_REGISTRY", None)
        result = subprocess.run(
            ["bash", str(LAUNCHER), "scan", "source", "-r", "."],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("INCOMPLETE_SCAN", result.stderr)

    def test_non_scan_commands_are_unmodified(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "fake-osv"
            fake.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
            fake.chmod(0o755)
            env = dict(os.environ, OPENHANDS_OSV_EXECUTABLE=str(fake))
            result = subprocess.run(
                ["bash", str(LAUNCHER), "--version"],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(["--version"], json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
