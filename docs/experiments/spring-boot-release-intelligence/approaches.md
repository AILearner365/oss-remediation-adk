# Experimental approaches

This document fixes the experiment design before implementation. The code is an
isolated feasibility probe, not a production Maven model builder or remediation
engine. Every conclusion carries source and request provenance.

## A1: Spring Boot BOM + OSV

A1 downloads published `spring-boot-dependencies` POMs from Maven Central,
walks their parent and imported BOM dependency-management metadata, resolves
ordinary nested `${property}` references, and queries OSV for the resulting
Maven package/version. It can establish a Boot-managed default and advisory
applicability. It cannot establish that an application includes the artifact,
Maven conflict mediation, active profiles, or an application's effective
override. Import ordering and parent inheritance are reported; this probe does
not claim complete Maven model resolution.

## A2: Maven resolution + OSV

A2 generates reproducible, case-specific sample applications and invokes the
installed Maven `dependency:tree` goal. It captures direct/transitive paths and
effective selected versions, then applies OSV evidence to the exact versions.
This delegates Maven mediation, parent/BOM processing, properties and active
dependency management to Maven. Results prove the supplied fixture and command,
not compatibility or every profile/environment of a production application.

## A3: deps.dev

A3 calls the public deps.dev v3 package-version and dependency endpoints. Direct
facts are version publication metadata, advisory keys, and the dependency graph
returned for that published artifact. Paths or candidate effects are labelled
inferences. deps.dev is not treated as an application-specific effective Maven
model, and an API failure is recorded separately from lack of capability.

## A4: combined

A4 reuses cached A1, A2 and A3 results. Maven's effective graph is authoritative
for application selection and paths; BOM evidence explains Boot management;
OSV establishes advisory applicability; deps.dev adds independent published
metadata/advisory corroboration. Conflicts remain explicit and weaker hosted
inferences never replace Maven evidence. The integration is worthwhile only if
it measurably adds coverage or provenance.

## Classification and success rules

`ADDRESSED`, `STILL_AFFECTED`, `UNKNOWN`, and
`ABSENT_ON_EXAMINED_PATH` describe vulnerability state.
`APPLICATION_CONTROLLED` is separately retained as effective-version
provenance, allowing (for example) `APPLICATION_CONTROLLED + STILL_AFFECTED`.
An empty query is not proof of remediation. A cell is `PROVEN` only when a live
executable probe supplies all evidence that approach claims; deterministic
tests alone cannot earn that status.

All HTTP responses are bounded and cached by URL/request hash. Measurements
include elapsed time, request/cache counts, response bytes, Maven time and
command outcome. No JFrog Xray code or evidence is used.
