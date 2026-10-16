---
name: dependency-remediation-decision
description: Use for autonomous software dependency vulnerability remediation before consequential edits. Establish finding coverage and version ownership, investigate credible solutions using current evidence, select and validate a compatible remediation, and reassess disproven decisions.
triggers:
  - vulnerability
  - vulnerabilities
  - remediation
  - dependency
---

# Dependency-remediation decision

Own the engineering decision. The task contract controls goals and constraints; the `maven-dependency-evidence` Skill supplies Maven evidence methods, not a competing workflow. Preserve the **original findings** as the coverage baseline. This sequence describes what an informed decision must establish, not a mandatory command order, report, or predetermined strategy.

## 1. Understand the whole problem and version ownership

Account for each relevant original finding: affected coordinate, resolved version, advisory, module, dependency path, and version owner (direct version/property, parent, imported BOM, upstream dependency, or override). Distinguish a managed version from the version actually resolved. Investigate inconsistencies and incomplete evidence instead of silently assuming they are resolved.

## 2. Identify credible remediation mechanisms

Consider mechanisms that fit observed ownership: parent/framework/BOM upgrade for related managed dependencies; direct upgrade for independently declared versions; upstream upgrade, compatible override, exclusion, or replacement when justified. Do not assume a framework upgrade is always correct, force a fixed number of alternatives, or choose a strategy solely because it is easy to edit. Reject candidates that violate task constraints.

## 3. Establish candidate facts **before consequential edits**

For credible candidates, verify current publication, stability, availability, permitted release family, Java/runtime compatibility, and the versions the target project is expected to resolve. **When a parent/BOM controls a family of affected dependencies, investigate compatible published parent/BOM candidates and their actual managed effects before preferring individual overrides.** Inspect published managing POMs and imports; account for the project's direct versions, properties, overrides, exclusions, and mediation. Use a disposable Maven resolution experiment when static evidence cannot settle an important question. Do not treat remembered versions or an unsuccessful lookup as proof.

When the harness supplies `SBRI_PRE_EDIT_EVIDENCE`, treat it as bounded security evidence from independently materialized Spring Boot candidate graphs. Inspect its referenced canonical JSON or raw Maven/scanner evidence when a decision-critical detail is omitted. A security rank is not a mandatory upgrade choice, and unavailable SBRI evidence does not prove that framework upgrades are impossible. Reuse an applicable retained result unless the source, candidates, scanner configuration, or comparison assumptions changed.

## 4. Predict original-finding coverage and downstream consequences

For **every relevant original finding**, compare each credible candidate's expected resolved coordinate/version with authoritative advisory affected/fixed ranges. Distinguish expected-fixed, expected-still-affected, and unknown. Identify material compatibility, transitive, upstream/downstream, API and runtime risks. A newer published version, BOM declaration, or passing build does not establish security clearance.

## 5. Make a supported choice

Before editing, have enough evidence to explain in the normal working context: why the dependency is present, why the chosen mechanism applies, which version changes are expected, what original findings are expected to remain, compatibility risks, meaningful unknowns, and why this candidate is preferable. If deciding requires an experiment, identify the hypothesis and its limits. **Do not use successive scanner runs in place of readily available pre-edit ownership, published-version, candidate-effect, and coverage investigation.** No separate mandatory plan, questionnaire, approval, or report is required.

## 6. Implement, validate, and reassess

Implement with available OpenHands tools and preserve justified existing behavior. Run `validate-remediation` for whole-project build, tests, vulnerability findings, and constraints; inspect its retained evidence against the original coverage baseline. Distinguish an incomplete implementation from a disproven candidate premise. Reassess the relevant decision when evidence contradicts it; preserve validated progress. The harness-owned independent Stop Hook, not an agent declaration, determines final acceptance. Report material uncertainty and actual changes accurately.
