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

    def resolve(self, boot: str, tomcat_override: str | None = None) -> dict:
        suffix = f"-override-{tomcat_override}" if tomcat_override else ""
        project = self.work_dir / f"boot-{boot}{suffix}"
        project.mkdir(parents=True, exist_ok=True)
        props = (f"<properties><tomcat.version>{tomcat_override}</tomcat.version></properties>"
                 if tomcat_override else "")
        pom = POM.format(boot=boot, artifact=f"case-{boot}{suffix}", properties=props)
        (project / "pom.xml").write_text(pom, encoding="utf-8")
        output = (project / "dependency-tree.json").resolve()
        command = ["mvn", "-B", "-q", "dependency:tree", "-DoutputType=tgf",
                   f"-DoutputFile={output}"]
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
        target = "org.apache.tomcat.embed:tomcat-embed-core"
        paths = []
        roots = [node_id for node_id in nodes if node_id not in children]
        queue = deque((root, []) for root in roots)
        while queue:
            node_id, path = queue.popleft()
            parts = nodes[node_id].split(":")
            coordinate = ":".join(parts[:2])
            # Maven TGF is g:a:type:version[:scope].
            current = path + [f"{coordinate}:{parts[3]}"]
            if coordinate == target:
                paths.append(current)
            for child in edges.get(node_id, []):
                queue.append((child, current))
        return {"boot": boot, "override": tomcat_override, "paths": paths,
                "selected_version": paths[0][-1].rsplit(":", 1)[-1] if paths else None,
                "command": command, "elapsed_seconds": elapsed,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:], "tree_file": str(output)}
