# Executed evaluation matrix

Live run: `evidence/run-20261013/results.json`. Every cell was executed against
the same real Boot 3.3.4 baseline and 3.3.5–3.3.8 candidates. The JSON `cells`
array contains each input expectation, observed value, evidence pointer and
limitation.

| Approach | C1 managed | C2 transitive | C3 incomplete fix | C4 override |
| --- | --- | --- | --- | --- |
| A1 BOM + OSV | PROVEN | NOT_SUPPORTED | PROVEN | NOT_SUPPORTED |
| A2 Maven + OSV | PROVEN | PROVEN | PROVEN | PROVEN |
| A3 deps.dev | PARTIALLY_PROVEN | PARTIALLY_PROVEN | PARTIALLY_PROVEN | NOT_SUPPORTED |
| A4 combined | PROVEN | PROVEN | PROVEN | PROVEN |

## Cell evidence

| Cell | Observed result and limitation |
| --- | --- |
| A1/C1 | BOM properties resolved Tomcat 10.1.30 → 10.1.31/33/34/34 with `tomcat.version` provenance; OSV comparison reproduced 1/1/3/3 original IDs absent. Management does not prove inclusion. |
| A1/C2 | No dependency inclusion/path exists in a BOM. Demonstrated limitation: NOT_SUPPORTED. |
| A1/C3 | Missing input fix remained null; real OSV range events established the 10.1.31 boundary for `GHSA-qvf5-hvjx-wm27`. Numeric range comparison is deliberately bounded. |
| A1/C4 | Boot defaults were visible, but the effective application property was not. NOT_SUPPORTED independently. |
| A2/C1 | Maven selected exactly the BOM versions for the fixture; OSV supplied vulnerability status. |
| A2/C2 | Maven returned `application -> starter-web -> starter-tomcat -> tomcat-embed-core` for every release. |
| A2/C3 | Exact effective versions plus OSV range evidence allowed evidence-based classification despite null scanner fix. |
| A2/C4 | With `tomcat.version=10.1.30`, every candidate selected 10.1.30: `APPLICATION_CONTROLLED + STILL_AFFECTED`. |
| A3/C1 | Version records and advisory keys were returned, but deps.dev cannot identify Boot BOM management. |
| A3/C2 | Hosted graphs returned the expected path and versions, but are published-package graphs rather than the application's effective model. |
| A3/C3 | Tested endpoints supply advisory keys, not full affected-range contents; absence cannot prove a fix. |
| A3/C4 | A published starter graph cannot observe the generated application's override. NOT_SUPPORTED. |
| A4/C1 | A1 supplied management, A2 effective selection, OSV applicability, deps.dev corroboration. |
| A4/C2 | Maven supplied the authoritative fixture path; deps.dev independently agreed. |
| A4/C3 | OSV supplied range events, Maven the selected version, and the null input remained explicit. |
| A4/C4 | A1 supplied the newer default, Maven proved 10.1.30 remained effective, OSV proved it affected. |

No cell is `FAILED` or `NOT_TESTED`. `NOT_SUPPORTED` means the successful live
call demonstrated that the approach lacks required information; it does not
mean a request failed.
