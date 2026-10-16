from __future__ import annotations

import json
import platform
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .experiment import BOOTS, DEPENDENCIES, EXPECTED_TOMCAT, PACKAGE
from .maven import MavenResolver
from .maven_scenarios import run_scenarios
from .metadata_maven import (MetadataOnlyMavenResolver,
                             classify_repository_delta, repository_size,
                             repository_snapshot)
from .validation import availability_check, equality_check, evaluate


class _PeakSampler:
    def __init__(self, path: Path):
        self.path = path
        self.peak = repository_size(path)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.wait(0.5):
            self.peak = max(self.peak, repository_size(self.path))

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        self.peak = max(self.peak, repository_size(self.path))


def _run_workload(resolver) -> dict:
    started = time.monotonic()
    maven = {boot: resolver.resolve(boot, targets=DEPENDENCIES) for boot in BOOTS}
    overrides = {boot: resolver.resolve(boot, "10.1.30", DEPENDENCIES)
                 for boot in BOOTS[1:]}
    scenarios = run_scenarios(resolver)
    return {"maven": maven, "overrides": overrides, "scenarios": scenarios,
            "elapsed_seconds": time.monotonic() - started}


def _selected_union(workload: dict) -> dict[str, str]:
    selected = {}
    for record in list(workload["maven"].values()) + list(workload["overrides"].values()):
        selected.update(record["selected_artifacts"])
    for record in workload["scenarios"].values():
        selected.update(record["observation"]["selected_artifacts"])
    return selected


def _storage(repository: Path, before: dict[str, int], workload: dict,
             peak: int, approach: str) -> dict:
    after = repository_snapshot(repository)
    inventory = classify_repository_delta(before, after, _selected_union(workload))
    transfers = {"transfer_attempt_events": None,
                 "successful_transfer_events": None,
                 "maven_reported_bytes": None,
                 "http_request_count": None,
                 "reason": "A2 quiet Maven output does not expose transport events"}
    if approach in ("A5", "A6"):
        records = list(workload["maven"].values()) + list(workload["overrides"].values())
        records += [value["observation"] for value in workload["scenarios"].values()]
        transfers = {
            key: sum(record["storage"]["transfers"][key] for record in records)
            for key in ("transfer_attempt_events", "successful_transfer_events",
                        "maven_reported_bytes")
        }
        transfers.update({"http_request_count": None,
                          "reason": "Maven CLI exposes transfer events, not HTTP request counts"})
    cats = inventory["categories"]
    return {"cache_bytes_before": sum(before.values()),
            "cache_bytes_after": sum(after.values()), "peak_cache_bytes": peak,
            "delta": inventory, "transfers": transfers,
            "no_application_dependency_jars": cats["application_dependency_jar"]["count"] == 0,
            "binary_summary": {
                "application_dependency_jars": cats["application_dependency_jar"],
                "plugin_bootstrap_jars": cats["plugin_bootstrap_jar"],
                "other_binary": cats["other_binary"]}}


def _normalized_paths(record: dict) -> dict:
    return {key: sorted(value) for key, value in record["target_paths"].items()}


def _accuracy(reference: dict, candidate: dict) -> dict:
    checks = []
    for group in ("maven", "overrides"):
        for case, observed in candidate[group].items():
            expected = reference[group][case]
            checks.append({"case": f"{group}.{case}.versions",
                           "passed": observed["selected_artifacts"] == expected["selected_artifacts"]})
            checks.append({"case": f"{group}.{case}.paths",
                           "passed": _normalized_paths(observed) == _normalized_paths(expected)})
    for case, observed in candidate["scenarios"].items():
        expected = reference["scenarios"][case]
        checks.append({"case": f"scenarios.{case}.selected_version",
                       "passed": observed["observation"]["selected_version"]
                                 == expected["observation"]["selected_version"]})
        checks.append({"case": f"scenarios.{case}.target_paths",
                       "passed": _normalized_paths(observed["observation"])
                                 == _normalized_paths(expected["observation"])})
    failed = [item for item in checks if not item["passed"]]
    return {"checks": checks, "passed": not failed,
            "passed_count": len(checks) - len(failed), "total_count": len(checks),
            "first_material_difference": failed[0] if failed else None}


def _release_comparison(a5: dict, historical: dict) -> dict:
    source = historical["a4"]["release_comparison"]
    candidates = {}
    for boot in BOOTS[1:]:
        artifacts = {}
        for package in DEPENDENCIES:
            selected = a5["maven"][boot]["selected_artifacts"].get(package)
            reference = source["candidates"][boot]["artifacts"][package]
            managed = historical["a1"]["managed"][boot][package]
            if selected != reference.get("version"):
                artifacts[package] = {
                    "version": selected, "status": "UNKNOWN",
                    "reason": "version absent from frozen v2 advisory comparison",
                    "paths": a5["maven"][boot]["target_paths"].get(package, [])}
                continue
            item = dict(reference)
            item["paths"] = a5["maven"][boot]["target_paths"].get(package, [])
            item["current_resolved_version"] = source["baseline_versions"].get(package)
            item["candidate_resolved_version"] = selected
            item["selection_reason"] = "selected by complete Maven application graph"
            item["control"] = ("application-controlled" if managed and
                               managed["version"] != selected else "Boot-BOM-managed")
            item["vulnerability_source"] = "frozen v2 OSV evidence"
            artifacts[package] = item
        summary = {
            "addressed": sum(len(x.get("addressed", [])) for x in artifacts.values()),
            "remaining": sum(len(x.get("still_affected", [])) for x in artifacts.values()),
            "new": sum(len(x.get("new_findings", [])) for x in artifacts.values()),
            "unknown": sum(len(x.get("unknown", [])) for x in artifacts.values()),
            "unchanged_dependencies": sum(
                x.get("candidate_resolved_version") == x.get("current_resolved_version")
                for x in artifacts.values()),
            "absent_dependencies": sum(x.get("version") is None for x in artifacts.values()),
        }
        candidates[boot] = {"artifacts": artifacts, "summary": summary,
                            "compatibility_evidence": "NOT_TESTED"}
    return {"baseline_versions": source["baseline_versions"], "candidates": candidates,
            "advisory_snapshot": "run-20261013-v2/results-v2.json"}


def _a5_cells(a5: dict, historical: dict) -> tuple[list[dict], list[dict]]:
    managed_versions = {b: historical["a1"]["managed"][b][PACKAGE]["version"] for b in BOOTS}
    selected_versions = {b: a5["maven"][b]["selected_version"] for b in BOOTS}
    path_ok = all(value["paths"] and all(
        any("spring-boot-starter-tomcat" in node for node in path)
        for path in value["paths"]) for value in a5["maven"].values())
    override_versions = {b: a5["overrides"][b]["selected_version"] for b in BOOTS[1:]}
    verdicts = {b: historical["a1"]["c3"]["candidate_verdicts"][b]["status"]
                for b in BOOTS[1:]}
    cells = [
        evaluate("A5", "C1", [
            equality_check("metadata-only selected defaults", selected_versions,
                           managed_versions, ["a5.maven", "historical.a1.managed"]),
            availability_check("frozen OSV evidence", verdicts,
                               ["historical.a1.c3"])],
                 ["plugin bootstrap binaries are required"]),
        evaluate("A5", "C2", [
            equality_check("complete starter transitive paths", path_ok, True,
                           ["a5.maven"])],
                 ["fixture scope"]),
        evaluate("A5", "C3", [
            equality_check("frozen conservative OSV verdicts", verdicts,
                           {b: "ADDRESSED" for b in BOOTS[1:]},
                           ["historical.a1.c3", "a5.maven"])],
                 ["advisories are frozen to v2"]),
        evaluate("A5", "C4", [
            equality_check("application override remains effective", override_versions,
                           {b: "10.1.30" for b in BOOTS[1:]},
                           ["a5.overrides"])],
                 ["property override fixture"]),
    ]
    expanded = []
    for scenario, record in a5["scenarios"].items():
        checks = [equality_check(name, observed, True,
                                 [f"a5.scenarios.{scenario}.checks.{name}"])
                  for name, observed in record["checks"].items()]
        expanded.append(evaluate("A5", scenario, checks,
                                 ["Maven-native metadata collection fixture"]))
    return cells, expanded


class A5Experiment:
    def __init__(self, output_dir: Path, cache_root: Path, reference_file: Path):
        self.output_dir = output_dir
        self.cache_root = cache_root
        self.reference_file = reference_file
        output_dir.mkdir(parents=True, exist_ok=True)
        cache_root.mkdir(parents=True, exist_ok=True)

    def _approach(self, name: str) -> dict:
        repository = self.cache_root / name.lower()
        work = self.output_dir / "maven-work" / name.lower()
        resolver = (MavenResolver(work, repository) if name == "A2"
                    else MetadataOnlyMavenResolver(work, repository, quiet=True))
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
        accuracy = _accuracy(a2["fresh"], a5["fresh"])
        vulnerability = _release_comparison(a5["fresh"], historical)
        cells, expanded = _a5_cells(a5["fresh"], historical)
        historical_vulnerability = historical["a4"]["release_comparison"]
        vuln_match = all(
            vulnerability["candidates"][boot]["artifacts"][package].get("addressed", [])
            == historical_vulnerability["candidates"][boot]["artifacts"][package].get("addressed", [])
            and vulnerability["candidates"][boot]["artifacts"][package].get("still_affected", [])
            == historical_vulnerability["candidates"][boot]["artifacts"][package].get("still_affected", [])
            and vulnerability["candidates"][boot]["artifacts"][package].get("new_findings", [])
            == historical_vulnerability["candidates"][boot]["artifacts"][package].get("new_findings", [])
            and vulnerability["candidates"][boot]["artifacts"][package].get("unknown", [])
            == historical_vulnerability["candidates"][boot]["artifacts"][package].get("unknown", [])
            for boot in BOOTS[1:] for package in DEPENDENCIES)
        result = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline_commit": "49929602b0e3100fdcd80025b6e3b5cae2cc0f5e",
            "reference_evidence": str(self.reference_file),
            "environment": self._environment(),
            "mechanism_evaluation": {
                "dependency_collect": "REJECTED: flat list cannot preserve dependency paths",
                "resolver_api": "NOT_SELECTED: greater bootstrap/model-builder complexity",
                "selected": "pinned Maven dependency:tree graph collector",
            },
            "a2_comparison_run": a2, "a5": a5,
            "accuracy": accuracy,
            "vulnerability_accuracy": {
                "matches_frozen_v2": vuln_match,
                "source": "run-20261013-v2/results-v2.json"},
            "release_comparison": vulnerability,
            "cells": historical["cells"] + cells,
            "expanded_cells": historical["expanded_cells"] + expanded,
            "measurements": {"total_elapsed_seconds": time.monotonic() - started},
        }
        path = self.output_dir / "results-a5.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result

    @staticmethod
    def _environment() -> dict:
        def first(command):
            return subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT).stdout.splitlines()[0]
        return {"python": platform.python_version(), "java": first(["java", "-version"]),
                "maven": first(["mvn", "--version"]),
                "git_commit": first(["git", "rev-parse", "HEAD"]),
                "git_branch": first(["git", "branch", "--show-current"])}


def qualify_a5_storage(results_file: Path, output_dir: Path, cache_dir: Path) -> dict:
    """Use a zero-dependency control to disambiguate plugin/application overlap."""
    empty_pom = """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>experiment</groupId>
<artifactId>bootstrap-control</artifactId><version>1</version></project>"""
    resolver = MetadataOnlyMavenResolver(output_dir / "bootstrap-control", cache_dir)
    observed = resolver.resolve_pom("project", empty_pom, [])
    bootstrap_jars = {
        item["path"] for item in observed["storage"]["delta"]["files"]
        if item["category"] == "plugin_bootstrap_jar"
    }
    result = json.loads(results_file.read_text(encoding="utf-8"))
    storage = result["a5"]["fresh"]["storage"]
    application_jar_paths = {
        f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar"
        for coordinate, version in _selected_union(result["a5"]["fresh"]).items()
        for group, artifact in [coordinate.split(":", 1)]
    }
    categories = storage["delta"]["categories"]
    reclassified = []
    for item in storage["delta"]["files"]:
        if (item["category"] == "application_dependency_jar"
                and item["path"] in bootstrap_jars):
            item["category"] = "plugin_bootstrap_jar"
            reclassified.append(item["path"])
            categories["application_dependency_jar"]["count"] -= 1
            categories["application_dependency_jar"]["bytes"] -= item["bytes"]
            categories["plugin_bootstrap_jar"]["count"] += 1
            categories["plugin_bootstrap_jar"]["bytes"] += item["bytes"]
        elif (item["category"] == "plugin_bootstrap_jar"
              and item["path"] not in bootstrap_jars):
            item["category"] = "other_binary"
            categories["plugin_bootstrap_jar"]["count"] -= 1
            categories["plugin_bootstrap_jar"]["bytes"] -= item["bytes"]
            categories["other_binary"]["count"] += 1
            categories["other_binary"]["bytes"] += item["bytes"]
    unexplained = [
        item["path"] for item in storage["delta"]["files"]
        if item["category"] in ("application_dependency_jar", "other_binary")
    ]
    storage["no_application_dependency_jars"] = not unexplained
    storage["binary_summary"] = {
        "application_dependency_jars": categories["application_dependency_jar"],
        "plugin_bootstrap_jars": categories["plugin_bootstrap_jar"],
        "other_binary": categories["other_binary"],
    }
    control = {
        "purpose": "zero-dependency plugin/bootstrap attribution control",
        "observation": observed,
        "bootstrap_jar_paths": sorted(bootstrap_jars),
        "reclassified_overlap_paths": sorted(
            set(reclassified) | (bootstrap_jars & application_jar_paths)),
        "unexplained_binary_paths": unexplained,
        "qualified_no_application_dependency_jars": not unexplained,
    }
    result["storage_qualification"] = control
    results_file.write_text(json.dumps(result, indent=2, sort_keys=True),
                            encoding="utf-8")
    control_file = output_dir / "bootstrap-control.json"
    control_file.write_text(json.dumps(control, indent=2, sort_keys=True),
                            encoding="utf-8")
    return control


def rerun_a5_quiet(results_file: Path, output_dir: Path, cache_dir: Path) -> dict:
    """Replace only A5 measurements with a quiet-output fair-timing run."""
    result = json.loads(results_file.read_text(encoding="utf-8"))
    previous = result["a5"]
    result["network_telemetry"] = {
        "execution_condition": "non-quiet isolated A5 pass; excluded from fair timing",
        "fresh_transfers": previous["fresh"]["storage"]["transfers"],
        "warm_transfers": previous["warm"]["storage"]["transfers"],
    }
    resolver = MetadataOnlyMavenResolver(output_dir / "maven-work" / "a5",
                                         cache_dir, quiet=True)
    passes = {}
    for temperature in ("fresh", "warm"):
        resolver.run_label = temperature
        before = repository_snapshot(cache_dir)
        with _PeakSampler(cache_dir) as sampler:
            workload = _run_workload(resolver)
        workload["storage"] = _storage(cache_dir, before, workload,
                                        sampler.peak, "A5")
        passes[temperature] = workload
    result["a5"] = passes
    result["accuracy"] = _accuracy(result["a2_comparison_run"]["fresh"],
                                    passes["fresh"])
    result["release_comparison"] = _release_comparison(
        passes["fresh"],
        json.loads(Path(result["reference_evidence"]).read_text(encoding="utf-8")))
    result["performance_note"] = (
        "A2 and A5 fair timing passes both used quiet Maven output; "
        "network telemetry came from a separate non-quiet A5 pass")
    results_file.write_text(json.dumps(result, indent=2, sort_keys=True),
                            encoding="utf-8")
    return result
