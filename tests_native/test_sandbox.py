"""Offline launch-policy tests, not proof of container isolation in deployment."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from native_remediation import sandbox
from native_remediation.contract import load_task
from native_remediation.files import Blocked
from tests_native.test_product import task_input


class SandboxTests(unittest.TestCase):
    def task(self):
        return load_task(dict(task_input(), sandbox=dict(image="sha256:" + "1" * 64)))

    def test_image_required_and_tags_refused_without_host_fallback(self):
        with self.assertRaises(Blocked):
            sandbox.check(load_task(task_input()))
        with self.assertRaises(Blocked):
            load_task(dict(task_input(), sandbox=dict(image="latest")))
        with patch.object(sandbox.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")):
            with self.assertRaises(Blocked):
                sandbox.check(self.task())

    def test_only_explicit_mounts_and_no_network_privilege_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            args = sandbox.invocation(self.task(), [(source, Path("/repo"), True)], "/repo")
            self.assertIn("--network=none", args)
            self.assertIn("--read-only", args)
            self.assertIn("--cap-drop=ALL", args)
            self.assertIn("--security-opt=no-new-privileges", args)
            self.assertIn("--pull=never", args)
            self.assertEqual(args.count("--mount"), 1)
            self.assertNotIn("--privileged", args)
            self.assertNotIn("/var/run/docker.sock", " ".join(args))
            self.assertNotIn("GOOGLE_APPLICATION_CREDENTIALS", " ".join(args))

    def test_build_runner_never_executes_build_on_host_or_mounts_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            bom = root / "bom.json"
            bom.write_text("{}")
            with patch.object(sandbox, "command", return_value={"exitCode": 0}) as runner, \
                    patch.object(sandbox, "stop_container") as stop:
                sandbox.run(["osv-scanner", "--sbom=" + str(bom)], source, 1, task=self.task())
                args = runner.call_args.args[0]
                self.assertEqual(args[:2], ["docker", "run"])
                mounts = [args[i + 1] for i, arg in enumerate(args) if arg == "--mount"]
                self.assertEqual(len(mounts), 3)
                self.assertTrue(any("bom.json" in item and item.endswith(",readonly") for item in mounts))
                self.assertFalse(any("src=" + str(root) + "," in item for item in mounts))
                stop.assert_called_once()

    def test_cannot_accept_when_container_quiescence_is_uncertain(self):
        with patch.object(sandbox.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")):
            with self.assertRaises(Blocked):
                sandbox.stop_container("offline-owned-container")

    def test_generated_symlink_is_rejected_before_host_report_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            (source / "report.xml").symlink_to("/private/trusted.xml")
            with patch.object(sandbox, "command", return_value={"exitCode": 0}), patch.object(sandbox, "stop_container"):
                with self.assertRaisesRegex(Blocked, "Unsafe generated"):
                    sandbox.run(["mvn", "test"], source, 1, task=self.task())


if __name__ == "__main__":
    unittest.main()
