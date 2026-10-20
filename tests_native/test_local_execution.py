"""Safe local process fixtures, not real Maven/OSV or security-isolation proof."""
import os
from pathlib import Path
import tempfile
import sys
import time
import unittest
from unittest.mock import patch

from native_remediation.files import command, environment


class LocalExecutionTests(unittest.TestCase):
    def test_command_timeout_kills_process_group_and_retains_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "child-survived"
            child = "import time,pathlib;time.sleep(1);pathlib.Path(" + repr(str(marker)) + ").touch()"
            parent = ("import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"
                      + repr(child) + "]);print('TIMEOUT_FIXTURE',flush=True);time.sleep(10)")
            started = time.monotonic()
            result = command([sys.executable, "-c", parent], root, 0.3, root / "command.json")
            self.assertTrue(result["timedOut"])
            self.assertLess(result["exitCode"], 0)
            self.assertIn("TIMEOUT_FIXTURE", result["stdout"])
            self.assertLess(time.monotonic() - started, 3)
            time.sleep(1.1)  # Harmless child's marker would exist if cleanup missed it.
            self.assertFalse(marker.exists())
            self.assertTrue((root / "command.json").is_file())

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
