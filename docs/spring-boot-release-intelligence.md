# Spring Boot Release Intelligence CLI

`sbri` evaluates actual Maven-selected dependency inventories with the selected
S4 pipeline: A5 TGF → CycloneDX 1.5 → security scanner → comparison.

Prerequisites: Python 3.11+, Java, Maven, and OSV Scanner 2.x on `PATH`.

```bash
./sbri evaluate --project ./application --range 3.3.4..3.3.8
./sbri evaluate --project ./application --releases 3.3.5,3.3.7,3.3.8 \
  --profiles production --modules service --output build/sbri
```

Outputs are `result.json`, `report.html`, and referenced files under
`evidence/`. Exit 0 means all requested releases were assessed, 3 means a
machine-readable partial result was produced, and 2 means configuration or
baseline execution prevented a usable result. Scanner exit 1 means findings,
not failure.

Optional JSON configuration keys are `maven`, `settings`, `profiles`, `modules`,
`scopes`, `scanner`, and `timeout`. CLI values take precedence. A CI job or
autonomous agent should consume `result.json`; HTML is rendered only from that
same representation. The schema is
`spring_boot_release_intelligence/result-schema-v1.json`.

For a trusted external scanner, supply one CycloneDX 1.5 vulnerability report
per release:

```bash
./sbri evaluate --project . --releases 3.3.8 \
  --scanner-report 3.3.4=base.cdx.json \
  --scanner-report 3.3.8=candidate.cdx.json
```

The reader correlates `vulnerabilities[].affects[].ref` with SBOM component
references and retains identities, aliases, severity and fixed evidence when
present. This demonstrates standards interchange, not a validated JFrog/Xray
integration.

Known limitations: security ranking does not establish compatibility; private
repository policy, very large reactors, corporate-parent ownership and every
WAR/provided-scope combination remain unverified. Missing fixed evidence stays
unknown. The utility never removes overrides or edits the source project.

The retained implementation validation is at
`docs/experiments/spring-boot-release-intelligence/implementation-evidence/run-20261016/`.
Its current OSV snapshot reported 80 baseline findings versus A7's historical
81 because one Medium finding was absent from the later advisory response; the
historical evidence was not rewritten.
