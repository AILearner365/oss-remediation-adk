from __future__ import annotations

import urllib.parse
from collections import deque

from .http import EvidenceHttpClient

BASE = "https://api.deps.dev/v3/systems/maven/packages"


class DepsDevClient:
    def __init__(self, http: EvidenceHttpClient):
        self.http = http

    def version(self, package: str, version: str) -> dict:
        url = f"{BASE}/{urllib.parse.quote(package, safe='')}/versions/{urllib.parse.quote(version, safe='')}"
        response, provenance = self.http.json(url)
        return {"response": response, "provenance": provenance}

    def dependencies(self, package: str, version: str) -> dict:
        url = (f"{BASE}/{urllib.parse.quote(package, safe='')}/versions/"
               f"{urllib.parse.quote(version, safe='')}:dependencies")
        response, provenance = self.http.json(url)
        return {"response": response, "provenance": provenance}

    @staticmethod
    def paths(graph: dict, target: str) -> list[list[str]]:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        outgoing: dict[int, list[int]] = {}
        for edge in edges:
            outgoing.setdefault(edge["fromNode"], []).append(edge["toNode"])
        found = []
        queue = deque([(0, [0])])
        while queue:
            current, path = queue.popleft()
            key = nodes[current].get("versionKey", {}) if current < len(nodes) else {}
            if key.get("name") == target:
                found.append([f"{nodes[i]['versionKey']['name']}:{nodes[i]['versionKey']['version']}"
                              for i in path])
                continue
            for child in outgoing.get(current, []):
                if child not in path:
                    queue.append((child, path + [child]))
        return found
