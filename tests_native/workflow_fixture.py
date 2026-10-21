"""TEST ONLY process boundaries for the connected SDK workflow test.

No network/model/GitHub calls. Never used by production entry points. Maven/OSV
responses are authored fixtures; the real evaluator still exports/parses/checks
the candidate, and the real Stop workflow still owns acceptance.
"""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from native_remediation import runtime, validation
from native_remediation.files import write


def runner(argv, source, timeout, output):
    assert timeout > 0
    version = ET.parse(source / "pom.xml").findtext("properties/library.version")
    result = dict(exitCode=0, timedOut=False, seconds=0, stdout="", stderr="")
    target = source / "target"
    target.mkdir(exist_ok=True)
    if "clean" in argv or validation.DEPENDENCY_GOAL in argv:
        assert "-Papproved-fixture" in argv, "Approved Maven profile was lost"
    if "clean" in argv:
        reports = target / "surefire-reports"
        reports.mkdir()
        (reports / "TEST-fixture.xml").write_text('<testsuite tests="2" skipped="0" failures="0" errors="0"/>')
    if validation.DEPENDENCY_GOAL in argv:
        write(target / validation.TREE_FILE, dict(groupId="fixture", artifactId="app", version="1",
            children=[dict(groupId="org.example", artifactId="library", version=version, scope="compile")]))
        effective = Path(next(a.split("=", 1)[1] for a in argv if a.startswith("-Doutput=")))
        effective.write_text('<project><groupId>fixture</groupId><artifactId>app</artifactId><version>1</version>'
                             '<properties><java.version>21</java.version></properties></project>')
    if "--version" in argv:
        result["stdout"] = "osv-scanner version: 2.6.0"
    if "scan" in argv:
        vulnerabilities = [dict(id="GHSA-fixture", aliases=["CVE-fixture"])] if version == "1.0.0" else []
        result.update(exitCode=int(bool(vulnerabilities)), stdout=json.dumps(dict(results=[dict(packages=[dict(
            package=dict(name="org.example:library", version=version, ecosystem="Maven"),
            vulnerabilities=vulnerabilities)])])))
    write(output, result)
    return result


def evaluator(*args, **kwargs):
    return validation.evaluate(*args, **kwargs, runner=runner)


def main():
    mode = sys.argv[1]
    if mode == "hook":
        # Real native command-hook subprocess and product Stop orchestration;
        # only deterministic command outputs are replaced with fixtures.
        with patch("native_remediation.delivery.GitHub", side_effect=AssertionError("No remote delivery in fixture")) as remote:
            result = runtime.hook(Path(sys.argv[2]), json.load(sys.stdin), evaluator=evaluator)
            remote.assert_not_called()
        print(json.dumps(result))
        return 2 if result["decision"] == "deny" else 0
    if mode == "sbri-failure":
        print("sbri fixture: approved profile repository unavailable", file=sys.stderr)
        return 2
    argv = sys.argv[2:]
    def value(flag):
        return argv[argv.index(flag) + 1]
    write(Path(value("--output")) / "result.json", dict(schema_version="1.0", status="SUCCESS", errors=[],
        execution=dict(profiles=value("--profiles").split(","), scopes=value("--scopes").split(","),
            release_selection=dict(resolved_candidates=value("--releases").split(","))),
        releases=[dict(version=v, assessment_status="COMPLETE") for v in ["4.0.6", *value("--releases").split(",")]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
