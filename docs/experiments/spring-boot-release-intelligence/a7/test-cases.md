# A7 test cases

## Acceptance matrix

| Case | Required independent expectation | A7 execution |
| --- | --- | --- |
| C1 Boot-managed | effective selected version changes | Focused baseline inventory exercised; candidate not exercised |
| C2 explicit override | selected override remains; Boot default reported separately | NOT EXERCISED |
| C3 other BOM | ownership is other-managed | NOT EXERCISED |
| C4 independent direct | remains visible and independent | NOT EXERCISED |
| C5 independent transitive | selected version and path retained | NOT EXERCISED |
| C6 new High/Critical | additional finding cannot be hidden by addressed findings | Offline disposition test only |
| C7 reactor | module occurrences and advisory identity deduplicate correctly | Offline module deduplication test only |
| C8 profile | identical profile input reaches every solution | NOT EXERCISED |
| C9 packaging/scopes | metadata and packaged content differences are explained | NOT EXERCISED |
| C10 incomplete | failure is incomplete, never clean | Offline negative test passed |

The live subset reuses the historical Boot 3.3.4 starter-web A5 fixture. Its
independent checks are exact A5/native inventory reconciliation and normalized
S1/S4 package-version-advisory equality. This is not enough to qualify any
solution as `PROVEN`.

## Offline acceptance

Run:

```bash
python -m unittest tests.test_a7 \
  tests.test_spring_boot_release_intelligence \
  tests.test_spring_boot_release_intelligence_contract
```

Candidate copies must preserve the source; contradictory controllers must be
rejected; SBOM generation must be deterministic; inventory differences must be
observable; and incomplete empty results must not become clean results.
