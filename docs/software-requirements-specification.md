# Enterprise OSS Remediation Platform
## Software Requirements Specification

**Status:** Draft 0.1  
**Repository:** `AILearner365/oss-remediation-adk`  
**Baseline branch:** `mvp-3-pr-summary-integration`  
**Document branch:** `docs/srs-requirements-foundation`

---

## 1. Purpose

This Software Requirements Specification defines the authoritative requirements baseline for an enterprise platform that remediates OSS vulnerabilities in Java Maven Spring Boot multi-module projects.

This document defines **what the platform must provide**. It does not prescribe the architecture, agent topology, orchestration model, prompts, state-management mechanism, persistence technology, or detailed implementation approach.

The approved SRS shall be used to:

- evaluate architecture completeness
- evaluate detailed design completeness
- guide implementation scope
- derive verification and test coverage
- assess release readiness
- identify deferred or unmet requirements
- maintain traceability from requirements through delivery

---

## 2. Product Vision

The platform shall provide safe, validated, reviewable, and traceable OSS vulnerability remediation with the least practical manual effort.

It shall support autonomous remediation through CI/CD execution and user-driven remediation through an interactive interface. Both entry points shall operate on the same underlying remediation lifecycle and persistent remediation workspace.

The initial release shall focus on Java Maven Spring Boot multi-module projects, GitHub repositories, and GitHub Actions. The platform shall be structured for later extension to additional source-control systems, CI/CD platforms, vulnerability providers, build systems, languages, and remediation boundaries.

---

## 3. Problem Statement

Java development teams frequently receive OSS vulnerability findings that require dependency, plugin, parent, BOM, or dependency-management changes across complex Maven multi-module projects.

The remediation process requires more than selecting a newer version. A valid remediation must account for dependency origin, module relationships, compatibility, project policies, build stability, validation results, unresolved risk, and technical review expectations.

The platform is required to reduce the manual effort and time needed to perform this work while preserving engineering safety, project stability, traceability, and review quality.

---

## 4. Business Goals

The platform shall support all of the following business goals:

1. Reduce the manual effort required to remediate OSS vulnerabilities.
2. Safely automate OSS vulnerability remediation while maintaining engineering quality.
3. Accelerate remediation without compromising build stability, validation, traceability, or review quality.
4. Produce remediation outcomes that developers and reviewers can understand, challenge, and continue refining.
5. Retain sufficient operational history to improve future platform capabilities and supported remediation scenarios.

---

## 5. Primary Users and Stakeholders

### 5.1 Primary User

The primary user is a Java developer responsible for maintaining a Java Maven Spring Boot multi-module repository.

### 5.2 Additional Stakeholders

- pull-request reviewers and technical leads
- application teams
- platform and build-engineering teams
- security and compliance teams
- policy administrators
- platform administrators

---

## 6. Key Business Concepts

### 6.1 Project

A broader application or product that may contain one or more repositories.

### 6.2 Repository

A source-code repository containing a Java Maven Spring Boot multi-module project or a component of a broader project.

### 6.3 Reference Branch

The branch supplied as the authoritative starting point and intended pull-request target for a remediation workflow.

### 6.4 Remediation Workspace

A persistent record of one remediation workflow for a specific repository and reference branch.

A workspace retains the context required to understand and continue that remediation, including inputs, policies, findings, decisions, changes, validations, evidence, completion state, pull-request linkage, reviewer discussions, and later remediation iterations.

### 6.5 Remediation Iteration

One execution or revision of remediation activity within a workspace.

### 6.6 Review-Ready

A remediation is review-ready when it contains sufficient change details, evidence, validation results, decision history, rationale, unresolved-risk information, and reviewer guidance for technical evaluation without relying on hidden workflow knowledge.

---

## 7. Entry Points and User Journeys

### 7.1 CI/CD-Initiated Remediation

The initial release shall support execution from GitHub Actions.

The workflow shall run autonomously using the supplied repository, reference branch, configured policies, validation scope, and severity threshold.

Upon completion, the resulting remediation workspace shall remain available for later review and continuation through an interactive interface.

### 7.2 User-Initiated Remediation

A user shall be able to start a new remediation workflow from an interactive interface using the same core inputs supported by CI/CD execution.

The workflow may complete autonomously and then continue as an interactive review and remediation workspace.

### 7.3 Existing Workspace Continuation

An authorized user shall be able to reopen an existing remediation workspace, including months after its original execution, to:

- review prior findings and decisions
- inspect evidence and validation outcomes
- ask questions
- provide additional constraints or reviewer guidance
- request further remediation
- update an existing pull request
- create a pull request when one was not previously created and a safe remediation later becomes available

---

## 8. Initial Release Scope

The initial release shall support:

- GitHub repositories
- GitHub Actions execution
- Java projects
- Maven builds
- Spring Boot applications
- Maven multi-module project structures
- OSS dependency and Maven plugin remediation
- parent POM, BOM, dependency-management, direct-dependency, and transitive-dependency control analysis
- Critical and High vulnerabilities by default
- configurable severity threshold through Low
- remediation without Java source-code changes
- remediation that does not require major Java or major Spring Boot upgrades when those upgrades require source-code changes
- pull-request creation when safe changes are available
- full remediation, partial remediation, and human-review-required completion states
- persistent remediation workspaces
- interactive review and post-review continuation

---

## 9. Platform Extension Scope

The platform shall be designed to accommodate later support for:

- Bitbucket and other source-control systems
- TeamCity and other CI/CD platforms
- existing vulnerability reports as inputs
- pluggable vulnerability providers used for discovery and post-remediation validation
- configurable custom validation integrations
- Java source-code remediation
- major framework and runtime upgrades
- additional build systems
- additional languages
- additional remediation types

These extension points are part of the platform requirements but are not all required in the initial release.

---

## 10. Requirement Structure

Requirements will be maintained using stable identifiers and the following attributes:

| Attribute | Description |
|---|---|
| ID | Stable requirement identifier |
| Statement | Atomic, testable requirement expressed as `The platform shall...` |
| Priority | Must, Should, or Could |
| Release | Initial Release or Platform Extension |
| Verification | Test, inspection, demonstration, analysis, or review |
| Traceability | Architecture, design, implementation, and test references added later |

---

## 11. Functional Requirement Categories

Detailed functional requirements will be added under the following categories:

1. Repository and branch inputs
2. Remediation workspace lifecycle
3. CI/CD-triggered execution
4. Interactive execution and continuation
5. Vulnerability discovery and findings ingestion
6. Severity and policy configuration
7. Maven multi-module analysis
8. Remediation determination and execution
9. Validation and post-remediation verification
10. Internal remediation improvement before completion
11. Completion-state determination
12. Remediation branch and pull-request lifecycle
13. Reviewer questions, feedback, and post-review updates
14. Evidence, decision history, and rejected alternatives
15. Auditability and retention
16. Roles and access control
17. Operational data collection and product evolution
18. Platform extension points

---

## 12. Non-Functional Requirement Categories

Detailed non-functional requirements will include:

- safety
- correctness
- reliability
- security and privacy
- auditability
- traceability
- explainability and reviewability
- configurability
- extensibility
- maintainability
- scalability
- performance
- availability and recovery
- concurrency control
- enterprise integration

Performance, concurrency, availability, and recovery targets may remain explicitly marked as TBD until enterprise scale assumptions are approved. No numerical target shall be invented without an agreed operational basis.

---

## 13. Completion States

### 13.1 Fully Remediated

All in-scope vulnerabilities are resolved and all required validations pass.

A review-ready pull request may be created.

### 13.2 Partially Remediated

A safe subset of vulnerabilities is resolved. Applied changes pass their required validations. Remaining findings are explicitly documented and remain unresolved because they fall outside the permitted remediation boundary or cannot be safely addressed under current constraints.

A pull request may be created and shall be clearly identified as partial remediation.

### 13.3 Human Review Required

The platform cannot safely produce an automated remediation under the current inputs, policies, evidence, or permitted remediation boundary.

The platform shall preserve and present the findings, attempted approaches, rejected alternatives, validation outcomes, risks, and recommended next actions. A pull request shall not be required when no safe change is available.

---

## 14. Guiding Requirements Principles

The requirements and later implementation shall preserve the following principles:

- safety before automation
- validation before completion
- evidence before recommendation
- traceability for significant decisions
- reviewability by default
- transparency of failures, limitations, and residual risk
- configurability instead of hard-coded enterprise policy
- deterministic analysis and validation where practical
- use of LLM reasoning where contextual judgment is required
- human collaboration when safe automated progress is not available
- extensibility without fundamental platform redesign

---

## 15. Open Requirement Items

The following items are intentionally retained as requirement-level TBDs until sufficient operational information is available:

- numerical availability target
- supported concurrent active workspaces
- maximum supported repository and reactor size
- maximum remediation execution duration
- recovery-time and recovery-point objectives
- organization-specific retention duration
- final role model and permission matrix
- exact duplicate-workspace handling behavior: block, warn, queue, or resume
- branch commit-history policy across review iterations

These TBDs must be resolved before the affected requirements are baselined for release acceptance.

---

## 16. Next Authoring Phase

The next phase will add the first detailed, uniquely identified, testable requirements for:

1. platform inputs
2. GitHub Actions execution
3. remediation workspaces
4. Maven multi-module discovery and analysis
5. vulnerability severity scope
6. remediation boundaries
7. completion-state and partial-remediation rules
8. pull-request behavior
9. review continuation
10. evidence and operational-history retention
