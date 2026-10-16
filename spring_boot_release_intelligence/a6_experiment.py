from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .a5_experiment import (_PeakSampler, _a5_cells, _accuracy,
                            _release_comparison, _run_workload, _storage,
                            _selected_union)
from .experiment import BOOTS, DEPENDENCIES, PACKAGE
from .maven import MavenResolver
from .metadata_maven import (CollectMavenResolver, MetadataOnlyMavenResolver,
                             parse_collect, repository_snapshot)
from .maven import parse_tgf
from .validation import availability_check, equality_check, evaluate


def dependency_selection(record: dict) -> dict[str, str]:
    """Return dependencies while excluding only the graph's application root."""
    roots = set(record.get("root_artifacts", []))
    return {coordinate: version
            for coordinate, version in record["selected_artifacts"].items()
            if coordinate not in roots}


def _selection_accuracy(reference: dict, candidate: dict) -> dict:
    checks = []
    for group in ("maven", "overrides"):
        for case, observed in candidate[group].items():
            expected = dependency_selection(reference[group][case])
            actual = dependency_selection(observed)
            checks.extend([
                {"case": f"{group}.{case}.selected_set",
                 "passed": set(actual) == set(expected),
                 "missing": sorted(set(expected) - set(actual)),
                 "unexpected": sorted(set(actual) - set(expected))},
                {"case": f"{group}.{case}.selected_versions",
                 "passed": actual == expected},
            ])
    for case, observed_case in candidate["scenarios"].items():
        expected = dependency_selection(reference["scenarios"][case]["observation"])
        actual = dependency_selection(observed_case["observation"])
        checks.extend([
            {"case": f"scenarios.{case}.selected_set",
             "passed": set(actual) == set(expected),
             "missing": sorted(set(expected) - set(actual)),
             "unexpected": sorted(set(actual) - set(expected))},
            {"case": f"scenarios.{case}.selected_versions",
             "passed": actual == expected},
        ])
    failed = [item for item in checks if not item["passed"]]
    return {"checks": checks, "passed": not failed,
            "passed_count": len(checks) - len(failed),
            "total_count": len(checks),
            "first_material_difference": failed[0] if failed else None}


def _record_signature(record: dict) -> tuple:
    return (record["coordinate"], record["type"], record["classifier"] or "",
            record["version"], record["scope"] or "")


def _dependency_record_signatures(record: dict) -> list[tuple]:
    roots = set(record.get("root_artifacts", []))
    return sorted(_record_signature(item) for item in record["selected_records"]
                  if item["coordinate"] not in roots)


def _artifact_detail_accuracy(reference: dict, candidate: dict) -> dict:
    checks = []
    for group in ("maven", "overrides"):
        for case, observed in candidate[group].items():
            checks.append({
                "case": f"{group}.{case}.type_classifier_scope_version",
                "passed": _dependency_record_signatures(observed) ==
                          _dependency_record_signatures(reference[group][case]),
            })
    for case, observed_case in candidate["scenarios"].items():
        checks.append({
            "case": f"scenarios.{case}.type_classifier_scope_version",
            "passed": _dependency_record_signatures(observed_case["observation"]) ==
                      _dependency_record_signatures(
                          reference["scenarios"][case]["observation"]),
        })
    failed = [item for item in checks if not item["passed"]]
    return {"checks": checks, "passed": not failed,
            "passed_count": len(checks) - len(failed),
            "total_count": len(checks),
            "first_material_difference": failed[0] if failed else None}


def _vulnerability_agreement(a5_release: dict, a6_release: dict) -> dict:
    fields = ("addressed", "still_affected", "new_findings", "unknown")
    checks = []
    for boot in BOOTS[1:]:
        for package in DEPENDENCIES:
            left = a5_release["candidates"][boot]["artifacts"][package]
            right = a6_release["candidates"][boot]["artifacts"][package]
            for field in fields:
                checks.append({"case": f"{boot}.{package}.{field}",
                               "passed": left.get(field, []) == right.get(field, [])})
    failed = [item for item in checks if not item["passed"]]
    return {"checks": checks, "passed": not failed,
            "passed_count": len(checks) - len(failed),
            "total_count": len(checks),
            "first_material_difference": failed[0] if failed else None}


def _a6_cells(a6: dict, historical: dict) -> tuple[list[dict], list[dict]]:
    selected = {boot: a6["maven"][boot]["selected_version"] for boot in BOOTS}
    managed = {boot: historical["a1"]["managed"][boot][PACKAGE]["version"]
               for boot in BOOTS}
    overrides = {boot: a6["overrides"][boot]["selected_version"]
                 for boot in BOOTS[1:]}
    verdicts = {boot: historical["a1"]["c3"]["candidate_verdicts"][boot]["status"]
                for boot in BOOTS[1:]}
    complete = all(record["collection_complete"]
                   for record in list(a6["maven"].values()) +
                   list(a6["overrides"].values()))
    cells = [
        evaluate("A6", "C1", [
            equality_check("collect selected defaults", selected, managed,
                           ["a6.maven", "historical.a1.managed"]),
            equality_check("all collections parsed completely", complete, True,
                           ["a6.maven", "a6.overrides"]),
            availability_check("frozen OSV evidence", verdicts,
                               ["historical.a1.c3"])],
                 ["flat artifact set; dependency paths unavailable"]),
        evaluate("A6", "C2", [
            equality_check("transitive target present at expected version",
                           selected, managed, ["a6.maven"])],
                 ["introduction path cannot be explained"]),
        evaluate("A6", "C3", [
            equality_check("frozen conservative OSV verdicts", verdicts,
                           {boot: "ADDRESSED" for boot in BOOTS[1:]},
                           ["historical.a1.c3", "a6.maven"])],
                 ["advisories are frozen to v2"]),
        evaluate("A6", "C4", [
            equality_check("application override remains effective", overrides,
                           {boot: "10.1.30" for boot in BOOTS[1:]},
                           ["a6.overrides"])],
                 ["property override fixture"]),
    ]
    expanded = []
    for scenario, record in a6["scenarios"].items():
        checks = [equality_check(name, observed, True,
                                 [f"a6.scenarios.{scenario}.checks.{name}"])
                  for name, observed in record["checks"].items()]
        expanded.append(evaluate("A6", scenario, checks,
                                 ["selected-artifact accuracy; paths not required"]))
    return cells, expanded


def _override_evidence(a6: dict, historical: dict) -> dict:
    affected = next(
        check["observed"]
        for cell in historical["cells"]
        if cell["approach"] == "A2" and cell["case"] == "C4"
        for check in cell["checks"]
        if check["name"] == "overridden version affected")
    return {
        "package": PACKAGE,
        "application_control": "tomcat.version=10.1.30",
        "candidates": {
            boot: {
                "boot_default_version": a6["maven"][boot]["selected_version"],
                "application_selected_version": a6["overrides"][boot]["selected_version"],
                "unchanged_from_baseline": (
                    a6["overrides"][boot]["selected_version"] ==
                    a6["maven"][BOOTS[0]]["selected_version"]),
                "vulnerability_status": affected,
                "attribution": "application-controlled; not fixed by Boot default",
            }
            for boot in BOOTS[1:]
        },
    }


class A6Experiment:
    def __init__(self, output_dir: Path, cache_root: Path, reference_file: Path):
        self.output_dir = output_dir
        self.cache_root = cache_root
        self.reference_file = reference_file
        output_dir.mkdir(parents=True, exist_ok=True)
        cache_root.mkdir(parents=True, exist_ok=True)

    def _approach(self, name: str) -> dict:
        repository = self.cache_root / name.lower()
        work = self.output_dir / "maven-work" / name.lower()
        if name == "A2":
            resolver = MavenResolver(work, repository)
        elif name == "A5":
            resolver = MetadataOnlyMavenResolver(work, repository, quiet=True)
        else:
            resolver = CollectMavenResolver(work, repository, quiet=True)
        passes = {}
        for temperature in ("fresh", "warm"):
            if hasattr(resolver, "run_label"):
                resolver.run_label = temperature
            before = repository_snapshot(repository)
            with _PeakSampler(repository) as sampler:
                workload = _run_workload(resolver)
            workload["storage"] = _storage(repository, before, workload,
                                             sampler.peak, name)
            passes[temperature] = workload
        return passes

    def run(self) -> dict:
        historical = json.loads(self.reference_file.read_text(encoding="utf-8"))
        started = time.monotonic()
        a2 = self._approach("A2")
        a5 = self._approach("A5")
        a6 = self._approach("A6")
        a5_path_accuracy = _accuracy(a2["fresh"], a5["fresh"])
        selection_accuracy = _selection_accuracy(a5["fresh"], a6["fresh"])
        detail_accuracy = _artifact_detail_accuracy(a5["fresh"], a6["fresh"])
        a5_release = _release_comparison(a5["fresh"], historical)
        a6_release = _release_comparison(a6["fresh"], historical)
        vulnerability = _vulnerability_agreement(a5_release, a6_release)
        a5_cells, a5_expanded = _a5_cells(a5["fresh"], historical)
        a6_cells, a6_expanded = _a6_cells(a6["fresh"], historical)
        ranking = sorted(
            ({"boot": boot, **value["summary"]}
             for boot, value in a6_release["candidates"].items()),
            key=lambda item: (-item["addressed"], item["remaining"], item["unknown"],
                              item["boot"]))
        result = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline_commit": "a3163f3fc9476cffd1b71dad0485f7fc9d8eeec6",
            "reference_evidence": str(self.reference_file),
            "environment": self._environment(),
            "mechanism": {
                "goal": "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:collect",
                "output": "flat mediated selected-artifact records",
                "paths_available": False,
                "acceptance": "complete selected set and versions must equal A5",
            },
            "a2": a2, "a5": a5, "a6": a6,
            "a5_path_accuracy_against_a2": a5_path_accuracy,
            "a6_selection_accuracy_against_a5": selection_accuracy,
            "a6_artifact_detail_accuracy_against_a5": detail_accuracy,
            "a6_vulnerability_agreement_with_a5": vulnerability,
            "release_comparison": a6_release,
            "application_override_evidence": _override_evidence(a6["fresh"], historical),
            "candidate_ranking_by_coverage_only": ranking,
            "ranking_warning": "coverage ordering is not a compatibility recommendation",
            "cells": historical["cells"] + a5_cells + a6_cells,
            "expanded_cells": historical["expanded_cells"] + a5_expanded + a6_expanded,
            "measurements": {"total_elapsed_seconds": time.monotonic() - started},
        }
        path = self.output_dir / "results-a6.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    @staticmethod
    def _environment() -> dict:
        return __import__("spring_boot_release_intelligence.a5_experiment",
                          fromlist=["A5Experiment"]).A5Experiment._environment()


def qualify_a6_storage(results_file: Path, output_dir: Path, cache_dir: Path) -> dict:
    empty_pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>experiment</groupId>
<artifactId>bootstrap-control</artifactId><version>1</version></project>"""
    resolver = CollectMavenResolver(output_dir / "bootstrap-control", cache_dir)
    observed = resolver.resolve_pom("project", empty_pom, [])
    bootstrap_jars = {item["path"] for item in observed["storage"]["delta"]["files"]
                      if item["category"] == "plugin_bootstrap_jar"}
    result = json.loads(results_file.read_text(encoding="utf-8"))
    storage = result["a6"]["fresh"]["storage"]
    categories = storage["delta"]["categories"]
    reclassified = []
    for item in storage["delta"]["files"]:
        if item["category"] == "application_dependency_jar" and item["path"] in bootstrap_jars:
            item["category"] = "plugin_bootstrap_jar"
            reclassified.append(item["path"])
            categories["application_dependency_jar"]["count"] -= 1
            categories["application_dependency_jar"]["bytes"] -= item["bytes"]
            categories["plugin_bootstrap_jar"]["count"] += 1
            categories["plugin_bootstrap_jar"]["bytes"] += item["bytes"]
        elif item["category"] == "plugin_bootstrap_jar" and item["path"] not in bootstrap_jars:
            item["category"] = "other_binary"
            categories["plugin_bootstrap_jar"]["count"] -= 1
            categories["plugin_bootstrap_jar"]["bytes"] -= item["bytes"]
            categories["other_binary"]["count"] += 1
            categories["other_binary"]["bytes"] += item["bytes"]
    unexplained = [item["path"] for item in storage["delta"]["files"]
                   if item["category"] in ("application_dependency_jar", "other_binary")]
    storage["no_application_dependency_jars"] = not unexplained
    storage["binary_summary"] = {
        "application_dependency_jars": categories["application_dependency_jar"],
        "plugin_bootstrap_jars": categories["plugin_bootstrap_jar"],
        "other_binary": categories["other_binary"],
    }
    control = {"purpose": "zero-dependency dependency:collect bootstrap attribution",
               "observation": observed,
               "bootstrap_jar_paths": sorted(bootstrap_jars),
               "reclassified_overlap_paths": sorted(reclassified),
               "unexplained_binary_paths": unexplained,
               "qualified_no_application_dependency_jars": not unexplained}
    result["a6_storage_qualification"] = control
    results_file.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "bootstrap-control.json").write_text(
        json.dumps(control, indent=2, sort_keys=True), encoding="utf-8")
    return control


def capture_a6_network_telemetry(results_file: Path, output_dir: Path,
                                 cache_dir: Path) -> dict:
    """Run a separate non-quiet pass so transfer logging cannot bias fair timing."""
    resolver = CollectMavenResolver(output_dir / "telemetry-work", cache_dir,
                                    quiet=False)
    passes = {}
    for temperature in ("fresh", "warm"):
        resolver.run_label = temperature
        before = repository_snapshot(cache_dir)
        workload = _run_workload(resolver)
        workload["storage"] = _storage(cache_dir, before, workload,
                                         sum(repository_snapshot(cache_dir).values()), "A6")
        passes[temperature] = workload["storage"]["transfers"]
    result = json.loads(results_file.read_text(encoding="utf-8"))
    result["a6_network_telemetry"] = {
        "execution_condition": "separate non-quiet isolated A6 pass; excluded from fair timing",
        "fresh_transfers": passes["fresh"], "warm_transfers": passes["warm"]}
    results_file.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result["a6_network_telemetry"]


def finalize_a6_evidence(results_file: Path) -> dict:
    """Add deterministic derived evidence after controls/telemetry complete."""
    result = json.loads(results_file.read_text(encoding="utf-8"))
    historical = json.loads(Path(result["reference_evidence"]).read_text(encoding="utf-8"))
    for approach, parser in (("a5", parse_tgf), ("a6", parse_collect)):
        workload = result[approach]["fresh"]
        records = list(workload["maven"].values()) + list(workload["overrides"].values())
        records += [item["observation"] for item in workload["scenarios"].values()]
        for record in records:
            parsed = parser(Path(record["tree_file"]), [])
            record["selected_records"] = parsed["selected_records"]
            if approach == "a5":
                record["root_artifacts"] = parsed["root_artifacts"]
    result["application_override_evidence"] = _override_evidence(
        result["a6"]["fresh"], historical)
    result["a6_artifact_detail_accuracy_against_a5"] = _artifact_detail_accuracy(
        result["a5"]["fresh"], result["a6"]["fresh"])
    results_file.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result
