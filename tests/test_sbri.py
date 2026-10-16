import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from spring_boot_release_intelligence.a7 import Dependency
from spring_boot_release_intelligence.report import TABLES, render_html
from spring_boot_release_intelligence.sbri_cli import main as cli_main
from spring_boot_release_intelligence.security_report import read_cyclonedx_vulnerabilities
from spring_boot_release_intelligence.standalone import (discover_boot_version,
                                                         _pom_inputs, _portable, rank_releases,
                                                         validate_result)


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
                      "project_id": "sample-app", "original_pom_sha256": "x"},
      "execution": {"requested_releases": ["1.0.1"], "evaluated_releases": ["1.0.0", "1.0.1"],
                    "selected_severities": SEVS, "scopes": ["compile"],
                    "profiles": [], "discovered_modules": ["api", "service"],
                    "other_severities": "None; all scanner severity categories selected"},
      "scanner": {"provider": "test", "version": "1", "inventory_format": "CycloneDX 1.5",
                  "snapshot_comparable": True},
      "releases": [
        {"version": "1.0.0", "assessment_status": "COMPLETE", "rank": None,
         "counts": {"original": counts(1), "addressed": counts(), "remaining": counts(1),
                    "new": counts(), "total": counts(1)}, "recommendation": "Baseline"},
        {"version": "1.0.1", "assessment_status": "COMPLETE", "rank": 1,
         "counts": {"original": counts(1), "addressed": counts(1), "remaining": counts(),
                    "new": counts(), "total": counts()}, "recommendation": "Preferred"}],
      "dependencies": [dependency, candidate], "findings": [finding], "override_notes": [],
      "evidence": {"coverage": "Complete test inventory", "limitations": ["Test limitation"]},
      "errors": []}


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
            fragment = rendered.split(f'<table id="table{index}"', 1)[1].split("</table>", 1)[0]
            positions = [fragment.index(f"<th>{heading}</th>") for heading in table]
            self.assertEqual(positions, sorted(positions))
        exact = [x.format(base="1.0.0", selected="1.0.1") for x in TABLES[3]]
        self.assertTrue(all(f"<th>{heading}</th>" in rendered for heading in exact))
        self.assertIn("<th>Boot 1.0.0 default</th>", rendered)
        self.assertNotIn("Boot {base} default", rendered)
        self.assertIn("g:a", rendered); self.assertIn("Preferred", rendered)

    def test_report_header_contains_complete_assessment_metadata(self):
        rendered = render_html(result_fixture())
        for value in ("sample-app", "1.0.0", "1.0.1", "test", "api, service",
                      "None", "compile", "CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN",
                      "all scanner severity categories selected", "Complete test inventory",
                      "Test limitation"):
            self.assertIn(value, rendered)
        self.assertEqual(4, rendered.count("<table id="))

    def test_filter_controls_are_emitted_for_every_header_without_mutating_result(self):
        result = result_fixture(); before = deepcopy(result)
        rendered = render_html(result)
        self.assertEqual(result, before)
        self.assertEqual(4, rendered.count('data-filterable="true"'))
        self.assertEqual(4, rendered.count('class="reset-filters"'))
        self.assertEqual(4, rendered.count('class="row-count"'))
        self.assertIn("new TableFilter(table)", rendered)

    def test_report_escapes_dependency_and_scanner_controlled_text(self):
        result = result_fixture()
        result["dependencies"][0]["coordinate"] = '<img src=x onerror="alert(1)">'
        result["findings"][0].update({"advisory_id": "<script>alert(2)</script>",
                                      "package": "unsafe&package",
                                      "evidence_reference": 'evidence/<bad>.json'})
        rendered = render_html(result)
        self.assertNotIn('<img src=x onerror="alert(1)">', rendered)
        self.assertNotIn("<script>alert(2)</script>", rendered)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", rendered)
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", rendered)

    def test_evidence_references_are_output_relative_and_exist(self):
        with tempfile.TemporaryDirectory() as value:
            output = Path(value)
            evidence = output / "evidence" / "1.0.0" / "scanner.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text("{}")
            reference = _portable(evidence, output)
            self.assertEqual("evidence/1.0.0/scanner.json", reference)
            self.assertTrue((output / reference).is_file())

    def test_external_evidence_reference_is_not_falsely_rewritten(self):
        with tempfile.TemporaryDirectory() as output_value, tempfile.TemporaryDirectory() as external_value:
            external = Path(external_value) / "scanner.json"
            external.write_text("{}")
            self.assertEqual(str(external), _portable(external, Path(output_value)))

    def test_reactor_modules_are_discovered_as_managed_project_components(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "pom.xml").write_text('''<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>example</groupId><artifactId>app</artifactId><version>1</version>
<name>Example Application</name><modules><module>service</module></modules>
<dependencyManagement><dependencies><dependency><groupId>example</groupId><artifactId>service</artifactId><version>${project.version}</version></dependency></dependencies></dependencyManagement>
</project>''')
            (root / "service").mkdir()
            (root / "service" / "pom.xml").write_text('''<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><parent><groupId>example</groupId><artifactId>app</artifactId><version>1</version></parent><artifactId>service</artifactId>
</project>''')
            inputs = _pom_inputs(root)
            self.assertEqual(["service"], inputs["modules"])
            self.assertEqual({"example:service"}, inputs["reactor"])
            self.assertEqual("Example Application", inputs["project_id"])

    def test_external_cyclonedx_vulnerability_ingestion(self):
        path = Path("tests/fixtures/external-scanner.cdx.json")
        report = json.loads(path.read_text())
        findings = read_cyclonedx_vulnerabilities(
            report, [Dependency("org.example", "library", "1.0")], str(path))
        self.assertEqual("EXT-2026-1", findings[0]["advisory_id"])
        self.assertEqual("HIGH", findings[0]["severity"])
        self.assertEqual(["1.1"], findings[0]["fixed_versions"])

    def test_cli_exit_codes_for_complete_partial_and_baseline_failure(self):
        for status, expected in (("SUCCESS", 0), ("PARTIAL", 3), ("FAILURE", 2)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as value:
                output = Path(value) / "out"; output.mkdir()
                result = result_fixture(); result["status"] = status
                evaluator = unittest.mock.Mock(); evaluator.evaluate.return_value = result
                with patch("spring_boot_release_intelligence.sbri_cli.discover_boot_version",
                           return_value={"version": "1.0.0"}), \
                     patch("spring_boot_release_intelligence.sbri_cli.select_candidates",
                           return_value=(["1.0.1"], {"method": "explicit"})), \
                     patch("spring_boot_release_intelligence.sbri_cli.Evaluator", return_value=evaluator):
                    self.assertEqual(expected, cli_main(["evaluate", "--project", value,
                        "--releases", "1.0.1", "--output", str(output)]))
                    self.assertTrue((output / "result.json").is_file())
                    self.assertTrue((output / "report.html").is_file())
        with tempfile.TemporaryDirectory() as value:
            evaluator = unittest.mock.Mock(); evaluator.evaluate.side_effect = ValueError("no baseline")
            with patch("spring_boot_release_intelligence.sbri_cli.discover_boot_version",
                       return_value={"version": "1.0.0"}), \
                 patch("spring_boot_release_intelligence.sbri_cli.select_candidates",
                       return_value=(["1.0.1"], {"method": "explicit"})), \
                 patch("spring_boot_release_intelligence.sbri_cli.Evaluator", return_value=evaluator):
                self.assertEqual(2, cli_main(["evaluate", "--project", value,
                    "--releases", "1.0.1", "--output", str(Path(value) / "out")]))

    def test_cli_passes_external_scanner_reports_and_optional_inputs(self):
        with tempfile.TemporaryDirectory() as value:
            output = Path(value) / "out"; output.mkdir()
            result = result_fixture(); evaluator = unittest.mock.Mock(); evaluator.evaluate.return_value = result
            with patch("spring_boot_release_intelligence.sbri_cli.discover_boot_version",
                       return_value={"version": "1.0.0"}), \
                 patch("spring_boot_release_intelligence.sbri_cli.select_candidates",
                       return_value=(["1.0.1"], {"method": "explicit"})), \
                 patch("spring_boot_release_intelligence.sbri_cli.Evaluator", return_value=evaluator) as constructor:
                code = cli_main(["evaluate", "--project", value, "--releases", "1.0.1",
                    "--output", str(output), "--profiles", "prod", "--modules", "api,web",
                    "--scopes", "runtime", "--severities", "critical,high",
                    "--scanner-report", "1.0.0=base.json",
                    "--scanner-report", "1.0.1=next.json", "--timeout", "42"])
                self.assertEqual(0, code)
                kwargs = constructor.call_args.kwargs
                self.assertEqual(["prod"], kwargs["profiles"])
                self.assertEqual(["api", "web"], kwargs["modules"])
                self.assertEqual(["runtime"], kwargs["scopes"])
                self.assertEqual(["CRITICAL", "HIGH"], kwargs["severities"])
                self.assertEqual(42, kwargs["timeout"])
                self.assertEqual({"1.0.0": Path("base.json"), "1.0.1": Path("next.json")},
                                 kwargs["scanner_reports"])

    def test_invalid_json_configuration_returns_configuration_exit_code(self):
        with tempfile.TemporaryDirectory() as value:
            config = Path(value) / "config.json"; config.write_text("{not-json")
            self.assertEqual(2, cli_main(["evaluate", "--project", value,
                "--releases", "1.0.1", "--config", str(config)]))

    def test_configuration_defined_release_selection_reaches_shared_selector(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); output = root / "out"; output.mkdir()
            config = root / "config.json"
            config.write_text(json.dumps({"release_selection": {"ranges": ["1.1.x"]},
                                          "scanner": "configured-scanner"}))
            evaluated = result_fixture(); evaluator = unittest.mock.Mock()
            evaluator.evaluate.return_value = evaluated
            selection = {"mode": "range", "source": "config",
                         "resolved_candidates": ["1.1.0"]}
            with patch("spring_boot_release_intelligence.sbri_cli.discover_boot_version",
                       return_value={"version": "1.0.0"}), \
                 patch("spring_boot_release_intelligence.sbri_cli.select_candidates",
                       return_value=(["1.1.0"], selection)) as selector, \
                 patch("spring_boot_release_intelligence.sbri_cli.Evaluator",
                       return_value=evaluator) as constructor:
                self.assertEqual(0, cli_main(["evaluate", "--project", str(root),
                    "--config", str(config), "--output", str(output)]))
            self.assertIsNone(selector.call_args.kwargs["versions"])
            self.assertIsNone(selector.call_args.kwargs["ranges"])
            self.assertEqual("1.1.x", selector.call_args.kwargs["config"]
                             ["release_selection"]["ranges"][0])
            self.assertEqual("configured-scanner", constructor.call_args.kwargs["scanner"])

    def test_failed_candidate_is_not_rendered_as_zero_findings(self):
        result = result_fixture()
        result["releases"].append({"version": "1.0.2", "assessment_status": "FAILED",
            "rank": None, "counts": {name: None for name in
            ("original", "addressed", "remaining", "new", "total")},
            "recommendation": "Not ranked — assessment failed"})
        result["errors"].append({"release": "1.0.2", "stage": "scanner",
                                 "message": "unavailable"})
        rendered = render_html(result)
        table2 = rendered.split('<table id="table2"', 1)[1].split("</table>", 1)[0]
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
