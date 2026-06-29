from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from oss_remediation_agent.contracts import Artifact, ToolResult
from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.tools.generic_patch_apply_tool import apply, dry_run
from oss_remediation_agent.tools.maven_project_tool import collect_maven_facts
from oss_remediation_agent.tools.osv_scanner_tool import normalize_osv_findings
from oss_remediation_agent.tools.validation_tool import validate_attempt
from oss_remediation_agent.utils.schema_validator import validate_common_artifact, validate_tool_result


class PolicyAndPatchToolTests(unittest.TestCase):
    def test_policy_defaults_are_safe(self):
        policy = RemediationPolicy()
        self.assertEqual(policy.severity_scope, ["CRITICAL", "HIGH"])
        self.assertIn("**/pom.xml", policy.allowed_file_patterns)
        self.assertIn("JAVA_SOURCE_CHANGE", policy.blocked_change_types)
        self.assertIn("SUPPRESSION_OR_IGNORE_WORKAROUND", policy.blocked_change_types)

    def test_contract_field_names_are_phase2_aligned(self):
        artifact = Artifact(
            artifact_id="artifact-1",
            workflow_id="workflow-1",
            created_by="UnitTest",
            status="SUCCESS",
        ).to_dict()
        self.assertIn("schemaVersion", artifact)
        self.assertIn("artifactId", artifact)
        self.assertIn("workflowId", artifact)
        self.assertIn("createdBy", artifact)
        self.assertNotIn("schema_version", artifact)
        self.assertEqual(validate_common_artifact(artifact), [])

    def test_tool_result_field_names_are_phase3_aligned(self):
        result = ToolResult.success("ExampleTool", "operation", "artifact.json", answer=1).to_dict()
        self.assertEqual(result["toolName"], "ExampleTool")
        self.assertEqual(result["toolVersion"], "1.0.0")
        self.assertEqual(result["artifactPath"], "artifact.json")
        self.assertIn("failureCode", result)
        self.assertNotIn("tool_name", result)
        self.assertEqual(validate_tool_result(result), [])

    def test_patch_tool_dry_run_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            pom = repo / "pom.xml"
            pom.write_text("<project><properties><x.version>1.0</x.version></properties></project>", encoding="utf-8")
            plan_path = _write_plan(root, [
                {
                    "patchId": "patch-1",
                    "file": "pom.xml",
                    "oldText": "<x.version>1.0</x.version>",
                    "newText": "<x.version>1.1</x.version>",
                    "expectedOccurrences": 1,
                }
            ])
            dry = dry_run(1, str(repo), str(plan_path), str(root / "dry.json"))
            self.assertEqual(dry["status"], "SUCCESS")
            self.assertEqual(dry["toolName"], "GenericPatchApplyTool")
            result = apply(1, str(repo), str(plan_path), str(root / "proof.json"), str(root / "patch.diff"))
            self.assertEqual(result["status"], "SUCCESS")
            self.assertIn("<x.version>1.1</x.version>", pom.read_text(encoding="utf-8"))

    def test_patch_apply_is_atomic_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            pom = repo / "pom.xml"
            original = "<project><a.version>1.0</a.version><b.version>1.0</b.version></project>"
            pom.write_text(original, encoding="utf-8")
            plan_path = _write_plan(root, [
                {
                    "patchId": "patch-1",
                    "file": "pom.xml",
                    "oldText": "<a.version>1.0</a.version>",
                    "newText": "<a.version>1.1</a.version>",
                    "expectedOccurrences": 1,
                },
                {
                    "patchId": "patch-2",
                    "file": "pom.xml",
                    "oldText": "<missing.version>1.0</missing.version>",
                    "newText": "<missing.version>1.1</missing.version>",
                    "expectedOccurrences": 1,
                },
            ])
            result = apply(1, str(repo), str(plan_path), str(root / "proof.json"), str(root / "patch.diff"))
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(pom.read_text(encoding="utf-8"), original)

    def test_osv_normalization_filters_maven_high(self):
        raw = {
            "results": [
                {
                    "packages": [
                        {
                            "package": {"ecosystem": "Maven", "name": "org.yaml:snakeyaml", "version": "1.33"},
                            "vulnerabilities": [
                                {
                                    "id": "GHSA-xxxx",
                                    "aliases": ["CVE-2026-0001"],
                                    "database_specific": {"severity": "HIGH"},
                                    "affected": [{"ranges": [{"events": [{"fixed": "2.2"}]}]}],
                                }
                            ],
                        }
                    ]
                }
            ]
        }
        findings = normalize_osv_findings(raw, ["CRITICAL", "HIGH"], "raw.json")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["dependency"]["packageName"], "org.yaml:snakeyaml")
        self.assertEqual(findings[0]["fixedVersions"], ["2.2"])

    def test_project_analyzer_basic_maven_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / "pom.xml").write_text(
                """
<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.4</version>
  </parent>
  <properties><java.version>17</java.version></properties>
  <modules><module>service-a</module></modules>
  <dependencyManagement></dependencyManagement>
</project>
""".strip(),
                encoding="utf-8",
            )
            (repo / "service-a").mkdir()
            (repo / "service-a" / "pom.xml").write_text("<project></project>", encoding="utf-8")
            def fake_run(command, cwd=None, timeout=1800):
                if "dependency:tree" in command:
                    return {"exitCode": 0, "stdout": "+- org.yaml:snakeyaml:jar:1.33:compile", "stderr": ""}
                return {"exitCode": 0, "stdout": "", "stderr": ""}
            with patch("oss_remediation_agent.tools.maven_project_tool.run_command", side_effect=fake_run):
                result = collect_maven_facts(str(repo), str(root / "analysis.json"), str(root / "baseline"), workflow_id="wf")
            self.assertEqual(result["status"], "SUCCESS")
            analysis = json.loads((root / "analysis.json").read_text(encoding="utf-8"))
            self.assertTrue(analysis["projectFacts"]["springBoot"]["detected"])
            self.assertTrue(analysis["projectFacts"]["dependencyManagementPresent"])
            self.assertEqual(analysis["dependencyResolutionEvidence"][0]["dependency"], "org.yaml:snakeyaml")

    def test_validation_change_scope_rejects_non_pom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            plan_path = _write_plan(root, [])
            proof = {
                "schemaVersion": "1.0",
                "artifactId": "proof",
                "workflowId": "wf",
                "createdBy": "test",
                "status": "SUCCESS",
                "filesChanged": ["src/main/java/App.java"],
                "patchResults": [],
            }
            proof_path = root / "proof.json"
            proof_path.write_text(json.dumps(proof), encoding="utf-8")
            result = validate_attempt(1, str(repo), str(plan_path), str(proof_path), str(root / "validation.json"), str(root), workflow_id="wf")
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["failureCode"], "CHANGE_SCOPE_FAILURE")


def _write_plan(root: Path, patches: list[dict]) -> Path:
    plan = {
        "schemaVersion": "1.0",
        "artifactId": "plan",
        "workflowId": "wf-test",
        "createdBy": "test",
        "status": "PATCH_AVAILABLE",
        "planId": "plan-1",
        "vulnerabilityDecisions": [{"decision": "PATCH", "vulnerabilityId": "VULN-1", "patches": patches}],
    }
    plan_path = root / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan_path


if __name__ == "__main__":
    unittest.main()
