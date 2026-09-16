from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from autonomous_oss_remediation_agent.config import (
    DeliveryConfig,
    ExecutionBudgetConfig,
    RemediationRequest,
    RuntimePolicy,
    ScannerConfig,
)
from autonomous_oss_remediation_agent.models import AgentTurnResult, Outcome
from autonomous_oss_remediation_agent.orchestrator import AutonomousRemediationOrchestrator


class _RemediatingSession:
    def __init__(self, capabilities):
        self.capabilities = capabilities

    async def run_turn(self, message):
        result = self.capabilities.edit_workspace_text(
            "replace",
            "pom.xml",
            old_text="<log4j2.version>2.14.1</log4j2.version>",
            new_text="<log4j2.version>2.17.1</log4j2.version>",
        )
        return AgentTurnResult(f"Updated Log4j after repository inspection: {result.get('status')}")

    async def close(self):
        return None


@unittest.skipUnless(os.getenv("RUN_AUTONOMOUS_REAL_E2E") == "1", "Real Maven/OSV smoke test is opt-in")
class AutonomousRealSmokeTests(unittest.TestCase):
    def test_vulnerable_spring_fixture_build_scan_remediate_validate(self):
        scanner = os.environ.get("AUTONOMOUS_OSV_SCANNER") or shutil.which("osv-scanner")
        if not scanner:
            self.skipTest("OSV Scanner is not configured")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(Path(__file__).resolve().parents[1] / "fixtures" / "autonomous-vulnerable-spring", source)
            _git(source, "init", "-b", "main")
            _git(source, "config", "user.name", "Test")
            _git(source, "config", "user.email", "test@example.com")
            _git(source, "add", "pom.xml")
            _git(source, "commit", "-m", "vulnerable baseline")
            request = RemediationRequest(
                repository_url=str(source),
                reference_branch="main",
                workspace_parent=str(root / "runs"),
                vulnerability_ids=("CVE-2021-44228",),
                severity_scope=("CRITICAL", "HIGH"),
                build_commands=("mvn -q -DskipTests package",),
                budget=ExecutionBudgetConfig(max_cycles=2, max_tool_calls=10, overall_timeout_seconds=1200),
                runtime_policy=RuntimePolicy(True, True, True),
                scanner=ScannerConfig(mode="configured", executable=scanner),
                delivery=DeliveryConfig(mode="manual"),
            )
            result = AutonomousRemediationOrchestrator(
                request,
                agent_session_factory=lambda capabilities, model: _RemediatingSession(capabilities),
            ).run()
            self.assertEqual(Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED, result.outcome, result.to_dict())
            self.assertTrue(result.validation.passed)
            self.assertEqual("VALIDATED_MANUAL_DELIVERY_REQUIRED", result.delivery.status)


def _git(cwd: Path, *args: str):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
