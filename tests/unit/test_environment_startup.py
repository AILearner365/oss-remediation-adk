import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from autonomous_oss_remediation_agent import environment
from autonomous_oss_remediation_agent import cli
from scripts import retained_evidence_acceptance


class EnvironmentStartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        package = self.root / "autonomous_oss_remediation_agent"
        package.mkdir()
        self.source = package / "environment.py"
        self.variables = {
            "GOOGLE_GENAI_USE_ENTERPRISE": "1",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
            "GOOGLE_CLOUD_PROJECT": "deutschebank-aipocs",
        }

    def load(self, process_values=None):
        with patch.object(environment, "__file__", str(self.source)), \
             patch.dict(os.environ, process_values or {}, clear=True):
            environment.load_repository_env()
            return {name: os.environ.get(name) for name in self.variables}

    def test_file_values_load_when_process_values_are_absent(self):
        (self.root / ".env").write_text(
            "\n".join(f"{name}={value}" for name, value in self.variables.items()),
            encoding="utf-8",
        )
        self.assertEqual(self.variables, self.load())

    def test_process_values_take_precedence(self):
        (self.root / ".env").write_text("GOOGLE_CLOUD_PROJECT=file-project\n", encoding="utf-8")
        self.assertEqual("process-project", self.load({"GOOGLE_CLOUD_PROJECT": "process-project"})[
            "GOOGLE_CLOUD_PROJECT"])

    def test_missing_file_is_allowed(self):
        self.assertEqual(dict.fromkeys(self.variables), self.load())

    def test_loads_from_source_path_when_working_directory_differs(self):
        (self.root / ".env").write_text("GOOGLE_CLOUD_LOCATION=us-central1\n", encoding="utf-8")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        original = Path.cwd()
        try:
            os.chdir(elsewhere)
            self.assertEqual("us-central1", self.load()["GOOGLE_CLOUD_LOCATION"])
        finally:
            os.chdir(original)

    def test_cli_loads_before_orchestrator_construction(self):
        events = []

        def construct(*args, **kwargs):
            events.append("orchestrator")
            raise RuntimeError("stop before run")

        with patch.object(cli, "load_repository_env", side_effect=lambda: events.append("env")), \
             patch.object(cli.RemediationRequest, "from_json_file", return_value=object()), \
             patch.object(cli, "AutonomousRemediationOrchestrator", side_effect=construct):
            with self.assertRaisesRegex(RuntimeError, "stop before run"):
                cli.main(["request.json"])
        self.assertEqual(["env", "orchestrator"], events)

    def test_acceptance_script_loads_before_fixture_construction(self):
        events = []

        def create_workspace(*args, **kwargs):
            events.append("workspace")
            raise RuntimeError("stop before fixture")

        with patch.object(retained_evidence_acceptance, "load_repository_env",
                          side_effect=lambda: events.append("env")), \
             patch.object(retained_evidence_acceptance.RunWorkspace, "create",
                          side_effect=create_workspace), \
             patch("sys.argv", ["retained_evidence_acceptance"]), redirect_stdout(io.StringIO()):
            self.assertEqual(1, retained_evidence_acceptance.main())
        self.assertEqual(["env", "workspace"], events)


if __name__ == "__main__":
    unittest.main()
