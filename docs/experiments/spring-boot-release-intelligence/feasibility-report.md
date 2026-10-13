# Feasibility report

## Execution summary

The 2026-10-13 live run executed 16 approach/case combinations on branch
`spring-boot-release-intelligence-feasibility` at commit
`ec9956b5b07033e31d96216662dca03de1e2b315`. Twelve offline tests passed. The
networked successful run took 72.250 seconds; Maven accounted for 70.521
seconds. It made 9 remaining network requests after reuse of metadata cached by
the two diagnostic attempts, transferred 48,917 response bytes, recorded 289
cache hits, and had no retries or network failures. The final fully warm run
took 69.423 seconds and made no network requests. Evidence occupied 8.0 MB,
mostly bounded responses and Maven graphs.

## Findings

All three source-specific implementations work within their stated boundaries.
A1 accurately reads the relevant Boot BOM properties and imported BOMs. A2
delegates the effective graph to Maven and is the only individual approach that
fully covers all four cases. A3 supplies useful published-version, advisory-key
and hosted-graph corroboration, but cannot independently establish Boot
management, application-effective resolution, override behavior, or advisory
range semantics.

The run reproduced the historical C1 regression exactly. Baseline Boot 3.3.4
managed and resolved Tomcat 10.1.30 with 33 original OSV IDs. Boot 3.3.5
(10.1.31) and 3.3.6 (10.1.33) each had 1 original ID no longer reported and 32
still reported. Boot 3.3.7 and 3.3.8 (10.1.34) each had 3 no longer reported and
30 still reported. No new candidate IDs were reported. The removed identities
were `GHSA-qvf5-hvjx-wm27` at 10.1.31, plus
`GHSA-27hp-xhwr-wr2m` and `GHSA-5j33-cvvr-w245` at 10.1.34. Explicit OSV fixed
events support those conclusions; mere query absence was not used as proof.

Maven and deps.dev both showed the tested path through `starter-web` and
`starter-tomcat`. deps.dev returned 34 nodes and 62 edges for each candidate,
including two graph paths to Tomcat. Maven's application-specific path is used
as stronger evidence. In C4, candidate Boot defaults changed while the
application's `tomcat.version=10.1.30` kept the effective dependency vulnerable.

## Reliability, performance, and bounded benchmark

The first two attempted executions exposed probe defects: an output path was
resolved relative to the generated Maven project, then the installed dependency
plugin emitted text for unsupported JSON output. Both were repaired; TGF
node/edge output is now parsed. Maven itself returned success in both cases, so
neither was classified as an approach limitation. See `execution-attempts.json`.

On the final warm run A1 took 0.443 seconds (288 cache reads), A2 took 68.237
seconds, A3 took 0.026 seconds (10 cache reads), and A4 integration took 0.0002
seconds with no duplicated HTTP calls. The requested 10-findings × 5-candidates
cached replay ran 50 comparisons in 0.000016 seconds with zero additional
network requests. The remaining 8 scale
combinations (20/100 candidates and 50/100 findings) were deliberately not live
tested; multiplying identical historical requests would add traffic without
testing new correctness. No throughput extrapolation is claimed.

## Unknowns and limitations

- The BOM reader supports parent/import/property patterns observed here, not a
  complete effective Maven model or all import-precedence/profile semantics.
- The numeric fixed-event comparator refuses qualifiers; full Maven version
  ordering remains a production gap.
- The fixture proves one starter path and one property override, not arbitrary
  profiles, exclusions, multi-module mediation, repositories, or compatibility.
- OSV and deps.dev are mutable services. Stored evidence is a timestamped
  observation, not a continuously valid assertion.
- Original-finding coverage is not application compatibility and is not a full
  independent candidate vulnerability scan.
