# A7 results

## Classification

All four solutions are **PARTIALLY PROVEN**. The bounded live subset establishes
useful mechanisms but does not execute the candidate comparison or C1–C10
matrix, so `PROVEN` would be unsupported.

35 offline tests passed: the 29 preserved A1–A6 tests and six focused A7 tests.
Live environment: Java 21.0.12.1, Maven 3.9.16, CycloneDX Maven Plugin 2.9.1,
and OSV Scanner 2.6.0.

| Result | S1 | S2 | S3 | S4 |
| --- | ---: | ---: | ---: | ---: |
| Selected components | 34 | 34/34 reconciled | 34 batch queries | 34 |
| Finding identities | 81 | scanner evidence inherited from S1 | advisory details retrieved | 81 |
| Fresh measured time | 24.551 s Maven + 1.769 s scan | combined cold run not measured | 7.294 s | 0.910 s scan; A5 collection reused |
| Warm measured time | 10.754 s Maven | not measured | not measured | 0.952 s scan |
| SBOM bytes | 89,883 | same native SBOM | n/a | 21,377 |
| Isolated Maven repository | 29,943,373 B | combined not measured | A5 historical boundary | no new Maven mechanism |
| Application dependency JARs | 34/34 | inherits S1 overhead | none beyond A5 | none beyond A5 |

OSV Scanner returned exit 1 because findings were present, not because scanning
failed. S1 and S4 produced exactly the same 81 normalized
package/version/advisory triples. Native CycloneDX and A5 inventories matched
34/34 with no one-sided entries. S3 used one batch request and 80 detail
requests; its 34 queries equal the naive count because only one configuration
was run, so cross-candidate deduplication benefit remains unmeasured.

Peak RSS is `NOT EXERCISED`: GNU `time` was unavailable. The minimal BOM passed
the official CycloneDX 1.5 JSON schema (schema SHA-256 is retained in machine
evidence), the focused structural validator, and OSV Scanner ingestion.
Request counts are application-level calls, not transport retry counts.

Machine evidence: [live-subset.json](evidence/live-subset.json) and its
[SHA-256 manifest](evidence/manifest.json). Large duplicate scanner responses,
HTTP caches, Maven repositories, and application JARs are intentionally not
retained.

## Reproduction commands

```bash
python -m unittest tests.test_a7 tests.test_spring_boot_release_intelligence \
  tests.test_spring_boot_release_intelligence_contract
mvn -B -q -f "$PROJECT/pom.xml" -Dmaven.repo.local="$ISOLATED_REPO" \
  org.cyclonedx:cyclonedx-maven-plugin:2.9.1:makeAggregateBom \
  -DoutputFormat=json -DoutputName=bom
python -m spring_boot_release_intelligence.a7_cli reconcile \
  "$A5_TREE" "$PROJECT/target/bom.json"
python -m spring_boot_release_intelligence.a7_cli osv-batch \
  "$A5_TREE" --output "$OUTPUT/osv-batch.json"
python -m spring_boot_release_intelligence.a7_cli minimal-sbom \
  "$A5_TREE" "$OUTPUT/application.cdx.json" --seed "$CASE_ID"
osv-scanner scan source --sbom "$OUTPUT/application.cdx.json" \
  --format json --output-file "$OUTPUT/osv.json" "$PROJECT"
```

Use new disposable project, repository and output paths for cold runs. Produce
each candidate directly from the original with `a7_cli materialize`. Scanner
exit 1 means findings were found; classify other nonzero exits as failures.
