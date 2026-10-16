# Real multi-module SBRI acceptance notes

## Outcome

The standalone S4 evaluator completed successfully against the unmodified
`main-runrunning` source commit
`9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`. Spring Boot `4.0.7` and `4.0.8`
were genuine forward patch releases published in Maven Central at execution
time. Each release was materialized independently from the `4.0.6` source.

## Frozen-output checks

| Check | Result |
| --- | --- |
| Canonical JSON parses and validates against `result-schema-v1.json` | PASS |
| Exactly four HTML tables | PASS |
| Tables 1–4 preserve approved order, column meanings and terminology | PASS |
| Table 3 header dynamically renders `Boot 4.0.6 default` | PASS |
| Report header contains application, releases, scanner, modules, profiles, scopes, severities, coverage and limitations | PASS |
| Table 4 `New version vulnerabilities` contains every selected-release finding | PASS |
| JSON and HTML counts/ranking agree | PASS |
| Evidence references are relative to this directory and resolve to retained files | PASS |
| Source root POM hash and Git working tree were unchanged | PASS |
| Finding arithmetic reconciles for all three releases and five severity categories | PASS |
| No overlapping advisory aliases were found within a package/release | PASS |

## Measured security result

| Rank | Spring Boot | Addressed | Remaining | New | Total |
| ---: | --- | ---: | ---: | ---: | ---: |
| — | 4.0.6 baseline | 0 | 50 | 0 | 50 |
| 1 | 4.0.8 | 38 | 12 | 0 | 12 |
| 2 | 4.0.7 | 33 | 17 | 0 | 17 |

Baseline totals were 9 Critical, 17 High, 19 Medium, 5 Low and 0 Unknown.
For `4.0.8`, 5 Critical, 11 High, 17 Medium and 5 Low findings were addressed;
4 Critical, 6 High and 2 Medium findings remained. The scanner observed no
additional findings for either candidate.

## Dependency ownership

Each evaluated graph contained 62 selected compile/runtime components:

- 55 `BOOT_MANAGED` dependencies.
- 3 internal reactor dependencies classified `OTHER_BOM_PARENT_MANAGED`, with
  `reactor dependencyManagement` recorded as their source.
- 2 `INDEPENDENT_DIRECT` dependencies: `org.apache.commons:commons-text:1.9`
  and `org.json:json:20230227`. Boot 4.0.x supplied no relevant managed default,
  so these are not mislabeled as Boot overrides.
- 2 `INDEPENDENT_TRANSITIVE` dependencies.
- No natural `BOOT_MANAGED_OVERRIDDEN`, ambiguous/unknown, excluded, or
  separately imported-BOM examples occurred in this application graph.

The optional `strict-deps`, `sbom`, and `security-scan` profiles were not
activated. SBRI used its default OSV Scanner pipeline.

## Limitations

- Ranking is security-only; this run resolves Maven graphs but does not claim
  runtime, API, packaging, or full regression-test compatibility.
- OSV live data was queried during one bounded run, but no immutable advisory
  database snapshot identifier was available. Results are internally
  consistent for this run; later executions may change with advisory data.
- Maven's aggregate dependency-tree output provides a complete selected graph
  for this application, but canonical module-occurrence attribution remains
  recorded as the aggregate root rather than a per-module occurrence list.
- Maven produced empty logs under `-q`, so those zero-byte artifacts were not
  retained; the non-empty TGF, CycloneDX inventory, scanner JSON and scanner
  logs are the operative evidence.
- Fixed-version evidence remains `Unknown` when OSV did not report a safe
  boundary. Missing evidence was not interpreted as zero vulnerability.

The Maven repository cache (21,068,345 bytes), materialized workspaces and HTTP
cache were excluded as reproducible/generated bulk. The retained evidence is
2,056,544 bytes and includes each release's TGF graph, CycloneDX inventory and
original OSV Scanner response.
