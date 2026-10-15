# A7 recommendation

## Select S4 for the bounded collector

S4—A5 TGF collection, deterministic minimal CycloneDX and OSV Scanner—is the
evidence-backed winner for the tested release-comparison boundary.

Across Boot 3.3.4, 3.3.5, 3.3.7 and 3.3.8 it demonstrated exact inventory and
S1/S2/S3/S4 finding agreement, severity/disposition arithmetic, override and
ownership visibility, dependency paths, explicit incomplete status, and no
unexplained scanner discrepancy.

Among correct solutions it avoids a second resolver and application JAR
downloads, delegates advisory semantics to OSV Scanner, tied for the smallest
repository, and recorded the lowest fresh/warm workload times.

This does not make S4 production-ready. C6 has synthetic but no live additional
finding; C9 lacks WAR/provided-scope coverage; private repositories,
scanner-cache telemetry, larger reactors and S3 HTTP RSS remain unverified.
Candidate builds/tests and compatibility validation remain a separate stage.
Reopen the selection if those environments reveal a material discrepancy.
