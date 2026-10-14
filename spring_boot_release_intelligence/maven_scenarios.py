from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .maven import MavenResolver

HEADER = """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion>{parent}<groupId>experiment</groupId>
<artifactId>{artifact}</artifactId><version>1</version>{body}</project>"""
TOMCAT = "org.apache.tomcat.embed:tomcat-embed-core"
CODEC = "commons-codec:commons-codec"


def _dependency(group, artifact, version=None, extra=""):
    value = f"<dependency><groupId>{group}</groupId><artifactId>{artifact}</artifactId>"
    if version:
        value += f"<version>{version}</version>"
    return value + extra + "</dependency>"


def run_scenarios(resolver: MavenResolver) -> dict:
    cases = {}
    require_paths = getattr(resolver, "preserves_paths", True)
    # Independent expectation: both dependencies are at equal depth; Maven's
    # documented nearest-definition tie-break selects the first declaration.
    mediation = HEADER.format(parent="", artifact="mediation", body="<dependencies>" +
        _dependency("org.apache.httpcomponents", "httpclient", "4.5.14") +
        _dependency("org.apache.poi", "poi", "5.2.5") + "</dependencies>")
    cases["transitive_mediation"] = _record(
        resolver.resolve_pom("scenario-mediation", mediation, [CODEC]),
        {"selected_version": "1.11", "path_contains": "org.apache.httpcomponents:httpclient:4.5.14"},
        require_path=require_paths)

    parent = """<parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.3.4</version></parent>"""
    starter = _dependency("org.springframework.boot", "spring-boot-starter-web")
    direct = HEADER.format(parent=parent, artifact="direct", body="<dependencies>" + starter +
        _dependency("org.apache.tomcat.embed", "tomcat-embed-core", "10.1.31") + "</dependencies>")
    cases["direct_override"] = _record(
        resolver.resolve_pom("scenario-direct", direct, [TOMCAT]),
        {"selected_version": "10.1.31", "path_contains": "experiment:direct:1"},
        require_path=require_paths)

    management = "<dependencyManagement><dependencies>" + _dependency(
        "org.apache.tomcat.embed", "tomcat-embed-core", "10.1.31") + "</dependencies></dependencyManagement>"
    managed = HEADER.format(parent=parent, artifact="managed", body=management +
                            "<dependencies>" + starter + "</dependencies>")
    cases["dependency_management_override"] = _record(
        resolver.resolve_pom("scenario-managed", managed, [TOMCAT]),
        {"selected_version": "10.1.31", "path_contains": "spring-boot-starter-tomcat:3.3.4"},
        require_path=require_paths)

    profile = "<profiles><profile><id>upgrade</id>" + management + "</profile></profiles>"
    profiled = HEADER.format(parent=parent, artifact="profile", body=profile +
                            "<dependencies>" + starter + "</dependencies>")
    cases["applicable_profile_inactive"] = _record(
        resolver.resolve_pom("scenario-profile-inactive", profiled, [TOMCAT]),
        {"selected_version": "10.1.30", "path_contains": "spring-boot-starter-tomcat:3.3.4"},
        require_path=require_paths)
    cases["applicable_profile_active"] = _record(
        resolver.resolve_pom("scenario-profile-active", profiled, [TOMCAT], ["upgrade"]),
        {"selected_version": "10.1.31", "path_contains": "spring-boot-starter-tomcat:3.3.4"},
        require_path=require_paths)

    exclusion = "<exclusions><exclusion><groupId>org.springframework.boot</groupId>" \
                "<artifactId>spring-boot-starter-tomcat</artifactId></exclusion></exclusions>"
    excluded = HEADER.format(parent=parent, artifact="excluded", body="<dependencies>" +
                             _dependency("org.springframework.boot", "spring-boot-starter-web",
                                         extra=exclusion) + "</dependencies>")
    cases["dependency_exclusion"] = _record(
        resolver.resolve_pom("scenario-exclusion", excluded, [TOMCAT]),
        {"selected_version": None, "path_contains": None},
        require_path=require_paths)
    cases["multi_module"] = (resolver.resolve_multi_module()
                             if hasattr(resolver, "resolve_multi_module")
                             else _multi_module(resolver))
    return cases


def _record(observation: dict, expected: dict, *, require_path: bool = True) -> dict:
    contains = expected["path_contains"]
    paths = observation["paths"]
    path_ok = (not paths if contains is None else
               any(any(contains in node for node in path) for path in paths))
    checks = {"selected_version": observation["selected_version"] == expected["selected_version"],
              "command_succeeded": observation["returncode"] == 0}
    if require_path:
        checks["path"] = path_ok
    else:
        target = next(iter(observation["target_presence"]))
        checks["selection_presence"] = (
            observation["target_presence"].get(target)
            == (expected["selected_version"] is not None))
        checks["collection_complete"] = observation.get("collection_complete", False)
    return {"expected": expected, "observation": observation, "checks": checks,
            "passed": all(checks.values())}


def _multi_module(resolver: MavenResolver) -> dict:
    root = resolver.work_dir / "scenario-multi-module"
    library, app = root / "library", root / "app"
    library.mkdir(parents=True, exist_ok=True)
    app.mkdir(parents=True, exist_ok=True)
    root_pom = """<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
<groupId>experiment</groupId><artifactId>multi-parent</artifactId><version>1</version><packaging>pom</packaging>
<modules><module>library</module><module>app</module></modules></project>"""
    child_parent = "<parent><groupId>experiment</groupId><artifactId>multi-parent</artifactId><version>1</version></parent>"
    library_pom = HEADER.format(parent=child_parent, artifact="library", body="<dependencies>" +
        _dependency("org.apache.tomcat.embed", "tomcat-embed-core", "10.1.30") + "</dependencies>")
    app_pom = HEADER.format(parent=child_parent, artifact="app", body=
        "<dependencyManagement><dependencies>" + _dependency(
            "org.apache.tomcat.embed", "tomcat-embed-core", "10.1.31") +
        "</dependencies></dependencyManagement><dependencies>" +
        _dependency("experiment", "library", "1") + "</dependencies>")
    (root / "pom.xml").write_text(root_pom, encoding="utf-8")
    (library / "pom.xml").write_text(library_pom, encoding="utf-8")
    (app / "pom.xml").write_text(app_pom, encoding="utf-8")
    started = time.monotonic()
    install_command = ["mvn", "-B", "-q", "install", "-DskipTests"]
    if resolver.local_repository:
        install_command.insert(3, f"-Dmaven.repo.local={resolver.local_repository.resolve()}")
    install = subprocess.run(install_command, cwd=root,
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             timeout=180)
    observation = resolver.resolve_pom("scenario-multi-module/app", app_pom, [TOMCAT])
    observation["install_returncode"] = install.returncode
    observation["install_elapsed_seconds"] = time.monotonic() - started
    record = _record(observation, {"selected_version": "10.1.31",
                                   "path_contains": "experiment:library:1"})
    record["checks"]["reactor_install"] = install.returncode == 0
    record["passed"] = all(record["checks"].values())
    return record
