# Live cases and pre-implementation expectations

All four cases use published Spring Boot 3.3.4 as baseline and 3.3.5–3.3.8 as
candidates. The common sample application uses
`org.springframework.boot:spring-boot-starter-web`; C4 additionally pins Tomcat.
This keeps comparisons reproducible while testing four distinct evidence
questions against a real artifact and real advisories.

## C1 — Boot-managed dependency

Artifact: `org.apache.tomcat.embed:tomcat-embed-core`. Expected managed versions
are 10.1.30, 10.1.31, 10.1.33, 10.1.34, and 10.1.34 for Boot 3.3.4–3.3.8.
The primary regression advisory is `GHSA-qvf5-hvjx-wm27`; the live baseline OSV
ID set is captured as the original finding set. Success requires baseline and
candidate managed versions, property/import provenance, advisory ranges, and a
per-original-ID verdict. A1 and A4 should support this directly; A2 adds actual
selection; A3 may expose package/advisory facts but cannot attribute management.

## C2 — resolved transitive dependency

Path under test:
`spring-boot-starter-web -> spring-boot-starter-tomcat -> tomcat-embed-core`.
Success requires Maven/deps.dev-observed baseline and candidate paths, effective
versions and OSV applicability. A2 and A4 are expected to prove the fixture's
effective result. A1 lacks inclusion/path evidence. A3 succeeds only to the
extent its actual public dependency graph represents this path.

## C3 — missing supplied fixed version

The input finding for `GHSA-qvf5-hvjx-wm27` deliberately has no scanner-supplied
fixed version; no fixed value is synthesized from version ordering. The probe
must inspect the real OSV affected ranges/events. If those events sufficiently
establish applicability, it may classify the tested version; if response data
is missing, contradictory or incomplete, the result must be `UNKNOWN`.
Success is correct uncertainty handling plus preservation of advisory content
and the absent input field—not necessarily an `ADDRESSED` verdict.

## C4 — application-controlled override

The sample application imports Boot's BOM but sets `tomcat.version=10.1.30`.
Candidates therefore advertise newer managed Tomcat defaults while Maven should
continue to select 10.1.30 on the examined starter path. Success requires both
versions, the dependency path, override provenance and a separate advisory
status. Expected application result is
`APPLICATION_CONTROLLED + STILL_AFFECTED` for
`GHSA-qvf5-hvjx-wm27`. A1 and A3 cannot independently establish the effective
application override.

## Reproduction prerequisites and commands

Prerequisites are Python 3, Java, Maven, network access to Maven Central, OSV
and deps.dev, and approximately 100 MB bounded cache headroom. Commands (added
by the implementation) are:

```bash
python3 -m unittest tests.test_spring_boot_release_intelligence_contract \
  tests.test_spring_boot_release_intelligence
python3 -m spring_boot_release_intelligence.cli run-live \
  --output docs/experiments/spring-boot-release-intelligence/evidence/latest
```

Live source contents can change. Historical counts are regression observations,
not mutable expectations; discrepancies are retained in the evidence report.
