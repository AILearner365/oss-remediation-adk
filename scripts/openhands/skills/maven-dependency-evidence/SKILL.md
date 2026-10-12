---
name: maven-dependency-evidence
description: Use for concrete Maven evidence about effective POMs, dependency paths, direct and transitive versions, parent/BOM ownership, published versions, candidate managed effects, security ranges, and Java compatibility during Maven dependency work.
triggers:
  - maven
  - dependency
  - dependencies
  - vulnerability
  - vulnerabilities
  - pom.xml
---

# Maven dependency evidence

Use the relevant read-only Maven and repository methods below to establish facts for an engineering decision. The `dependency-remediation-decision` Skill owns strategy selection, original-finding coverage, and reassessment. These are **evidence methods, not a mandatory command checklist or an instruction to prefer any particular remediation**.

## What is currently resolved, and who controls it?

- Inspect root/module `pom.xml`, parent declarations, properties, imported BOMs, `dependencyManagement`, direct declarations, exclusions, and upstream paths.
- Use `mvn help:effective-pom` and targeted `mvn dependency:tree -Dverbose -pl MODULE` (plus `-am` or other appropriate reactor options when needed). The dependency tree describes actual resolution; it does **not** enumerate published versions. A BOM-managed version is not necessarily the version resolved in the target.
- Investigate conflicts between observed build output and external lookup rather than dismissing the locally resolved version.

## Which parent and dependency versions actually exist?

- For published parent updates: `mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:display-parent-updates`
- For published dependency updates: `mvn org.codehaus.mojo:versions-maven-plugin:2.22.0:display-dependency-updates`
- Inspect artifact-specific Maven repository `maven-metadata.xml` and authoritative release notes when consequential. Versions Plugin suggestions are **not exhaustive**, and metadata `latest`/`release` fields may include milestones or release candidates. Verify stability according to the artifact's release conventions.
- A failed lookup is not evidence of nonexistence. Check coordinates, repository configuration, resolution behavior, and alternative authoritative metadata before concluding a release is unavailable. Do not rely on remembered version numbers.

## What would a published parent/BOM candidate actually change?

- Retrieve its exact published POM, e.g. `mvn dependency:get -Dartifact=GROUP:ARTIFACT:VERSION:pom -Dtransitive=false` in a disposable context, or read it from the configured repository. Inspect inherited parents, properties, imported BOMs, and managed versions of affected artifacts.
- Account for the target project's direct versions, properties, overrides, exclusions, and Maven mediation. A published parent/BOM POM does not prove the target project's resolved graph.
- When necessary, use a disposable workspace copy to query candidate effective POMs and dependency trees **without editing the working project**. Do not use `help:effective-pom -Dartifact=...` as proof of a candidate graph.
- Prefer read-only investigation; Maven can populate its local cache. Do not run `versions:set` or `versions:use-*` merely to discover candidates.

## How reliable are security and compatibility claims?

- Cross-check original retained findings and authoritative advisories against expected **resolved** artifact versions and advisory affected/fixed ranges. Distinguish evidence, inference, and unknowns.
- Consult relevant framework release notes, Java requirements, dependency-management documentation, and affected module/API consumers. Maven Enforcer `dependencyConvergence` and `requireUpperBoundDeps` may help on a disposable candidate graph but do not prove runtime compatibility.
- `validate-remediation` supplies full-project self-validation and retained scanner/build/test evidence after implementation. Direct agent-facing OSV execution is not required; independent validation remains the acceptance authority. A partial or missing scan is not proof of zero findings.
