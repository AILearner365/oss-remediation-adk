# Strengthened feasibility report

## Previous conclusion and weakness

Commit `a325aa4b2749de30450c2292a331988e83a0f34b` recommended A2 plus narrow A1
and OSV. Its live observations were useful, but `_cells()` assigned feasibility
statuses directly, OSV reasoning considered any historical fixed event
sufficient, Maven coverage centered on one successful starter/Tomcat fixture,
and its replay benchmark did not measure scale.

## New evidence

Twenty-three deterministic tests pass: the original six plus identity comparison,
graph traversal, all five feasibility status derivations, explicit affected
versions, introduced/fixed/last-affected boundaries, multiple and reintroduced
intervals, known/unknown qualifiers, and contradictory advisory events.
The four A5 additions cover TGF path parsing, download-purpose inventory,
transfer-metric semantics and the pinned isolated collector contract.

The fresh live run completed 16 original cells and 28 expanded approach/scenario
cells. All seven real Maven scenarios passed their expected version and path
checks. This independently demonstrates mediation, direct and managed overrides,
profile activation, exclusions, and multi-module resolution. A1 and A3 were
correctly `NOT_SUPPORTED` for those application-specific questions.

The multi-dependency comparison observed:

- Tomcat: 1 original finding addressed at Boot 3.3.5/3.3.6 and 3 at
  3.3.7/3.3.8; 32 or 30 remain affected.
- Spring Web: 1 of 2 original findings addressed in every candidate; 1 remains.
- Logback Core: 0 of 6 addressed through Boot 3.3.7; Boot 3.3.8 addresses 2 and
  leaves 4.
- SnakeYAML 2.2 did not change and had no original findings in this observation.
- No candidate introduced a newly reported finding for these four artifacts.

Each absent original ID was upgraded to `ADDRESSED` only after its real advisory
placed the candidate outside all safely interpreted affected intervals. No
unknowns occurred in this live set, but deterministic contradictory/unsupported
cases return `UNKNOWN`.

## Performance and reliability

The fresh-cache run took 140.438 seconds: A1 9.830 seconds, A2 127.503 seconds,
A3 0.638 seconds, and combined comparison 1.852 seconds. It made 149 network
requests, transferred 3,600,119 bytes, recorded 162 cache hits, and had zero
failures/retries. The final warm-cache run took 115.640 seconds, made zero
network requests, and spent 114.569 seconds in Maven. Warm candidate comparison
computation took 0.0064 seconds over already acquired evidence. These are bounded
workload measurements, not a scalability extrapolation.

## Changed conclusions

The 4×4 labels did not change, but their confidence improved materially. A2's
application-resolution capability is no longer inferred from one favorable
fixture. A4 remains capable, but deps.dev still adds corroboration rather than a
required fact. The expanded results strengthen—not broaden—the recommendation:
Maven is the effective-model authority and OSV interpretation must remain
conservative.

## Remaining limitations

- The Maven-version comparator supports common numeric and known qualifier forms
  but returns unknown for unfamiliar semantics; using Maven ComparableVersion
  directly remains a production requirement.
- Repository mirrors, authentication, optional dependencies, classifiers,
  relocations, imported-BOM precedence conflicts and more complex profile
  activation remain untested.
- Only four resolved dependencies and five Boot versions were compared.
- Build/runtime compatibility and whole-application candidate scans were not
  executed, so vulnerability counts cannot select a release.
- Source mutation, withdrawal and rate limiting need longer-running tests.

## A5 addendum — 2026-10-14

A5 used Maven's pinned dependency-tree graph collector with isolated disposable
repositories. It matched an independently rerun A2 on all 32 selected-version
and path comparisons, passed C1–C4 and all seven expanded scenarios, and
reproduced every frozen v2 per-finding vulnerability classification.

For the same 16-resolution workload, isolated A2 took 218.652 s fresh and
161.863 s warm; A5 took 183.472 s fresh and 162.453 s warm. A5 was 35.180 s
(16.1%) faster fresh but 0.590 s (0.4%) slower warm. The fresh A2 cache was
61,247,561 bytes; A5 was 21,134,449 bytes, a 40,113,112-byte (65.5%) reduction.
A2 downloaded seven application JARs (4,725,608 bytes), including reactor/build
artifacts needed by its multi-module install. A5 downloaded none. A5 still
required 50 plugin/bootstrap JARs (14,912,596 bytes), 460 POMs (6,118,943
bytes), and 510 successful Maven transfer events reporting 21,091,327 bytes.
Warm A5 added no files. Network values came from a separate non-quiet A5
telemetry pass so the fair A2/A5 timings both used quiet Maven output.

Maven did not expose transport-level HTTP request counts. A2 ran with the
existing quiet command, so its transfer-event/byte metrics are unavailable;
no bandwidth saving is claimed from the cache-size difference. See
[a5-comparison-report.md](a5-comparison-report.md) for the full comparison.

## A6 addendum — 2026-10-14

A6 used the pinned Maven `dependency:collect` goal and parsed its flat mediated
artifact records. It matched the freshly rerun A5 complete dependency set and
versions on 32/32 assertions, detailed type/classifier/scope/version records on
16/16 assertions, and 64/64 frozen vulnerability result-set assertions. C1–C4
and all seven expanded selection scenarios were `PROVEN`.
The multi-module command included the reactor library and applied the app's
10.1.31 dependency management without installing module artifacts.

On the identical quiet 16-resolution workload, A2 took 183.180 s fresh and
142.750 s warm, A5 took 177.746 s and 150.766 s, and A6 took 176.896 s and
151.175 s. Relative to A5, A6 was 0.851 s (0.48%) faster fresh and 0.409 s
(0.27%) slower warm: negligible in this workload. Both A5 and A6 produced an
identical 21,134,449-byte cache containing 460 POMs (6,118,943 bytes), no Maven
metadata files, no application dependency JARs, and 50 plugin/bootstrap JARs
(14,912,596 bytes). Separate A6 telemetry recorded 510 successful transfer
events and 21,091,327 Maven-reported bytes fresh, and zero warm. HTTP request
counts remain unavailable.

The result supports flat selected artifacts as sufficient for the tested
vulnerability-coverage calculation. It does not establish path provenance,
reachability explanation, competing-path diagnosis, or compatibility. Because
A6 offered no material resource advantage while A5 retains those diagnostic
paths, A5 remains preferred. See
[a6-comparison-report.md](a6-comparison-report.md).
