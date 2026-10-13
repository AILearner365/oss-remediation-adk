# Evidence-derived evaluation matrix

Evidence: `evidence/run-20261013-v2/results-v2.json`. Each cell contains the
executed checks, observed/expected values, evidence pointers and limitations.

| Approach | C1 managed | C2 transitive | C3 missing fix | C4 override |
| --- | --- | --- | --- | --- |
| A1 BOM + OSV | PROVEN | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED |
| A2 Maven + OSV | PROVEN | PROVEN | PROVEN | PROVEN |
| A3 deps.dev | PARTIALLY_PROVEN | PARTIALLY_PROVEN | PARTIALLY_PROVEN | NOT_SUPPORTED |
| A4 combined | PROVEN | PROVEN | PROVEN | PROVEN |

These statuses match the previous matrix, but are no longer literals in
`_cells()`. For example, A2/C4 requires both the expected effective override and
a `STILL_AFFECTED` advisory verdict. Any mismatch produces `FAILED`.

## Expanded Maven matrix

Seven executed scenarios independently test the six requested mechanisms (the
profile case has inactive and active controls):

| Scenario | A1 | A2 | A3 | A4 |
| --- | --- | --- | --- | --- |
| Transitive mediation | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN |
| Direct version override | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN |
| dependencyManagement override | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN |
| Profile inactive control | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN |
| Applicable active profile | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN |
| Dependency exclusion | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN |
| Multi-module resolution | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED | PROVEN |

All A2 expectations passed: commons-codec 1.11 won the equal-depth transitive
tie through the first dependency; direct, dependency-management, active-profile
and multi-module management selected Tomcat 10.1.31; the inactive profile kept
10.1.30; and the exclusion removed Tomcat from the examined graph.

No approach was marked `FAILED` or `NOT_TESTED` in this run. Deterministic tests
prove those states are produced for contradictory and absent execution evidence.
