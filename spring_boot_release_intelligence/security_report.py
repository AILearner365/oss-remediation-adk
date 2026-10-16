from __future__ import annotations

import re
from pathlib import Path

from .a7 import Dependency


SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def severity_from_score(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 9:
        return "CRITICAL"
    if score >= 7:
        return "HIGH"
    if score >= 4:
        return "MEDIUM"
    return "LOW"


def _score(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coordinate_from_purl(purl: str | None) -> str | None:
    match = re.match(r"pkg:maven/([^/]+)/([^@?]+)", purl or "")
    return f"{match.group(1)}:{match.group(2)}" if match else None


def read_osv_json(report: dict, inventory: list[Dependency], source: str) -> list[dict]:
    """Normalize OSV Scanner JSON without performing advisory matching."""
    by_artifact: dict[tuple[str, str], list[Dependency]] = {}
    for dependency in inventory:
        by_artifact.setdefault((dependency.artifact, dependency.version), []).append(dependency)
    findings = {}
    for result in report.get("results", []):
        for package in result.get("packages", []):
            observed = package.get("package", {})
            version = observed.get("version")
            matches = by_artifact.get((observed.get("name", ""), version), [])
            groups = package.get("groups", [])
            for vulnerability in package.get("vulnerabilities", []):
                advisory = vulnerability.get("id")
                affected = vulnerability.get("affected", [])
                coordinate = next((_coordinate_from_purl(item.get("package", {}).get("purl"))
                                   for item in affected if _coordinate_from_purl(
                                       item.get("package", {}).get("purl"))), None)
                coordinate_matches = [item for item in inventory
                                      if item.coordinate == coordinate and item.version == version]
                if coordinate_matches:
                    matches = coordinate_matches
                if len(matches) != 1 or not advisory:
                    continue
                aliases = sorted(set(vulnerability.get("aliases", [])))
                ratings = [group for group in groups if advisory in group.get("ids", [])]
                scores = [_score(group.get("max_severity")) for group in ratings]
                scores = [value for value in scores if value is not None]
                score = max(scores) if scores else None
                fixed = sorted({event["fixed"] for item in affected
                                for value_range in item.get("ranges", [])
                                for event in value_range.get("events", []) if "fixed" in event})
                dependency = matches[0]
                identity = f"{dependency.coordinate}|{advisory}"
                findings[identity] = {
                    "identity": identity, "package": dependency.coordinate,
                    "version": version, "advisory_id": advisory, "aliases": aliases,
                    "severity": severity_from_score(score), "score": score,
                    "fixed_versions": fixed, "fixed_evidence_status":
                        "KNOWN" if fixed else "UNKNOWN",
                    "source": source, "evidence_reference": source,
                }
    return [findings[key] for key in sorted(findings)]


def read_cyclonedx_vulnerabilities(report: dict, inventory: list[Dependency],
                                   source: str) -> list[dict]:
    """Read standard CycloneDX vulnerabilities and correlate by bom-ref/purl."""
    components = {item.get("bom-ref"): item for item in report.get("components", [])}
    inventory_by_purl = {item.purl: item for item in inventory}
    findings = {}
    for vulnerability in report.get("vulnerabilities", []):
        advisory = vulnerability.get("id")
        aliases = {item.get("id") for item in vulnerability.get("references", [])
                   if item.get("id")}
        aliases.update(item.get("value") for item in vulnerability.get("properties", [])
                       if "alias" in item.get("name", "").lower() and item.get("value"))
        aliases = sorted(aliases)
        ratings = vulnerability.get("ratings", [])
        score_values = [_score(item.get("score")) for item in ratings]
        score_values = [item for item in score_values if item is not None]
        score = max(score_values) if score_values else None
        named = next((str(item.get("severity", "")).upper() for item in ratings
                      if str(item.get("severity", "")).upper() in SEVERITIES), None)
        fixed = sorted({version.get("version") for affect in vulnerability.get("affects", [])
                        for version in affect.get("versions", [])
                        if version.get("status") == "unaffected" and version.get("version")})
        for affect in vulnerability.get("affects", []):
            component = components.get(affect.get("ref"), {})
            purl = component.get("purl") or affect.get("ref")
            dependency = inventory_by_purl.get(purl)
            if not dependency or not advisory:
                continue
            identity = f"{dependency.coordinate}|{advisory}"
            findings[identity] = {
                "identity": identity, "package": dependency.coordinate,
                "version": dependency.version, "advisory_id": advisory,
                "aliases": aliases, "severity": named or severity_from_score(score),
                "score": score, "fixed_versions": fixed,
                "fixed_evidence_status": "KNOWN" if fixed else "UNKNOWN",
                "source": source, "evidence_reference": source,
            }
    return [findings[key] for key in sorted(findings)]
