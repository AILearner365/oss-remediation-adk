from __future__ import annotations

import hashlib
import json
import re
import shutil
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path

CYCLONEDX_SPEC = "1.5"
OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/{}"
POM_NS = "http://maven.apache.org/POM/4.0.0"


@dataclass(frozen=True)
class Dependency:
    group: str
    artifact: str
    version: str
    scope: str = "compile"
    module: str = "root"
    direct: bool = False
    path: tuple[str, ...] = ()
    management: str = "AMBIGUOUS"

    @property
    def coordinate(self) -> str:
        return f"{self.group}:{self.artifact}"

    @property
    def purl(self) -> str:
        return f"pkg:maven/{self.group}/{self.artifact}@{self.version}"


def inventory_from_a5(result: dict, module: str = "root") -> list[Dependency]:
    roots = set(result.get("root_artifacts", []))
    records = result.get("selected_records")
    if records:
        return [Dependency(r["group_id"], r["artifact_id"], r["version"],
                           r.get("scope") or "compile", module)
                for r in records if r.get("coordinate") not in roots]
    return [Dependency(*coordinate.split(":", 1), version, module=module)
            for coordinate, version in sorted(result["selected_artifacts"].items())
            if coordinate not in roots]


def minimal_cyclonedx(dependencies: list[Dependency], *, serial_seed: str) -> dict:
    """Create deterministic inventory-only CycloneDX JSON.

    This converter deliberately does not interpret vulnerabilities.  Duplicate
    Maven coordinates are one component while module/path occurrences remain
    as component properties.
    """
    grouped: dict[str, list[Dependency]] = {}
    for dependency in dependencies:
        grouped.setdefault(dependency.purl, []).append(dependency)
    components = []
    for purl, occurrences in sorted(grouped.items()):
        first = occurrences[0]
        modules = sorted({item.module for item in occurrences})
        scopes = sorted({item.scope for item in occurrences})
        paths = sorted({" > ".join(item.path) for item in occurrences if item.path})
        properties = [
            {"name": "a7:modules", "value": ",".join(modules)},
            {"name": "a7:maven-scopes", "value": ",".join(scopes)},
        ]
        if paths:
            properties.append({"name": "a7:dependency-paths", "value": "\n".join(paths)})
        components.append({
            "type": "library", "bom-ref": purl, "group": first.group,
            "name": first.artifact, "version": first.version, "purl": purl,
            "scope": "excluded" if scopes == ["test"] else "required",
            "properties": properties,
        })
    digest = hashlib.sha256(serial_seed.encode()).hexdigest()[:32]
    return {
        "bomFormat": "CycloneDX", "specVersion": CYCLONEDX_SPEC,
        "serialNumber": f"urn:uuid:{uuid.UUID(digest)}", "version": 1,
        "metadata": {"tools": {"components": [{"type": "application",
            "name": "spring-boot-release-intelligence-a7", "version": "1"}]}},
        "components": components,
        "dependencies": [{"ref": component["bom-ref"], "dependsOn": []}
                         for component in components],
    }


def validate_minimal_cyclonedx(bom: dict) -> list[str]:
    errors = []
    if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != CYCLONEDX_SPEC:
        errors.append("unexpected CycloneDX envelope")
    refs = []
    for component in bom.get("components", []):
        for field in ("type", "bom-ref", "group", "name", "version", "purl"):
            if not component.get(field):
                errors.append(f"component missing {field}")
        refs.append(component.get("bom-ref"))
    if len(refs) != len(set(refs)):
        errors.append("duplicate bom-ref")
    dependency_refs = {item.get("ref") for item in bom.get("dependencies", [])}
    if dependency_refs != set(refs):
        errors.append("dependency references do not match components")
    return errors


def cyclonedx_inventory(bom: dict) -> set[tuple[str, str]]:
    return {(f"{item.get('group', '')}:{item['name']}", item["version"])
            for item in bom.get("components", []) if item.get("version")}


def reconcile(a5: list[Dependency], bom: dict) -> dict:
    left = {(item.coordinate, item.version) for item in a5}
    right = cyclonedx_inventory(bom)
    return {"equal": left == right, "a5_only": sorted(left - right),
            "cyclonedx_only": sorted(right - left),
            "a5_count": len(left), "cyclonedx_count": len(right)}


class CandidateConfigurationError(ValueError):
    pass


def materialize_candidate(source: Path, destination: Path, candidate: str) -> dict:
    """Copy a project and replace exactly one verified Boot controller.

    Supported controllers are the Boot parent version, an imported Boot BOM
    version, or a property referenced by that BOM. Multiple controllers are
    rejected instead of guessed.
    """
    shutil.copytree(source, destination)
    pom = destination / "pom.xml"
    tree = ET.parse(pom)
    root = tree.getroot()
    ns = {"m": POM_NS}
    controllers: list[tuple[ET.Element, str]] = []
    parent = root.find("m:parent", ns)
    if parent is not None and parent.findtext("m:groupId", namespaces=ns) == "org.springframework.boot" \
            and parent.findtext("m:artifactId", namespaces=ns) == "spring-boot-starter-parent":
        controllers.append((parent.find("m:version", ns), "parent"))
    for dependency in root.findall(".//m:dependencyManagement/m:dependencies/m:dependency", ns):
        if dependency.findtext("m:groupId", namespaces=ns) == "org.springframework.boot" \
                and dependency.findtext("m:artifactId", namespaces=ns) == "spring-boot-dependencies":
            version = dependency.find("m:version", ns)
            if version is not None and version.text and version.text.startswith("${"):
                name = version.text[2:-1]
                element = root.find(f"m:properties/m:{name}", ns)
                if element is None:
                    raise CandidateConfigurationError("Boot BOM property is not locally controlled")
                controllers.append((element, f"property:{name}"))
            else:
                controllers.append((version, "imported-bom"))
    if len(controllers) != 1 or controllers[0][0] is None:
        raise CandidateConfigurationError("CANDIDATE_CONFIGURATION_AMBIGUOUS")
    element, kind = controllers[0]
    original = element.text
    element.text = candidate
    ET.register_namespace("", POM_NS)
    tree.write(pom, encoding="utf-8", xml_declaration=True)
    return {"controller": kind, "original": original, "candidate": candidate,
            "pom": str(pom)}


class OsvBatchClient:
    def __init__(self, opener=urllib.request.urlopen):
        self.opener = opener
        self.requests = 0

    def _json(self, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "spri-a7/1"})
        self.requests += 1
        with self.opener(request, timeout=30) as response:
            return json.load(response)

    def query(self, inventories: list[list[Dependency]]) -> dict:
        unique = sorted({(item.coordinate, item.version)
                         for inventory in inventories for item in inventory})
        queries = [{"package": {"ecosystem": "Maven", "name": package},
                    "version": version} for package, version in unique]
        response = self._json(OSV_BATCH, {"queries": queries})
        results = response.get("results")
        if not isinstance(results, list) or len(results) != len(queries):
            raise RuntimeError("incomplete OSV batch response")
        advisory_ids = sorted({item["id"] for result in results
                               for item in result.get("vulns", []) if item.get("id")})
        advisories = {}
        failures = []
        for advisory_id in advisory_ids:
            try:
                advisory = self._json(OSV_VULN.format(advisory_id))
                canonical = advisory.get("id", advisory_id)
                aliases = sorted(set(advisory.get("aliases", [])))
                advisories[canonical] = {**advisory, "aliases": aliases}
            except Exception as error:  # retained as incomplete, never clean
                failures.append({"advisory": advisory_id, "error": type(error).__name__})
        return {"queries": queries, "results": results, "advisories": advisories,
                "detail_failures": failures, "complete": not failures,
                "request_count": self.requests,
                "deduplicated_query_count": len(queries),
                "naive_query_count": sum(len(value) for value in inventories)}


def finding_identity(finding: dict) -> tuple[str, str, str]:
    return (finding["package"], finding["version"], finding["advisory"])


def compare_findings(baseline: list[dict], candidate: list[dict], complete: bool) -> dict:
    original = {finding_identity(item): item for item in baseline}
    current = {finding_identity(item): item for item in candidate}
    original_advisories = {(key[0], key[2]) for key in original}
    remaining = [item for key, item in current.items()
                 if (key[0], key[2]) in original_advisories]
    additional = [item for key, item in current.items()
                  if (key[0], key[2]) not in original_advisories]
    addressed = [item for key, item in original.items()
                 if not any(k[0] == key[0] and k[2] == key[2] for k in current)]
    return {"addressed": addressed, "remaining": remaining, "additional": additional,
            "candidate_total": list(current.values()),
            "assessment": "COMPLETE" if complete else "INCOMPLETE",
            "clean": complete and not current}


SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def severity_summary(findings: list[dict]) -> dict[str, int]:
    result = {severity: 0 for severity in SEVERITIES}
    for finding in findings:
        severity = str(finding.get("severity", "UNKNOWN")).upper()
        result[severity if severity in result else "UNKNOWN"] += 1
    return result


def release_comparison(baseline: list[dict], candidate: list[dict],
                       complete: bool) -> dict:
    comparison = compare_findings(baseline, candidate, complete)
    result = {name: severity_summary(comparison[name]) for name in
              ("addressed", "remaining", "additional", "candidate_total")}
    result["original"] = severity_summary(baseline)
    result["counts"] = {"original": len(baseline),
                        **{name: len(comparison[name]) for name in
                           ("addressed", "remaining", "additional", "candidate_total")}}
    result["invariants"] = {
        "original_equals_addressed_plus_remaining":
            len(baseline) == len(comparison["addressed"]) + len(comparison["remaining"]),
        "candidate_equals_remaining_plus_additional":
            len(candidate) == len(comparison["remaining"]) + len(comparison["additional"]),
    }
    result["assessment"] = comparison["assessment"]
    return result


def management_category(coordinate: str, *, direct: bool,
                        explicit_versions: set[str], boot_defaults: dict[str, str],
                        other_defaults: dict[str, str]) -> str:
    """Classify only from independently supplied effective-model evidence."""
    if coordinate in boot_defaults and coordinate in other_defaults:
        return "AMBIGUOUS"
    if coordinate in explicit_versions and coordinate in boot_defaults:
        return "BOOT_MANAGED_OVERRIDDEN"
    if coordinate in other_defaults:
        return "OTHER_MANAGED"
    if coordinate in boot_defaults:
        return "BOOT_MANAGED"
    return "INDEPENDENT_DIRECT" if direct else "INDEPENDENT_TRANSITIVE"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
