# Evidence-derived evaluation matrix

Evidence: `evidence/run-20261013-v2/results-v2.json`. Each cell contains the
executed checks, observed/expected values, evidence pointers and limitations.

| Approach | C1 managed | C2 transitive | C3 missing fix | C4 override |
| --- | --- | --- | --- | --- |
| A1 BOM + OSV | PROVEN | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED |
| A2 Maven + OSV | PROVEN | PROVEN | PROVEN | PROVEN |
| A3 deps.dev | PARTIALLY_PROVEN | PARTIALLY_PROVEN | PARTIALLY_PROVEN | NOT_SUPPORTED |
| A4 combined | PROVEN | PROVEN | PROVEN | PROVEN |
| A5 metadata-only Maven + BOM + OSV | PROVEN | PROVEN | PROVEN | PROVEN |
| A6 Maven dependency:collect + BOM + OSV | PROVEN | PROVEN | PROVEN | PROVEN |

These statuses match the previous matrix, but are no longer literals in
`_cells()`. For example, A2/C4 requires both the expected effective override and
a `STILL_AFFECTED` advisory verdict. Any mismatch produces `FAILED`.

## Expanded Maven matrix

Seven executed scenarios independently test the six requested mechanisms (the
profile case has inactive and active controls):

| Scenario | A1 | A2 | A3 | A4 | A5 | A6 |
| --- | --- | --- | --- | --- | --- | --- |
| Transitive mediation | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN | PROVEN |
| Direct version override | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN | PROVEN |
| dependencyManagement override | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN | PROVEN |
| Profile inactive control | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN | PROVEN |
| Applicable active profile | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN | PROVEN |
| Dependency exclusion | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN | PROVEN |
| Multi-module resolution | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN | PROVEN |

For A6, every expanded scenario is also `PROVEN` for complete selected-set and
version accuracy. A6 does not claim path support; A2/A5 path assertions remain
unchanged and still pass.

All A2 expectations passed: commons-codec 1.11 won the equal-depth transitive
tie through the first dependency; direct, dependency-management, active-profile
and multi-module management selected Tomcat 10.1.31; the inactive profile kept
10.1.30; and the exclusion removed Tomcat from the examined graph.

No approach was marked `FAILED` or `NOT_TESTED` in this run. Deterministic tests
prove those states are produced for contradictory and absent execution evidence.

## A2 versus A5 executed accuracy

Evidence: `evidence/run-20261014-a5/results-a5.json`. A5 matched the freshly
executed isolated A2 reference on 32/32 selected-version and complete target-path
checks across five releases, four override cases and seven expanded scenarios.
Every expected-versus-observed scenario check passed. Reapplying the frozen v2
OSV comparison produced identical addressed, remaining, new and unknown sets for
every release/dependency cell. No material difference was available to
investigate; the first-difference field is null.

## A6 executed accuracy

Evidence: `evidence/run-20261014-a6/results-a6.json`. Against the freshly rerun
A5 reference, A6 passed 32/32 checks covering the complete selected coordinate
set and every selected version across five releases, four overrides and seven
expanded scenarios. It also matched 64/64 addressed, still-affected, new and
unknown finding-set comparisons. All 16 detailed type/classifier/scope/version
record comparisons also matched. A6 has no path cells: lack of paths is a known
capability distinction rather than a rewritten A5 expectation.
