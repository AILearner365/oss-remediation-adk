from pathlib import Path
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from oss_remediation_agent.tools.generic_patch_apply_tool import apply as apply_patch_plan
from oss_remediation_agent.tools.generic_patch_apply_tool import dry_run as dry_run_patch_plan
from oss_remediation_agent.tools.maven_project_tool import collect_maven_facts
from oss_remediation_agent.tools.pr_creation_tool import create_pr_summary
from oss_remediation_agent.tools.validation_tool import validate_attempt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class PhaseAFixtureIntegrationTests(unittest.TestCase):
    """Fixture-based integration tests for the deterministic MVP tool layer.

    These tests use committed Maven fixture projects as inputs. External command
    execution is mocked where appropriate so the tests remain stable in CI while
    still exercising real fixture files, artifact generation, and tool contracts.
    """

    def test_project_analyzer_on_single_module_fixture(self):
        with _copied_fixture("maven-single-module-direct") as repo:
            output_dir = repo.parent / "artifacts"

            with patch("oss_remediation_agent.tools.maven_project_tool.run_command", side_effect=_maven_evidence_success):
                result = collect_maven_facts(str(repo), str(output_dir / "project-analyzer-report.json"), str(output_dir), workflow_id="wf-fixture")

            self.assertEqual(result["status"], "SUCCESS")
            report = _read_json(output_dir / "project-analyzer-report.json")
            self.assertEqual(report["projectFacts"]["projectType"], "MAVEN")
            self.assertFalse(report["projectFacts"]["isMultiModule"])
            self.assertIn("pom.xml", report["projectFacts"]["pomFiles"])
            self.assertEqual(report["projectFacts"]["java"]["detectedVersions"], ["17"])
            self.assertEqual(report["dependencyResolutionEvidence"][0]["dependency"], "org.yaml:snakeyaml")

    def test_project_analyzer_on_multi_module_fixture(self):
        with _copied_fixture("maven-multi-module") as repo:
            output_dir = repo.parent / "artifacts"

            with patch("oss_remediation_agent.tools.maven_project_tool.run_command", side_effect=_maven_evidence_success):
                result = collect_maven_facts(str(repo), str(output_dir / "project-analyzer-report.json"), str(output_dir), workflow_id="wf-fixture")

            self.assertEqual(result["status"], "SUCCESS")
            report = _read_json(output_dir / "project-analyzer-report.json")
            self.assertTrue(report["projectFacts"]["isMultiModule"])
            self.assertTrue(report["projectFacts"]["springBoot"]["detected"])
            self.assertEqual(report["projectFacts"]["springBoot"]["version"], "3.2.4")
            self.assertEqual({module["moduleName"] for module in report["projectFacts"]["modules"]}, {"service-a", "service-b"})
            self.assertIn("service-a/pom.xml", report["projectFacts"]["pomFiles"])
            self.assertTrue(report["projectFacts"]["dependencyManagementPresent"])

    def test_patch_tool_against_property_managed_fixture_pom(self):
        with _copied_fixture("maven-property-managed-version") as repo:
            plan_path = repo.parent / "patch-plan.json"
            proof_path = repo.parent / "patch-application-proof.json"
            diff_path = repo.parent / "patch.diff"
            dry_path = repo.parent / "patch-dry-run-result.json"
            _write_patch_plan(
                plan_path,
                old_text="<snakeyaml.version>1.33</snakeyaml.version>",
                new_text="<snakeyaml.version>2.2</snakeyaml.version>",
                old_version="1.33",
                new_version="2.2",
            )

            dry = dry_run_patch_plan(1, str(repo), str(plan_path), str(dry_path))
            self.assertEqual(dry["status"], "SUCCESS")
            applied = apply_patch_plan(1, str(repo), str(plan_path), str(proof_path), str(diff_path))

            self.assertEqual(applied["status"], "SUCCESS")
            pom_text = (repo / "pom.xml").read_text(encoding="utf-8")
            self.assertIn("<snakeyaml.version>2.2</snakeyaml.version>", pom_text)
            self.assertNotIn("<snakeyaml.version>1.33</snakeyaml.version>", pom_text)
            proof = _read_json(proof_path)
            self.assertEqual(proof["patchResults"][0]["status"], "APPLIED")
            self.assertIn("pom.xml", proof["filesChanged"])

    def test_validation_tool_against_fixture_generated_artifacts(self):
        with _copied_fixture("maven-property-managed-version") as repo:
            root = repo.parent
            plan_path = root / "patch-plan.json"
            proof_path = root / "patch-application-proof.json"
            validation_path = root / "validation-result.json"
            _write_patch_plan(
                plan_path,
                old_text="<snakeyaml.version>1.33</snakeyaml.version>",
                new_text="<snakeyaml.version>2.2</snakeyaml.version>",
                old_version="1.33",
                new_version="2.2",
            )
            apply_patch_plan(1, str(repo), str(plan_path), str(proof_path), str(root / "patch.diff"))

            with patch("oss_remediation_agent.tools.validation_tool.run_command", side_effect=_successful_git_and_maven), \
                 patch("oss_remediation_agent.tools.validation_tool.validate_post_remediation", return_value={
                     "status": "SUCCESS",
                     "payload": {"remainingCriticalCount": 0, "remainingHighCount": 0, "remainingVulnerabilities": []},
                 }):
                result = validate_attempt(1, str(repo), str(plan_path), str(proof_path), str(validation_path), str(root), workflow_id="wf-fixture")

            self.assertEqual(result["status"], "SUCCESS")
            validation = _read_json(validation_path)
            self.assertEqual(validation["changeScopeValidation"]["status"], "SUCCESS")
            self.assertEqual(validation["buildValidation"]["status"], "SUCCESS")
            self.assertEqual(validation["testValidation"]["status"], "SUCCESS")
            self.assertEqual(validation["osvValidation"]["remainingCriticalCount"], 0)
            self.assertEqual(validation["osvValidation"]["remainingHighCount"], 0)

    def test_pr_summary_from_fixture_manifest(self):
        with _copied_fixture("maven-property-managed-version") as repo:
            root = repo.parent
            validation_path = root / "attempt-1" / "validation-result.json"
            validation_path.parent.mkdir(parents=True)
            validation_path.write_text(json.dumps({
                "changeScopeValidation": {"status": "SUCCESS"},
                "buildValidation": {"status": "SUCCESS"},
                "testValidation": {"status": "SUCCESS"},
                "osvValidation": {
                    "status": "SUCCESS",
                    "remainingCriticalCount": 0,
                    "remainingHighCount": 0,
                    "newCriticalHighIntroduced": False,
                },
            }), encoding="utf-8")
            manifest = {
                "workflowId": "wf-fixture",
                "workspaceRoot": str(root),
                "baseline": {"baselineBuildResult": "baseline/baseline-build-result.json"},
                "attempts": [{"attemptNumber": 1, "validationResult": "attempt-1/validation-result.json"}],
                "acceptedPatchSet": {
                    "status": "VALIDATED",
                    "remediationSummary": [{
                        "vulnerabilityId": "GHSA-fixture",
                        "dependency": "org.yaml:snakeyaml",
                        "oldVersion": "1.33",
                        "newVersion": "2.2",
                        "status": "REMEDIATED",
                        "statusReason": "Fixture remediation validated successfully.",
                    }],
                },
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = create_pr_summary(str(manifest_path), str(root / "final" / "pr-summary.json"), str(root / "final" / "pr-description.md"), workflow_id="wf-fixture")

            self.assertEqual(result["status"], "SUCCESS")
            summary = _read_json(root / "final" / "pr-summary.json")
            self.assertEqual(summary["status"], "ELIGIBLE")
            self.assertEqual(summary["prType"], "FULL_REMEDIATION")
            self.assertEqual(summary["remediationSummary"][0]["dependency"], "org.yaml:snakeyaml")
            self.assertEqual(summary["remediationSummary"][0]["oldVersion"], "1.33")
            self.assertEqual(summary["remediationSummary"][0]["newVersion"], "2.2")
            markdown = (root / "final" / "pr-description.md").read_text(encoding="utf-8")
            self.assertIn("org.yaml:snakeyaml", markdown)
            self.assertIn("2.2", markdown)


def _copied_fixture(name: str):
    class FixtureContext:
        def __enter__(self):
            self.temp_dir = tempfile.TemporaryDirectory()
            root = Path(self.temp_dir.name)
            source = FIXTURES / name
            target = root / name
            shutil.copytree(source, target)
            return target

        def __exit__(self, exc_type, exc, tb):
            self.temp_dir.cleanup()

    return FixtureContext()


def _write_patch_plan(path: Path, old_text: str, new_text: str, old_version: str, new_version: str) -> None:
    path.write_text(json.dumps({
        "schemaVersion": "1.0",
        "artifactId": "remediation-patch-plan-fixture",
        "workflowId": "wf-fixture",
        "createdBy": "IntegrationTest",
        "status": "PATCH_AVAILABLE",
        "planId": "plan-fixture",
        "vulnerabilityDecisions": [{
            "vulnerabilityId": "GHSA-fixture",
            "decision": "PATCH",
            "dependency": {
                "packageName": "org.yaml:snakeyaml",
                "currentVersion": old_version,
            },
            "patches": [{
                "patchId": "patch-fixture-1",
                "file": "pom.xml",
                "oldText": old_text,
                "newText": new_text,
                "oldVersion": old_version,
                "newVersion": new_version,
                "expectedOccurrences": 1,
            }],
        }],
    }), encoding="utf-8")


def _maven_evidence_success(command, cwd=None, timeout=1800):
    if "dependency:tree" in command:
        return {"exitCode": 0, "stdout": "+- org.yaml:snakeyaml:jar:1.33:compile", "stderr": ""}
    return {"exitCode": 0, "stdout": "", "stderr": ""}


def _successful_git_and_maven(command, cwd=None, timeout=1800):
    if command[:2] == ["git", "diff"] and "--name-only" in command:
        return {"exitCode": 0, "stdout": "pom.xml\n", "stderr": ""}
    if command[:2] == ["git", "diff"]:
        return {"exitCode": 0, "stdout": "-<snakeyaml.version>1.33</snakeyaml.version>\n+<snakeyaml.version>2.2</snakeyaml.version>\n", "stderr": ""}
    return {"exitCode": 0, "stdout": "ok", "stderr": ""}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
