from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from .maven import POM, parse_tgf
from .maven_scenarios import HEADER, TOMCAT, _dependency, _record


PLUGIN_GOAL = "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree"
_BINARY_SUFFIXES = {".jar", ".war", ".zip", ".class", ".so", ".dll", ".dylib", ".exe"}
_SIZE = re.compile(r"\((\d+(?:\.\d+)?)\s*([kMGT]?B)\s+at")


def repository_snapshot(repository: Path) -> dict[str, int]:
    if not repository.exists():
        return {}
    snapshot = {}
    for path in repository.rglob("*"):
        try:
            if path.is_file():
                snapshot[str(path.relative_to(repository))] = path.stat().st_size
        except FileNotFoundError:
            # Maven atomically replaces temporary download files.
            continue
    return snapshot


def repository_size(repository: Path) -> int:
    return sum(repository_snapshot(repository).values())


def _application_jar_paths(selected: dict[str, str]) -> set[str]:
    paths = set()
    for coordinate, version in selected.items():
        group, artifact = coordinate.split(":", 1)
        paths.add(f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar")
    return paths


def classify_repository_delta(before: dict[str, int], after: dict[str, int],
                              selected: dict[str, str]) -> dict:
    application_jars = _application_jar_paths(selected)
    categories: dict[str, dict[str, int]] = {}
    files = []
    for path, size in sorted(after.items()):
        if before.get(path) == size:
            continue
        name, suffix = Path(path).name, Path(path).suffix.lower()
        if suffix == ".pom":
            category = "pom"
        elif name.startswith("maven-metadata") and suffix == ".xml":
            category = "maven_metadata"
        elif suffix == ".jar":
            category = ("application_dependency_jar" if path in application_jars
                        else "plugin_bootstrap_jar")
        elif suffix in _BINARY_SUFFIXES:
            category = "other_binary"
        else:
            category = "tracking_or_checksum"
        values = categories.setdefault(category, {"count": 0, "bytes": 0})
        values["count"] += 1
        values["bytes"] += size
        files.append({"path": path, "bytes": size, "category": category})
    for category in ("pom", "maven_metadata", "application_dependency_jar",
                     "plugin_bootstrap_jar", "other_binary", "tracking_or_checksum"):
        categories.setdefault(category, {"count": 0, "bytes": 0})
    return {"categories": categories, "files": files,
            "changed_file_count": len(files),
            "changed_bytes": sum(item["bytes"] for item in files)}


def transfer_metrics(log: str) -> dict:
    attempts = sum("Downloading from " in line for line in log.splitlines())
    successes = sum("Downloaded from " in line for line in log.splitlines())
    reported_bytes = 0
    for line in log.splitlines():
        if "Downloaded from " not in line:
            continue
        match = _SIZE.search(line)
        if match:
            number, unit = match.groups()
            multiplier = {"B": 1, "kB": 1000, "MB": 1000 ** 2,
                          "GB": 1000 ** 3, "TB": 1000 ** 4}[unit]
            reported_bytes += round(float(number) * multiplier)
    return {"transfer_attempt_events": attempts,
            "successful_transfer_events": successes,
            "maven_reported_bytes": reported_bytes,
            "http_request_count": None,
            "http_request_count_reason": "Maven CLI does not expose transport-level request counts"}


class MetadataOnlyMavenResolver:
    """Maven-native graph collection with an isolated local repository.

    The dependency plugin itself needs binary bootstrap artifacts. The collector
    is accepted only when the post-run inventory contains no selected
    application dependency JARs or other unexplained binaries.
    """

    def __init__(self, work_dir: Path, local_repository: Path, *, quiet: bool = False):
        self.work_dir = work_dir
        self.local_repository = local_repository
        self.log_dir = work_dir / "logs"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.local_repository.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_label = ""
        self.quiet = quiet

    def resolve(self, boot: str, tomcat_override: str | None = None,
                targets: list[str] | None = None) -> dict:
        suffix = f"-override-{tomcat_override}" if tomcat_override else ""
        props = (f"<properties><tomcat.version>{tomcat_override}</tomcat.version></properties>"
                 if tomcat_override else "")
        pom = POM.format(boot=boot, artifact=f"case-{boot}{suffix}", properties=props)
        result = self.resolve_pom(f"boot-{boot}{suffix}", pom, targets or [TOMCAT])
        result.update({"boot": boot, "override": tomcat_override})
        return result

    def resolve_pom(self, name: str, pom: str, targets: list[str],
                    profiles: list[str] | None = None) -> dict:
        project = self.work_dir / name
        project.mkdir(parents=True, exist_ok=True)
        (project / "pom.xml").write_text(pom, encoding="utf-8")
        output = (project / "dependency-tree.tgf").resolve()
        command = ["mvn", "-B", f"-Dmaven.repo.local={self.local_repository.resolve()}",
                   PLUGIN_GOAL, "-DoutputType=tgf", f"-DoutputFile={output}"]
        if self.quiet:
            command.insert(2, "-q")
        if profiles:
            command.append(f"-P{','.join(profiles)}")
        return self._execute(name, project, output, command, targets)

    def _execute(self, name: str, project: Path, output: Path,
                 command: list[str], targets: list[str]) -> dict:
        before = repository_snapshot(self.local_repository)
        before_bytes = sum(before.values())
        suffix = f"-{self.run_label}" if self.run_label else ""
        log_file = self.log_dir / f"{name.replace('/', '-')}{suffix}.log"
        started = time.monotonic()
        with log_file.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(command, cwd=project, text=True,
                                       stdout=stream, stderr=subprocess.STDOUT)
            try:
                process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise RuntimeError(f"Maven metadata collection timed out: {command}")
        elapsed = time.monotonic() - started
        log = log_file.read_text(encoding="utf-8")
        if process.returncode or not output.exists():
            raise RuntimeError(f"Maven metadata collection failed ({process.returncode}):\n{log[-4000:]}")
        parsed = parse_tgf(output, targets)
        after = repository_snapshot(self.local_repository)
        final_bytes = sum(after.values())
        inventory = classify_repository_delta(before, after, parsed["selected_artifacts"])
        categories = inventory["categories"]
        compliant = (categories["application_dependency_jar"]["count"] == 0
                     and categories["other_binary"]["count"] == 0)
        parsed.update({
            "command": command, "mechanism": PLUGIN_GOAL,
            "elapsed_seconds": elapsed, "returncode": process.returncode,
            "stdout": log[-4000:], "log_file": str(log_file),
            "tree_file": str(output), "storage": {
                "cache_bytes_before": before_bytes,
                "cache_bytes_after": final_bytes,
                "peak_cache_bytes": final_bytes,
                "delta": inventory,
                "transfers": transfer_metrics(log),
                "no_application_dependency_jars": compliant,
                "strict_claim": ("NO_APPLICATION_DEPENDENCY_JARS; "
                                 "PLUGIN_BOOTSTRAP_BINARIES_RECORDED")
                              if compliant else "NONCOMPLIANT_BINARY_DOWNLOAD",
            },
        })
        return parsed

    def resolve_multi_module(self) -> dict:
        root = self.work_dir / "scenario-multi-module"
        library, app = root / "library", root / "app"
        library.mkdir(parents=True, exist_ok=True)
        app.mkdir(parents=True, exist_ok=True)
        root_pom = """<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
<groupId>experiment</groupId><artifactId>multi-parent</artifactId><version>1</version><packaging>pom</packaging>
<modules><module>library</module><module>app</module></modules></project>"""
        child_parent = "<parent><groupId>experiment</groupId><artifactId>multi-parent</artifactId><version>1</version></parent>"
        library_pom = HEADER.format(parent=child_parent, artifact="library",
            body="<dependencies>" + _dependency("org.apache.tomcat.embed",
            "tomcat-embed-core", "10.1.30") + "</dependencies>")
        app_pom = HEADER.format(parent=child_parent, artifact="app", body=
            "<dependencyManagement><dependencies>" + _dependency(
            "org.apache.tomcat.embed", "tomcat-embed-core", "10.1.31") +
            "</dependencies></dependencyManagement><dependencies>" +
            _dependency("experiment", "library", "1") + "</dependencies>")
        (root / "pom.xml").write_text(root_pom, encoding="utf-8")
        (library / "pom.xml").write_text(library_pom, encoding="utf-8")
        (app / "pom.xml").write_text(app_pom, encoding="utf-8")
        output = (root / "app-dependency-tree.tgf").resolve()
        command = ["mvn", "-B", f"-Dmaven.repo.local={self.local_repository.resolve()}",
                   "-f", str((root / "pom.xml").resolve()), "-pl", "app", "-am",
                   PLUGIN_GOAL, "-DoutputType=tgf", f"-DoutputFile={output}"]
        if self.quiet:
            command.insert(2, "-q")
        observation = self._execute("scenario-multi-module", root, output,
                                    command, [TOMCAT])
        record = _record(observation, {"selected_version": "10.1.31",
                                       "path_contains": "experiment:library:1"})
        record["checks"]["reactor_collection_without_install"] = (
            not list(root.rglob("*.jar"))
            and observation["storage"]["no_application_dependency_jars"])
        record["passed"] = all(record["checks"].values())
        return record
