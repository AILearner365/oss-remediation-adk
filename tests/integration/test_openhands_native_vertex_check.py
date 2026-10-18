"""No-cost Vertex resolver adapter tests, no real gcloud mutation or SDK calls."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_vertex_check as vertex


class ExistingVertexResolverTests(unittest.TestCase):
    def test_resolves_existing_function_without_model_call(self):
        with tempfile.TemporaryDirectory() as root:
            script = Path(root) / "env.sh"
            script.write_text(
                "openhands_resolve_vertex_env() { "
                "VERTEXAI_PROJECT=test-project; VERTEXAI_LOCATION=us-central1; }\n",
                encoding="utf-8",
            )
            result = vertex.resolve_existing_vertex_environment(script)
        self.assertEqual(result["vertexProject"], "test-project")
        self.assertEqual(result["vertexLocation"], "us-central1")
        self.assertFalse(result["modelRequestPerformed"])
        self.assertFalse(result["modelExecutionAuthorized"])
        self.assertFalse(result["adcRefreshVerified"])
        self.assertFalse(result["native1551VertexExtraVerified"])

    def test_missing_resolver_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                vertex.resolve_existing_vertex_environment(Path(root) / "absent.sh")

    def test_no_gcloud_sync_or_vertex_verify_called(self):
        with tempfile.TemporaryDirectory() as root:
            script = Path(root) / "env.sh"
            script.write_text(
                "openhands_resolve_vertex_env() { VERTEXAI_PROJECT=p; VERTEXAI_LOCATION=r; }\n"
                "openhands_sync_gcloud_project() { echo SYNC_CALLED; }\n"
                "verify_vertex() { echo MODEL_CALLED; }\n",
                encoding="utf-8",
            )
            result = vertex.resolve_existing_vertex_environment(script)
        self.assertEqual(result["vertexProject"], "p")
        self.assertFalse(result["modelRequestPerformed"])


if __name__ == "__main__":
    unittest.main()
