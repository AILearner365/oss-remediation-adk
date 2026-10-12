---
name: dependency-remediation-decision
description: Use for autonomous OSS vulnerability remediation decisions before consequential dependency edits. Trace vulnerabilities to version owners, evaluate actual candidate effects and compatibility, select a defensible approach, and revise disproven premises.
triggers:
  - vulnerability
  - vulnerabilities
  - remediation
  - dependency
---

# Dependency-remediation decision

Own the remediation decision; the task contract determines scope and constraints. Use the `maven-dependency-evidence` Skill for Maven facts. Preserve the original findings as the coverage baseline. Never choose a version solely because it is newer or remembered as fixed.

## 1. Explain each finding before proposing the edit

Using retained vulnerability findings, establish affected coordinates, resolved version, advisory, affected module and dependency path. For Maven, obtain the *actual* dependency tree and effective POM and identify who determines the version: a direct declaration/property, parent, imported BOM, upstream dependency, or an override. Distinguish a BOM-managed version from the version actually resolved by the project. If the observed build and an external version lookup disagree, investigate the discrepancy rather than declaring an existing version impossible.

## 2. Identify the applicable remediation mechanism

Connect each root cause to credible approaches: parent/framework or BOM upgrade when it controls related versions; direct upgrade when independently declared; upstream upgrade, compatible override/exclusion, or replacement where justified. Reject hard-constraint violations immediately. Do not assume the framework is the solution or fabricate a fixed number of alternatives.

## 3. Establish real candidate effects *before changing the working POM*

Use domain evidence to verify publication, stability, permitted release family, availability, and Java requirements. For a parent/BOM candidate, examine its **published managing POM and imports**, then establish affected managed versions **and** any declarations that would override them in this project. For direct/upstream candidates, examine the introduced dependency path and expected effective version. When static inspection cannot establish resolution, use a *separate, disposable* Maven resolution experiment if proportionate; keep the task workspace unchanged until the decision.

## 4. Predict goal coverage and compatibility

For **every original relevant finding**, compare the candidate's expected *resolved* coordinate/version against authoritative advisory affected/fixed ranges. Separate expected resolved, expected remaining, and uncertain findings; do not equate publication, upgrade, or successful build with security clearance. Use retained validation findings and advisory sources, **not a direct OSV scanner command as a required investigation step**.

Evaluate supported Java/framework release alignment, dependency families, API/runtime changes, transitive conflicts and affected downstream modules. Documented compatibility is evidence; runtime compatibility still requires tests. Prefer a candidate that addresses related findings together when the evidence supports it.

## 5. Commit to the strongest supported decision

Before a consequential edit, be able to explain in normal working context: root cause; proposed mechanism and real candidate; expected resolved versions; advisory coverage and remaining findings; compatibility and constraints; material unknowns; why this candidate is preferred. Do not create a required report, special form or approval step. Obtain readily available decision-critical evidence before editing; if a hypothesis requires testing, say what the experiment can prove.

## 6. Implement and learn

Implement using existing OpenHands editing/build tools, then use `validate-remediation` for full-project self-validation. Retain original scope and inspect its complete findings and evidence. When results contradict a decision, identify the *specific failed premise* (availability, management, resolution, advisory coverage, compatibility or implementation) and return to the applicable decision step. Preserve validated work; do not repeat disproven candidates without new evidence. The existing independent Stop Hook, not the agent, determines final acceptance.
