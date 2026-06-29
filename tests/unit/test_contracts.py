import unittest

from oss_remediation_agent.contracts import Artifact, ToolResult
from oss_remediation_agent.utils.schema_validator import validate_common_artifact, validate_tool_result


class ContractTests(unittest.TestCase):
    def test_artifact_field_names_are_phase2_aligned(self):
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


if __name__ == "__main__":
    unittest.main()
