from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from oss_remediation_agent.tools.validation_tool import validate_attempt


class ValidationToolTests(unittest.TestCase):
    def test_validation_change_scope_rejects_non_pom_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps({"vulnerabilityDecisions": []}), encoding="utf-8")
            proof = _proof(["README.md"])
            proof_path = root / "proof.json"
            proof_path.write_text(json.dumps(proof), encoding="utf-8")
            result = validate_attempt(1, str(repo), str(plan_path), str(proof_path), str(root / "validation.json"), str(root), workflow_id="wf")
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["failureCode"], "CHANGE_SCOPE_FAILURE")

    def test_validation_fails_on_build_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, repo, plan_path, proof_path = _workspace(root_path=Path(tmp))

            def fake_run(command, cwd=None, timeout=1800):
                if command[:2] == ["git", "diff"] and "--name-only" in command:
                    return {"exitCode": 0, "stdout": "pom.xml\n", "stderr": ""}
                if command[:2] == ["git", "diff"]:
                    return {"exitCode": 0, "stdout": "-<x>1.0</x>\n+<x>1.1</x>\n", "stderr": ""}
                return {"exitCode": 1, "stdout": "", "stderr": "build failed"}

            with patch("oss_remediation_agent.tools.validation_tool.run_command", side_effect=fake_run):
                result = validate_attempt(1, str(repo), str(plan_path), str(proof_path), str(root / "validation.json"), str(root), workflow_id="wf")
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["failureCode"], "BUILD_FAILURE")

    def test_validation_fails_on_test_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, repo, plan_path, proof_path = _workspace(root_path=Path(tmp))
            calls = []

            def fake_run(command, cwd=None, timeout=1800):
                if command[:2] == ["git", "diff"] and "--name-only" in command:
                    return {"exitCode": 0, "stdout": "pom.xml\n", "stderr": ""}
                if command[:2] == ["git", "diff"]:
                    return {"exitCode": 0, "stdout": "-<x>1.0</x>\n+<x>1.1</x>\n", "stderr": ""}
                calls.append(command)
                if command == ["mvn", "clean", "install"]:
                    return {"exitCode": 0, "stdout": "build ok", "stderr": ""}
                return {"exitCode": 1, "stdout": "", "stderr": "tests failed"}

            with patch("oss_remediation_agent.tools.validation_tool.run_command", side_effect=fake_run):
                result = validate_attempt(1, str(repo), str(plan_path), str(proof_path), str(root / "validation.json"), str(root), workflow_id="wf")
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["failureCode"], "TEST_FAILURE")

    def test_validation_fails_on_osv_scan_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, repo, plan_path, proof_path = _workspace(root_path=Path(tmp))

            with patch("oss_remediation_agent.tools.validation_tool.run_command", side_effect=_successful_git_and_maven), \
                 patch("oss_remediation_agent.tools.validation_tool.validate_post_remediation", return_value={"status": "FAILED", "payload": {}}):
                result = validate_attempt(1, str(repo), str(plan_path), str(proof_path), str(root / "validation.json"), str(root), workflow_id="wf")
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["failureCode"], "OSV_VALIDATION_FAILURE")

    def test_validation_fails_when_new_critical_high_is_introduced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, repo, plan_path, proof_path = _workspace(root_path=Path(tmp))
            baseline_path = root / "baseline-assessment.json"
            baseline_path.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
            remaining = [
                {
                    "vulnerabilityId": "GHSA-new",
                    "severity": "HIGH",
                    "dependency": {"packageName": "org.example:new-lib", "currentVersion": "1.0"},
                }
            ]
            osv_result = {"status": "SUCCESS", "payload": {"remainingCriticalCount": 0, "remainingHighCount": 1, "remainingVulnerabilities": remaining}}
            with patch("oss_remediation_agent.tools.validation_tool.run_command", side_effect=_successful_git_and_maven), \
                 patch("oss_remediation_agent.tools.validation_tool.validate_post_remediation", return_value=osv_result):
                result = validate_attempt(1, str(repo), str(plan_path), str(proof_path), str(root / "validation.json"), str(root), workflow_id="wf", baseline_assessment_path=str(baseline_path))
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["failureCode"], "OSV_VALIDATION_FAILURE")
            validation = json.loads((root / "validation.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["osvValidation"]["newCriticalHighIntroduced"])


def _proof(files_changed: list[str]) -> dict:
    return {
        "schemaVersion": "1.0",
        "artifactId": "proof",
        "workflowId": "wf",
        "createdBy": "test",
        "status": "SUCCESS",
        "filesChanged": files_changed,
        "patchResults": [],
    }


def _workspace(root_path: Path):
    repo = root_path / "repo"
    repo.mkdir()
    (repo / "pom.xml").write_text("<project><x>1.1</x></project>", encoding="utf-8")
    plan_path = root_path / "plan.json"
    plan_path.write_text(json.dumps({"vulnerabilityDecisions": [{"patches": [{"file": "pom.xml"}]}]}), encoding="utf-8")
    proof_path = root_path / "proof.json"
    proof_path.write_text(json.dumps(_proof(["pom.xml"])), encoding="utf-8")
    return root_path, repo, plan_path, proof_path


def _successful_git_and_maven(command, cwd=None, timeout=1800):
    if command[:2] == ["git", "diff"] and "--name-only" in command:
        return {"exitCode": 0, "stdout": "pom.xml\n", "stderr": ""}
    if command[:2] == ["git", "diff"]:
        return {"exitCode": 0, "stdout": "-<x>1.0</x>\n+<x>1.1</x>\n", "stderr": ""}
    return {"exitCode": 0, "stdout": "ok", "stderr": ""}


if __name__ == "__main__":
    unittest.main()
