"""Safe local process fixtures, not real Maven/OSV or security-isolation proof."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_remediation.files import command, environment


class LocalExecutionTests(unittest.TestCase):
    def test_existing_local_runner_executes_maven_osv_standins_without_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("mvn", "osv-scanner"):
                executable = root / name
                executable.write_text("#!/bin/sh\nprintf 'LOCAL_TOOL_FIXTURE\\n'\n")
                executable.chmod(0o700)
                result = command([str(executable), "--version"], root, 5)
                self.assertEqual(result["exitCode"], 0)
                self.assertEqual(result["stdout"].strip(), "LOCAL_TOOL_FIXTURE")

    def test_authorized_proxy_environment_is_retained_not_credential_variables(self):
        with patch.dict(os.environ, dict(HTTPS_PROXY="http://proxy.example.invalid:8080",
                       no_proxy="localhost", GH_TOKEN="fixture-not-a-token")):
            selected = environment()
            self.assertEqual(selected["HTTPS_PROXY"], "http://proxy.example.invalid:8080")
            self.assertEqual(selected["no_proxy"], "localhost")
            self.assertNotIn("GH_TOKEN", selected)


if __name__ == "__main__":
    unittest.main()
