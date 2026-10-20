"""Build/test + resolved Maven graph + OSV coverage on an immutable Git export.

OSV receives a CycloneDX inventory derived from Maven's actual resolved trees,
not source POM guesses. Missing modules/packages or scanner errors are unknown.
"""
import json
import re
import time
from urllib.parse import quote
import uuid
import xml.etree.ElementTree as ET

from .files import Blocked, command, digest, write, require_independent_authority
from .repository import export

TREE_FILE = "native-remediation-dependencies.json"
DEPENDENCY_GOAL = "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree"
EFFECTIVE_GOAL = "org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom"


def xml(path):
    root = ET.parse(path).getroot()
    for element in root.iter():
        element.tag = element.tag.split("}")[-1]
    return root


def resolved_inventory(source, effective):
    root = xml(effective)
    projects = [root] if root.tag == "project" else list(root.findall("project"))
    models = {}
    for project in projects:
        identity = tuple(project.findtext(k) or "" for k in ("groupId", "artifactId", "version"))
        if not all(identity) or identity in models:
            raise Blocked("Incomplete or duplicate effective reactor models")
        models[identity] = {p.tag: p.text or "" for p in project.findall("properties/*")}
    if not models:
        raise Blocked("Effective reactor models missing")
    graphs, packages, roots = [], set(), set()
    for path in source.rglob(TREE_FILE):
        if path.parent.name != "target":
            continue
        graph = json.loads(path.read_text())
        identity = tuple(graph.get(k, "") for k in ("groupId", "artifactId", "version"))
        if identity not in models or identity in roots:
            raise Blocked("Resolved graph does not match the effective reactor")
        roots.add(identity)
        def walk(node):
            identity = tuple(node.get(k, "") for k in ("groupId", "artifactId", "version"))
            if not all(isinstance(x, str) and x and "${" not in x for x in identity):
                raise Blocked("Unresolved dependency coordinates")
            if identity not in models:
                packages.add((identity[0] + ":" + identity[1], identity[2]))
            children = node.get("children", [])
            if not isinstance(children, list):
                raise Blocked("Invalid dependency graph")
            for child in children:
                walk(child)
        walk(graph)
        graphs.append(dict(path=str(path.relative_to(source)), graph=graph))
    if roots != set(models) or not packages:
        raise Blocked("Missing reactor dependency graphs or zero external dependencies")
    properties = {g + ":" + a: props for (g, a, _), props in models.items()}
    return dict(modules=sorted(properties), properties=properties,
                packages=[dict(name=n, version=v) for n, v in sorted(packages)], graphs=graphs)


def sbom(packages):
    components = []
    for package in packages:
        group, artifact = package["name"].split(":", 1)
        purl = "pkg:maven/" + quote(group, safe="") + "/" + quote(artifact, safe="") + "@" + quote(package["version"], safe="")
        components.append(dict(type="library", group=group, name=artifact,
                               version=package["version"], purl=purl, **{"bom-ref": purl}))
    return dict(bomFormat="CycloneDX", specVersion="1.5", version=1,
                serialNumber="urn:uuid:" + str(uuid.uuid4()), components=components)


def scan_result(payload, packages, exit_code, stderr):
    if (exit_code not in (0, 1) or not isinstance(payload, dict)
            or not isinstance(payload.get("results"), list)
            or re.search(r"\b(error|failed|unscannable|filtered)\b", stderr, re.I)):
        raise Blocked("OSV error/incomplete extraction; absence of findings is not PASS")
    expected = {(p["name"], p["version"]) for p in packages}
    covered, findings = set(), {}
    for source in payload["results"]:
        if not isinstance(source.get("packages"), list):
            raise Blocked("OSV package coverage missing")
        for row in source["packages"]:
            package = row.get("package", {})
            key = (package.get("name"), package.get("version"))
            if package.get("ecosystem") != "Maven" or key not in expected:
                raise Blocked("Unexpected OSV package identity")
            covered.add(key)
            vulnerabilities = row.get("vulnerabilities", [])
            if not isinstance(vulnerabilities, list):
                raise Blocked("Malformed vulnerability coverage")
            for vuln in vulnerabilities:
                if not isinstance(vuln, dict) or not vuln.get("id"):
                    raise Blocked("Malformed OSV finding")
                identifiers = sorted({vuln["id"], *vuln.get("aliases", [])})
                identity = (package["name"], tuple(identifiers))
                findings[identity] = dict(package=package["name"], version=package["version"],
                    ids=identifiers, summary=vuln.get("summary", ""), affected=vuln.get("affected", []))
    if covered != expected or bool(findings) != (exit_code == 1):
        raise Blocked("OSV exit/report disagreement or incomplete resolved-package coverage")
    return dict(coverage=dict(expected=len(expected), scanned=len(covered), complete=True,
                scope="Resolved Maven project dependency graphs, all scopes; excludes build-plugin/JDK/OS dependencies"),
                findings=sorted(findings.values(), key=lambda f: (f["package"], f["ids"])))


def test_counts(source):
    count = 0
    for pattern in ("**/surefire-reports/TEST-*.xml", "**/failsafe-reports/TEST-*.xml"):
        for path in source.glob(pattern):
            report = xml(path)
            suites = [report] if report.tag == "testsuite" else list(report.findall("testsuite"))
            for suite in suites:
                if int(suite.get("failures", "0")) or int(suite.get("errors", "0")):
                    raise Blocked("Test report contains failures")
                count += int(suite.get("tests", "0")) - int(suite.get("skipped", "0"))
    return count


def evaluate(workspace, tree, task, directory, *, deadline, runner=None):
    if runner is None:
        require_independent_authority()
        runner = command
    directory.mkdir(parents=True, exist_ok=False)
    result = dict(tree=tree, outcome="INCONCLUSIVE", reasons=[], commands=[])
    try:
        source = directory / "source"
        export(workspace, tree, source)
        # Do not trust candidate-authored generated files as resolution evidence.
        for path in source.rglob(TREE_FILE):
            raise Blocked("Candidate contains reserved generated dependency evidence")
        def run(argv, name):
            remaining = int(deadline - time.time())
            if remaining <= 0:
                raise Blocked("Validation/task time budget exhausted")
            record = runner(argv, source, min(task["limits"]["command_seconds"], remaining),
                            directory / (name + ".json"))
            result["commands"].append(dict(name=name, exitCode=record["exitCode"], timedOut=record["timedOut"]))
            if record["timedOut"]:
                raise Blocked(name + " timed out")
            return record
        tool = task["tools"]
        prefix = [tool["maven"], "-B", "-ntp", "-Dstyle.color=never",
                  "-Dmaven.repo.local=" + str(source.parent / "maven-cache")]
        if tool["profiles"]:
            prefix += ["-P" + ",".join(tool["profiles"])]
        # Install includes verify/tests and makes reactor artifacts resolvable in
        # the subsequent graph command, using only this task's Maven cache.
        build = run(prefix + ["clean", "install", "-DskipTests=false", "-Dmaven.test.skip=false", "-DskipITs=false"], "build")
        if build["exitCode"]:
            result["outcome"] = "FAIL"
            raise Blocked("Maven build/tests failed; see private build evidence")
        # A raw build output, not a writable mount of the trusted evidence directory.
        effective = source / "target" / "effective-pom.xml"
        resolve = run(prefix + [DEPENDENCY_GOAL, EFFECTIVE_GOAL, "-DoutputType=json",
            "-DoutputFile=target/" + TREE_FILE, "-Doutput=" + str(effective), "-Dverbose=false"], "resolve")
        if resolve["exitCode"]:
            raise Blocked("Maven dependency resolution/effective model failed")
        inventory = resolved_inventory(source, effective)
        result.update(inventory=inventory, tests=test_counts(source))
        write(directory / "resolved.json", inventory)
        write(directory / "bom.cdx.json", sbom(inventory["packages"]))
        config = directory / "osv-scanner.toml"
        config.write_text("# Trusted validator: no vulnerability ignore entries.\n")
        version = run([tool["osv"], "--version"], "scanner-version")
        if version["exitCode"] or not re.search(r"osv-scanner version: 2\.6\.0\b", version["stdout"]):
            raise Blocked("OSV 2.6.0 required for the verified CLI contract")
        scan = run([tool["osv"], "scan", "source", "--sbom=" + str(directory / "bom.cdx.json"),
                    "--format=json", "--all-packages", "--all-vulns", "--config=" + str(config)], "scan")
        normalized = scan_result(json.loads(scan["stdout"]), inventory["packages"], scan["exitCode"], scan["stderr"])
        result.update(normalized)
        checks = tool["checks"] + [item["check"] for item in task["constraints"]]
        for index, argv in enumerate(checks):
            if run(argv, "acceptance-check-" + str(index))["exitCode"]:
                result["outcome"] = "FAIL"
                raise Blocked("Additional acceptance check failed")
        result["outcome"] = "COMPLETE"
    except (Blocked, OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        result["reasons"].append(str(exc)[:500])
    write(directory / "evaluation.json", result)
    return result


def compare(baseline, candidate, policy):
    if baseline.get("outcome") != "COMPLETE" or candidate.get("outcome") != "COMPLETE":
        return dict(outcome="FAIL" if candidate.get("outcome") == "FAIL" else "INCONCLUSIVE",
                    reasons=candidate.get("reasons") or ["Baseline/candidate evidence incomplete"])
    for evidence in (baseline, candidate):
        coverage = evidence.get("coverage", {})
        count = len({(p["name"], p["version"]) for p in evidence["inventory"]["packages"]})
        if (coverage.get("complete") is not True or count == 0
                or coverage.get("expected") != count or coverage.get("scanned") != count):
            return dict(outcome="INCONCLUSIVE", reasons=["Resolved dependency/scanner coverage is incomplete"])
    reasons, unknown = [], []
    before, after = baseline["inventory"], candidate["inventory"]
    if before["modules"] != after["modules"]:
        unknown.append("Reactor module coverage changed")
    versions = lambda inventory: {p["name"]: set(q["version"] for q in inventory["packages"]
        if p["name"] == q["name"]) for p in inventory["packages"]}
    old, new = versions(before), versions(after)
    missing = set(old) - set(new) - set(policy["allowed_removed_dependencies"])
    if missing:
        unknown.append("Dependencies disappeared without approval: " + ", ".join(sorted(missing)))
    for coordinate in set(old) & set(new):
        if old[coordinate] == new[coordinate]:
            continue
        def release(value):
            if not re.fullmatch(r"\d+(\.\d+)*", value):
                raise ValueError(value)
            return tuple(int(x) for x in value.split(".")) + (0,) * (8 - len(value.split(".")))
        try:
            old_versions, new_versions = [release(v) for v in old[coordinate]], [release(v) for v in new[coordinate]]
            if not policy["allow_major_upgrades"] and max(v[0] for v in new_versions) > max(v[0] for v in old_versions):
                reasons.append("Major upgrade not authorized: " + coordinate)
            if not policy["allow_downgrades"] and min(new_versions) < min(old_versions):
                reasons.append("Downgrade not authorized: " + coordinate)
        except ValueError:
            unknown.append("Non-release version policy requires explicit adapter: " + coordinate)
    for module in set(before["properties"]) & set(after["properties"]):
        for key in policy["protected_properties"]:
            if before["properties"][module].get(key) != after["properties"][module].get(key):
                reasons.append("Protected effective property changed: " + module + ":" + key)
    if candidate["tests"] < max(baseline["tests"], policy["minimum_tests"]):
        reasons.append("Executed test coverage regressed or is below the acceptance minimum")
    remaining, introduced = candidate["findings"], []
    for finding in remaining:
        if not any(finding["package"] == prior["package"] and set(finding["ids"]) & set(prior["ids"])
                   for prior in baseline["findings"]):
            introduced.append(finding)
    if introduced:
        reasons.append("New vulnerabilities introduced")
    if len(remaining) > policy["max_remaining_findings"]:
        reasons.append("Remaining vulnerabilities exceed acceptance policy")
    if any(set(f["ids"]) & set(policy["target_ids"]) for f in remaining):
        reasons.append("Requested vulnerability identifiers remain")
    return dict(outcome="FAIL" if reasons else "INCONCLUSIVE" if unknown else "PASS",
                reasons=reasons + unknown, remaining=remaining, introduced=introduced,
                baselineDigest=digest(baseline), candidateDigest=digest(candidate))
