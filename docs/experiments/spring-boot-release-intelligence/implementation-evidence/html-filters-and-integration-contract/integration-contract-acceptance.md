# SBRI integration-contract acceptance

The reusable external contract is documented in
`docs/spring-boot-release-intelligence.md`. It describes only implemented CLI
options and keeps the integration independent of SBRI's Python internals.

Verified boundaries:

- Required Maven project and mutually exclusive range/explicit-release inputs.
- Optional Maven executable/settings, profiles, modules, scopes, severities,
  scanner, supplied CycloneDX reports, output path, timeout and JSON defaults.
- Canonical `result.json`, derived `report.html`, retained `evidence/`, schema
  location, important consumer fields and portable references.
- Exit `0` for complete assessment, `3` for usable partial assessment and `2`
  for configuration/baseline failure.
- OSV Scanner exit `1` remains a successful finding-bearing scan; missing
  output, timeout or other exit codes remain execution errors.
- Complete, partial, failure, malformed-config, external scanner-report, CLI
  precedence/option forwarding, schema, structured-error and evidence-path
  behaviors are covered by focused tests.
- SBRI owns evidence acquisition and security-only comparison. Consumers own
  strategy selection, compatibility reasoning, changes, build/tests and
  independent post-change validation.

The only CLI implementation adjustment moves JSON configuration and release
selection into the existing error boundary so malformed configuration reliably
returns the documented code `2` instead of escaping with a traceback. No new
status or exit code was introduced.
