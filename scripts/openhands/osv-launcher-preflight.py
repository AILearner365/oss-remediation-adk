#!/usr/bin/env python3
"""Offline OSV launcher regression (fake scanner, no network/model/build)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts/openhands/openhands-osv-scanner.sh"
REGISTRY = "http://127.0.0.1:9876/maven"


def check(executable: Path, arguments: list[str], expected: list[str], *, registry: bool = True) -> None:
    env = os.environ.copy()
    env.update(OPENHANDS_OSV_EXECUTABLE=str(executable))
    if registry:
        env["OPENHANDS_OSV_MAVEN_REGISTRY"] = REGISTRY
    else:
        env.pop("OPENHANDS_OSV_MAVEN_REGISTRY", None)
    result = subprocess.run(
        ["bash", str(LAUNCHER), *arguments],
        env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, (arguments, result.stderr, result.stdout)
    assert json.loads(result.stdout) == expected, (arguments, result.stdout, expected)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "fake-osv"
        fake.write_text("#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
        fake.chmod(0o700)
        suffix = ["--data-source=native", f"--maven-registry={REGISTRY}"]
        check(fake, ["--format", "json", "-r", "."],
              ["scan", "source", "--format", "json", "-r", ".", *suffix])
        check(fake, ["scan", "source", "-r", ".", "--format", "json"],
              ["scan", "source", "-r", ".", "--format", "json", *suffix])
        check(fake, ["scan", "source", "-r", ".", "--data-source=deps.dev",
                     "--maven-registry=http://untrusted", "--format", "json"],
              ["scan", "source", "-r", ".", "--format", "json", *suffix])
        check(fake, ["scan", "source", "-r", ".", "--data-source", "deps.dev",
                     "--maven-registry", "http://untrusted"],
              ["scan", "source", "-r", ".", *suffix])
        check(fake, ["--help"], ["--help"], registry=False)
        check(fake, ["--version"], ["--version"], registry=False)
        check(fake, ["scan", "sbom", "-L", "bom.json"],
              ["scan", "sbom", "-L", "bom.json"], registry=False)
        check(fake, ["--sbom", "bom.json", "-r", "."],
              ["--sbom", "bom.json", "-r", "."], registry=False)
        env = os.environ.copy()
        env["OPENHANDS_OSV_EXECUTABLE"] = str(fake)
        env.pop("OPENHANDS_OSV_MAVEN_REGISTRY", None)
        for arguments in [["--format", "json", "-r", "."], ["scan", "source", "-r", "."]]:
            result = subprocess.run(
                ["bash", str(LAUNCHER), *arguments],
                env=env, capture_output=True, text=True, check=False,
            )
            assert result.returncode == 2, (arguments, result)
            assert "INCOMPLETE_SCAN" in result.stderr, (arguments, result.stderr)
    print("OSV_LAUNCHER_PREFLIGHT=PASS")
    print("legacy_and_modern_source_scans_maven_registry=True; model_api_calls=0; scanner_network_calls=0")


if __name__ == "__main__":
    main()
