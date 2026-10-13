from __future__ import annotations

import re

from .http import EvidenceHttpClient

OSV_QUERY = "https://api.osv.dev/v1/query"
OSV_VULN = "https://api.osv.dev/v1/vulns/{}"
TOKEN = re.compile(r"[0-9]+|[A-Za-z]+")
QUALIFIERS = {"alpha": -5, "a": -5, "beta": -4, "b": -4, "milestone": -3,
              "m": -3, "rc": -2, "cr": -2, "snapshot": -1, "": 0,
              "final": 0, "ga": 0, "release": 0, "sp": 1}


def _maven_parts(version: str):
    """Conservative Maven-order subset; returns None for unsafe qualifiers."""
    raw = TOKEN.findall(version.lower())
    if not raw:
        return None
    parts = []
    for value in raw:
        if value.isdigit():
            parts.append((1, int(value)))
        elif value in QUALIFIERS:
            if QUALIFIERS[value] != 0:
                parts.append((0, QUALIFIERS[value]))
        else:
            return None
    while parts and parts[-1] == (1, 0):
        parts.pop()
    return parts


def compare_maven_versions(left: str, right: str) -> int | None:
    """Compare a safe Maven-like subset; unknown semantics are not guessed."""
    a, b = _maven_parts(left), _maven_parts(right)
    if a is None or b is None:
        return None
    size = max(len(a), len(b))
    for index in range(size):
        x = a[index] if index < len(a) else (1, 0)
        y = b[index] if index < len(b) else (1, 0)
        if x[0] != y[0]:
            return -1 if x[0] == 0 and x[1] < 0 else 1
        if x[1] != y[1]:
            return -1 if x[1] < y[1] else 1
    return 0


class OsvClient:
    def __init__(self, http: EvidenceHttpClient):
        self.http = http

    def query(self, package: str, version: str) -> dict:
        response, provenance = self.http.json(OSV_QUERY, {
            "package": {"ecosystem": "Maven", "name": package}, "version": version})
        return {"package": package, "version": version,
                "vulnerabilities": response.get("vulns", []), "provenance": provenance}

    def advisory(self, advisory_id: str) -> dict:
        response, provenance = self.http.json(OSV_VULN.format(advisory_id))
        return {"advisory": response, "provenance": provenance}

    @staticmethod
    def matching_affected(advisory: dict, package: str) -> list[dict]:
        return [a for a in advisory.get("affected", [])
                if a.get("package", {}).get("ecosystem") == "Maven"
                and a.get("package", {}).get("name") == package]

    @classmethod
    def range_evidence(cls, advisory: dict, package: str) -> dict:
        affected = cls.matching_affected(advisory, package)
        ranges = [value_range for item in affected for value_range in item.get("ranges", [])]
        events = [event for value_range in ranges for event in value_range.get("events", [])]
        versions = sorted({v for item in affected for v in item.get("versions", [])})
        return {"package_match": bool(affected), "ranges": ranges, "events": events,
                "explicit_versions": versions,
                "fixed_events": [e["fixed"] for e in events if "fixed" in e],
                "last_affected_events": [e["last_affected"] for e in events
                                         if "last_affected" in e]}

    @staticmethod
    def compare_original(baseline: dict, candidate: dict) -> dict:
        original = {v["id"] for v in baseline["vulnerabilities"]}
        candidate_ids = {v["id"] for v in candidate["vulnerabilities"]}
        return {"original_ids": sorted(original),
                "still_reported": sorted(original & candidate_ids),
                "not_reported": sorted(original - candidate_ids),
                "new_ids": sorted(candidate_ids - original)}


def advisory_verdict(advisory: dict, package: str, version: str) -> dict:
    evidence = OsvClient.range_evidence(advisory, package)
    if not evidence["package_match"]:
        return {"status": "UNKNOWN", "reason": "package not present", "range_evidence": evidence}
    if version in evidence["explicit_versions"]:
        return {"status": "STILL_AFFECTED", "reason": "explicit affected version",
                "range_evidence": evidence}
    interpreted = 0
    for value_range in evidence["ranges"]:
        if value_range.get("type") not in (None, "ECOSYSTEM"):
            continue
        active = False
        valid = True
        seen_start = False
        start_boundary = None
        for event in value_range.get("events", []):
            keys = set(event) & {"introduced", "fixed", "last_affected"}
            if len(keys) != 1:
                valid = False
                break
            key = next(iter(keys))
            boundary = event[key]
            if key == "introduced":
                if seen_start:
                    valid = False
                    break
                seen_start = True
                start_boundary = boundary
                comparison = 1 if boundary == "0" else compare_maven_versions(version, boundary)
                if comparison is None:
                    valid = False
                    break
                active = comparison >= 0
            elif key == "fixed":
                if not seen_start:
                    valid = False
                    break
                if start_boundary != "0":
                    interval_order = compare_maven_versions(start_boundary, boundary)
                    if interval_order is None or interval_order >= 0:
                        valid = False
                        break
                comparison = compare_maven_versions(version, boundary)
                if comparison is None:
                    valid = False
                    break
                if active and comparison < 0:
                    return {"status": "STILL_AFFECTED", "reason": "inside introduced/fixed interval",
                            "range_evidence": evidence}
                active = False
                seen_start = False
                start_boundary = None
            else:
                if not seen_start:
                    valid = False
                    break
                if start_boundary != "0":
                    interval_order = compare_maven_versions(start_boundary, boundary)
                    if interval_order is None or interval_order > 0:
                        valid = False
                        break
                comparison = compare_maven_versions(version, boundary)
                if comparison is None:
                    valid = False
                    break
                if active and comparison <= 0:
                    return {"status": "STILL_AFFECTED", "reason": "inside last-affected interval",
                            "range_evidence": evidence}
                active = False
                seen_start = False
                start_boundary = None
        if valid:
            interpreted += 1
            if active:
                return {"status": "STILL_AFFECTED", "reason": "inside open affected interval",
                        "range_evidence": evidence}
    if evidence["ranges"] and interpreted == len(evidence["ranges"]):
        return {"status": "ADDRESSED", "reason": "outside all complete affected intervals",
                "range_evidence": evidence}
    return {"status": "UNKNOWN", "reason": "range missing, unsupported, or contradictory",
            "range_evidence": evidence}
