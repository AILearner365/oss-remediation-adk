"""Offline tests for the OpenHands session-scoped OSV launcher."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CONTROL_REPO = Path(__file__).resolve().parents[2]
LAUNCHER = CONTROL_REPO / "scripts/openhands/openhands-osv-scanner.sh"
RUNNER = CONTROL_REPO / "scripts/openhands/openhands-gate2-stop-hook-run.py"


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

    def test_scan_cannot_override_session_registry_or_data_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "fake-osv"
            fake.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
            fake.chmod(0o755)
            env = dict(os.environ, OPENHANDS_OSV_EXECUTABLE=str(fake),
                       OPENHANDS_OSV_MAVEN_REGISTRY="http://127.0.0.1:8765/")
            result = subprocess.run(
                ["bash", str(LAUNCHER), "scan", "source", ".",
                 "--data-source", "deps.dev", "--maven-registry=http://example.invalid/"],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                ["scan", "source", ".", "--data-source=native",
                 "--maven-registry=http://127.0.0.1:8765/"],
                json.loads(result.stdout),
            )

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

    def test_importing_runner_does_not_import_legacy_agent(self):
        probe = f"""
import os
import runpy
import subprocess
import sys
import tempfile
import types
from pathlib import Path

def module(name, **attributes):
    value = types.ModuleType(name)
    for key, item in attributes.items():
        setattr(value, key, item)
    sys.modules[name] = value
    return value

class Placeholder:
    pass

module("openhands")
module("openhands.sdk", AgentContext=Placeholder, Conversation=Placeholder, LLM=Placeholder)
module("openhands.sdk.event", HookExecutionEvent=Placeholder)
module("openhands.sdk.hooks", HookConfig=Placeholder, HookDefinition=Placeholder, HookMatcher=Placeholder)
module("openhands.tools")
module("openhands.tools.preset")
module("openhands.tools.preset.default", get_default_agent=lambda **kwargs: None)

runner = runpy.run_path({str(RUNNER)!r}, run_name="openhands_runner_import_test")
legacy = sorted(name for name in sys.modules if name == "autonomous_oss_remediation_agent"
                or name.startswith("autonomous_oss_remediation_agent."))
if legacy:
    raise SystemExit("legacy imports: " + ", ".join(legacy))

class Config:
    def __init__(self, name=None, params=None, tools=None):
        self.name = name
        self.params = params or {{}}
        self.tools = tools or []
    def model_copy(self, update):
        values = {{"name": self.name, "params": self.params, "tools": self.tools}}
        values.update(update)
        return Config(**values)

with tempfile.TemporaryDirectory() as tmp:
    launcher_dir = Path(tmp)
    launcher = launcher_dir / "osv-scanner"
    launcher.write_text("#!/bin/sh\\nexit 0\\n")
    launcher.chmod(0o700)
    agent = Config(tools=[Config(name="terminal")])
    configured = runner["configure_scanner_terminal"](
        agent,
        launcher_dir=launcher_dir,
        scanner_binary=Path("/scanner"),
        registry_url="http://127.0.0.1:1234/",
    )
    params = configured.tools[0].params
    resolved = subprocess.run(
        [params["shell_path"], "-i", "-c", "command -v osv-scanner"],
        env={{**os.environ, **params["env"]}}, capture_output=True, text=True,
    )
    if resolved.stdout.strip() != str(launcher):
        raise SystemExit("configured terminal did not resolve session launcher: " + resolved.stdout)
"""
        result = subprocess.run(
            [sys.executable, "-c", probe], cwd=CONTROL_REPO,
            capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
