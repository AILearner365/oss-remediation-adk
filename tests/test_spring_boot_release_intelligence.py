import json
import tempfile
import unittest
from pathlib import Path

from spring_boot_release_intelligence.depsdev import DepsDevClient
from spring_boot_release_intelligence.experiment import explicit_range_verdict
from spring_boot_release_intelligence.osv import OsvClient, advisory_verdict, compare_maven_versions
from spring_boot_release_intelligence.validation import check, equality_check, evaluate
from spring_boot_release_intelligence.maven import parse_tgf
from spring_boot_release_intelligence.metadata_maven import (
    MetadataOnlyMavenResolver, classify_repository_delta, transfer_metrics)


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

    def test_tgf_parser_preserves_selected_versions_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory) / "tree.tgf"
            tree.write_text(
                "1 example:app:jar:1\n"
                "2 org.example:middle:jar:2:compile\n"
                "3 org.example:target:jar:3:runtime\n#\n"
                "1 2 compile\n2 3 runtime\n", encoding="utf-8")
            result = parse_tgf(tree, ["org.example:target"])
        self.assertEqual(result["selected_artifacts"]["org.example:target"], "3")
        self.assertEqual(result["target_paths"]["org.example:target"], [[
            "example:app:1", "org.example:middle:2", "org.example:target:3"]])

    def test_repository_inventory_separates_dependency_and_plugin_jars(self):
        after = {
            "org/example/lib/1/lib-1.pom": 10,
            "org/example/lib/1/lib-1.jar": 20,
            "org/apache/maven/plugins/plugin/1/plugin-1.jar": 30,
            "org/example/lib/maven-metadata-central.xml": 40,
        }
        result = classify_repository_delta({}, after, {"org.example:lib": "1"})
        self.assertEqual(result["categories"]["application_dependency_jar"]["count"], 1)
        self.assertEqual(result["categories"]["plugin_bootstrap_jar"]["count"], 1)
        self.assertEqual(result["categories"]["pom"]["count"], 1)
        self.assertEqual(result["categories"]["maven_metadata"]["count"], 1)

    def test_transfer_metrics_are_explicitly_not_http_request_counts(self):
        log = ("Downloading from central: https://repo/x.pom\n"
               "Downloaded from central: https://repo/x.pom (2.5 kB at 1 kB/s)\n")
        result = transfer_metrics(log)
        self.assertEqual(result["transfer_attempt_events"], 1)
        self.assertEqual(result["successful_transfer_events"], 1)
        self.assertEqual(result["maven_reported_bytes"], 2500)
        self.assertIsNone(result["http_request_count"])

    def test_a5_command_is_pinned_and_uses_isolated_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resolver = MetadataOnlyMavenResolver(root / "work", root / "repo")
            self.assertEqual(resolver.local_repository, root / "repo")
        from spring_boot_release_intelligence.metadata_maven import PLUGIN_GOAL
        self.assertEqual(
            PLUGIN_GOAL,
            "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree")


if __name__ == "__main__":
    unittest.main()
