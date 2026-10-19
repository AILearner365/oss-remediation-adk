import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_remediation as bridge
from openhands_shared.contracts import IntelligenceOutcome


class NativeSbriHandoffTests(unittest.TestCase):
    def test_intelligence_summary_reaches_first_message(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            text = "Boot 4.0.8 addresses 38 of 50 baseline findings; 12 remain.\n"
            (root / "summary.txt").write_text(text)
            artifact = SimpleNamespace(artifact_id="intelligence-summary",
                relative_path="summary.txt", size_bytes=len(text.encode()),
                sha256=hashlib.sha256(text.encode()).hexdigest())
            request = SimpleNamespace(objective="Remediate Maven vulnerabilities",
                acceptance=SimpleNamespace(build_commands=("mvn verify",),
                severity_scope=("HIGH",)), sbri_mode="enabled")
            class Store:
                database_path = root / "tasks.sqlite3"
                def get_request(self, task_id): return request
                def get_intelligence(self, task_id):
                    return SimpleNamespace(outcome=IntelligenceOutcome.COMPLETE,
                                           summary_artifact_id="intelligence-summary")
                def list_artifacts(self, task_id): return (artifact,)
            with patch.object(bridge, "load_stop_hook_config",
                return_value=(Store.database_path.resolve(),
                              SimpleNamespace(artifact_root=root))):
                result = bridge.render_task_objective(Store(), "task", hook_config=root / "hook.json")
            self.assertIn("38 of 50", result)
            self.assertIn("12 remain", result)
            self.assertIn("not an upgrade instruction", result)

    def test_missing_hook_blocks_enabled_sbri(self):
        class Store:
            def get_request(self, task_id):
                return SimpleNamespace(objective="Remediate Maven vulnerabilities",
                    acceptance=SimpleNamespace(build_commands=("mvn verify",),
                        severity_scope=("HIGH",)), sbri_mode="enabled")
            def get_intelligence(self, task_id):
                return SimpleNamespace(outcome=IntelligenceOutcome.COMPLETE,
                                       summary_artifact_id="intelligence-summary")
            def list_artifacts(self, task_id):
                return (SimpleNamespace(artifact_id="intelligence-summary"),)
        with self.assertRaisesRegex(bridge.HandoffError, "requires trusted Stop Hook"):
            bridge.render_task_objective(Store(), "task")


if __name__ == "__main__":
    unittest.main()
