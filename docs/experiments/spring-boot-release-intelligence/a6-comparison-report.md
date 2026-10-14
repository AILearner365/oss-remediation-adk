# A6 Maven dependency:collect comparison

## Decision

Keep A5 as the preferred release-intelligence collector. A6 is feasible for a
narrow selected-artifact/version vulnerability comparison, but its missing paths
remove diagnostic evidence and it produced no material runtime, storage, or
network advantage over A5.

## Mechanism and parsing

A6 uses Maven's own effective model, mediation and reactor handling:

```bash
mvn -B -q -Dmaven.repo.local=<isolated-cache> \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:collect \
  -DoutputFile=<dependency-collect.txt>
```

Profiles add `-P<profile>`. The reactor case adds `-f <root-pom> -pl app -am`.
No `install` is run. The parser accepts Maven records formatted as
`groupId:artifactId:type[:classifier]:version:scope`, requires the resolved-files
marker, rejects malformed or contradictory records, and treats Maven's literal
`none` as an explicit empty collection. It preserves scope, type, classifier,
selected version and presence, but does not infer paths.

## Accuracy and completeness

The controlled run used separate empty A2, A5 and A6 repositories, the same
five Boot versions, four override cases, seven scenarios, POMs, profiles,
environment, frozen v2 advisory evidence and expectations.

| Measure | A2 | A5 | A6 |
| --- | ---: | ---: | ---: |
| Reference version/path checks | reference | 32/32 | paths not claimed |
| Complete selected-set/version checks vs A5 | — | reference | 32/32 |
| Type/classifier/scope/version record checks | — | reference | 16/16 |
| Frozen vulnerability result checks | reference | reference | 64/64 |
| C1–C4 | 4 PROVEN | 4 PROVEN | 4 PROVEN |
| Expanded scenarios | 7/7 | 7/7 | 7/7 |

The selected dependency set and detailed artifact records were identical in
every tested configuration. A6 respected Boot management, imported
management/properties, transitive mediation,
direct and dependency-management overrides, active/inactive profiles,
exclusions, and the multi-module reactor. The override cases retained Tomcat
10.1.30, preventing false attribution of Boot's newer default as a fix.

Lack of paths did not change the tested coverage calculation because each
original finding was keyed to an artifact and the candidate's complete selected
set supplied its effective version or independently checked absence. It does
prevent explaining which introduction path changed, diagnosing competing paths,
or proving reachability beyond selected-set presence.

## Release comparison

Boot 3.3.5 and 3.3.6 addressed 2 original findings and left 39; 3.3.7 addressed
4 and left 37; 3.3.8 addressed 6 and left 35. No new, unknown or absent-package
findings occurred. Boot-managed SnakeYAML remained 2.2 in every standard
candidate. Separately, the application override kept Tomcat at 10.1.30 and
`STILL_AFFECTED` for every candidate despite newer Boot defaults. Coverage-only
ordering places 3.3.8 first, but this is not a candidate recommendation because
compatibility was not tested.

## Runtime, storage, and downloads

| Metric | A2 fresh | A2 warm | A5 fresh | A5 warm | A6 fresh | A6 warm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Workload seconds | 183.180 | 142.750 | 177.746 | 150.766 | 176.896 | 151.175 |
| Final/peak cache bytes | 61,247,561 | 61,247,561 | 21,134,449 | 21,134,449 | 21,134,449 | 21,134,449 |
| Application JAR count | 7 | 0 new | 0 | 0 new | 0 | 0 new |
| Plugin/bootstrap JAR count | 129 | 0 new | 50 | 0 new | 50 | 0 new |
| POM count/bytes | 656 / 7,999,638 | 0 new | 460 / 6,118,943 | 0 new | 460 / 6,118,943 | 0 new |

A6 was 0.851 seconds (0.48%) faster than A5 fresh and 0.409 seconds (0.27%)
slower warm. These negligible differences do not support an efficiency claim.
A separate non-quiet A6 pass observed 510 successful transfer events and
21,091,327 Maven-reported bytes fresh, then zero warm—the same values previously
observed for A5. Maven does not expose transport-level HTTP request counts.

Independent zero-dependency controls attributed 50 JARs (14,912,596 bytes) to
each metadata plugin/bootstrap closure. Both controls reclassified the same
`commons-logging:1.2` overlap and found zero application dependency JARs and
zero unexplained binaries. Thus A6 is not JAR-free; it is application-JAR-free.
All repositories were isolated under disposable cache roots, not `~/.m2`.

## Simplicity and limitations

The collect output is simpler to parse than a graph, but operational setup and
bootstrap costs are the same. Complete-set comparison and absence validation are
mandatory because a partial flat list could otherwise create false fixes. A5's
graph provides more evidence with effectively identical resource use.

Untested cases remain repository mirrors/authentication, classifiers in actual
application fixtures, relocations, optional dependencies, complex imported-BOM
precedence, non-file profile activation, and larger workloads. Neither approach
proves binary/runtime compatibility or replaces candidate build/test and
independent scanning.

## Evidence

- Machine result: `evidence/run-20261014-a6/results-a6.json`
- Compact metrics: `evidence/run-20261014-a6/metrics-summary.json`
- A5/A6 bootstrap controls: `evidence/run-20261014-a6/a5-qualification/` and `a6-qualification/`
- A2/A5/A6 POMs and outputs: `evidence/run-20261014-a6/maven-work/`
- Separate A6 transfer logs: `evidence/run-20261014-a6/telemetry-work/`
- Charts: `evidence/run-20261014-a6/a6-charts.html`
- Integrity manifest: `evidence/run-20261014-a6/manifest.json`
