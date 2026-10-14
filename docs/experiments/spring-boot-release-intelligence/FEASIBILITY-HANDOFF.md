# Spring Boot Release Intelligence feasibility handoff

## Phase status

The A1–A6 feasibility phase is closed at commit
`16672586e722d1d0a8b045f8618d88f6a5a77de2`.

- **Decision:** retain A5 as the preferred release-intelligence dependency
  collector.
- **Decision:** retain ordinary Maven build/test execution, represented by the
  broader A2 role, for compatibility validation of shortlisted candidates.
- **Decision:** keep A1's BOM intelligence and conservative OSV interpretation
  as supporting evidence; deps.dev remains optional corroboration.
- **Not decided:** the placement, contracts, integration architecture, or
  end-to-end design of any next-phase utility.

This document preserves the experimental conclusion. It is not a production
design or authorization to integrate with autonomous remediation.

## Evidence language

The following labels distinguish the strength and purpose of statements:

- **Measured fact:** produced by an executed command and preserved evidence.
- **Decision:** the conclusion chosen from the measured results and stated
  constraints.
- **Assumption:** a condition used by the bounded experiment that still needs
  validation in a broader environment.
- **Unresolved:** deliberately unanswered or unsupported by this phase.

Feasibility cells use `PROVEN`, `PARTIALLY_PROVEN`, `NOT_SUPPORTED`, `FAILED`,
and `NOT_TESTED`. Those statuses describe only the executed cases and must not
be interpreted as production-readiness claims.

## 1. Original objective and scope

The objective was to determine whether credible Spring Boot release candidates
can be compared against original Maven vulnerability findings using evidence
about:

- published Spring Boot releases and managed dependency versions;
- the application's effective selected dependencies and, where available,
  their introduction paths;
- conservative OSV advisory interpretation, including incomplete and
  contradictory evidence;
- application overrides, mediation, profiles, exclusions, and multi-module
  resolution; and
- the storage, network, and runtime costs of candidate evaluation.

The experiment evaluated Boot 3.3.4 with candidates 3.3.5–3.3.8, the original
C1–C4 cases, seven expanded Maven scenarios, and a frozen multi-dependency OSV
comparison. It did not build a production resolver, scanner, recommendation
engine, compatibility service, or autonomous remediation integration.

## 2. Approaches and evaluated results

| Approach | Evaluated role | C1–C4 result | Expanded application scenarios | Phase disposition |
| --- | --- | --- | --- | --- |
| A1 — Boot BOM + OSV | Managed defaults, provenance, advisory applicability | C1/C3 `PROVEN`; C2/C4 `NOT_SUPPORTED` | `NOT_SUPPORTED` | Retain as narrow supporting intelligence |
| A2 — Maven resolution + OSV | Application-effective versions and paths; normal Maven behavior | 4/4 `PROVEN` | 7/7 `PROVEN` | Retain broader build/test role; do not use as the preferred lightweight collector |
| A3 — deps.dev | Hosted metadata/graph corroboration | C1–C3 `PARTIALLY_PROVEN`; C4 `NOT_SUPPORTED` | `NOT_SUPPORTED` | Optional corroboration only |
| A4 — combined | Maven authority plus BOM/OSV and hosted corroboration | 4/4 `PROVEN` | 7/7 `PROVEN` through Maven component | Preserve evidence model; no separate runtime framework needed |
| A5 — pinned `dependency:tree` TGF | Isolated metadata-only effective graph with selected versions and paths | 4/4 `PROVEN` | 7/7 `PROVEN` | **Preferred collector** |
| A6 — pinned `dependency:collect` | Isolated flat effective selected-artifact set | 4/4 `PROVEN` | 7/7 `PROVEN` for selection, not paths | Valid narrow alternative; not preferred |

**Measured fact:** A5 matched the isolated A2 reference on 32/32 selected-version
and path checks. A6 matched A5 on 32/32 complete-set/version checks, 16/16
type/classifier/scope/version record checks, and 64/64 frozen vulnerability
result-set checks. The detailed status derivation is in
[evaluation-matrix.md](evaluation-matrix.md).

## 3. Final decision

**Decision:** use A5's pinned Maven-native metadata collector for future bounded
release-intelligence graph construction, subject to the unresolved next-phase
contracts below.

A5 invokes:

```text
org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
```

with TGF output and an explicit disposable `maven.repo.local`. It delegates
model building, mediation, profiles, exclusions, and reactor behavior to Maven;
it does not implement a custom resolver.

**Decision:** A5 replaces only A2's dependency-collection function. It does not
replace normal Maven builds, tests, independent scanning, or compatibility
validation for shortlisted candidates.

## 4. Why A5 was preferred over A2 and A6

### A5 versus A2

**Measured fact:** in the accepted A5 comparison, fresh A2 used 61,247,561
cache bytes while A5 used 21,134,449 bytes, a 65.5% reduction. A2 downloaded
seven application/reactor JARs totaling 4,725,608 bytes; A5 downloaded no
application dependency JARs. A5 was 16.1% faster in that fresh run and 0.4%
slower warm.

**Decision:** prefer A5 for repeated candidate graph collection because it
preserves the required versions and paths with substantially less fresh storage
and without application dependency JAR downloads.

**Boundary:** A2's broader Maven build/test behavior remains necessary when
compatibility, compilation, packaging, tests, or runtime behavior must be
established.

### A5 versus A6

**Measured fact:** in the same A2/A5/A6 workload, A5 took 177.746 seconds fresh
and 150.766 seconds warm; A6 took 176.896 and 151.175 seconds. Both used exactly
21,134,449 cache bytes, 460 POMs, and 50 plugin/bootstrap JARs totaling
14,912,596 bytes. The 0.48% fresh advantage and 0.27% warm disadvantage for A6
were negligible.

**Measured fact:** A6 reproduced the complete selected sets, detailed artifact
records, and vulnerability classifications, but intentionally provided no
dependency paths.

**Decision:** retain A5 because it adds path provenance and mediation diagnostics
at no material measured resource cost. A6 remains credible only when the entire
requirement is flat artifact presence/version comparison and path explanation is
explicitly unnecessary.

## 5. Tests and preserved evidence

**Measured fact:** 29 deterministic tests passed at phase close. They cover
status derivation, OSV interval and qualifier behavior, contradictory evidence,
deps.dev graph traversal, TGF parsing, flat collect parsing, classifier fields,
empty collection handling, isolated repository commands, and storage/transfer
classification.

**Measured fact:** the A5 evidence manifest contains 116 hashed files. The A6
manifest contains 218 hashed files. Both use SHA-256 and were verified before
their commits.

Primary evidence:

- [Strengthened feasibility report](feasibility-report.md)
- [A1–A6 evaluation matrix](evaluation-matrix.md)
- [A5 comparison report](a5-comparison-report.md)
- [A6 comparison report](a6-comparison-report.md)
- [A5 compact metrics](evidence/run-20261014-a5/metrics-summary.json)
- [A5 full results](evidence/run-20261014-a5/results-a5.json)
- [A5 manifest](evidence/run-20261014-a5/manifest.json)
- [A6 compact metrics](evidence/run-20261014-a6/metrics-summary.json)
- [A6 full results](evidence/run-20261014-a6/results-a6.json)
- [A6 manifest](evidence/run-20261014-a6/manifest.json)
- [A5 charts](evidence/run-20261014-a5/a5-charts.html)
- [A6 charts](evidence/run-20261014-a6/a6-charts.html)

Earlier `run-20261013` and `run-20261013-v2` observations remain historical
inputs. The A5/A6 evidence directories are additive; no earlier results were
rewritten by this closure.

## 6. Proven capabilities and untested limitations

### Proven within the bounded fixtures

- **Measured fact:** Maven-selected versions and dependency paths matched the A2
  reference for five Boot versions, four property-override cases, and seven
  expanded scenarios.
- **Measured fact:** transitive mediation, direct overrides,
  `dependencyManagement`, active/inactive profiles, exclusions, and a
  two-module reactor produced their independently expected results.
- **Measured fact:** the application override kept Tomcat at 10.1.30 and
  `STILL_AFFECTED` for every candidate despite newer Boot defaults.
- **Measured fact:** conservative OSV handling covered introduced, fixed,
  last-affected, multiple/reintroduced intervals, explicit versions, common
  Maven qualifiers, missing evidence, and contradictions.
- **Measured fact:** A5 and A6 used isolated disposable repositories and
  downloaded zero application dependency JARs after independent bootstrap
  attribution.
- **Measured fact:** candidate comparisons retained addressed, remaining, new,
  unknown, unchanged, and absent categories rather than ranking by one count.

### Untested or not established

- **Unresolved:** authenticated/private repositories, mirrors, proxies, and
  repository policy interactions.
- **Unresolved:** relocations, optional dependency edge cases, real classified
  application artifacts, complex imported-BOM precedence, and non-file profile
  activation.
- **Unresolved:** Maven-version semantics beyond the deliberately conservative
  implemented subset; production use should rely on Maven's established
  `ComparableVersion` semantics or an equivalent authoritative implementation.
- **Unresolved:** whole-application scanner equivalence, binary/runtime
  compatibility, compilation, packaging, and test behavior after upgrades.
- **Unresolved:** transport-level HTTP request counts, long-running source
  mutation/rate-limit behavior, and performance at materially larger scales.
- **Assumption:** the bounded public Maven Central fixtures are representative
  enough to establish feasibility, not production completeness.
- **Assumption:** frozen v2 advisory evidence is appropriate for controlled
  equivalence comparisons; it is not current vulnerability intelligence.

## 7. Reusable implementation modules

The following experiment modules can inform a later implementation without
being treated as stable public interfaces:

| Module | Reusable experimental capability |
| --- | --- |
| `bom.py` | Spring Boot parent/BOM property and import resolution |
| `maven.py` | Maven TGF parsing and the A2 reference resolver |
| `metadata_maven.py` | Isolated A5/A6 collectors, repository inventory, transfer parsing |
| `maven_scenarios.py` | Shared Maven fixtures and independent scenario expectations |
| `osv.py` | OSV queries, finding identity comparison, conservative advisory verdicts |
| `depsdev.py` | Hosted deps.dev metadata and graph corroboration |
| `http.py` | Bounded evidence-aware HTTP access and caching |
| `validation.py` | Check outcomes and evidence-derived feasibility statuses |
| `experiment.py` | Original A1–A4 orchestration and release comparison inputs |
| `a5_experiment.py` | A2/A5 workloads, accuracy, storage qualification, release comparison |
| `a6_experiment.py` | A2/A5/A6 equivalence, flat-record validation, telemetry qualification |
| `charts.py` | Lightweight charts generated from machine-readable evidence |
| `cli.py` | Experimental reproduction entry points |

**Boundary:** leading-underscore helpers, CLI options, result dictionaries, and
module placement are experimental implementation details, not committed APIs.

## 8. Current implementation boundaries and dependencies

- Python uses the standard library; there is no dedicated package or published
  library contract for this experiment.
- Live execution depends on Java, Apache Maven, Maven Central or equivalent
  repositories, OSV, and—only for A3 corroboration—deps.dev.
- A5/A6 pin Maven Dependency Plugin 3.8.1 and require explicit isolated local
  repositories. The plugin still downloads bootstrap JARs, so the supported
  claim is “no application dependency JARs,” not “JAR-free.”
- The code operates on bounded POM fixtures and frozen scanner/advisory inputs.
  It does not accept a production scanner contract or arbitrary application
  repository as a supported interface.
- Result JSON, evidence pointers, chart HTML/SVG, and Markdown reports are
  experiment artifacts. Their schemas and paths are not stable contracts.
- No code in this package is integrated with the autonomous remediation or
  OpenHands implementation.

## 9. Known technical debt and correctness risks

- A6 reuses private helpers from `a5_experiment.py`; those helpers have no stable
  ownership boundary.
- A5/A6 storage qualification has similar logic that should not be generalized
  until the next-phase contracts and consumers are known.
- A2's reference command and several fixture versions remain experiment-specific;
  only A5/A6 pin the dependency-plugin goal explicitly.
- Some historical A2 TGF outputs use a `.json` filename. Consumers must not infer
  format solely from the extension.
- Advisory status depends on conservative custom Maven version handling. Unknown
  qualifiers correctly return uncertainty, but broader production semantics are
  not implemented.
- Absence is safe only when collection completeness is independently established;
  a partial flat result must never be interpreted as remediation.
- Bootstrap attribution relies on repository inventories plus independent empty
  controls. A new plugin version can change that closure and must be requalified.
- Results contain environment-specific command/evidence paths and large nested
  observations; they are useful evidence, not a compact external API.
- Network byte values are Maven-reported transfer payloads, not transport-level
  accounting. HTTP request counts were unavailable for A5/A6.
- External advisory and repository data can change or disappear; frozen evidence
  improves reproducibility but is not suitable for current production decisions.

## 10. Exact reproduction instructions

Run from the repository root on
`spring-boot-release-intelligence-feasibility`. Always use new output directories
and disposable cache roots; never point these commands at the committed evidence
directories or the user's shared `~/.m2/repository`.

### Deterministic tests

```bash
python3 -m unittest \
  tests.test_spring_boot_release_intelligence \
  tests.test_spring_boot_release_intelligence_contract
```

### A5 controlled reproduction

```bash
A5_OUTPUT="$(mktemp -d /tmp/sbri-a5-output.XXXXXX)"
A5_INITIAL_CACHE="$(mktemp -d /tmp/sbri-a5-initial.XXXXXX)"
A5_QUIET_CACHE="$(mktemp -d /tmp/sbri-a5-quiet.XXXXXX)"
A5_CONTROL_CACHE="$(mktemp -d /tmp/sbri-a5-control.XXXXXX)"

python3 -m spring_boot_release_intelligence.cli run-a5 \
  --output "$A5_OUTPUT" \
  --cache-root "$A5_INITIAL_CACHE" \
  --reference docs/experiments/spring-boot-release-intelligence/evidence/run-20261013-v2/results-v2.json

python3 -m spring_boot_release_intelligence.cli rerun-a5-quiet \
  --results "$A5_OUTPUT/results-a5.json" \
  --output "$A5_OUTPUT" \
  --cache-root "$A5_QUIET_CACHE"

python3 -m spring_boot_release_intelligence.cli qualify-a5-storage \
  --results "$A5_OUTPUT/results-a5.json" \
  --output "$A5_OUTPUT" \
  --cache-root "$A5_CONTROL_CACHE"

python3 -m spring_boot_release_intelligence.cli generate-a5-charts \
  --results "$A5_OUTPUT/results-a5.json" \
  --output "$A5_OUTPUT/charts"
```

### A6 controlled reproduction

```bash
A6_OUTPUT="$(mktemp -d /tmp/sbri-a6-output.XXXXXX)"
A6_CACHE_ROOT="$(mktemp -d /tmp/sbri-a6-main.XXXXXX)"
A6_A5_CONTROL_CACHE="$(mktemp -d /tmp/sbri-a6-a5-control.XXXXXX)"
A6_CONTROL_CACHE="$(mktemp -d /tmp/sbri-a6-control.XXXXXX)"
A6_TELEMETRY_CACHE="$(mktemp -d /tmp/sbri-a6-telemetry.XXXXXX)"

python3 -m spring_boot_release_intelligence.cli run-a6 \
  --output "$A6_OUTPUT" \
  --cache-root "$A6_CACHE_ROOT" \
  --reference docs/experiments/spring-boot-release-intelligence/evidence/run-20261013-v2/results-v2.json

python3 -m spring_boot_release_intelligence.cli qualify-a5-storage \
  --results "$A6_OUTPUT/results-a6.json" \
  --output "$A6_OUTPUT/a5-qualification" \
  --cache-root "$A6_A5_CONTROL_CACHE"

python3 -m spring_boot_release_intelligence.cli qualify-a6-storage \
  --results "$A6_OUTPUT/results-a6.json" \
  --output "$A6_OUTPUT/a6-qualification" \
  --cache-root "$A6_CONTROL_CACHE"

python3 -m spring_boot_release_intelligence.cli capture-a6-telemetry \
  --results "$A6_OUTPUT/results-a6.json" \
  --output "$A6_OUTPUT" \
  --cache-root "$A6_TELEMETRY_CACHE"

python3 -m spring_boot_release_intelligence.cli finalize-a6-evidence \
  --results "$A6_OUTPUT/results-a6.json"

python3 -m spring_boot_release_intelligence.cli generate-a6-charts \
  --results "$A6_OUTPUT/results-a6.json" \
  --output "$A6_OUTPUT/charts"
```

Fresh measurements require empty cache roots. Warm measurements are the second
pass within each runner. Do not compare a newly created cache with a prewarmed
cache. Live timings and remote data can vary; correctness gates must be evaluated
separately from timing.

### Verify committed manifests

```bash
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

for manifest_path in sorted(Path(
        "docs/experiments/spring-boot-release-intelligence/evidence"
        ).glob("run-20261014-a*/manifest.json")):
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    for item in manifest["files"]:
        path = root / item["path"]
        assert path.stat().st_size == item["bytes"], path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], path
    assert len(manifest["files"]) == manifest["file_count"]
    print(manifest_path, "verified", manifest["file_count"])
PY
```

Additional commands and prerequisites are retained in
[live-test-cases.md](live-test-cases.md).

## 11. Decisions deferred to the next phase

These decisions were deliberately not made during feasibility:

1. **Utility placement and consumers — unresolved.** Decide whether this belongs
   in a library, service, command, workflow component, or another boundary only
   after identifying real consumers and lifecycle ownership.
2. **Input contract and scanner adapters — unresolved.** Define application,
   eligible-release, and finding inputs; then decide how OSV, JFrog Xray, or
   other scanners map into that contract without conflating advisory identities.
3. **Output schema and status/error conventions — unresolved.** Stabilize
   versioned result schemas, provenance, uncertainty, partial failure, retry,
   absence, and application-control semantics before exposing an API.
4. **Report templates and customization — unresolved.** Determine which human
   and machine reports consumers require before standardizing Markdown, HTML,
   chart, or evidence-bundle templates.
5. **Configuration and extension mechanisms — unresolved.** Repository policy,
   credentials, mirrors, timeouts, caching, eligible release rules, advisory
   sources, and plugin versions need explicit ownership and security review.
6. **Integration with autonomous remediation — unresolved.** No integration
   contract, tool surface, prompt behavior, or decision authority was designed
   or approved in this phase.
7. **End-to-end acceptance requirements — unresolved.** Define acceptance across
   real repositories, private dependency infrastructure, candidate builds/tests,
   independent rescanning, compatibility/regression evidence, failure recovery,
   performance, auditability, and human approval before production work begins.

The next phase should begin with those decisions and acceptance criteria, not by
promoting the experiment's internal dictionaries or CLI into a premature API.
