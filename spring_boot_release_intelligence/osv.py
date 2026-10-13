from __future__ import annotations

from .http import EvidenceHttpClient

OSV_QUERY = "https://api.osv.dev/v1/query"
OSV_VULN = "https://api.osv.dev/v1/vulns/{}"


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
        events = [event for item in affected for value_range in item.get("ranges", [])
                  for event in value_range.get("events", [])]
        return {"package_match": bool(affected), "events": events,
                "fixed_events": [e["fixed"] for e in events if "fixed" in e],
                "last_affected_events": [e["last_affected"] for e in events
                                         if "last_affected" in e],
                "explicit_versions_count": sum(len(a.get("versions", [])) for a in affected)}

    @staticmethod
    def compare_original(baseline: dict, candidate: dict) -> dict:
        original = {v["id"] for v in baseline["vulnerabilities"]}
        candidate_ids = {v["id"] for v in candidate["vulnerabilities"]}
        return {"original_ids": sorted(original),
                "still_reported": sorted(original & candidate_ids),
                # This means only absent from the candidate query until advisory
                # range evidence upgrades it to ADDRESSED.
                "not_reported": sorted(original - candidate_ids),
                "new_ids": sorted(candidate_ids - original)}
