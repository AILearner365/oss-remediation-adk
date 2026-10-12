---
name: maven-dependency-evidence
description: Use when examining Maven POMs, dependency conflicts, available or resolved library versions, Maven parent and BOM management, or Java dependency vulnerabilities.
triggers:
  - maven
  - dependency
  - dependencies
  - vulnerability
  - vulnerabilities
  - pom.xml
---

# Maven dependency evidence

## Evidence-driven dependency decisions

Treat remediation as a dependency-ownership, vulnerability-coverage, and compatibility problem, not simply a search for newer versions. Adapt the investigation to the decision at hand:

- **Framework/BOM-managed vulnerabilities:** Establish the effective managing parent, BOM, or property. Before changing versions, compare relevant stable parent/BOM candidates with the affected dependency versions they actually manage and the advisory fixed ranges. Identify which target findings each candidate is expected to resolve and which would remain; do not infer complete coverage from a newer parent version or a successful Maven build. If candidate resolution cannot be established read-only, treat the implementation as an explicit hypothesis to test, not a verified solution. Investigate whether compatible published framework releases resolve related findings together before selecting independent overrides.
- **Direct or residual vulnerable dependencies:** Identify the effective dependency path, advisory affected/fixed ranges, published compatible candidates, and what remains unresolved after each credible candidate.
- **Uncertain release or version:** Establish a consequential candidate's publication, resolvability, stability, and relevant compatibility *before selecting or editing*. A plausible version number or unrelated update report is not evidence of availability.
- **Compatibility-sensitive substitutions:** Assess dependency-family alignment, upstream/downstream consumers, runtime/API effects, and the resolved graph. An exclusion or `dependencyManagement` entry does not by itself establish a working replacement or preserve security coverage.
- **Contradictory evidence:** Identify the failed premise and reassess the strategy before repeating it. Revisit a disproven candidate only when new evidence supports it; preserve validated progress and the full original vulnerability/coverage scope.

Use available Maven, repository, advisory, and build evidence to settle material uncertainties. Compare meaningfully different credible approaches when useful, without forcing an arbitrary number of alternatives or a predetermined POM edit. Choose a proportionate defensible solution, then validate the dependency graph, security findings, compatibility, build, and tests as applicable.

Use the repository's existing Maven tools before guessing version availability or dependency ownership.

- Inspect `pom.xml` and relevant parent/BOM and `dependencyManagement` entries to identify which layer controls a candidate; `mvn dependency:tree` shows the resolved graph, not all published versions.
- When a candidate version matters, establish the effective current version and its managing parent, BOM, property, or declaration. Verify the exact current artifact/version against repository metadata where available; an absent listing or failed lookup requires investigation, not an assumption of nonexistence.
- When current published versions matter, use the Maven Versions Plugin: `mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates` for dependencies and `mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:display-parent-updates` for parents. Maven repository `maven-metadata.xml` can show published versions of a named artifact. The plugin's suggested update is not necessarily every intervening published version, nor necessarily a production-stable release. Repository `maven-metadata.xml` lists published versions; its `latest` and `release` fields do not reliably classify production stability (milestones/RCs may appear there). Identify stable candidates using artifact-specific release conventions and authoritative project release information, not a universal numeric-only regex. When a candidate requires an upgrade, compare stable candidates against the effective current version before considering security and compatibility. Published or newer does not establish vulnerability remediation or compatibility.
- For known vulnerabilities, cross-check advisory affected ranges and fixed-version information with effective dependency versions and retained vulnerability evidence. The agent's security evidence comes from retained findings and authoritative advisories; do not require agent-facing OSV execution. `validate-remediation` remains the full-project self-validation interface.
- **Before-edit candidate BOM inspection:** Retrieve the exact published candidate parent/BOM POM (for example with `mvn dependency:get -Dartifact=GROUP:ARTIFACT:VERSION:pom -Dtransitive=false` in a disposable context or from the configured Maven repository), inspect its properties, inherited parents, and imported BOMs. Correlate the candidate's managed versions with each originally affected artifact. A published BOM POM alone does **not** establish the target project's resolved graph: inspect local direct versions, overrides, exclusions, and dependency mediation. If these make resolution uncertain, use an isolated disposable copy to run Maven effective-POM/dependency-tree queries without modifying the working project. Do not use a guessed `help:effective-pom -Dartifact=...` invocation as proof of candidate resolution.
- **Candidate security prediction:** For each original relevant advisory, distinguish expected-fixed, expected-still-affected, and unknown based on candidate *resolved* versions and the advisory's actual affected/fixed range. When advisory data are unavailable or ambiguous, retain the uncertainty rather than declaring clearance. Use the independent validator only to establish actual post-change security results.
- **Compatibility investigation:** Consult Spring Boot release notes and dependency-management documentation for Java requirements, supported release family, and managed-library changes. Inspect affected modules and API consumers; where useful, run Maven Enforcer `dependencyConvergence` or `requireUpperBoundDeps` checks on a disposable candidate graph. Those rules identify selected graph issues, not full binary/runtime compatibility.
- Verify materially consequential release or compatibility claims with current authoritative project/repository sources when reasonably available. Distinguish failed retrieval from evidence of nonexistence.
- Prefer focused, read-only investigation first. Commands may download to Maven's cache; do not use `versions:set`, `versions:use-*`, or other mutating commands merely to discover options.

Select solutions independently, applying the task constraints and general engineering guidance. This Skill supplies evidence access, not a prescribed remediation strategy.

- Run `validate-remediation` when you need full-project build, test, vulnerability, and constraint validation. Review its findings and retained evidence to investigate failures. Incomplete dependency coverage is not proof of zero vulnerabilities.
