from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .http import EvidenceHttpClient

CENTRAL = "https://repo.maven.apache.org/maven2"
TOKEN = re.compile(r"\$\{([^}]+)\}")


@dataclass
class ManagedDependency:
    package: str
    version: str
    origin: str
    property_chain: list[str]


class BomResolver:
    """Deliberately bounded POM/parent/import resolver; not an effective model."""

    def __init__(self, http: EvidenceHttpClient):
        self.http = http
        self.documents: list[dict] = []

    @staticmethod
    def _pom_url(group: str, artifact: str, version: str) -> str:
        return f"{CENTRAL}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.pom"

    @staticmethod
    def _text(node, name):
        child = node.find(f"{{*}}{name}") if node is not None else None
        return child.text.strip() if child is not None and child.text else None

    def _expand(self, value: str | None, props: dict[str, str]) -> tuple[str | None, list[str]]:
        chain = []
        for _ in range(20):
            if value is None:
                return None, chain
            match = TOKEN.search(value)
            if not match:
                return value, chain
            key = match.group(1)
            if key not in props or key in chain:
                return value, chain
            chain.append(key)
            value = value[:match.start()] + props[key] + value[match.end():]
        return value, chain

    def resolve(self, group: str, artifact: str, version: str) -> dict[str, ManagedDependency]:
        return self._resolve(group, artifact, version, {}, set())

    def _resolve(self, group, artifact, version, inherited_props, seen):
        coordinate = f"{group}:{artifact}:{version}"
        if coordinate in seen:
            return {}
        seen.add(coordinate)
        url = self._pom_url(group, artifact, version)
        raw, provenance = self.http.request(url)
        root = ET.fromstring(raw)
        props = dict(inherited_props)
        props.update({c.tag.split("}")[-1]: (c.text or "").strip()
                      for p in root.findall("{*}properties") for c in p})
        project_group = self._text(root, "groupId") or group
        project_version = self._text(root, "version") or version
        props.update({"project.groupId": project_group, "project.version": project_version,
                      "pom.groupId": project_group, "pom.version": project_version})
        managed: dict[str, ManagedDependency] = {}
        parent = root.find("{*}parent")
        if parent is not None:
            pg, pa, pv = (self._text(parent, x) for x in ("groupId", "artifactId", "version"))
            if pg and pa and pv:
                managed.update(self._resolve(pg, pa, pv, props, seen))
        imports = []
        local = []
        dm = root.find("{*}dependencyManagement")
        deps = dm.find("{*}dependencies") if dm is not None else None
        for dep in list(deps or []):
            g, a = self._text(dep, "groupId"), self._text(dep, "artifactId")
            raw_version = self._text(dep, "version")
            resolved, chain = self._expand(raw_version, props)
            if self._text(dep, "type") == "pom" and self._text(dep, "scope") == "import" and resolved:
                imports.append((g, a, resolved))
            elif g and a and resolved:
                local.append((f"{g}:{a}", ManagedDependency(f"{g}:{a}", resolved,
                              coordinate, chain)))
        for g, a, v in imports:
            managed.update(self._resolve(g, a, v, props, seen))
        managed.update(local)
        self.documents.append({"coordinate": coordinate, "url": url,
                               "provenance": provenance,
                               "imports": [":".join(x) for x in imports]})
        return managed
