# A7 solution comparison

| Criterion | S1 | S2 | S3 | S4 |
| --- | --- | --- | --- | --- |
| Effective inventory | Native CycloneDX | A5 + native | A5 | A5 |
| Paths | No | Yes | Yes | Yes |
| All-candidate finding agreement | Exact | Exact | Exact | Exact |
| Second Maven resolution | Yes | Yes | No | No |
| Application JAR downloads | 95 | 95 | 0 | 0 |
| Fresh/warm seconds | 74.512/57.270 | 125.183/85.143 | 62.750/40.542 | **61.650/37.771** |
| Repository bytes | 71,350,075 | 87,027,720 | **20,241,909** | **20,241,909** |
| Main maintenance risk | Plugin inventory behavior | Duplicate resolution | API/advisory semantics | Small SBOM converter/scanner contract |

S1 is correct but lacks A5 paths and downloads application JARs. S2 adds paths
without a measured correctness advantage and is most expensive. S3 is finding
equivalent and deduplicates queries, but owns advisory detail, alias and severity
semantics and made 81 API calls. S4 delegates those semantics to OSV Scanner,
retains A5 paths, avoids a second resolver and has the best measured
time/storage combination.

No Critical/High discrepancy is unexplained. The source-scan difference follows
non-transitive semantics; the packaged-JAR difference follows metadata-only
starters and repackager-added content.
