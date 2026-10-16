# A5 metadata-only Maven comparison

## Decision

Use a hybrid: A5 for application-effective graph collection and frozen-evidence
vulnerability comparison; retain normal Maven build/test execution for
shortlisted candidate compatibility validation. A5 is a viable replacement for
the A2 **collection stage**, not for build/runtime validation.

## Mechanism selection

The experiment tried Maven Dependency Plugin `dependency:collect`. It avoided
application JARs but emitted a flat resolved-artifact list, so it could not
preserve the paths required to explain mediation and vulnerability reachability.
A direct Maven Resolver/Model Builder integration was considered but not needed:
the established Maven graph builder exposed by the pinned command below
preserved paths and used Maven's own effective-model/mediation behavior.

```bash
mvn -B -Dmaven.repo.local=<isolated-cache> \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree \
  -DoutputType=tgf -DoutputFile=<evidence.tgf>
```

Profiles add `-P<profile>`. Multi-module resolution uses the root POM with
`-pl app -am`; it does not run `install` or create reactor JARs.

## Accuracy

The fresh comparison reran A2 and A5 against identical POMs, Boot 3.3.4–3.3.8,
Tomcat overrides, profiles, Java/Maven environment, expectations and frozen v2
OSV evidence.

| Measure | A2 | A5 |
| --- | ---: | ---: |
| Version/path assertions | 32/32 | 32/32 |
| Original C1–C4 | 4 PROVEN | 4 PROVEN |
| Expanded scenarios | 7/7 | 7/7 |
| Frozen vulnerability classifications | reference | exact match |

The tested scenarios cover transitive mediation, direct overrides,
`dependencyManagement`, inactive/active profiles, exclusions and a reactor
multi-module graph. No first material graph or verdict difference occurred.

Across the four actual dependencies, releases 3.3.5/3.3.6 addressed 2 original
findings and left 39; 3.3.7 addressed 4 and left 37; 3.3.8 addressed 6 and left
35. No new or unknown findings appeared in the frozen snapshot. One dependency
was unchanged in every candidate; none was absent. These counts do not establish
compatibility or select a release.

## Runtime and storage

| Metric | A2 fresh | A2 warm | A5 fresh | A5 warm |
| --- | ---: | ---: | ---: | ---: |
| Workload time (s) | 218.652 | 161.863 | 183.472 | 162.453 |
| Final/peak durable cache (bytes) | 61,247,561 | 61,247,561 | 21,134,449 | 21,134,449 |
| Application dependency JARs | 7 / 4,725,608 B | 0 new | 0 / 0 B | 0 new |
| Plugin/bootstrap JARs | 129 / 48,370,649 B | 0 new | 50 / 14,912,596 B | 0 new |
| POMs | 656 / 7,999,638 B | 0 new | 460 / 6,118,943 B | 0 new |
| Successful Maven transfer events | unavailable | unavailable | 510 | 0 |
| Maven-reported transfer bytes | unavailable | unavailable | 21,091,327 | 0 |

A5 saved 40,113,112 durable bytes (65.5%) and 35.180 seconds (16.1%) fresh.
It was 0.590 seconds (0.4%) slower warm. Both fair timing passes used quiet
Maven output. Maven transfer events came from a separate non-quiet A5 telemetry
pass and are not HTTP
request counts; transport-level counts were unavailable. A2 used its historical
quiet command, so its network bytes/events are unavailable and no bandwidth
saving is asserted.

An empty-project control downloaded the same 50-JAR plugin closure and proved
that `commons-logging:1.2`, which overlaps one application graph, was a plugin
bootstrap download. There were no selected application JARs or unexplained
binaries after this independent qualification. A5 prevents growth of the shared
`~/.m2` cache by always requiring an explicit disposable
`maven.repo.local`; the shared cache was neither read nor written.

## Maintainability and limitations

A5 reuses Maven's graph builder and is smaller/safer than a custom Resolver
integration. It adds isolation, inventory and reactor-command code beyond A2.
The pinned plugin requires binary bootstrap artifacts, so A5 is not “JAR-free.”
Repository mirrors/authentication, classifiers, relocations, optional
dependencies, complex import precedence, non-file profile activation and
transport-level request accounting remain untested. The measured workload is
bounded and does not establish scale. Compatibility builds/tests were not run.

The initial non-quiet telemetry run retained parsed cold transfer metrics and
bounded stdout tails but its per-case full log filenames were overwritten by
the warm pass. The final fair-timing rerun retains distinct quiet fresh/warm
logs. This telemetry-log retention gap does not affect graph, storage inventory
or timing results, but it is explicitly not hidden.

## Evidence and charts

- Machine result: `evidence/run-20261014-a5/results-a5.json`
- Bootstrap control: `evidence/run-20261014-a5/bootstrap-control.json`
- POMs and TGF trees: `evidence/run-20261014-a5/maven-work/`
- Warm logs: `evidence/run-20261014-a5/maven-work/a5/logs/`
- Reproducible charts: `evidence/run-20261014-a5/a5-charts.html`
- Commands: [live-test-cases.md](live-test-cases.md)
