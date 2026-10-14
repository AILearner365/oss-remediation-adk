# Live and deterministic test cases

## Original C1–C4

C1–C4 retain Boot 3.3.4 and candidates 3.3.5–3.3.8, the real
`spring-boot-starter-web -> spring-boot-starter-tomcat -> tomcat-embed-core`
path, and `GHSA-qvf5-hvjx-wm27`. C4 pins `tomcat.version=10.1.30`.
Expected Tomcat versions remain 10.1.30, 10.1.31, 10.1.33, 10.1.34 and
10.1.34. The missing scanner fix in C3 remains null; the OSV interval, rather
than version-number inference or query absence, supplies the conclusion.

## Expanded real Maven cases

| ID | Inputs | Independently expected result |
| --- | --- | --- |
| M1 mediation | httpclient 4.5.14 then Apache POI 5.2.5 | equal-depth first declaration selects commons-codec 1.11 |
| M2 direct override | Boot 3.3.4 starter-web + direct Tomcat 10.1.31 | direct path selects 10.1.31 |
| M3 dependencyManagement | Boot 3.3.4 plus Tomcat management 10.1.31 | transitive Tomcat is 10.1.31 |
| M4 profile controls | same management only in profile `upgrade` | inactive 10.1.30; `-Pupgrade` 10.1.31 |
| M5 exclusion | starter-web excludes starter-tomcat | Tomcat absent on examined path |
| M6 multi-module | app manages 10.1.31; library requests 10.1.30 | app graph resolves library path to 10.1.31 |

The multi-dependency release comparison examines resolved Tomcat Core, Spring
Web, Logback Core and SnakeYAML for every Boot candidate. It records paths,
original/still/addressed/new/unknown IDs and advisory/query provenance. Candidate
selection is deliberately withheld because compatibility evidence is not tested.

## Reproduction

```bash
python3 -m unittest tests.test_spring_boot_release_intelligence_contract \
  tests.test_spring_boot_release_intelligence -v

python3 -m spring_boot_release_intelligence.cli run-live \
  --output docs/experiments/spring-boot-release-intelligence/evidence/run-20261013-v2

A5 uses disposable cache roots; never point these commands at `~/.m2`:

```bash
A5_CACHE_ROOT="$(mktemp -d /tmp/sbri-a5-caches.XXXXXX)"
python3 -m spring_boot_release_intelligence.cli run-a5 \
  --output docs/experiments/spring-boot-release-intelligence/evidence/run-20261014-a5 \
  --cache-root "$A5_CACHE_ROOT" \
  --reference docs/experiments/spring-boot-release-intelligence/evidence/run-20261013-v2/results-v2.json

A5_CONTROL_CACHE="$(mktemp -d /tmp/sbri-a5-control.XXXXXX)"
python3 -m spring_boot_release_intelligence.cli qualify-a5-storage \
  --results docs/experiments/spring-boot-release-intelligence/evidence/run-20261014-a5/results-a5.json \
  --output docs/experiments/spring-boot-release-intelligence/evidence/run-20261014-a5 \
  --cache-root "$A5_CONTROL_CACHE"

python3 -m spring_boot_release_intelligence.cli generate-a5-charts \
  --results docs/experiments/spring-boot-release-intelligence/evidence/run-20261014-a5/results-a5.json \
  --output docs/experiments/spring-boot-release-intelligence/evidence/run-20261014-a5/charts
```

The A5 run repeats C1–C4 and all seven expanded cases for fresh and warm A2/A5
passes. The zero-dependency control is required because
`commons-logging:commons-logging:1.2` occurs in one application graph and in
the plugin bootstrap closure; filename matching alone would misclassify it.
```

Prerequisites: Python 3, Java, Maven and network access to Maven Central, OSV
and deps.dev. Source data is mutable; evidence is timestamped.
