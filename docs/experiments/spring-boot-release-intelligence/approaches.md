# Experimental approaches — strengthened evaluation

The experiment remains isolated from production and OpenHands. Version 2 adds
independent executable checks: a cell status is derived from its recorded check
outcomes, never assigned directly. `PASS` means the observed value matched an
expectation established before execution; `FAIL` is contradictory evidence;
`UNAVAILABLE` means the approach lacks required information; `NOT_EXECUTED`
means no observation exists. These map to `PROVEN`, `FAILED`,
`NOT_SUPPORTED`/`PARTIALLY_PROVEN`, and `NOT_TESTED` respectively.

## A1 — Spring Boot BOM + OSV

A1 reads real Spring Boot parent/import/property metadata and queries OSV. Its
OSV interpreter handles introduced/fixed/last-affected events, multiple and
reintroduced intervals, explicit affected versions, and a conservative subset
of Maven qualifier ordering. Unsupported qualifiers, malformed intervals,
non-ECOSYSTEM ranges, missing packages and contradictions return `UNKNOWN`.
Candidate absence from an OSV query is never itself proof of remediation.

A1 establishes managed defaults and advisory applicability, not application
inclusion, conflict mediation, active profiles, exclusions, or overrides. The
BOM parser remains deliberately narrower than Maven's effective model.

## A2 — Maven resolution + OSV

A2 delegates effective resolution to Maven's `dependency:tree` output and
validates selected versions and paths. Besides the original Boot/Tomcat fixture,
real published artifacts now exercise transitive mediation, direct overrides,
dependency-management overrides, active/inactive profiles, exclusions and a
two-module reactor. Expectations are explicit and compared with command output.

## A3 — deps.dev

A3 records public version metadata, advisory keys and hosted dependency graphs.
The live graph corroborates the published Boot starter path, but cannot establish
an application's effective model or OSV affected intervals. It is therefore
partial for C1–C3 and unsupported for C4 and the expanded application scenarios.

## A4 — combined

A4 preserves source precedence: Maven for effective application resolution,
Boot metadata for management provenance, OSV for advisory applicability, and
deps.dev only for hosted corroboration. Integration reuses results and does not
convert weaker hosted inference into application evidence.

## A5 — isolated Maven metadata-only collection + BOM + OSV

A5 invokes the pinned Maven-native
`org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree` collector with a
dedicated `maven.repo.local`. `dependency:collect` was rejected because its
flat output did not preserve paths; a direct Resolver integration was not chosen
because Maven's existing graph builder met the experiment needs with less model-
building/bootstrap code. A5 never implements mediation itself.

The same Boot releases, overrides and seven expanded fixtures were executed.
For multi-module input, A5 uses one reactor graph command with `-pl app -am`
instead of installing module JARs. An independent empty-project control
attributes the pinned plugin's binary closure. A5 downloaded no selected
application-dependency JARs, but it did download 50 plugin/bootstrap JARs
(14,912,596 bytes); therefore the accurate claim is “no application dependency
JARs,” not “no JARs.”

OSV conclusions reuse the frozen v2 advisory evidence so A2/A5 classification
differences cannot be caused by source mutation.

## Classification safeguards

Vulnerability verdicts are `ADDRESSED`, `STILL_AFFECTED`, `UNKNOWN`, or
`ABSENT_ON_EXAMINED_PATH`; `APPLICATION_CONTROLLED` remains separate provenance.
New candidate findings are separate from original-finding coverage. Neither a
higher version nor a lower vulnerability count proves compatibility or makes a
candidate preferable.
