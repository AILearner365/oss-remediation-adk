import json
import tempfile
import unittest
from pathlib import Path

from spring_boot_release_intelligence.depsdev import DepsDevClient
from spring_boot_release_intelligence.experiment import explicit_range_verdict
from spring_boot_release_intelligence.osv import OsvClient, advisory_verdict, compare_maven_versions
from spring_boot_release_intelligence.validation import check, equality_check, evaluate


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
                                  "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.0.1"}]}]}]}
        self.assertEqual(explicit_range_verdict(advisory, "g:a", "2.0.1")["status"], "ADDRESSED")
        self.assertEqual(explicit_range_verdict(advisory, "g:a", "2.0.0")["status"], "STILL_AFFECTED")

    def test_qualifier_version_is_not_compared_as_numeric(self):
        advisory = {"affected": [{"package": {"ecosystem": "Maven", "name": "g:a"},
                                  "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.0.Final"}]}]}]}
        self.assertEqual(explicit_range_verdict(advisory, "g:a", "2.0-RC1")["status"], "STILL_AFFECTED")

    def test_unknown_qualifier_is_conservatively_unknown(self):
        advisory = {"affected": [{"package": {"ecosystem": "Maven", "name": "g:a"},
                                  "ranges": [{"type": "ECOSYSTEM", "events": [
                                      {"introduced": "1.0-weird"}, {"fixed": "2.0"}]}]}]}
        self.assertEqual(advisory_verdict(advisory, "g:a", "1.5")["status"], "UNKNOWN")

    def test_reintroduced_interval_is_still_affected(self):
        advisory = {"affected": [{"package": {"ecosystem": "Maven", "name": "g:a"},
            "ranges": [{"type": "ECOSYSTEM", "events": [
                {"introduced": "1.0"}, {"fixed": "2.0"},
                {"introduced": "3.0"}, {"fixed": "4.0"}]}]}]}
        self.assertEqual(advisory_verdict(advisory, "g:a", "3.5")["status"], "STILL_AFFECTED")
        self.assertEqual(advisory_verdict(advisory, "g:a", "2.5")["status"], "ADDRESSED")

    def test_multiple_ranges_are_all_considered(self):
        advisory = {"affected": [{"package": {"ecosystem": "Maven", "name": "g:a"},
            "ranges": [
                {"type": "ECOSYSTEM", "events": [{"introduced": "1"}, {"fixed": "2"}]},
                {"type": "ECOSYSTEM", "events": [{"introduced": "5"}, {"last_affected": "6"}]}]}]}
        self.assertEqual(advisory_verdict(advisory, "g:a", "5.5")["status"], "STILL_AFFECTED")
        self.assertEqual(advisory_verdict(advisory, "g:a", "7")["status"], "ADDRESSED")

    def test_explicit_affected_version_overrides_range_absence(self):
        advisory = {"affected": [{"package": {"ecosystem": "Maven", "name": "g:a"},
                                  "versions": ["9.9"]}]}
        self.assertEqual(advisory_verdict(advisory, "g:a", "9.9")["status"], "STILL_AFFECTED")

    def test_contradictory_interval_is_unknown(self):
        advisory = {"affected": [{"package": {"ecosystem": "Maven", "name": "g:a"},
            "ranges": [{"type": "ECOSYSTEM", "events": [
                {"introduced": "3.0"}, {"fixed": "2.0"}]}]}]}
        self.assertEqual(advisory_verdict(advisory, "g:a", "4.0")["status"], "UNKNOWN")

    def test_maven_known_qualifier_order(self):
        self.assertLess(compare_maven_versions("1.0-RC1", "1.0"), 0)
        self.assertEqual(compare_maven_versions("1.0.Final", "1.0"), 0)
        self.assertGreater(compare_maven_versions("1.0-sp1", "1.0"), 0)

    def test_validation_status_is_derived_from_checks(self):
        self.assertEqual(evaluate("A", "C", [equality_check("x", 1, 1, ["e"])], [])["status"], "PROVEN")
        self.assertEqual(evaluate("A", "C", [check("x", "UNAVAILABLE", None, 1, ["e"])], [])["status"], "NOT_SUPPORTED")
        self.assertEqual(evaluate("A", "C", [check("x", "PASS", 1, 1, ["e"]),
                                                check("y", "UNAVAILABLE", None, 1, ["e"])], [])["status"], "PARTIALLY_PROVEN")
        self.assertEqual(evaluate("A", "C", [equality_check("x", 2, 1, ["e"])], [])["status"], "FAILED")
        self.assertEqual(evaluate("A", "C", [check("x", "NOT_EXECUTED", None, 1, ["e"])], [])["status"], "NOT_TESTED")

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
