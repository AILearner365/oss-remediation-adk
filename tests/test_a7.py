import json
import tempfile
import unittest
from pathlib import Path

from spring_boot_release_intelligence.a7 import (
    CandidateConfigurationError, Dependency, compare_findings,
    materialize_candidate, minimal_cyclonedx, reconcile,
    validate_minimal_cyclonedx, management_category, release_comparison,
)


class A7Tests(unittest.TestCase):
    def test_minimal_bom_is_deterministic_and_deduplicates_occurrences(self):
        values = [Dependency("g", "a", "1", module="one"),
                  Dependency("g", "a", "1", module="two")]
        first = minimal_cyclonedx(values, serial_seed="case")
        self.assertEqual(first, minimal_cyclonedx(values, serial_seed="case"))
        self.assertEqual([], validate_minimal_cyclonedx(first))
        self.assertEqual(1, len(first["components"]))
        self.assertTrue(reconcile(values, first)["equal"])

    def test_reconciliation_exposes_inventory_difference(self):
        bom = minimal_cyclonedx([Dependency("g", "a", "2")], serial_seed="x")
        result = reconcile([Dependency("g", "a", "1")], bom)
        self.assertFalse(result["equal"])
        self.assertEqual([("g:a", "1")], result["a5_only"])

    def test_incomplete_assessment_is_never_clean(self):
        result = compare_findings([], [], False)
        self.assertEqual("INCOMPLETE", result["assessment"])
        self.assertFalse(result["clean"])

    def test_findings_use_package_and_advisory_across_versions(self):
        baseline = [{"package": "g:a", "version": "1", "advisory": "X"}]
        candidate = [{"package": "g:a", "version": "2", "advisory": "X"},
                     {"package": "g:b", "version": "1", "advisory": "Y"}]
        result = compare_findings(baseline, candidate, True)
        self.assertEqual(1, len(result["remaining"]))
        self.assertEqual(1, len(result["additional"]))
        self.assertEqual(0, len(result["addressed"]))

    def test_parent_candidate_materialization_starts_from_source(self):
        pom = """<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
<parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.3.4</version></parent>
<artifactId>x</artifactId></project>"""
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); source = root / "source"; source.mkdir()
            (source / "pom.xml").write_text(pom)
            one = materialize_candidate(source, root / "one", "3.3.5")
            two = materialize_candidate(source, root / "two", "3.3.8")
            self.assertEqual("3.3.4", one["original"])
            self.assertIn("3.3.5", (root / "one/pom.xml").read_text())
            self.assertIn("3.3.8", (root / "two/pom.xml").read_text())
            self.assertIn("3.3.4", (source / "pom.xml").read_text())

    def test_ambiguous_dual_controller_is_rejected(self):
        pom = """<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
<parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.3.4</version></parent>
<artifactId>x</artifactId><dependencyManagement><dependencies><dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-dependencies</artifactId><version>3.3.4</version></dependency></dependencies></dependencyManagement></project>"""
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); source = root / "source"; source.mkdir()
            (source / "pom.xml").write_text(pom)
            with self.assertRaisesRegex(CandidateConfigurationError, "AMBIGUOUS"):
                materialize_candidate(source, root / "candidate", "3.3.5")

    def test_release_arithmetic_and_new_high_finding(self):
        baseline = [{"package": "g:a", "version": "1", "advisory": "A",
                     "severity": "MEDIUM"}]
        candidate = [{"package": "g:b", "version": "1", "advisory": "B",
                      "severity": "HIGH"}]
        result = release_comparison(baseline, candidate, True)
        self.assertTrue(all(result["invariants"].values()))
        self.assertEqual(1, result["addressed"]["MEDIUM"])
        self.assertEqual(1, result["additional"]["HIGH"])

    def test_management_categories_are_evidence_driven(self):
        boot = {"g:a": "2", "g:b": "2"}
        other = {"g:c": "1"}
        self.assertEqual("BOOT_MANAGED_OVERRIDDEN", management_category(
            "g:a", direct=False, explicit_versions={"g:a"}, boot_defaults=boot,
            other_defaults=other))
        self.assertEqual("OTHER_MANAGED", management_category(
            "g:c", direct=True, explicit_versions=set(), boot_defaults=boot,
            other_defaults=other))
        self.assertEqual("INDEPENDENT_TRANSITIVE", management_category(
            "g:d", direct=False, explicit_versions=set(), boot_defaults=boot,
            other_defaults=other))


if __name__ == "__main__":
    unittest.main()
