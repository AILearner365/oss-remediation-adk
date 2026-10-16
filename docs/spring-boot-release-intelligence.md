# Spring Boot Release Intelligence CLI

`sbri` evaluates actual Maven-selected dependency inventories with the selected
S4 pipeline: A5 TGF → CycloneDX 1.5 → security scanner → comparison.

Prerequisites: Python 3.11+, Java, Maven, and OSV Scanner 2.x on `PATH`.

```bash
./sbri evaluate --project ./application --range 3.3.4..3.3.8
./sbri evaluate --project ./application --releases 3.3.5,3.3.7,3.3.8 \
  --profiles production --modules service --output build/sbri
```

Outputs are `result.json`, `report.html`, and referenced files under
`evidence/`. Exit 0 means all requested releases were assessed, 3 means a
machine-readable partial result was produced, and 2 means configuration or
baseline execution prevented a usable result. Scanner exit 1 means findings,
not failure.

Optional JSON configuration keys are `maven`, `settings`, `profiles`, `modules`,
`scopes`, `scanner`, `severities`, and `timeout`. CLI values take precedence. A CI job or
autonomous agent should consume `result.json`; HTML is rendered only from that
same representation. The schema is
`spring_boot_release_intelligence/result-schema-v1.json`.

## External integration contract

SBRI is a local command-line tool. Consumers do not need to import or understand
its Python modules.

Required inputs:

- `--project PATH`: the Maven reactor or project root containing `pom.xml`.
- Exactly one of `--range LOWER..UPPER` or `--releases V1,V2`: candidate Spring
  Boot releases. The discovered baseline is always assessed independently and
  should not be repeated merely to make it appear as a candidate.

Optional inputs:

- `--output PATH` (default `output`) for all canonical and retained artifacts.
- `--maven COMMAND` and `--settings PATH` for the Maven executable and settings.
- `--profiles CSV`, `--modules CSV`, and `--scopes CSV` for Maven profile,
  reactor-module, and dependency-scope selection.
- `--severities CSV` for the displayed and ranked severity set. The supported
  names are `CRITICAL,HIGH,MEDIUM,LOW,UNKNOWN`.
- `--scanner COMMAND` to select the trusted scanner executable.
- Repeated `--scanner-report VERSION=PATH` inputs to ingest supplied CycloneDX
  1.5 vulnerability reports instead of invoking the default scanner. Supply a
  report for the baseline and every candidate being assessed.
- `--timeout SECONDS` for each Maven/scanner command.
- `--config PATH` for JSON defaults. Supported keys are `maven`, `settings`,
  `profiles`, `modules`, `scopes`, `scanner`, `severities`, and `timeout`.

Project path, release selection, scanner-report paths and output directory are
CLI parameters, not configuration-file keys. A small configuration is:

```json
{
  "profiles": ["production"],
  "modules": ["service", "web"],
  "scopes": ["compile", "runtime"],
  "severities": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"],
  "timeout": 600
}
```

It can be reused without editing SBRI:

```bash
./sbri evaluate --project "$APP_WORKSPACE" --releases 4.0.7,4.0.8 \
  --config ./sbri-config.json --output "$ARTIFACT_DIR"
```

### Outputs and consumption

The output boundary is:

- `result.json`: authoritative result conforming to
  `spring_boot_release_intelligence/result-schema-v1.json`.
- `report.html`: portable presentation generated only from that JSON. Its
  filters and sorting never recalculate findings, rankings, or totals.
- `evidence/`: referenced Maven graphs, CycloneDX inventories, scanner reports,
  and error logs. References in newly generated JSON are output-relative when
  the evidence is retained under the output directory.

An external consumer can read the important fields without relying on report
markup:

```python
import json
from pathlib import Path

result = json.loads(Path("build/sbri/result.json").read_text())
baseline = result["application"]["original_spring_boot_version"]
candidates = [r for r in result["releases"] if r["version"] != baseline]
complete = [r for r in candidates if r["assessment_status"] == "COMPLETE"]
preferred_security_result = min(complete, key=lambda r: r["rank"])
critical_high_remaining = sum(
    preferred_security_result["counts"]["remaining"][severity]
    for severity in ("CRITICAL", "HIGH")
)
new_findings = preferred_security_result["counts"]["new"]
selected_dependencies = [
    {"coordinate": d["coordinate"], "version": d["selected_version"],
     "ownership": d["ownership"], "paths": d["paths"]}
    for d in result["dependencies"]
    if d["release"] == preferred_security_result["version"]
]
advisory_evidence = [
    {"id": f["advisory_id"], "package": f["package"],
     "severity": f["severity"], "fixed": f["fixed_versions"],
     "evidence": f["evidence_reference"]}
    for f in result["findings"]
    if f["release"] == preferred_security_result["version"]
]
assert result["status"] in {"SUCCESS", "PARTIAL", "FAILURE"}
errors = result["errors"]
```

Consumers must inspect `status`, each release's `assessment_status`, and
`errors`; absent or failed scanner evidence is never equivalent to zero
findings.

### Exit codes

- `0`: every requested assessment completed and usable canonical outputs were
  produced.
- `3`: usable baseline/candidate results were retained, but at least one
  requested assessment was incomplete. Read `errors` and the per-release
  status before using the result.
- `2`: invalid configuration or baseline failure prevented a usable result.

OSV Scanner exit `1` means findings were detected and is accepted as a
successful scanner execution when its report exists. Other scanner exit codes,
a timeout, or a missing report are execution failures and become structured
release errors. Deterministic contract tests cover complete, partial and
baseline-failure CLI outcomes.

### Responsibility boundary

SBRI owns Maven resolution, independent Boot candidate materialization,
scanner execution or report ingestion, vulnerability comparison, ownership
evidence, security-only ranking, and canonical artifacts. A consuming agent or
CI workflow owns the remediation objective, compatibility and functional risk,
strategy selection, source edits, builds/tests, independent post-change
validation, and the final decision that remediation is complete. Rank 1 is
security evidence, not an instruction to upgrade.

An OpenHands-style flow therefore remains generic:

1. The task requests release intelligence for an isolated application clone.
2. The harness invokes `sbri evaluate` and records the exit code plus artifact
   directory.
3. The agent reads `result.json`, including incomplete assessments and errors.
4. It compares remaining findings, ownership, selected versions, paths and
   advisory evidence while considering non-security constraints separately.
5. It chooses and implements a strategy outside SBRI.
6. Deterministic build, test, scanner and dependency checks independently
   validate the implemented change.

No OpenHands-specific adapter or lifecycle hook is required by this contract.

For a trusted external scanner, supply one CycloneDX 1.5 vulnerability report
per release:

```bash
./sbri evaluate --project . --releases 3.3.8 \
  --scanner-report 3.3.4=base.cdx.json \
  --scanner-report 3.3.8=candidate.cdx.json
```

The reader correlates `vulnerabilities[].affects[].ref` with SBOM component
references and retains identities, aliases, severity and fixed evidence when
present. This demonstrates standards interchange, not a validated JFrog/Xray
integration.

Known limitations: security ranking does not establish compatibility; private
repository policy, very large reactors, corporate-parent ownership and every
WAR/provided-scope combination remain unverified. Missing fixed evidence stays
unknown. The utility never removes overrides or edits the source project.

The retained implementation validation is at
`docs/experiments/spring-boot-release-intelligence/implementation-evidence/run-20261016/`.
Its current OSV snapshot reported 80 baseline findings versus A7's historical
81 because one Medium finding was absent from the later advisory response; the
historical evidence was not rewritten.
