from __future__ import annotations

import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .bom import BomResolver
from .depsdev import DepsDevClient
from .http import EvidenceHttpClient
from .maven import MavenResolver
from .maven_scenarios import run_scenarios
from .osv import OsvClient, advisory_verdict
from .validation import availability_check, check, equality_check, evaluate

BOOTS = ["3.3.4", "3.3.5", "3.3.6", "3.3.7", "3.3.8"]
PACKAGE = "org.apache.tomcat.embed:tomcat-embed-core"
STARTER = "org.springframework.boot:spring-boot-starter-web"
PRIMARY = "GHSA-qvf5-hvjx-wm27"
DEPENDENCIES = [PACKAGE, "org.springframework:spring-web",
                "ch.qos.logback:logback-core", "org.yaml:snakeyaml"]
EXPECTED_TOMCAT = {"3.3.4": "10.1.30", "3.3.5": "10.1.31",
                   "3.3.6": "10.1.33", "3.3.7": "10.1.34", "3.3.8": "10.1.34"}


def explicit_range_verdict(advisory: dict, package: str, version: str) -> dict:
    """Backward-compatible name for the conservative OSV interpreter."""
    return advisory_verdict(advisory, package, version)


class Experiment:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.http = EvidenceHttpClient(output_dir / "http-cache")
        self.bom = BomResolver(self.http)
        self.osv = OsvClient(self.http)
        self.maven = MavenResolver(output_dir / "maven-work")
        self.depsdev = DepsDevClient(self.http)
        self._queries = {}
        self._advisories = {}

    def _query(self, package, version):
        key = (package, version)
        if key not in self._queries:
            self._queries[key] = self.osv.query(package, version)
        return self._queries[key]

    def _advisory(self, advisory_id):
        if advisory_id not in self._advisories:
            self._advisories[advisory_id] = self.osv.advisory(advisory_id)
        return self._advisories[advisory_id]

    def run(self) -> dict:
        started = time.monotonic()
        stages = {}

        stage = time.monotonic(); before = dict(self.http.metrics)
        managed = {}
        for boot in BOOTS:
            model = self.bom.resolve("org.springframework.boot", "spring-boot-dependencies", boot)
            managed[boot] = {package: (vars(model[package]) if package in model else None)
                             for package in DEPENDENCIES}
        baseline = self._query(PACKAGE, managed["3.3.4"][PACKAGE]["version"])
        primary = self._advisory(PRIMARY)
        comparisons = {}
        for boot in BOOTS[1:]:
            version = managed[boot][PACKAGE]["version"]
            candidate = self._query(PACKAGE, version)
            comparisons[boot] = {
                "managed_version": version,
                "original_finding_comparison": self.osv.compare_original(baseline, candidate),
                "primary_advisory_verdict": advisory_verdict(primary["advisory"], PACKAGE, version)}
        stages["A1"] = self._stage(stage, before)

        stage = time.monotonic(); before = dict(self.http.metrics)
        maven = {boot: self.maven.resolve(boot, targets=DEPENDENCIES) for boot in BOOTS}
        overrides = {boot: self.maven.resolve(boot, "10.1.30", DEPENDENCIES)
                     for boot in BOOTS[1:]}
        scenarios = run_scenarios(self.maven)
        stages["A2"] = self._stage(stage, before)

        stage = time.monotonic(); before = dict(self.http.metrics)
        deps_graphs, deps_versions = {}, {}
        for boot in BOOTS:
            graph = self.depsdev.dependencies(STARTER, boot)
            deps_graphs[boot] = {"paths": self.depsdev.paths(graph["response"], PACKAGE),
                                 "error": graph["response"].get("error"),
                                 "provenance": graph["provenance"],
                                 "node_count": len(graph["response"].get("nodes", [])),
                                 "edge_count": len(graph["response"].get("edges", []))}
            version = managed[boot][PACKAGE]["version"]
            metadata = self.depsdev.version(PACKAGE, version)
            deps_versions[version] = {"version_key": metadata["response"].get("versionKey"),
                                      "advisory_keys": metadata["response"].get("advisoryKeys", []),
                                      "provenance": metadata["provenance"]}
        stages["A3"] = self._stage(stage, before)

        stage = time.monotonic(); before = dict(self.http.metrics)
        release_comparison = self._multi_dependency(maven)
        c3 = {"input_fixed_version": None, "advisory_id": PRIMARY, "advisory": primary,
              "candidate_verdicts": {b: comparisons[b]["primary_advisory_verdict"]
                                     for b in BOOTS[1:]}}
        cells = self._cells(managed, comparisons, maven, overrides, deps_graphs,
                            deps_versions, c3)
        expanded = self._expanded_cells(scenarios)
        stages["A4_and_comparison"] = self._stage(stage, before)

        result = {"schema_version": 2, "generated_at": datetime.now(timezone.utc).isoformat(),
                  "baseline_reviewed_commit": "a325aa4b2749de30450c2292a331988e83a0f34b",
                  "environment": self._environment(),
                  "inputs": {"boot_versions": BOOTS, "dependencies": DEPENDENCIES,
                             "primary_advisory": PRIMARY},
                  "a1": {"managed": managed, "comparisons": comparisons,
                         "bom_documents": self.bom.documents, "c3": c3},
                  "a2": {"maven": maven, "overrides": overrides, "scenarios": scenarios},
                  "a3": {"graphs": deps_graphs, "versions": deps_versions},
                  "a4": {"release_comparison": release_comparison,
                         "source_precedence": ["Maven effective graph", "Boot BOM",
                                               "OSV advisory", "deps.dev corroboration"]},
                  "cells": cells, "expanded_cells": expanded,
                  "measurements": {"total_elapsed_seconds": time.monotonic() - started,
                                   "by_stage": stages, "http": self.http.metrics,
                                   "evidence_bytes": self._evidence_bytes()}}
        (self.output_dir / "results-v2.json").write_text(json.dumps(result, indent=2, sort_keys=True),
                                                           encoding="utf-8")
        return result

    def _multi_dependency(self, maven):
        started = time.perf_counter()
        http_started = self.http.metrics["elapsed_seconds"]
        baseline_versions = {p: maven[BOOTS[0]]["selected_artifacts"].get(p) for p in DEPENDENCIES}
        baseline_queries = {p: self._query(p, v) for p, v in baseline_versions.items() if v}
        candidates = {}
        for boot in BOOTS[1:]:
            artifacts = {}
            for package in DEPENDENCIES:
                version = maven[boot]["selected_artifacts"].get(package)
                if not version:
                    artifacts[package] = {"version": None, "status": "ABSENT_ON_EXAMINED_PATH"}
                    continue
                query = self._query(package, version)
                comparison = self.osv.compare_original(baseline_queries[package], query)
                addressed, unknown, addressed_evidence = [], [], {}
                for advisory_id in comparison["not_reported"]:
                    record = self._advisory(advisory_id)
                    verdict = advisory_verdict(record["advisory"], package, version)
                    if verdict["status"] == "ADDRESSED":
                        addressed.append(advisory_id)
                        addressed_evidence[advisory_id] = {
                            "verdict": verdict, "provenance": record["provenance"]}
                    else:
                        unknown.append(advisory_id)
                artifacts[package] = {"version": version,
                    "paths": maven[boot]["target_paths"].get(package, []),
                    "original_findings": comparison["original_ids"],
                    "addressed": addressed, "still_affected": comparison["still_reported"],
                    "addressed_evidence": addressed_evidence,
                    "unknown": unknown, "new_findings": comparison["new_ids"],
                    "provenance": query["provenance"]}
            candidates[boot] = {"artifacts": artifacts,
                "compatibility_evidence": "NOT_TESTED",
                "selection_warning": "vulnerability counts are evidence dimensions, not a compatibility ranking"}
        total = time.perf_counter() - started
        network = self.http.metrics["elapsed_seconds"] - http_started
        return {"baseline_versions": baseline_versions, "candidates": candidates,
                "total_seconds": total, "network_seconds": network,
                "comparison_computation_seconds": max(0.0, total - network)}

    @staticmethod
    def _cells(managed, comparisons, maven, overrides, graphs, versions, c3):
        expected_verdicts = {b: "ADDRESSED" for b in BOOTS[1:]}
        actual_verdicts = {b: comparisons[b]["primary_advisory_verdict"]["status"] for b in BOOTS[1:]}
        managed_versions = {b: managed[b][PACKAGE]["version"] for b in BOOTS}
        selected_versions = {b: maven[b]["selected_version"] for b in BOOTS}
        path_expected = all(bool(value["paths"]) and
                            all(any("spring-boot-starter-tomcat" in node for node in path)
                                for path in value["paths"])
                            for value in maven.values())
        override_versions = {b: overrides[b]["selected_version"] for b in BOOTS[1:]}
        hosted_paths = {b: graphs[b]["paths"] for b in BOOTS}
        cells = []
        cells.append(evaluate("A1", "C1", [
            equality_check("published managed versions", managed_versions, EXPECTED_TOMCAT, ["a1.managed"]),
            availability_check("OSV original identity comparison", comparisons, ["a1.comparisons"])],
            ["management does not prove inclusion"]))
        cells.append(evaluate("A1", "C2", [check("application path", "UNAVAILABLE", None,
            "resolved transitive path", ["a1.managed"])], ["BOM has no inclusion graph"]))
        cells.append(evaluate("A1", "C3", [
            equality_check("scanner fixed version remains absent", c3["input_fixed_version"], None, ["a1.c3"]),
            equality_check("advisory interval classifications", actual_verdicts, expected_verdicts, ["a1.c3"])],
            ["unsafe ranges become UNKNOWN"]))
        cells.append(evaluate("A1", "C4", [check("effective override", "UNAVAILABLE", None,
            "10.1.30", ["a1.managed"])], ["BOM does not evaluate applications"]))

        a2_common = [equality_check("Maven selected managed defaults", selected_versions,
                                    EXPECTED_TOMCAT, ["a2.maven"])]
        cells.append(evaluate("A2", "C1", a2_common + [availability_check(
            "OSV evidence", comparisons, ["a1.comparisons"])], ["fixture scope"]))
        cells.append(evaluate("A2", "C2", [equality_check("starter transitive path", path_expected,
            True, ["a2.maven"])], ["fixture scope"]))
        cells.append(evaluate("A2", "C3", [equality_check("safe advisory verdicts", actual_verdicts,
            expected_verdicts, ["a1.c3", "a2.maven"])], ["OSV remains advisory authority"]))
        cells.append(evaluate("A2", "C4", [equality_check("override remains effective", override_versions,
            {b: "10.1.30" for b in BOOTS[1:]}, ["a2.overrides"]),
            equality_check("overridden version affected", advisory_verdict(
                c3["advisory"]["advisory"], PACKAGE, "10.1.30")["status"],
                "STILL_AFFECTED", ["a1.c3"])], ["property override fixture"]))

        cells.append(evaluate("A3", "C1", [availability_check("published advisory keys", versions,
            ["a3.versions"]), check("Boot management attribution", "UNAVAILABLE", None, "available",
            ["a3.versions"])], ["published metadata is not a BOM model"]))
        cells.append(evaluate("A3", "C2", [availability_check("hosted paths", hosted_paths,
            ["a3.graphs"], available=all(hosted_paths.values())),
            check("application-effective path", "UNAVAILABLE", None, "available",
            ["a3.graphs"])], ["hosted graph is not application-specific"]))
        cells.append(evaluate("A3", "C3", [availability_check("advisory identities", versions,
            ["a3.versions"]), check("affected ranges", "UNAVAILABLE", None, "available",
            ["a3.versions"])], ["tested endpoint lacks range contents"]))
        cells.append(evaluate("A3", "C4", [check("application override", "UNAVAILABLE", None,
            "10.1.30", ["a3.graphs"])], ["no application POM"]))

        for case, checks in {
            "C1": a2_common + [availability_check("BOM provenance", managed, ["a1.managed"])],
            "C2": [equality_check("Maven path", path_expected, True, ["a2.maven"]),
                   availability_check("hosted corroboration", hosted_paths, ["a3.graphs"])],
            "C3": [equality_check("conservative OSV verdict", actual_verdicts, expected_verdicts, ["a1.c3"])],
            "C4": [equality_check("effective override", override_versions,
                    {b: "10.1.30" for b in BOOTS[1:]}, ["a2.overrides"])],
        }.items():
            cells.append(evaluate("A4", case, checks, ["compatibility remains separate"]))
        return cells

    @staticmethod
    def _expanded_cells(scenarios):
        cells = []
        for scenario, record in scenarios.items():
            cells.append(evaluate("A1", scenario, [check("application resolution", "UNAVAILABLE",
                None, record["expected"], [f"a2.scenarios.{scenario}"])], ["BOM-only limitation"]))
            checks = [equality_check(name, value, True, [f"a2.scenarios.{scenario}.checks.{name}"])
                      for name, value in record["checks"].items()]
            cells.append(evaluate("A2", scenario, checks, ["reproducible Maven fixture"]))
            cells.append(evaluate("A3", scenario, [check("application resolution", "UNAVAILABLE",
                None, record["expected"], [f"a2.scenarios.{scenario}"])], ["no application model"]))
            cells.append(evaluate("A4", scenario, checks, ["A2 supplies application resolution"]))
        return cells

    def _stage(self, started, before):
        return {"elapsed_seconds": time.monotonic() - started,
                "http_delta": {key: self.http.metrics[key] - before[key]
                               for key in self.http.metrics}}

    def _evidence_bytes(self):
        return sum(path.stat().st_size for path in self.output_dir.rglob("*") if path.is_file())

    @staticmethod
    def _environment():
        def output(command):
            return subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT).stdout.splitlines()[0]
        return {"python": platform.python_version(), "java": output(["java", "-version"]),
                "maven": output(["mvn", "--version"]),
                "git_commit": output(["git", "rev-parse", "HEAD"]),
                "git_branch": output(["git", "branch", "--show-current"])}
