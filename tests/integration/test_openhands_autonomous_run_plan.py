"""Preparation-only run plan tests; no Vertex, Maven, scanner or network."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from openhands_autonomous_run_plan import prepare, TARGET, PACKAGE, MODEL


class AutonomousRunPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.base = root / "baseline"
        self.fixed = root / "fixed"
        self.base.mkdir()
        self.fixed.mkdir()
        self.scanner = root / "osv"
        self.scanner.write_bytes(b"offline approved-scanner-placeholder")
        pom = """<project><dependencies><dependency><groupId>org.yaml</groupId>
<artifactId>snakeyaml</artifactId><version>1.33</version>
</dependency></dependencies></project>"""
        (self.base / "pom.xml").write_text(pom)
        (self.fixed / "pom.xml").write_text(pom.replace("1.33", "2.0"))
        subprocess.run(["git", "init", "-q", str(self.base)], check=True)
        subprocess.run(["git", "-C", str(self.base), "add", "pom.xml"], check=True)
        subprocess.run(["git", "-C", str(self.base), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit",
                        "-qm", "baseline"], check=True)
        self.baseline_report = root / "baseline.json"
        self.fixed_report = root / "fixed.json"
        def report(count):
            return {"results": [{"packages": [{
                "package": {"name": PACKAGE}, "vulnerabilities": [{"id": TARGET}]
            }]}]} if count else {"results": []}
        self.baseline_report.write_text(json.dumps(report(1)))
        self.fixed_report.write_text(json.dumps(report(0)))

    def tearDown(self):
        self.temp.cleanup()

    def run_plan(self):
        return prepare(self.base, self.fixed, self.baseline_report,
                       self.fixed_report, self.scanner)

    def test_no_model_permission_or_fixed_candidate_leaks_into_agent_objective(self):
        result = self.run_plan()
        self.assertEqual(result["model"], MODEL)
        self.assertEqual(result["status"], "PREPARED_NOT_AUTHORIZED")
        self.assertFalse(result["modelExecutionAuthorized"])
        self.assertFalse(result["modelInvocationAllowed"])
        self.assertEqual(result["verifiedBaselineFindings"][0]["advisory"], TARGET)
        self.assertEqual(result["fixedComparisonFindingCount"], 0)
        self.assertNotIn("2.0", result["agentObjective"])
        self.assertNotIn(str(self.fixed), result["agentObjective"])
        self.assertTrue(result["executionBoundary"]["requiresExplicitSeparateApproval"])

    def test_rejects_modified_baseline_source(self):
        (self.base / "pom.xml").write_text("modified")
        with self.assertRaises(ValueError):
            self.run_plan()

    def test_rejects_remaining_fixed_findings(self):
        self.fixed_report.write_bytes(self.baseline_report.read_bytes())
        with self.assertRaises(ValueError):
            self.run_plan()

    def test_rejects_scanner_symlink(self):
        link = self.scanner.parent / "scanner-link"
        link.symlink_to(self.scanner)
        with self.assertRaises(ValueError):
            prepare(self.base, self.fixed, self.baseline_report, self.fixed_report, link)


if __name__ == "__main__":
    unittest.main()
