import json
import tempfile
import unittest
from pathlib import Path

from spring_boot_release_intelligence.depsdev import DepsDevClient
from spring_boot_release_intelligence.experiment import explicit_range_verdict
from spring_boot_release_intelligence.osv import OsvClient


class OfflineIntelligenceTests(unittest.TestCase):
    def test_osv_original_identity_comparison_keeps_new_separate(self):
        baseline = {"vulnerabilities": [{"id": "A"}, {"id": "B"}]}
        candidate = {"vulnerabilities": [{"id": "B"}, {"id": "C"}]}
        self.assertEqual(OsvClient.compare_original(baseline, candidate), {
            "original_ids": ["A", "B"], "still_reported": ["B"],
            "not_reported": ["A"], "new_ids": ["C"]})

    def test_no_package_range_is_unknown(self):
        result = explicit_range_verdict({"affected": []}, "g:a", "2.0")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_explicit_numeric_fixed_event_can_support_addressed(self):
        advisory = {"affected": [{"package": {"ecosystem": "Maven", "name": "g:a"},
                                  "ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.0.1"}]}]}]}
        self.assertEqual(explicit_range_verdict(advisory, "g:a", "2.0.1")["status"], "ADDRESSED")
        self.assertEqual(explicit_range_verdict(advisory, "g:a", "2.0.0")["status"], "UNKNOWN")

    def test_qualifier_version_is_not_compared_as_numeric(self):
        advisory = {"affected": [{"package": {"ecosystem": "Maven", "name": "g:a"},
                                  "ranges": [{"events": [{"fixed": "2.0.Final"}]}]}]}
        self.assertEqual(explicit_range_verdict(advisory, "g:a", "2.1.Final")["status"], "UNKNOWN")

    def test_deps_dev_path_uses_edges_not_node_order(self):
        graph = {"nodes": [
            {"versionKey": {"name": "root", "version": "1"}},
            {"versionKey": {"name": "target", "version": "2"}},
            {"versionKey": {"name": "middle", "version": "3"}}],
            "edges": [{"fromNode": 0, "toNode": 2}, {"fromNode": 2, "toNode": 1}]}
        self.assertEqual(DepsDevClient.paths(graph, "target"),
                         [["root:1", "middle:3", "target:2"]])

    def test_original_fixture_is_unchanged(self):
        fixture = Path(__file__).parent / "fixtures" / "spring_boot_release_intelligence_cases.json"
        cases = json.loads(fixture.read_text())["cases"]
        self.assertEqual([c["id"] for c in cases], ["C1", "C2", "C3", "C4"])


if __name__ == "__main__":
    unittest.main()
