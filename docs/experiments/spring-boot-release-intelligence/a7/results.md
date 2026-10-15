# A7 continuation results

Historical A1–A6 evidence and the previous A7
[single-baseline evidence](evidence/live-subset.json) are unchanged. New live
evidence is the hash-verified [candidate summary](evidence/candidate-run-summary.json).
Large scanner responses, Maven repositories, JARs and caches were excluded.
C6's introduced-High branch is synthetic and is not labeled live.

Environment: Maven 3.9.16, Java 21.0.12.1, CycloneDX Maven Plugin 2.9.1 and OSV
Scanner 2.6.0. Maven/build commands returned zero. Scanner exit 1 denotes
findings rather than execution failure.

## Vulnerability comparison

Identity is selected package, normalized advisory ID and version; disposition
matches package/advisory across versions. Both required arithmetic invariants
passed for every release.

| Boot | Original C/H/M/L/U | Addressed C/H/M/L/U | Remaining C/H/M/L/U | Additional C/H/M/L/U | Candidate total C/H/M/L/U |
| --- | --- | --- | --- | --- | --- |
| 3.3.4 | 11/28/30/12/0 | 0/0/0/0/0 | 11/28/30/12/0 | 0/0/0/0/0 | 11/28/30/12/0 (81) |
| 3.3.5 | 11/28/30/12/0 | 0/1/3/0/0 | 11/27/27/12/0 | 0/0/0/0/0 | 11/27/27/12/0 (77) |
| 3.3.7 | 11/28/30/12/0 | 1/2/3/0/0 | 10/26/27/12/0 | 0/0/0/0/0 | 10/26/27/12/0 (75) |
| 3.3.8 | 11/28/30/12/0 | 1/2/4/1/0 | 10/26/26/11/0 | 0/0/0/0/0 | 10/26/26/11/0 (73) |

The candidate fixture's findings are Boot-managed. Focused real fixtures also
proved overridden, other-managed, independent-direct and
independent-transitive reporting. For the override, Boot 3.3.8 manages Tomcat
10.1.34 but the application property selects 10.1.30; 33 Tomcat advisories
remain versus 30 at 10.1.34. Removing the override was not tested or advised.

## Equivalence and packaging

- S1/S2/S4 matched exactly for all 34 components and all 81/77/75/73 findings.
- S3 matched those identities exactly. It deduplicated 136 naive queries to 95
  (30.1% fewer), then made 80 detail calls: 81 API calls total.
- Source-only scans returned zero because this mode did not resolve Maven
  transitives; it is not ground truth for the application.
- Executable 3.3.4 and 3.3.8 JARs built. The explained 34-to-30 packaging
  difference is listed in `test-cases.md`.

## Performance and resources

“Fresh” starts with an empty per-solution repository, then processes candidates
in fixed order to measure shared-cache reuse. Only the first candidate is
individually cold. “Warm” repeats the workload. Times include required Maven
and security stages.

| Solution | Fresh | Warm | Fresh peak subprocess RSS | Repository | App JARs / bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1 | 74.512 s | 57.270 s | 200,294,400 B | 71,350,075 B | 95 / 60,060,405 B |
| S2 | 125.183 s | 85.143 s | 219,074,560 B | 87,027,720 B | 95 / 60,060,405 B |
| S3 | 62.750 s | 40.542 s | 189,919,232 B* | 20,241,909 B | 0 / 0 B |
| S4 | **61.650 s** | **37.771 s** | **183,119,872 B** | **20,241,909 B** | **0 / 0 B** |

`*` S3's HTTP-stage RSS was not separately sampled. S1/S2 SBOMs were
89,883–89,904 bytes; S4 SBOMs were 21,377–21,393 bytes. The disposable
workspace reached 358,279,081 bytes, including 44,566,410 bytes of unretained
scanner output. Scanner-cache growth remains `NOT EXERCISED`.
