import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from openhands_shared.contracts import TaskRequest
from openhands_shared.store import SQLiteTaskStore

def contract(mode):
    return {
        "contractVersion":"1",
        "idempotencyKey":"delivery-roundtrip-" + mode,
        "repository":{"url":"https://github.com/AILearner365/maven-multimodule-app.git",
                      "baseRef":"refs/heads/main-runrunning",
                      "expectedCommit":"9ea1b0ed5ca255db0fc7c659d050896d3ed5db78"},
        "objective":"Investigate and remediate Maven vulnerabilities in the multi-module application.",
        "constraints":{"javaVersionUnchanged":True,
            "springBoot":{"allowPatch":True,"allowMinor":True,"allowMajor":False,"allowDowngrade":False},
            "prohibitSuppressions":True,"prohibitedNewSeverities":["CRITICAL","HIGH"]},
        "acceptance":{"buildCommands":["mvn -B -ntp clean verify"],
                      "severityScope":["CRITICAL","HIGH","MEDIUM","LOW"]},
        "agent":{"profile":"gate2-dependency-remediation-v1",
                 "modelProfile":"vertex-gemini-2-5-flash",
                 "maxIterations":12,"maxValidationDenials":2},
        "intelligence":{"sbri":{"mode":"auto"}},
        "delivery":{"mode":mode},
        "metadata":{"source":"experiment-client"}
    }

class DeliveryContractTest(unittest.TestCase):
    def test_roundtrip_preserves_explicit_modes(self):
        for mode in ("none", "github_pr"):
            with self.subTest(mode=mode):
                parsed = TaskRequest.from_dict(contract(mode))
                self.assertEqual(parsed.delivery_mode, mode)
                self.assertEqual(TaskRequest.from_dict(parsed.to_dict()).delivery_mode, mode)
                with tempfile.TemporaryDirectory() as d:
                    with SQLiteTaskStore(Path(d)/"tasks.sqlite3") as store:
                        task = store.register_task(parsed)
                        self.assertEqual(store.get_request(task.status.task_id).delivery_mode, mode)
if __name__ == "__main__":
    unittest.main()
