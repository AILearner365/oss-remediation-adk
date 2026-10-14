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

These statuses match the previous matrix, but are no longer literals in
`_cells()`. For example, A2/C4 requires both the expected effective override and
a `STILL_AFFECTED` advisory verdict. Any mismatch produces `FAILED`.

## Expanded Maven matrix

Seven executed scenarios independently test the six requested mechanisms (the
profile case has inactive and active controls):

| Scenario | A1 | A2 | A3 | A4 | A5 |
| --- | --- | --- | --- | --- | --- |
| Transitive mediation | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN |
| Direct version override | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN |
| dependencyManagement override | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN |
| Profile inactive control | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN |
| Applicable active profile | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN |
| Dependency exclusion | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN |
| Multi-module resolution | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN | PROVEN |

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
