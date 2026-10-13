from __future__ import annotations

import subprocess
import time
from collections import deque
from pathlib import Path


POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{boot}</version>
  </parent>
  <groupId>experiment</groupId><artifactId>{artifact}</artifactId><version>1</version>
{properties}
  <dependencies><dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency></dependencies>
</project>
"""


class MavenResolver:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, boot: str, tomcat_override: str | None = None,
                targets: list[str] | None = None) -> dict:
        suffix = f"-override-{tomcat_override}" if tomcat_override else ""
        project = self.work_dir / f"boot-{boot}{suffix}"
        project.mkdir(parents=True, exist_ok=True)
        props = (f"<properties><tomcat.version>{tomcat_override}</tomcat.version></properties>"
                 if tomcat_override else "")
        pom = POM.format(boot=boot, artifact=f"case-{boot}{suffix}", properties=props)
        result = self.resolve_pom(project.name, pom, targets or
                                  ["org.apache.tomcat.embed:tomcat-embed-core"])
        result.update({"boot": boot, "override": tomcat_override})
        return result

    def resolve_pom(self, name: str, pom: str, targets: list[str],
                    profiles: list[str] | None = None) -> dict:
        project = self.work_dir / name
        project.mkdir(parents=True, exist_ok=True)
        (project / "pom.xml").write_text(pom, encoding="utf-8")
        output = (project / "dependency-tree.json").resolve()
        command = ["mvn", "-B", "-q", "dependency:tree", "-DoutputType=tgf",
                   f"-DoutputFile={output}"]
        if profiles:
            command.append(f"-P{','.join(profiles)}")
        return self._execute(project, output, command, targets)

    def _execute(self, project: Path, output: Path, command: list[str],
                 targets: list[str]) -> dict:
        started = time.monotonic()
        completed = subprocess.run(command, cwd=project, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=180)
        elapsed = time.monotonic() - started
        if completed.returncode or not output.exists():
            raise RuntimeError(f"Maven dependency:tree failed ({completed.returncode}):\n{completed.stdout}")
        node_lines, edge_lines = output.read_text(encoding="utf-8").split("#", 1)
        nodes = {}
        for line in node_lines.splitlines():
            if line.strip():
                node_id, coordinate = line.split(" ", 1)
                nodes[node_id] = coordinate
        edges = {}
        children = set()
        for line in edge_lines.splitlines():
            if line.strip():
                parent, child, *_ = line.split()
                edges.setdefault(parent, []).append(child)
                children.add(child)
        paths = {target: [] for target in targets}
        selected = {}
        roots = [node_id for node_id in nodes if node_id not in children]
        queue = deque((root, []) for root in roots)
        while queue:
            node_id, path = queue.popleft()
            parts = nodes[node_id].split(":")
            coordinate = ":".join(parts[:2])
            # Maven TGF is g:a:type:version[:scope].
            current = path + [f"{coordinate}:{parts[3]}"]
            selected.setdefault(coordinate, parts[3])
            if coordinate in paths:
                paths[coordinate].append(current)
            for child in edges.get(node_id, []):
                queue.append((child, current))
        primary_paths = paths[targets[0]] if targets else []
        return {"paths": primary_paths, "target_paths": paths,
                "selected_version": (primary_paths[0][-1].rsplit(":", 1)[-1]
                                     if primary_paths else None),
                "selected_artifacts": selected,
                "command": command, "elapsed_seconds": elapsed,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:], "tree_file": str(output)}
