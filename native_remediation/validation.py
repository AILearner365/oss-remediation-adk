"""Shared independent Maven/policy validation and scanner-neutral comparison."""
import json
import re
import time
import xml.etree.ElementTree as ET

from .files import Blocked, command, digest, write, require_independent_authority
from .repository import export
from .scanners import ScanRequest, scanner, complete_coverage, sbom, normalize_osv as scan_result

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
    java = {}
    for project in projects:
        coordinate = project.findtext("groupId") + ":" + project.findtext("artifactId")
        configuration = {}
        for plugin in project.findall("build/plugins/plugin"):
            if plugin.findtext("artifactId") == "maven-compiler-plugin":
                configuration.update({k: plugin.findtext("configuration/" + k)
                                      for k in ("source", "target", "release")})
        java[coordinate] = configuration
    from .capabilities import discover_boot
    return dict(modules=sorted(properties), properties=properties,
                packages=[dict(name=n, version=v) for n, v in sorted(packages)], graphs=graphs,
                spring_boot=discover_boot(source), java_configuration=java)


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


def module_versions(inventory):
    """Recover ownership from existing resolved graphs, never pair version sets.

    Older records without graphs have no module ownership evidence.
    """
    graphs = inventory.get("graphs")
    if not graphs:
        return None
    roots = [row["graph"] for row in graphs]
    identity = lambda node: tuple(node[k] for k in ("groupId", "artifactId", "version"))
    reactor = {identity(root) for root in roots}
    modules = {}
    for root in roots:
        module = root["groupId"] + ":" + root["artifactId"]
        if module in modules:
            raise ValueError("Duplicate reactor module")
        packages = modules[module] = {}
        def walk(node):
            coordinates = identity(node)
            if any(not isinstance(v, str) or not v or "${" in v for v in coordinates):
                raise ValueError("Unresolved graph identity")
            if coordinates not in reactor:
                packages.setdefault(coordinates[0] + ":" + coordinates[1], set()).add(coordinates[2])
            for child in node.get("children", []):
                walk(child)
        walk(root)
    if set(modules) != set(inventory["modules"]):
        raise ValueError("Incomplete module ownership evidence")
    actual = {(name, version) for packages in modules.values() for name, versions in packages.items()
              for version in versions}
    if actual != {(p["name"], p["version"]) for p in inventory["packages"]}:
        raise ValueError("Graph/package inventory disagreement")
    return modules


def require_baseline(baseline, tree, task):
    """COMPLETE includes resolution, all configured checks and exact coverage."""
    try:
        inventory, coverage = baseline["inventory"], baseline["coverage"]
        packages = {(p["name"], p["version"]) for p in inventory["packages"]}
        valid = (baseline["outcome"] == "COMPLETE" and baseline["tree"] == tree
            and not baseline.get("reasons") and bool(packages)
            and ('scanner' not in baseline or baseline['scanner'] == task['scanner'])
            and complete_coverage(baseline)
            and type(baseline["tests"]) is int and baseline["tests"] >= task["policy"]["minimum_tests"]
            and isinstance(baseline["findings"], list)
            and all(isinstance(f, dict) and (f.get('package'), f.get('version')) in packages
                and isinstance(f.get('ids'), list) and f['ids']
                and all(isinstance(v, str) and v for v in f['ids']) for f in baseline['findings'])
            and set(inventory["properties"]) == set(inventory["modules"])
            and bool(module_versions(inventory)))
    except (KeyError, TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise Blocked("Baseline incomplete/invalid: require build, tests, checks, reactor graphs and complete scanner coverage")


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
        if result["tests"] < task["policy"]["minimum_tests"]:
            result["outcome"] = "FAIL"
            raise Blocked("Executed tests below the configured minimum")
        write(directory / "resolved.json", inventory)
        result['scanner'] = dict(task['scanner'])
        try:
            normalized = scanner(task['scanner']).scan(ScanRequest(inventory['packages'], source,
                directory, task['scanner'], tool, run))
            from .scanners import validate_result
            validate_result(normalized, inventory['packages'])
            result.update(normalized)
            write(directory / 'scanner-result.json', normalized)
            if normalized.get('status') != 'COMPLETE' or not complete_coverage(result):
                result['reasons'].append('Scanner completion/coverage is incomplete')
        except (Blocked, OSError, ValueError, KeyError, TypeError) as exc:
            result['status'] = 'FAILED'
            result['reasons'].append(str(exc)[:500])
        checks = tool["checks"] + [item["check"] for item in task["constraints"]]
        for index, argv in enumerate(checks):
            if run(argv, "acceptance-check-" + str(index))["exitCode"]:
                result["outcome"] = "FAIL"
                raise Blocked("Additional acceptance check failed")
        result["outcome"] = "COMPLETE" if not result['reasons'] else 'INCONCLUSIVE'
    except (Blocked, OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        result["reasons"].append(str(exc)[:500])
    write(directory / "evaluation.json", result)
    return result


def policy_checks(baseline, candidate, policy):
    reasons, unknown = [], []
    checks = {}
    def mark(name, previous):
        checks[name] = 'FAIL' if len(reasons) > previous[0] else 'INCONCLUSIVE' if len(unknown) > previous[1] else 'PASS'
    checkpoint = (0, 0)
    before, after = baseline["inventory"], candidate["inventory"]
    java_keys = ("java.version", "maven.compiler.release", "maven.compiler.source", "maven.compiler.target")
    old_java = {m: {k: p.get(k) for k in java_keys} for m, p in before["properties"].items()}
    new_java = {m: {k: p.get(k) for k in java_keys} for m, p in after["properties"].items()}
    java_policy = policy.get("java", {"allow_change": False, "allowed_versions": []})
    if not java_policy["allow_change"] and (old_java != new_java
            or before.get("java_configuration") != after.get("java_configuration")):
        reasons.append("Java language/compiler configuration change not authorized")
    allowed_java = java_policy["allowed_versions"]
    java_values = [v for p in new_java.values() for v in p.values() if v]
    java_values += [v for p in after.get("java_configuration", {}).values() for v in p.values() if v]
    if allowed_java and any(v not in allowed_java for v in java_values):
        reasons.append("Java version outside the approved set")
    mark('javaPolicy', checkpoint)
    checkpoint = (len(reasons), len(unknown))
    if before["modules"] != after["modules"]:
        unknown.append("Reactor module coverage changed")
    versions = lambda inventory: {p["name"]: set(q["version"] for q in inventory["packages"]
        if p["name"] == q["name"]) for p in inventory["packages"]}
    old, new = versions(before), versions(after)
    boot_policy = policy.get("spring_boot", dict(patch=True, minor=True, major=False, downgrade=False))
    boot_pairs = [(before.get("spring_boot"), after.get("spring_boot"))]
    try:
        old_modules, new_modules = module_versions(before), module_versions(after)
    except (ValueError, KeyError, TypeError, AttributeError):
        old_modules = new_modules = None
        unknown.append("Spring Boot module ownership evidence is invalid")
    groups = [(old, new, "aggregate (module ownership unavailable)")]
    if old_modules is not None and new_modules is not None:
        groups = [(old_modules[m], new_modules[m], m) for m in set(old_modules) & set(new_modules)]
    for previous, current, owner in groups:
        for coordinate in set(previous) | set(current):
            a, b = previous.get(coordinate, set()), current.get(coordinate, set())
            if not coordinate.startswith("org.springframework.boot:") or a == b:
                continue
            if len(a) == len(b) == 1:
                boot_pairs.append((next(iter(a)), next(iter(b))))
            else:
                unknown.append("Ambiguous Spring Boot version movement: " + owner + ":" + coordinate)
                if (a and b and not boot_policy["downgrade"] and all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in a | b)
                        and min(tuple(map(int, v.split("."))) for v in b)
                        < min(tuple(map(int, v.split("."))) for v in a)):
                    reasons.append("Spring Boot downgrade movement not authorized")
    for previous, current in boot_pairs:
        if previous == current:
            continue
        if not previous or not current or not re.fullmatch(r"\d+\.\d+\.\d+", previous) or not re.fullmatch(r"\d+\.\d+\.\d+", current):
            unknown.append("Spring Boot controller/release movement needs verified evidence")
            continue
        a, b = tuple(map(int, previous.split("."))), tuple(map(int, current.split(".")))
        movement = "downgrade" if b < a else "major" if b[0] != a[0] else "minor" if b[1] != a[1] else "patch"
        if not boot_policy[movement]:
            reasons.append("Spring Boot " + movement + " movement not authorized")
    mark('springBootPolicy', checkpoint)
    checkpoint = (len(reasons), len(unknown))
    missing = set(old) - set(new) - set(policy["allowed_removed_dependencies"])
    if missing:
        unknown.append("Dependencies disappeared without approval: " + ", ".join(sorted(missing)))
    for coordinate in set(old) & set(new):
        if coordinate.startswith("org.springframework.boot:"):
            continue  # Category-specific policy; other transitive families retain generic constraints.
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
    mark('dependencyPolicy', checkpoint)
    checkpoint = (len(reasons), len(unknown))
    if candidate["tests"] < max(baseline["tests"], policy["minimum_tests"]):
        reasons.append("Executed test coverage regressed or is below the acceptance minimum")
    mark('tests', checkpoint)
    return reasons, unknown, checks


def dependency_paths(inventory, coordinate, versions):
    paths = []
    def walk(node, path):
        name = node['groupId'] + ':' + node['artifactId']
        path = path + [name + '@' + node['version']]
        if name == coordinate and node['version'] in versions:
            paths.append(path)
        for child in node.get('children', []):
            walk(child, path)
    for graph in inventory.get('graphs', []):
        walk(graph['graph'], [])
    return [list(p) for p in sorted({tuple(p) for p in paths})]


def finding_comparison(baseline, candidate, comparable):
    """Transitive alias union, per component; versions are evidence, not identity."""
    groups, invalid = [], []
    for side, evaluation in (('baseline', baseline), ('candidate', candidate)):
        inventory = {(p['name'], p['version']) for p in evaluation.get('inventory', {}).get('packages', [])}
        for finding in evaluation.get('findings', []):
            if (not finding.get('ids') or (finding.get('package'), finding.get('version')) not in inventory):
                invalid.append(dict(finding, reason='Unproven affected-component/advisory identity',
                    baselineFindings=[finding] if side == 'baseline' else [],
                    candidateFindings=[finding] if side == 'candidate' else []))
                continue
            group = dict(package=finding['package'], ids=set(finding['ids']), baseline=[], candidate=[])
            group[side].append(finding)
            changed = True
            while changed:
                changed = False
                for prior in list(groups):
                    if prior['package'] == group['package'] and prior['ids'] & group['ids']:
                        group['ids'].update(prior['ids'])
                        for key in ('baseline', 'candidate'):
                            group[key].extend(prior[key])
                        groups.remove(prior)
                        changed = True
            groups.append(group)
    result = dict(resolved=[], remaining=[], introduced=[], unknown=invalid)
    for group in sorted(groups, key=lambda g: (g['package'], sorted(g['ids']))):
        old, new = group['baseline'], group['candidate']
        row = dict(package=group['package'], ids=sorted(group['ids']),
            baselineVersions=sorted({f['version'] for f in old}), candidateVersions=sorted({f['version'] for f in new}),
            baselineFindings=old, candidateFindings=new)
        for side, evaluation in (('baseline', baseline), ('candidate', candidate)):
            row[side + 'DependencyVersions'] = sorted({p['version'] for p in evaluation.get('inventory', {}).get('packages', []) if p['name'] == group['package']})
        row['dependencyPaths'] = {side: dependency_paths(evaluation.get('inventory', {}), group['package'], row[side + 'DependencyVersions'])
            for side, evaluation in (('baseline', baseline), ('candidate', candidate))}
        category = 'remaining' if old and new else 'resolved' if old else 'introduced'
        presence_proven = (baseline.get('outcome') == 'COMPLETE' and complete_coverage(baseline)
            and baseline.get('scanner') == candidate.get('scanner')
            and isinstance(candidate.get('findings'), list))
        if not comparable and not (new and presence_proven):
            category = 'unknown'
            row['reason'] = 'Scanner configuration/completion/coverage is not comparable'
        result[category].append(row)
    return result


def compare(baseline, candidate, policy):
    """One acceptance report for all adapters, including incomplete evaluations."""
    comparable = (baseline.get('outcome') == 'COMPLETE'
        and complete_coverage(baseline) and complete_coverage(candidate)
        and baseline.get('scanner') == candidate.get('scanner')
        and isinstance(baseline.get('findings'), list) and isinstance(candidate.get('findings'), list))
    vulnerabilities = finding_comparison(baseline, candidate, comparable)
    checks = dict(build='INCONCLUSIVE', tests='INCONCLUSIVE', scanCoverage='PASS' if comparable else 'INCONCLUSIVE',
        remediation='INCONCLUSIVE', newVulnerabilities='INCONCLUSIVE', springBootPolicy='INCONCLUSIVE',
        javaPolicy='INCONCLUSIVE', dependencyPolicy='INCONCLUSIVE', evidenceIntegrity='PASS', taskChecks='INCONCLUSIVE')
    reasons, unknown = [], []
    if candidate.get('outcome') == 'FAIL':
        reasons.extend(candidate.get('reasons') or ['Candidate mandatory check failed'])
    elif candidate.get('outcome') != 'COMPLETE':
        unknown.extend(candidate.get('reasons') or ['Baseline/candidate evidence incomplete'])
    if candidate.get('outcome') == 'COMPLETE' and candidate.get('reasons'):
        unknown.extend(candidate['reasons'])
    if not comparable:
        unknown.append('Resolved dependency/scanner coverage is incomplete')
    if baseline.get('scanner') != candidate.get('scanner'):
        checks['evidenceIntegrity'] = 'INCONCLUSIVE'
        unknown.append('Scanner implementation/configuration differs from the baseline')
    for record in candidate.get('commands', []):
        name = record.get('name', '')
        if name == 'build':
            checks['build'] = 'INCONCLUSIVE' if record.get('timedOut') else 'FAIL' if record.get('exitCode') else 'PASS'
        if name.startswith('acceptance-check-') and record.get('exitCode'):
            checks['taskChecks'] = 'FAIL' if not record.get('timedOut') else 'INCONCLUSIVE'
    if candidate.get('outcome') == 'COMPLETE':
        checks['build'] = checks['tests'] = checks['taskChecks'] = 'PASS'
    if baseline.get('inventory') and candidate.get('inventory') and 'tests' in candidate:
        try:
            failures, missing, policies = policy_checks(baseline, candidate, policy)
            reasons.extend(failures)
            unknown.extend(missing)
            checks.update(policies)
        except (Blocked, ValueError, KeyError, TypeError, AttributeError):
            unknown.append('Invalid Maven ownership/policy evidence')
            checks['evidenceIntegrity'] = 'INCONCLUSIVE'
    current = vulnerabilities['remaining'] + vulnerabilities['introduced']
    if comparable:
        checks['remediation'] = checks['newVulnerabilities'] = 'PASS'
    if vulnerabilities['introduced']:
        reasons.append('New vulnerabilities introduced')
        checks['newVulnerabilities'] = 'FAIL'
    if len(current) > policy['max_remaining_findings']:
        reasons.append('Remaining vulnerabilities exceed acceptance policy')
        checks['remediation'] = 'FAIL'
    if any(set(f['ids']) & set(policy['target_ids']) for f in current):
        reasons.append('Requested vulnerability identifiers remain')
        checks['remediation'] = 'FAIL'
    if vulnerabilities['unknown']:
        unknown.append('Some vulnerability identities/statuses are unknown')
        if checks['remediation'] == 'PASS':
            checks['remediation'] = 'INCONCLUSIVE'
    if any(v == 'FAIL' for v in checks.values()) and not reasons:
        reasons.append('Mandatory check failed')
    if any(v == 'INCONCLUSIVE' for v in checks.values()) and not unknown:
        unknown.append('Mandatory check evidence incomplete')
    return dict(outcome='FAIL' if reasons else 'INCONCLUSIVE' if unknown else 'PASS',
        scanner=baseline.get('scanner', {'type': 'osv', 'version': 'legacy'}),
        reasons=list(dict.fromkeys(reasons + unknown)), feedback=list(dict.fromkeys(reasons + unknown)),
        checks=checks, summary=dict(baseline=len(vulnerabilities['resolved']) + len(vulnerabilities['remaining'])
            + sum(bool(f.get('baselineFindings')) for f in vulnerabilities['unknown']),
            **{key: len(rows) for key, rows in vulnerabilities.items()}),
        vulnerabilities=vulnerabilities, remaining=vulnerabilities['remaining'], introduced=vulnerabilities['introduced'],
        baselineDigest=digest(baseline), candidateDigest=digest(candidate),
        evidence=dict(baselineTree=baseline.get('tree'), candidateTree=candidate.get('tree')))
