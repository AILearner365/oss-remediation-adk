# Recommendation

Use **A2 (Maven resolution + OSV) as the smallest viable core**, with the A1 BOM
reader retained as explanatory provenance and release pre-filtering. Do not put
deps.dev on the required decision path.

A2 alone was the only individual approach proven across C1–C4: it identifies
the actual tested application's direct/transitive paths, honors Boot's effective
management, detects the application override, and gives OSV the exact selected
version. A1 adds cheap, valuable evidence about why Boot selected a default and
can avoid resolving irrelevant candidates, but cannot prove inclusion or
application control. A3 agreed with the tested graph yet remained partial in
three cases and unsupported for the override; its additional network and
reconciliation complexity did not improve any final verdict.

Thus the practical combination is **A2 + the narrow A1 metadata component +
OSV**, not full A4. deps.dev can remain optional corroboration or a diagnostics
fallback, clearly labelled as a published-package graph. Before production,
add a real Maven version comparator, repository/auth handling, profiles and
multi-module cases, conflict/exclusion cases, durable rate-limit behavior, and
candidate compatibility/build tests. Keep vulnerability remediation and
compatibility as separate conclusions.
