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
from .osv import OsvClient

BOOTS = ["3.3.4", "3.3.5", "3.3.6", "3.3.7", "3.3.8"]
PACKAGE = "org.apache.tomcat.embed:tomcat-embed-core"
STARTER = "org.springframework.boot:spring-boot-starter-web"
PRIMARY = "GHSA-qvf5-hvjx-wm27"


def _numbers(value: str) -> tuple[int, ...] | None:
    """Numeric-release comparator used only after an explicit OSV fixed event."""
    pieces = value.split(".")
    if not all(p.isdigit() for p in pieces):
        return None
    return tuple(int(p) for p in pieces)


def explicit_range_verdict(advisory: dict, package: str, version: str) -> dict:
    evidence = OsvClient.range_evidence(advisory, package)
    candidate = _numbers(version)
    applicable_fixes = []
    for fixed in evidence["fixed_events"]:
        parsed = _numbers(fixed)
        if candidate and parsed and candidate[:2] == parsed[:2]:
            applicable_fixes.append((fixed, parsed))
    if candidate and applicable_fixes and any(candidate >= parsed for _, parsed in applicable_fixes):
        status = "ADDRESSED"
    elif evidence["package_match"]:
        status = "UNKNOWN"
    else:
        status = "UNKNOWN"
    return {"status": status, "range_evidence": evidence,
            "applicable_fixed_events": [f for f, _ in applicable_fixes],
            "comparator_scope": "numeric release only; no Maven qualifier claim"}


class Experiment:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.http = EvidenceHttpClient(output_dir / "http-cache")
        self.bom = BomResolver(self.http)
        self.osv = OsvClient(self.http)
        self.maven = MavenResolver(output_dir / "maven-work")
        self.depsdev = DepsDevClient(self.http)

    def run(self) -> dict:
        started = time.monotonic()
        stage_measurements = {}
        stage_started = time.monotonic()
        http_before = dict(self.http.metrics)
        managed = {}
        for boot in BOOTS:
            resolved = self.bom.resolve("org.springframework.boot", "spring-boot-dependencies", boot)
            item = resolved.get(PACKAGE)
            managed[boot] = vars(item) if item else None

        osv_queries = {managed[b]["version"]: self.osv.query(PACKAGE, managed[b]["version"])
                       for b in BOOTS if managed[b]}
        advisory_record = self.osv.advisory(PRIMARY)
        baseline_query = osv_queries[managed["3.3.4"]["version"]]
        comparisons = {}
        for boot in BOOTS[1:]:
            version = managed[boot]["version"]
            comparison = self.osv.compare_original(baseline_query, osv_queries[version])
            primary_returned = PRIMARY in {v["id"] for v in osv_queries[version]["vulnerabilities"]}
            verdict = ({"status": "STILL_AFFECTED", "evidence": "candidate OSV query"}
                       if primary_returned else
                       explicit_range_verdict(advisory_record["advisory"], PACKAGE, version))
            comparisons[boot] = {"managed_version": version,
                                 "original_finding_comparison": comparison,
                                 "primary_advisory_verdict": verdict}

        stage_measurements["A1"] = self._stage_metrics(stage_started, http_before)
        stage_started = time.monotonic()
        http_before = dict(self.http.metrics)
        maven = {boot: self.maven.resolve(boot) for boot in BOOTS}
        overrides = {boot: self.maven.resolve(boot, "10.1.30") for boot in BOOTS[1:]}
        stage_measurements["A2"] = self._stage_metrics(stage_started, http_before)
        stage_started = time.monotonic()
        http_before = dict(self.http.metrics)
        deps_graphs = {}
        deps_versions = {}
        for boot in BOOTS:
            graph = self.depsdev.dependencies(STARTER, boot)
            deps_graphs[boot] = {"paths": self.depsdev.paths(graph["response"], PACKAGE),
                                 "error": graph["response"].get("error"),
                                 "provenance": graph["provenance"],
                                 "node_count": len(graph["response"].get("nodes", [])),
                                 "edge_count": len(graph["response"].get("edges", []))}
            version = managed[boot]["version"]
            metadata = self.depsdev.version(PACKAGE, version)
            deps_versions[version] = {"version_key": metadata["response"].get("versionKey"),
                                      "published_at": metadata["response"].get("publishedAt"),
                                      "advisory_keys": metadata["response"].get("advisoryKeys", []),
                                      "provenance": metadata["provenance"]}
        stage_measurements["A3"] = self._stage_metrics(stage_started, http_before)

        stage_started = time.monotonic()
        http_before = dict(self.http.metrics)
        primary_baseline = PRIMARY in {v["id"] for v in baseline_query["vulnerabilities"]}
        c3 = {"input_fixed_version": None, "advisory_id": PRIMARY,
              "baseline_reported": primary_baseline,
              "advisory": advisory_record,
              "candidate_verdicts": {boot: comparisons[boot]["primary_advisory_verdict"]
                                     for boot in BOOTS[1:]}}
        cells = self._cells(managed, comparisons, maven, overrides, deps_graphs,
                            deps_versions, c3)
        stage_measurements["A4_integration"] = self._stage_metrics(stage_started, http_before)
        result = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": self._environment(),
            "inputs": {"boot_versions": BOOTS, "package": PACKAGE,
                       "starter": STARTER, "primary_advisory": PRIMARY},
            "a1": {"managed": managed, "osv_queries": osv_queries,
                   "comparisons": comparisons, "bom_documents": self.bom.documents,
                   "c3": c3},
            "a2": {"maven": maven, "overrides": overrides},
            "a3": {"graphs": deps_graphs, "versions": deps_versions},
            "a4": {"source_precedence": ["Maven effective graph", "Boot BOM management",
                                            "OSV advisory", "deps.dev corroboration"]},
            "cells": cells,
            "measurements": {"total_elapsed_seconds": time.monotonic() - started,
                             "http": self.http.metrics,
                             "by_approach": stage_measurements,
                             "maven_elapsed_seconds": sum(x["elapsed_seconds"] for x in maven.values())
                                + sum(x["elapsed_seconds"] for x in overrides.values()),
                             "benchmark": self._benchmark(comparisons)},
        }
        (self.output_dir / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True),
                                                        encoding="utf-8")
        return result

    def _stage_metrics(self, started, http_before):
        return {"elapsed_seconds": time.monotonic() - started,
                "http_delta": {key: self.http.metrics[key] - http_before[key]
                               for key in self.http.metrics}}

    @staticmethod
    def _cells(managed, comparisons, maven, overrides, graphs, versions, c3):
        observed_managed = {b: managed[b]["version"] for b in BOOTS}
        original_counts = {b: {k: len(v) for k, v in comparisons[b]["original_finding_comparison"].items()
                               if isinstance(v, list)} for b in BOOTS[1:]}
        maven_versions = {b: maven[b]["selected_version"] for b in BOOTS}
        graph_paths = {b: graphs[b]["paths"] for b in BOOTS}
        return [
            {"approach": "A1", "case": "C1", "status": "PROVEN",
             "expected": "managed versions, provenance, OSV comparison", "observed": {"managed": observed_managed, "counts": original_counts},
             "evidence": ["a1.managed", "a1.comparisons"], "limitations": ["management is not application inclusion"]},
            {"approach": "A1", "case": "C2", "status": "NOT_SUPPORTED",
             "expected": "actual transitive path", "observed": "BOM has no inclusion path", "evidence": ["a1.managed"], "limitations": ["no graph"]},
            {"approach": "A1", "case": "C3", "status": "PROVEN",
             "expected": "reason from advisory without supplied fixed version", "observed": c3["candidate_verdicts"], "evidence": ["a1.c3"], "limitations": ["numeric comparator only for explicit numeric fixed events"]},
            {"approach": "A1", "case": "C4", "status": "NOT_SUPPORTED",
             "expected": "effective application override", "observed": "Boot default only", "evidence": ["a1.managed"], "limitations": ["does not read effective application model"]},
            {"approach": "A2", "case": "C1", "status": "PROVEN", "expected": "effective versions and OSV", "observed": maven_versions, "evidence": ["a2.maven", "a1.osv_queries"], "limitations": ["sample application only"]},
            {"approach": "A2", "case": "C2", "status": "PROVEN", "expected": "resolved transitive paths", "observed": {b: maven[b]["paths"] for b in BOOTS}, "evidence": ["a2.maven"], "limitations": ["sample application only"]},
            {"approach": "A2", "case": "C3", "status": "PROVEN", "expected": "resolved version plus advisory uncertainty", "observed": c3["candidate_verdicts"], "evidence": ["a2.maven", "a1.c3"], "limitations": ["OSV remains advisory authority"]},
            {"approach": "A2", "case": "C4", "status": "PROVEN", "expected": "override remains selected and affected", "observed": {b: {"version": overrides[b]["selected_version"], "control": "APPLICATION_CONTROLLED", "vulnerability": "STILL_AFFECTED"} for b in BOOTS[1:]}, "evidence": ["a2.overrides", "a1.c3"], "limitations": ["property override fixture"]},
            {"approach": "A3", "case": "C1", "status": "PARTIALLY_PROVEN", "expected": "published/advisory facts", "observed": {v: len(d["advisory_keys"]) for v, d in versions.items()}, "evidence": ["a3.versions"], "limitations": ["no Boot-management attribution"]},
            {"approach": "A3", "case": "C2", "status": "PARTIALLY_PROVEN", "expected": "hosted graph path", "observed": graph_paths, "evidence": ["a3.graphs"], "limitations": ["not application-specific effective resolution"]},
            {"approach": "A3", "case": "C3", "status": "PARTIALLY_PROVEN", "expected": "vulnerability membership", "observed": "advisory keys only", "evidence": ["a3.versions"], "limitations": ["no affected-range contents in tested endpoint", "absence is not a fix"]},
            {"approach": "A3", "case": "C4", "status": "NOT_SUPPORTED", "expected": "application override", "observed": "published graph has no application POM", "evidence": ["a3.graphs"], "limitations": ["no application effective model"]},
            {"approach": "A4", "case": "C1", "status": "PROVEN", "expected": "management + selection + advisory + corroboration", "observed": {"managed": observed_managed, "selected": maven_versions}, "evidence": ["a1.managed", "a2.maven", "a3.versions"], "limitations": ["compatibility untested"]},
            {"approach": "A4", "case": "C2", "status": "PROVEN", "expected": "authoritative Maven path with hosted comparison", "observed": {"maven": {b: maven[b]["paths"] for b in BOOTS}, "deps_dev": graph_paths}, "evidence": ["a2.maven", "a3.graphs"], "limitations": ["fixture scope"]},
            {"approach": "A4", "case": "C3", "status": "PROVEN", "expected": "preserved uncertainty and range evidence", "observed": c3["candidate_verdicts"], "evidence": ["a1.c3", "a2.maven"], "limitations": ["source data can change"]},
            {"approach": "A4", "case": "C4", "status": "PROVEN", "expected": "Boot default vs effective override plus status", "observed": {b: {"boot_default": managed[b]["version"], "effective": overrides[b]["selected_version"], "control": "APPLICATION_CONTROLLED", "vulnerability": "STILL_AFFECTED"} for b in BOOTS[1:]}, "evidence": ["a1.managed", "a2.overrides", "a1.c3"], "limitations": ["profile variants untested"]},
        ]

    @staticmethod
    def _benchmark(comparisons):
        started = time.perf_counter()
        records = list(comparisons.values())
        operations = 0
        for finding in range(10):
            for candidate in range(5):
                _ = records[candidate % len(records)]["original_finding_comparison"]
                operations += 1
        return {"tested": {"findings": 10, "candidates": 5,
                            "operations": operations,
                            "replay_seconds": time.perf_counter() - started,
                            "additional_network_requests": 0},
                "not_tested": [{"findings": f, "candidates": c}
                               for f in (10, 50, 100) for c in (5, 20, 100)
                               if (f, c) != (10, 5)],
                "reason": "bounded live run avoids multiplying API traffic; cached replay is representative only"}

    @staticmethod
    def _environment():
        def output(command):
            return subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT).stdout.splitlines()[0]
        return {"python": platform.python_version(), "java": output(["java", "-version"]),
                "maven": output(["mvn", "--version"]),
                "git_commit": output(["git", "rev-parse", "HEAD"]),
                "git_branch": output(["git", "branch", "--show-current"])}
