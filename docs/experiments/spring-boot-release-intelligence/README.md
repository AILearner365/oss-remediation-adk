# Spring Boot release vulnerability-coverage feasibility

## Objective
Given a current Spring Boot version, an eligible upgrade range, and vulnerability findings from **OSV (testing)** or **JFrog Xray (production)**, identify **which published Spring Boot releases address the most *original findings*** and why. This is a research/acceptance contract, **not** an implementation of a scanner, dependency resolver, database, or autonomous remediation agent.

```text
Application + OSV/Xray findings
  -> normalize (CVE/GHSA/advisory, Maven GAV, fixed range if known, source)
  -> enumerate real, eligible Spring Boot releases
  -> establish dependency version AND dependency path for each candidate
     (official managed catalog/BOM, hosted graph where valid, Maven fallback)
  -> ask vulnerability advisory whether the selected version is affected
  -> evidence-backed findings per release -> coverage and uncertainty ranking
  -> later: candidate-specific application resolution and independent scan
```

### What must be answered
For each original vulnerability: What package/version is currently affected? Is a fixed version known? Who selects the current version? For a candidate release, is the artifact explicitly managed, managed through an imported BOM, transitively introduced by a starter or other library, application overridden, absent from the examined path, or not established? Which candidate package version **would be selected**, and does the specific original vulnerability affect it? Where did each fact come from? Never assume a managed package is actually included in an app. Never assume a higher version fixes an advisory. New candidate vulnerabilities are a separate later scan; *original-finding coverage* is not proof of overall security.

### Evidence classifications
- **addressed_by_candidate_default_graph**: documented selection/path and credible advisory evidence the specific original finding no longer affects the selected package version. Not yet proof for a specific application.
- **still_affected**: advisory evidence explicitly establishes the candidate selected version is affected.
- **not_selected_on_examined_path**: a particular starter path disappears; do **not** call the whole app fixed or decommissioned.
- **application_controlled**: application dependency/override prevents attribution of the selected version to Boot alone.
- **unknown**: insufficient package identity, candidate resolution, advisory range, provenance, or conflict; never count as fixed.
- **verified_in_application**: reserved for later application-aware resolution plus independent scanner confirmation.

For coverage, count distinct **original vulnerability findings** (advisory ID + affected component identity); separately report distinct affected components. Keep addressed, still-affected, missing-path, and unknown counts distinct. If competing paths/versions could be selected, do not award a confirmed fix based on one favorable path.

### Four acceptance cases
| ID | Scenario | What the probe must prove | Failure mode to catch |
| --- | --- | --- | --- |
| C1 | Known fixed version, Boot-managed dependency (including imported BOM) | Enumerate actual releases; record managed candidate versions, BOM provenance, advisory status, first eligible matching release | Mistaking management for actual app inclusion or comparing versions lexically |
| C2 | Known fixed version, **unmanaged starter transitive** dependency | Resolve or retrieve `starter -> upstream -> vulnerable package` under candidate Boot management, compare exact path and selected versions | Pretending catalog includes all transitives; blindly trusting a generic graph as app-specific |
| C3 | **No fixed version** supplied by scanner | Query OSV advisory affected ranges or candidate package/version; classify as addressed ONLY with sufficiently complete evidence, otherwise unknown | Counting missing OSV response as a verified fix |
| C4 | Package version controlled by **app override or app-specific dependency** | Show why Boot's newer managed version alone doesn't establish resolution; application-aware verification needed | Incorrect attribution of a fix to Spring Boot |

Each case must include a positive and an uncertainty/negative outcome. Test alternate management changes (newly managed/removed), disappearance of a starter path, and conflicting advisories as extensions; do not fabricate fixture evidence.

### Data source feasibility, not assumed correctness
1. Spring Boot released versions: published repository metadata; filter actual versions and stated eligibility, no invented releases.
2. Official Spring Boot managed dependency coordinates or effective Maven BOM: managed versions, including imports. Catalog = managed versions, not necessarily actual graph.
3. deps.dev hosted Maven dependency graph: **candidate** external source for transitive paths. Verify experimentally whether it reproduces the Boot BOM/starter context; if it cannot, record gap and try Maven metadata-only collection. No requirement to download dependency JARs for metadata-only inspection.
4. OSV: vulnerability advisory/version intelligence; scanner fixed version is optional. JFrog Xray is an interchangeable production input and may have source-specific advisory IDs/ranges. Do not conflate advisory IDs without mapping.
5. Reusable index/cache is optional, after comparing latency and accuracy of hosted retrieval vs local metadata processing. Do not build a full database before need is demonstrated.

### Probe evidence log (required for each live case)
- Case ID, timestamp, source branch/commit, application/sample Maven coordinates and current Boot version
- Scanner source and raw source reference (redact credentials), exact advisory ID and affected package version
- Known fixed version/range OR explicit missing value
- Candidate release enumeration source, chosen release(s), managed catalog/BOM evidence URL
- Candidate selected dependency version and **path**, origin of management, source URL/API response excerpt
- OSV/Xray advisory affected-version evidence, including unknown/contradictions
- Classification (per vulnerability, per Boot release), why, explicit gaps
- API calls, request size, bytes transferred/cache use, latency, Maven calls, JAR downloads and disk overhead
- Final reproduction instructions, PASS/PARTIAL/FAIL/NOT RUN; never claim an unexecuted probe passed

### Performance/volume evaluation
After correctness on the four cases, replay 10, 50, and 100 unique vulnerability findings across 5, 20, and 100 eligible published releases (where they actually exist). Track warm/cold cache, API requests, transfer size, runtime, disk writes, response completeness, error/rate-limit behavior, and memory. Deduplicate packages/advisories; batch OSV lookups as supported, reuse per-release metadata, compare all findings together. Prefer documented remote services and bounded caching. This is an evaluation plan, not a performance promise.

### Exit / next decision
Compare **hosted-data-only**, **hosted + small Maven fallback**, and **pre-indexed Boot release metadata** on correctness, coverage, runtime and disk usage. Choose the least complex method satisfying evidence completeness; leave actual remediation and new-vulnerability scanning outside this feasibility scope.

Sources:
- https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html
- https://docs.deps.dev/api/v3/
- https://google.github.io/osv.dev/api/
- https://jfrog.com/help/r/jfrog-rest-apis/xray-rest-apis
