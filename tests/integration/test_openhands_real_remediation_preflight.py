"""Read-only real Maven/OSV prerequisite checks; zero live scanner/LLM calls."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_remediation_preflight as preflight


class RealRemediationPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.scanner = self.root / "osv-scanner"
        self.scanner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.scanner.chmod(0o700)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"], check=True)
        (self.repo / "pom.xml").write_text("<project/>\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "pom.xml"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "base"], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_repo_and_tools_report_prerequisites_not_acceptance(self):
        real = preflight.command
        def commands(args, cwd, *, timeout=15):
            if args[0] in {"mvn", str(self.scanner)}:
                return {"ok": True, "exitCode": 0}
            return real(args, cwd, timeout=timeout)
        with patch.object(preflight, "command", side_effect=commands):
            outcome = preflight.preflight(self.repo, self.scanner)
        self.assertEqual(outcome["verdict"], "READY_FOR_BASELINE_SETUP")
        self.assertTrue(outcome["noModelExecuted"])
        self.assertTrue(outcome["noScannerExecuted"])
        self.assertIn("OSV vulnerability baseline and target findings", outcome["notProven"])

    def test_dirty_repository_fails(self):
        (self.repo / "dirty.txt").write_text("untracked", encoding="utf-8")
        with patch.object(preflight, "command", return_value={"ok": True}):
            result = preflight.preflight(self.repo, self.scanner)
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertFalse(result["checks"]["cleanGitWorktree"])

    def test_symlink_scanner_rejected(self):
        alias = self.root / "scanner-symlink"
        alias.symlink_to(self.scanner)
        with self.assertRaises(ValueError):
            preflight.preflight(self.repo, alias)


if __name__ == "__main__":
    unittest.main()
