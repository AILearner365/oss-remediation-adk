# A7 test cases

Boot `3.3.4`, `3.3.5`, `3.3.7` and `3.3.8` were independently materialized
from the original 3.3.4 project. Effective A5 resolution confirmed each Boot
version.

| Case | Status | Executed evidence |
| --- | --- | --- |
| C1 Boot-managed change | **PROVEN** | Spring Core selected 6.1.13/6.1.14/6.1.16/6.1.16; Tomcat selected 10.1.30/10.1.31/10.1.34/10.1.34 |
| C2 explicit override | **PROVEN** | `tomcat.version=10.1.30` remained selected with its path for all candidates; the 3.3.8 override retained 33 Tomcat advisories versus 30 at its default 10.1.34 |
| C3 other BOM | **PROVEN** | A real imported Jackson BOM 2.16.2 selected Databind 2.16.2 and was classified `OTHER_MANAGED` |
| C4 independent direct | **PROVEN** | Explicit `commons-io:2.11.0` resolved directly and its live advisory remained visible |
| C5 independent transitive | **PROVEN** | Commons Codec 1.11 retained its HttpClient path; a mediated transitive graph retained a live Log4j finding |
| C6 additional finding | **PARTIAL** | Deterministic High-addition and arithmetic tests passed; no live candidate introduced a finding |
| C7 multi-module | **PROVEN** | Reactor collection selected Tomcat 10.1.31 through `experiment:library:1`; module occurrences deduplicate in the SBOM test |
| C8 profile | **PROVEN** | Inactive/active profile selected Tomcat 10.1.30/10.1.31 and scanning observed 33/32 Tomcat advisories |
| C9 packaging/scopes | **PARTIAL** | Executable Boot JAR builds passed for 3.3.4 and 3.3.8; WAR/provided scope was not exercised |
| C10 incomplete evidence | **PROVEN** | Incomplete empty results cannot report clean; ambiguous candidate controllers and contradictory evidence are rejected |

Both packaged JARs contained 30 libraries versus 34 metadata dependencies. The
five metadata-only starter artifacts absent from packaging were
`spring-boot-starter-web`, `spring-boot-starter`, `spring-boot-starter-json`,
`spring-boot-starter-tomcat`, and `spring-boot-starter-logging`; the repackager
added `spring-boot-jarmode-tools`.

## Reproduction

```bash
python -m unittest tests.test_a7 tests.test_spring_boot_release_intelligence \
  tests.test_spring_boot_release_intelligence_contract
python -m spring_boot_release_intelligence.a7_cli materialize \
  "$ORIGINAL" "$CANDIDATE" 3.3.8
python -m spring_boot_release_intelligence.a7_cli minimal-sbom \
  "$A5_TREE" "$OUTPUT/application.cdx.json" --seed 3.3.8
osv-scanner scan source --sbom "$OUTPUT/application.cdx.json" \
  --format json --output-file "$OUTPUT/osv.json" "$CANDIDATE"
```

S1 uses `org.cyclonedx:cyclonedx-maven-plugin:2.9.1:makeAggregateBom`.
A5 uses `org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree` with TGF.
Use a new isolated repository per solution for the fresh workload and reuse it
for the warm pass.
