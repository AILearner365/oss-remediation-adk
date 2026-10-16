import json
import tempfile
import unittest
from pathlib import Path

from spring_boot_release_intelligence.a7 import Dependency
from spring_boot_release_intelligence.report import TABLES, render_html
from spring_boot_release_intelligence.security_report import read_cyclonedx_vulnerabilities
from spring_boot_release_intelligence.standalone import (discover_boot_version,
                                                         rank_releases, validate_result)


SEVS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]


def counts(total=0):
    value = {key: 0 for key in SEVS}; value["HIGH"] = total; return value


def result_fixture():
    finding = {"identity": "g:a|ADV", "package": "g:a", "version": "1",
               "advisory_id": "ADV", "severity": "HIGH", "fixed_versions": ["2"]}
    dependency = {"release": "1.0.0", "coordinate": "g:a", "ownership": "BOOT_MANAGED",
                  "boot_managed_default": "1", "selected_version": "1", "findings": [finding]}
    candidate = {**dependency, "release": "1.0.1", "selected_version": "2", "findings": []}
    return {"schema_version": "1.0", "status": "SUCCESS",
      "application": {"project_path": "/p", "original_spring_boot_version": "1.0.0",
                      "original_pom_sha256": "x"},
      "execution": {"requested_releases": ["1.0.1"], "evaluated_releases": ["1.0.0", "1.0.1"],
                    "selected_severities": SEVS, "scopes": ["compile"]},
      "scanner": {"provider": "test", "version": "1", "inventory_format": "CycloneDX 1.5"},
      "releases": [
        {"version": "1.0.0", "assessment_status": "COMPLETE", "rank": None,
         "counts": {"original": counts(1), "addressed": counts(), "remaining": counts(1),
                    "new": counts(), "total": counts(1)}, "recommendation": "Baseline"},
        {"version": "1.0.1", "assessment_status": "COMPLETE", "rank": 1,
         "counts": {"original": counts(1), "addressed": counts(1), "remaining": counts(),
                    "new": counts(), "total": counts()}, "recommendation": "Preferred"}],
      "dependencies": [dependency, candidate], "findings": [finding], "override_notes": [],
      "evidence": {}, "errors": []}


class SbriTests(unittest.TestCase):
    def test_discovers_boot_parent(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "pom.xml").write_text('''<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.3.4</version></parent><artifactId>x</artifactId></project>''')
            self.assertEqual("3.3.4", discover_boot_version(root)["version"])

    def test_contract_validation_and_arithmetic(self):
        self.assertEqual([], validate_result(result_fixture()))
        schema = json.loads(Path("spring_boot_release_intelligence/result-schema-v1.json").read_text())
        try:
            import jsonschema
            jsonschema.validate(result_fixture(), schema)
        except ImportError:
            self.skipTest("jsonschema is not installed")
        broken = result_fixture(); broken["releases"][1]["counts"]["total"]["HIGH"] = 2
        self.assertIn("1.0.1: candidate arithmetic", validate_result(broken))

    def test_exact_four_table_headings_and_json_consistency(self):
        result = result_fixture(); rendered = render_html(result)
        self.assertEqual(4, rendered.count("<table id="))
        for index, table in enumerate(TABLES[:2], 1):
            fragment = rendered.split(f'<table id="table{index}">', 1)[1].split("</table>", 1)[0]
            positions = [fragment.index(f"<th>{heading}</th>") for heading in table]
            self.assertEqual(positions, sorted(positions))
        exact = [x.format(base="1.0.0", selected="1.0.1") for x in TABLES[3]]
        self.assertTrue(all(f"<th>{heading}</th>" in rendered for heading in exact))
        self.assertIn("g:a", rendered); self.assertIn("Preferred", rendered)

    def test_external_cyclonedx_vulnerability_ingestion(self):
        path = Path("tests/fixtures/external-scanner.cdx.json")
        report = json.loads(path.read_text())
        findings = read_cyclonedx_vulnerabilities(
            report, [Dependency("org.example", "library", "1.0")], str(path))
        self.assertEqual("EXT-2026-1", findings[0]["advisory_id"])
        self.assertEqual("HIGH", findings[0]["severity"])
        self.assertEqual(["1.1"], findings[0]["fixed_versions"])

    def test_failed_candidate_is_not_rendered_as_zero_findings(self):
        result = result_fixture()
        result["releases"].append({"version": "1.0.2", "assessment_status": "FAILED",
            "rank": None, "counts": {name: None for name in
            ("original", "addressed", "remaining", "new", "total")},
            "recommendation": "Not ranked — assessment failed"})
        result["errors"].append({"release": "1.0.2", "stage": "scanner",
                                 "message": "unavailable"})
        rendered = render_html(result)
        table2 = rendered.split('<table id="table2">', 1)[1].split("</table>", 1)[0]
        self.assertNotIn("1.0.2", table2)
        self.assertIn("1.0.2 / scanner: unavailable", rendered)

    def test_ranking_is_severity_first_and_ignores_override_notes(self):
        result = result_fixture()
        first = result["releases"][1]
        first["version"] = "1.0.1"; first["counts"]["total"] = counts(5)
        second = json.loads(json.dumps(first)); second["version"] = "1.0.2"
        second["counts"]["total"] = counts(0); second["counts"]["total"]["CRITICAL"] = 1
        result["releases"].append(second)
        result["override_notes"] = ["An opportunity note that must not affect ranking"]
        rank_releases(result["releases"], "1.0.0")
        self.assertEqual(1, first["rank"])
        self.assertEqual(2, second["rank"])


if __name__ == "__main__":
    unittest.main()
