"""Real shared-runner probe interface: offline only, no Maven/OSV/LLM calls."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_real_shared_baseline_probe as probe


class RealSharedProbeTests(unittest.TestCase):
    def test_absent_paths_block_before_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(probe, "ExistingDeterministicBaselineRunner") as runner:
                with self.assertRaises(OSError):
                    probe.probe(Path(temp) / "missing", Path(temp) / "scanner")
                runner.assert_not_called()

    def test_scanner_symlink_refused_before_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scanner = root / "scanner"
            scanner.write_bytes(b"fake")
            symlink = root / "link"
            symlink.symlink_to(scanner)
            with patch.object(probe, "ExistingDeterministicBaselineRunner") as runner:
                with self.assertRaises(ValueError):
                    probe.probe(root, symlink)
                runner.assert_not_called()

    def test_explicit_identity_and_no_agent_entrypoint(self):
        from inspect import getsource
        source = getsource(probe)
        self.assertIn("ExistingDeterministicBaselineRunner().run", source)
        self.assertIn('["git", "clone"', source)
        self.assertNotIn("dispatch_native_once(", source)
        self.assertNotIn("/run", source.split("def probe(", 1)[1].split("def main(", 1)[0])


if __name__ == "__main__":
    unittest.main()
