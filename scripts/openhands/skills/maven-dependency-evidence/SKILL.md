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

Use the repository's existing Maven tools before guessing version availability or dependency ownership.

- Inspect `pom.xml` and relevant parent/BOM and `dependencyManagement` entries to identify which layer controls a candidate; `mvn dependency:tree` shows the resolved graph, not all published versions.
- When a candidate version matters, establish the effective current version and its managing parent, BOM, property, or declaration. Verify the exact current artifact/version against repository metadata where available; an absent listing or failed lookup requires investigation, not an assumption of nonexistence.
- When current published versions matter, use the Maven Versions Plugin: `mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates` for dependencies and `mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:display-parent-updates` for parents. Maven repository `maven-metadata.xml` can show published versions of a named artifact. The plugin's suggested update is not necessarily every intervening published version, nor necessarily a production-stable release. Repository `maven-metadata.xml` lists published versions; its `latest` and `release` fields do not reliably classify production stability (milestones/RCs may appear there). Identify stable candidates using artifact-specific release conventions and authoritative project release information, not a universal numeric-only regex. When a candidate requires an upgrade, compare stable candidates against the effective current version before considering security and compatibility. Published or newer does not establish vulnerability remediation or compatibility.
- For known vulnerabilities, cross-check scanner/advisory affected ranges and fixed-version information with effective dependency versions. If available, use the OSV Scanner supplied in the task environment.
- Verify materially consequential release or compatibility claims with current authoritative project/repository sources when reasonably available. Distinguish failed retrieval from evidence of nonexistence.
- Prefer focused, read-only investigation first. Commands may download to Maven's cache; do not use `versions:set`, `versions:use-*`, or other mutating commands merely to discover options.

Select solutions independently, applying the task constraints and general engineering guidance. This Skill supplies evidence access, not a prescribed remediation strategy.

- Treat scanner output as valid clearance evidence only when execution and dependency extraction are complete. Zero reported findings paired with unresolved modules, extraction errors, missing dependency coverage, or a failed command is **incomplete/unknown**, never proof of zero vulnerabilities. Compare effective affected coordinates (including group ID) and report unresolved coverage honestly.
