from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autonomous_oss_remediation_agent.config import MavenConfig, RemediationRequest
from autonomous_oss_remediation_agent.deterministic.maven import (
    MavenExecutionPolicyError,
    MavenService,
)
from autonomous_oss_remediation_agent.models import CommandResult


class _Runner:
    def __init__(self, exit_code: int = 0):
        self.exit_code = exit_code
        self.commands = []

    def run_argv(self, command, **kwargs):
        self.commands.append((list(command), kwargs))
        return CommandResult(list(command), str(kwargs.get("cwd")), self.exit_code)


class AutonomousMavenPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_maven_config_defaults_to_wrapper_first_auto_mode(self):
        request = RemediationRequest.from_dict({"repositoryUrl": "https://example.test/repo"})
        wrapper = self.repository / "mvnw.cmd"
        wrapper.write_text("@echo off\n", encoding="utf-8")

        executable = MavenService(
            self.repository,
            _Runner(),
            request.maven,
            platform_name="nt",
        ).maven_executable()

        self.assertEqual("auto", request.maven.mode)
        self.assertEqual(str(wrapper), executable)
        self.assertEqual({"mode": "auto"}, request.to_dict()["maven"])

    def test_explicit_auto_mode_selects_windows_wrapper(self):
        wrapper = self.repository / "mvnw.cmd"
        wrapper.write_text("@echo off\n", encoding="utf-8")
        service = MavenService(
            self.repository,
            _Runner(),
            MavenConfig(mode="auto"),
            platform_name="nt",
        )
        self.assertEqual(str(wrapper), service.maven_executable())

    def test_auto_mode_uses_path_maven_when_wrapper_is_absent(self):
        system_maven = str(self.repository / "path" / "mvn.cmd")
        service = MavenService(
            self.repository,
            _Runner(),
            MavenConfig(mode="auto"),
            platform_name="nt",
            which=lambda command: system_maven if command == "mvn.cmd" else None,
        )
        self.assertEqual(system_maven, service.maven_executable())

    def test_auto_mode_ignores_opposite_platform_wrapper(self):
        (self.repository / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")
        system_maven = str(self.repository / "path" / "mvn.cmd")
        service = MavenService(
            self.repository,
            _Runner(),
            MavenConfig(mode="auto"),
            platform_name="nt",
            which=lambda command: system_maven if command == "mvn.cmd" else None,
        )
        self.assertEqual(system_maven, service.maven_executable())

    def test_system_mode_ignores_windows_wrapper(self):
        (self.repository / "mvnw.cmd").write_text("@echo off\n", encoding="utf-8")
        system_maven = str(self.repository / "path" / "mvn.cmd")
        service = MavenService(
            self.repository,
            _Runner(),
            MavenConfig(mode="system"),
            platform_name="nt",
            which=lambda command: system_maven if command == "mvn.cmd" else None,
        )
        self.assertEqual(system_maven, service.maven_executable())

    def test_wrapper_mode_selects_windows_wrapper(self):
        wrapper = self.repository / "mvnw.cmd"
        wrapper.write_text("@echo off\n", encoding="utf-8")
        service = MavenService(
            self.repository,
            _Runner(),
            MavenConfig(mode="wrapper"),
            platform_name="nt",
        )
        self.assertEqual(str(wrapper), service.maven_executable())

    def test_wrapper_mode_selects_unix_wrapper_on_non_windows(self):
        wrapper = self.repository / "mvnw"
        wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
        wrapper.chmod(0o755)
        service = MavenService(
            self.repository,
            _Runner(),
            MavenConfig(mode="wrapper"),
            platform_name="posix",
        )
        self.assertEqual(str(wrapper), service.maven_executable())

    def test_wrapper_mode_fails_when_platform_wrapper_is_absent(self):
        service = MavenService(
            self.repository,
            _Runner(),
            MavenConfig(mode="wrapper"),
            platform_name="nt",
        )
        with self.assertRaisesRegex(MavenExecutionPolicyError, "mvnw.cmd"):
            service.maven_executable()

    def test_invalid_maven_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Maven mode"):
            MavenConfig(mode="fallback")
        with self.assertRaisesRegex(ValueError, "Unsupported Maven mode"):
            RemediationRequest.from_dict(
                {
                    "repositoryUrl": "https://example.test/repo",
                    "maven": {"mode": "fallback"},
                }
            )
        with self.assertRaisesRegex(ValueError, "maven must be an object"):
            RemediationRequest.from_dict(
                {
                    "repositoryUrl": "https://example.test/repo",
                    "maven": [],
                }
            )

    def test_wrapper_execution_failure_does_not_fall_back_to_system_maven(self):
        wrapper = self.repository / "mvnw.cmd"
        wrapper.write_text("@echo off\n", encoding="utf-8")
        runner = _Runner(exit_code=1)
        results = MavenService(
            self.repository,
            runner,
            MavenConfig(mode="wrapper"),
            platform_name="nt",
        ).run_baseline(())

        self.assertFalse(results[0].succeeded)
        self.assertEqual(1, len(runner.commands))
        self.assertEqual(str(wrapper), runner.commands[0][0][0])


if __name__ == "__main__":
    unittest.main()
