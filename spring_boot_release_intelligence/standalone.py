from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .a7 import (Dependency, SEVERITIES, materialize_candidate,
                 minimal_cyclonedx, release_comparison)
from .bom import BomResolver
from .http import EvidenceHttpClient
from .maven import parse_tgf
from .metadata_maven import PLUGIN_GOAL, classify_repository_delta, repository_snapshot
from .report import write_report
from .security_report import read_cyclonedx_vulnerabilities, read_osv_json

SCHEMA_VERSION = "1.0"
BOOT_METADATA = "https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-dependencies/maven-metadata.xml"


def discover_boot_version(project: Path) -> dict:
    root = ET.parse(project / "pom.xml").getroot()
    parent = root.find("{*}parent")
    values = []
    if parent is not None and parent.findtext("{*}groupId") == "org.springframework.boot" \
            and parent.findtext("{*}artifactId") == "spring-boot-starter-parent":
        values.append((parent.findtext("{*}version"), "parent"))
    properties = {child.tag.split("}")[-1]: (child.text or "").strip()
                  for node in root.findall("{*}properties") for child in node}
    for dependency in root.findall(".//{*}dependencyManagement/{*}dependencies/{*}dependency"):
        if dependency.findtext("{*}groupId") == "org.springframework.boot" \
                and dependency.findtext("{*}artifactId") == "spring-boot-dependencies":
            version = dependency.findtext("{*}version") or ""
            if version.startswith("${") and version.endswith("}"):
                name = version[2:-1]
                version = properties.get(name)
                source = f"property:{name}"
            else:
                source = "imported-bom"
            values.append((version, source))
    values = [(version, source) for version, source in values if version]
    if len(values) != 1:
        raise ValueError("CANDIDATE_CONFIGURATION_AMBIGUOUS: expected one local Boot controller")
    return {"version": values[0][0], "controller": values[0][1]}


def _version_tuple(value: str):
    return tuple(int(part) for part in value.split("."))


def select_releases(request: str) -> tuple[list[str], dict]:
    if ".." not in request:
        values = [value.strip() for value in request.split(",") if value.strip()]
        return values, {"method": "explicit", "requested": request}
    lower, upper = request.split("..", 1)
    with urllib.request.urlopen(BOOT_METADATA, timeout=30) as response:
        raw = response.read()
    root = ET.fromstring(raw)
    published = [node.text for node in root.findall(".//version") if node.text]
    prefix = ".".join(lower.split(".")[:2]) + "."
    eligible = [value for value in published if value.startswith(prefix)
                and re.fullmatch(r"\d+\.\d+\.\d+", value)
                and _version_tuple(lower) <= _version_tuple(value) <= _version_tuple(upper)]
    return eligible, {"method": "maven-central-metadata", "requested": request,
                      "metadata_sha256": hashlib.sha256(raw).hexdigest()}


def _pom_inputs(project: Path) -> dict:
    root = ET.parse(project / "pom.xml").getroot()
    parent = root.find("{*}parent")
    corporate_parent = bool(parent is not None and not (
        parent.findtext("{*}groupId") == "org.springframework.boot" and
        parent.findtext("{*}artifactId") == "spring-boot-starter-parent"))
    properties = {child.tag.split("}")[-1]: (child.text or "").strip()
                  for node in root.findall("{*}properties") for child in node}
    direct, explicit, imports = set(), {}, []
    dependencies = root.find("{*}dependencies")
    for dependency in list(dependencies or []):
        coordinate = f"{dependency.findtext('{*}groupId')}:{dependency.findtext('{*}artifactId')}"
        direct.add(coordinate)
        if dependency.findtext("{*}version"):
            explicit[coordinate] = "pom.xml dependency version"
    management = root.find("{*}dependencyManagement/{*}dependencies")
    for dependency in list(management) if management is not None else []:
        group, artifact = dependency.findtext("{*}groupId"), dependency.findtext("{*}artifactId")
        version = dependency.findtext("{*}version") or ""
        if version.startswith("${"):
            version = properties.get(version[2:-1], version)
        if dependency.findtext("{*}type") == "pom" and dependency.findtext("{*}scope") == "import":
            if group != "org.springframework.boot" or artifact != "spring-boot-dependencies":
                imports.append((group, artifact, version))
        elif version:
            explicit[f"{group}:{artifact}"] = "pom.xml dependencyManagement"
    modules = [node.text.strip() for node in root.findall("{*}modules/{*}module")
               if node.text and node.text.strip()]
    reactor = set()
    root_group = root.findtext("{*}groupId") or (parent.findtext("{*}groupId") if parent is not None else None)
    root_version = root.findtext("{*}version") or (parent.findtext("{*}version") if parent is not None else None)
    for module in modules:
        module_pom = project / module / "pom.xml"
        if not module_pom.exists():
            continue
        module_root = ET.parse(module_pom).getroot()
        group = module_root.findtext("{*}groupId") or root_group
        artifact = module_root.findtext("{*}artifactId")
        if group and artifact:
            reactor.add(f"{group}:{artifact}")
        for dependency in module_root.findall("{*}dependencies/{*}dependency"):
            coordinate = f"{dependency.findtext('{*}groupId')}:{dependency.findtext('{*}artifactId')}"
            direct.add(coordinate)
            if dependency.findtext("{*}version"):
                explicit[coordinate] = f"{module}/pom.xml dependency version"
    return {"direct": direct, "explicit": explicit, "imports": imports,
            "properties": properties, "corporate_parent": corporate_parent,
            "modules": modules, "reactor": reactor, "reactor_version": root_version,
            "project_id": root.findtext("{*}name") or root.findtext("{*}artifactId") or project.name}


def _portable(path: str | Path, output: Path) -> str:
    """Return an output-relative evidence reference when the path is retained there."""
    value = Path(path)
    try:
        return value.resolve().relative_to(output.resolve()).as_posix()
    except ValueError:
        return str(value)


def _run(command: list[str], cwd: Path, log: Path, timeout: int) -> dict:
    started = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=timeout)
        output, code, error = completed.stdout, completed.returncode, None
    except subprocess.TimeoutExpired as exc:
        output, code, error = (exc.stdout or ""), 124, f"timed out after {timeout}s"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(output, encoding="utf-8")
    return {"command": command, "exit_code": code, "seconds": time.monotonic() - started,
            "log": str(log), "error": error}


def _tool_version(command: list[str]) -> str | None:
    try:
        value = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=20)
        return value.stdout.splitlines()[0] if value.stdout else None
    except (OSError, subprocess.SubprocessError):
        return None


def validate_result(result: dict) -> list[str]:
    errors = []
    for key in ("schema_version", "status", "application", "execution", "scanner",
                "releases", "dependencies", "findings", "evidence", "errors"):
        if key not in result:
            errors.append(f"missing {key}")
    for release in result.get("releases", []):
        if release.get("assessment_status") == "COMPLETE":
            counts = release["counts"]
            if sum(counts["original"].values()) != (sum(counts["addressed"].values()) +
                                                     sum(counts["remaining"].values())):
                errors.append(f"{release['version']}: original arithmetic")
            if sum(counts["total"].values()) != (sum(counts["remaining"].values()) +
                                                  sum(counts["new"].values())):
                errors.append(f"{release['version']}: candidate arithmetic")
    return errors


def rank_releases(releases: list[dict], baseline: str) -> None:
    """Apply the frozen severity-first security ranking in place."""
    candidates = [item for item in releases if item["version"] != baseline
                  and item["assessment_status"] == "COMPLETE"]
    def ranking(item):
        total = item["counts"]["total"]; new = item["counts"]["new"]
        return tuple(total[s] for s in SEVERITIES) + tuple(new[s] for s in SEVERITIES)
    for rank, item in enumerate(sorted(candidates, key=ranking), 1):
        item["rank"] = rank
        item["recommendation"] = ("Preferred — best measured security result" if rank == 1
                                  else f"Rank {rank} by assessed security findings")


class Evaluator:
    def __init__(self, project: Path, releases: list[str], output: Path, *,
                 maven: str = "mvn", settings: Path | None = None,
                 profiles: list[str] | None = None, modules: list[str] | None = None,
                 scopes: list[str] | None = None, scanner: str = "osv-scanner",
                 severities: list[str] | None = None, timeout: int = 300,
                 scanner_reports: dict[str, Path] | None = None):
        self.project, self.releases, self.output = project.resolve(), releases, output.resolve()
        self.maven, self.settings, self.profiles, self.modules = maven, settings, profiles or [], modules or []
        self.scopes = scopes or ["compile", "runtime"]
        self.scanner, self.severities, self.timeout = scanner, severities or list(SEVERITIES), timeout
        self.scanner_reports = scanner_reports or {}
        self.evidence = self.output / "evidence"
        self.cache = self.evidence / "maven-repository"
        self.http = EvidenceHttpClient(self.evidence / "http-cache", timeout=min(timeout, 30))

    def _management(self, version: str, pom: dict) -> tuple[dict, dict, list[str]]:
        warnings = []
        try:
            boot = BomResolver(self.http).resolve("org.springframework.boot", "spring-boot-dependencies", version)
        except Exception as error:
            boot = {}; warnings.append(f"Boot management unavailable: {error}")
        other = {}
        for group, artifact, imported_version in pom["imports"]:
            try:
                other.update(BomResolver(self.http).resolve(group, artifact, imported_version))
            except Exception as error:
                warnings.append(f"Imported management unavailable for {group}:{artifact}: {error}")
        return boot, other, warnings

    def _collect(self, project: Path, version: str) -> tuple[list[Dependency], dict]:
        directory = self.evidence / version
        directory.mkdir(parents=True, exist_ok=True)
        tree = directory / "dependency-tree.tgf"
        before = repository_snapshot(self.cache)
        command = [self.maven, "-B", "-q", f"-Dmaven.repo.local={self.cache}"]
        if self.settings: command.extend(["-s", str(self.settings)])
        if self.profiles: command.append(f"-P{','.join(self.profiles)}")
        if self.modules: command.extend(["-pl", ",".join(self.modules), "-am"])
        command.extend([PLUGIN_GOAL, "-DoutputType=tgf", f"-DoutputFile={tree}"])
        run = _run(command, project, directory / "maven.log", self.timeout)
        if run["exit_code"] or not tree.exists():
            raise RuntimeError(f"Maven collection failed ({run['exit_code']}): {run['log']}")
        initial = parse_tgf(tree, [])
        detailed = parse_tgf(tree, list(initial["selected_artifacts"]))
        roots = set(detailed["root_artifacts"])
        records = {item["coordinate"]: item for item in detailed["selected_records"]}
        inventory = []
        for coordinate, selected in sorted(detailed["selected_artifacts"].items()):
            if coordinate in roots: continue
            record = records[coordinate]; scope = record.get("scope") or "compile"
            if scope not in self.scopes: continue
            group, artifact = coordinate.split(":", 1)
            paths = detailed["target_paths"].get(coordinate, [])
            inventory.append(Dependency(group, artifact, selected, scope,
                                        direct=any(len(path) == 2 for path in paths),
                                        path=tuple(paths[0]) if paths else ()))
        after = repository_snapshot(self.cache)
        selected = {item.coordinate: item.version for item in inventory}
        run["repository_delta"] = classify_repository_delta(before, after, selected)["categories"]
        run["tree"] = str(tree)
        return inventory, run

    def _scan(self, version: str, inventory: list[Dependency]) -> tuple[list[dict], dict]:
        directory = self.evidence / version
        sbom_path = directory / "inventory.cdx.json"
        sbom_path.write_text(json.dumps(minimal_cyclonedx(inventory, serial_seed=version),
                                        indent=2, sort_keys=True) + "\n")
        supplied = self.scanner_reports.get(version)
        if supplied:
            report_path = directory / "scanner.cdx.json"
            shutil.copy2(supplied, report_path)
            report = json.loads(report_path.read_text())
            return read_cyclonedx_vulnerabilities(report, inventory, str(report_path)), {
                "provider": "cyclonedx-report", "exit_code": 0, "report": str(report_path),
                "sbom": str(sbom_path), "seconds": 0.0}
        report_path = directory / "scanner.json"
        scan_root = directory / "scan-root"; scan_root.mkdir(exist_ok=True)
        command = [self.scanner, "scan", "source", "--sbom", str(sbom_path),
                   "--format", "json", "--output-file", str(report_path), str(scan_root)]
        run = _run(command, scan_root, directory / "scanner.log", self.timeout)
        if run["exit_code"] not in (0, 1) or not report_path.exists():
            raise RuntimeError(f"Scanner failed ({run['exit_code']}): {run['log']}")
        report = json.loads(report_path.read_text())
        run.update({"provider": "osv-scanner", "report": str(report_path), "sbom": str(sbom_path)})
        return read_osv_json(report, inventory, str(report_path)), run

    def evaluate(self) -> dict:
        started = time.monotonic(); self.output.mkdir(parents=True, exist_ok=True)
        self.evidence.mkdir(parents=True, exist_ok=True); self.cache.mkdir(parents=True, exist_ok=True)
        discovery = discover_boot_version(self.project); base = discovery["version"]
        versions = list(dict.fromkeys([base] + self.releases))
        pom_inputs = _pom_inputs(self.project)
        original_hash = hashlib.sha256((self.project / "pom.xml").read_bytes()).hexdigest()
        observations, errors = {}, []
        for version in versions:
            workspace = self.evidence / "work" / version
            try:
                if workspace.exists(): shutil.rmtree(workspace)
                materialize_candidate(self.project, workspace, version,
                    ignore=shutil.ignore_patterns(".git", "target", "output", "__pycache__"))
                verified = discover_boot_version(workspace)["version"]
                if verified != version: raise RuntimeError(f"effective controller remained {verified}")
                inventory, maven_run = self._collect(workspace, version)
                findings, scanner_run = self._scan(version, inventory)
                boot, other, warnings = self._management(version, pom_inputs)
                dependencies = []
                by_coordinate = {item.coordinate: [] for item in inventory}
                for finding in findings: by_coordinate.setdefault(finding["package"], []).append(finding)
                for item in inventory:
                    boot_item, other_item = boot.get(item.coordinate), other.get(item.coordinate)
                    override = pom_inputs["explicit"].get(item.coordinate)
                    property_override = next((name for name in getattr(boot_item, "property_chain", [])
                                              if name in pom_inputs["properties"]), None)
                    if item.coordinate in pom_inputs["reactor"]:
                        ownership = "OTHER_BOM_PARENT_MANAGED"
                    elif boot_item and other_item: ownership = "OWNERSHIP_UNKNOWN"
                    elif boot_item and (override or property_override): ownership = "BOOT_MANAGED_OVERRIDDEN"
                    elif boot_item: ownership = "BOOT_MANAGED"
                    elif other_item: ownership = "OTHER_BOM_PARENT_MANAGED"
                    elif pom_inputs["corporate_parent"] and item.coordinate not in pom_inputs["explicit"]:
                        ownership = "OWNERSHIP_UNKNOWN"
                    else: ownership = "INDEPENDENT_DIRECT" if item.direct else "INDEPENDENT_TRANSITIVE"
                    dependencies.append({"release": version, "coordinate": item.coordinate,
                        "selected_version": item.version, "scope": item.scope, "direct": item.direct,
                        "ownership": ownership,
                        "boot_managed_default": getattr(boot_item, "version", None),
                        "management_source": ("reactor dependencyManagement" if item.coordinate in pom_inputs["reactor"]
                                              else getattr(other_item, "origin", None)),
                        "override_source": override or (f"property:{property_override}" if property_override else None),
                        "paths": [list(item.path)] if item.path else [], "module_occurrences": [item.module],
                        "findings": [{**finding,
                            "source": _portable(finding["source"], self.output),
                            "evidence_reference": _portable(finding["evidence_reference"], self.output)}
                            for finding in by_coordinate.get(item.coordinate, [])],
                        "limitations": warnings})
                observations[version] = {"inventory": inventory, "dependencies": dependencies,
                                         "findings": findings, "maven": maven_run,
                                         "scanner": scanner_run, "warnings": warnings}
            except Exception as error:
                errors.append({"release": version, "stage": "evaluation", "message": str(error),
                               "log_path": str(self.evidence / version)})
        if base not in observations:
            status = "FAILURE"
        else:
            status = "PARTIAL" if errors else "SUCCESS"
        baseline_findings = observations.get(base, {}).get("findings", [])
        releases = []
        for version in versions:
            if version not in observations:
                releases.append({"version": version, "assessment_status": "FAILED", "rank": None,
                                 "counts": {name: None for name in
                                            ("original", "addressed", "remaining", "new", "total")},
                                 "recommendation": "Not ranked — assessment failed"})
                continue
            filtered_base = [x for x in baseline_findings if x["severity"] in self.severities]
            filtered = [x for x in observations[version]["findings"] if x["severity"] in self.severities]
            comparison = release_comparison(filtered_base, filtered, True)
            releases.append({"version": version, "assessment_status": "COMPLETE", "rank": None,
                "counts": {"original": comparison["original"], "addressed": comparison["addressed"],
                           "remaining": comparison["remaining"], "new": comparison["additional"],
                           "total": comparison["candidate_total"]},
                "recommendation": "Baseline" if version == base else "Assessed",
                "evidence": {"maven": _portable(observations[version]["maven"]["tree"], self.output),
                             "scanner": _portable(observations[version]["scanner"]["report"], self.output)}})
        rank_releases(releases, base)
        candidates = [item for item in releases if item["version"] != base
                      and item["assessment_status"] == "COMPLETE"]
        dependencies = [item for value in observations.values() for item in value["dependencies"]]
        baseline_coordinates = {item["coordinate"] for item in dependencies if item["release"] == base}
        for dependency in dependencies:
            release_coordinates = {item["coordinate"] for item in dependencies
                                   if item["release"] == dependency["release"]}
            dependency["introduced"] = dependency["coordinate"] not in baseline_coordinates
            dependency["removed_from_release"] = sorted(baseline_coordinates - release_coordinates)
        findings = []
        baseline_advisories = {(item["package"], item["advisory_id"])
                               for item in baseline_findings}
        for version, observation in observations.items():
            for finding in observation["findings"]:
                portable_finding = {**finding,
                    "source": _portable(finding["source"], self.output),
                    "evidence_reference": _portable(finding["evidence_reference"], self.output)}
                findings.append({**portable_finding, "release": version,
                                 "disposition": ("ORIGINAL" if version == base else
                                     "REMAINING" if (finding["package"], finding["advisory_id"])
                                     in baseline_advisories else "ADDITIONAL"),
                                 "displayed": finding["severity"] in self.severities})
        override_notes = []
        preferred = next((item["version"] for item in candidates if item["rank"] == 1), None)
        if preferred:
            for dependency in dependencies:
                if dependency["release"] == preferred and dependency["ownership"] == "BOOT_MANAGED_OVERRIDDEN" \
                        and dependency["findings"] and dependency["boot_managed_default"] != dependency["selected_version"]:
                    override_notes.append(f"Spring Boot {preferred} manages {dependency['coordinate']} "
                        f"{dependency['boot_managed_default']}, but the application selects "
                        f"{dependency['selected_version']} through {dependency['override_source']}. "
                        "Worth investigating; override removal has not been tested.")
        result = {"schema_version": SCHEMA_VERSION, "status": status,
            "application": {"project_path": str(self.project),
                            "project_id": pom_inputs["project_id"],
                            "original_spring_boot_version": base,
                            "controller": discovery["controller"], "original_pom_sha256": original_hash},
            "execution": {"requested_releases": self.releases,
                          "evaluated_releases": list(observations), "profiles": self.profiles,
                          "modules": self.modules, "discovered_modules": pom_inputs["modules"],
                          "scopes": self.scopes,
                          "selected_severities": self.severities,
                          "other_severities": ("None; all scanner severity categories selected" if
                              set(self.severities) == set(SEVERITIES) else "SCANNED_BUT_HIDDEN"),
                          "maven": self.maven, "maven_version": _tool_version([self.maven, "-version"]),
                          "elapsed_seconds": time.monotonic() - started,
                          "original_project_unchanged": original_hash == hashlib.sha256(
                              (self.project / "pom.xml").read_bytes()).hexdigest()},
            "scanner": {"provider": "cyclonedx-report" if self.scanner_reports else "osv-scanner",
                        "version": None if self.scanner_reports else _tool_version([self.scanner, "--version"]),
                        "inventory_format": "CycloneDX 1.5", "snapshot_comparable": True},
            "releases": releases, "dependencies": dependencies, "findings": findings,
            "override_notes": override_notes,
            "evidence": {"directory": _portable(self.evidence, self.output),
                         "coverage": "Complete compile/runtime Maven-selected inventory for each successfully assessed release",
                         "http_metrics": self.http.metrics,
                         "limitations": ["Security-only ranking; compatibility not assessed",
                                         "Private repositories, large reactors and all packaging scopes remain unverified"]},
            "errors": [{**error, "log_path": _portable(error["log_path"], self.output)}
                       for error in errors]}
        schema_errors = validate_result(result)
        if schema_errors: raise RuntimeError(f"result contract validation failed: {schema_errors}")
        (self.output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        write_report(result, self.output / "report.html")
        return result
