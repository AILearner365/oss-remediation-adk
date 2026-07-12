# Enterprise OSS Remediation Platform
## Software Requirements Specification (SRS)

**Status:** Phase 1 Draft — Foundation  
**Repository:** `AILearner365/oss-remediation-adk`  
**Baseline branch:** `mvp-3-pr-summary-integration`  
**Document branch:** `docs/srs-requirements-foundation`

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification establishes the authoritative requirements baseline for an enterprise platform that remediates OSS vulnerabilities in Java Maven Spring Boot multi-module projects.

This document defines **what the platform is expected to provide**. It does not prescribe the architecture, agent topology, orchestration model, prompts, persistence mechanism, state-management approach, or detailed implementation design.

Once approved, this SRS shall be used to:

- evaluate architecture completeness against approved requirements
- evaluate detailed design completeness and consistency
- guide implementation scope and release planning
- derive verification, test coverage, and acceptance criteria
- assess release readiness
- identify deferred, partially satisfied, or unmet requirements
- maintain traceability from requirements through architecture, design, implementation, testing, and release acceptance

### 1.2 Document Scope

Phase 1 establishes the stable business and product foundation for the SRS. It covers:

- business context
- problem statement
- product vision
- business goals
- users and stakeholders
- business concepts and definitions
- external systems and system context
- platform scope
- initial release scope
- platform evolution scope
- success definition
- guiding principles

Detailed functional and non-functional requirements will be added in later phases using uniquely identified, atomic, testable, and traceable requirement statements.

---

## 2. Business Context

Enterprise Java teams routinely receive OSS vulnerability findings affecting application dependencies, Maven plugins, parent POMs, BOMs, dependency-management entries, and transitive dependency paths.

In a Maven multi-module project, a single vulnerable component may be declared or controlled at different levels of the project hierarchy and may affect multiple modules. Remediation therefore requires more than selecting a newer version. It requires understanding dependency origin, module relationships, compatibility constraints, project policies, validation scope, build stability, residual risk, and technical review expectations.

Traditional remediation is often manual, repetitive, time-consuming, and dependent on individual developer experience. Teams may also lack consistent evidence explaining why a remediation was selected, why alternatives were rejected, what validation was performed, and what risk remains.

The platform is intended to reduce this burden by supporting safe, validated, reviewable, and traceable remediation while preserving engineering control and technical accountability.

---

## 3. Problem Statement

Given a Java Maven Spring Boot multi-module repository containing OSS vulnerabilities, the platform must support the end-to-end remediation lifecycle from repository intake through vulnerability analysis, remediation, validation, completion-state determination, pull-request delivery, and technical review continuation.

The platform must reduce manual effort and remediation time without compromising project stability, configured policy boundaries, validation quality, traceability, or reviewability.

The platform must also preserve sufficient context and evidence so that developers and reviewers can understand, question, continue, and refine a remediation after the initial execution has completed.

---

## 4. Product Vision

The Enterprise OSS Remediation Platform shall provide the safest practical validated remediation with the least practical manual effort.

The platform is intended to support:

- autonomous remediation initiated through CI/CD execution
- user-initiated remediation through an interactive interface
- continuation of an existing remediation workspace after an autonomous or interactive execution
- technical review, follow-up questions, additional guidance, and post-review remediation updates
- persistent operational history that supports auditability, product improvement, and future expansion of supported remediation scenarios

The initial release will focus on Java Maven Spring Boot multi-module repositories, GitHub, and GitHub Actions. The broader platform vision includes later support for additional source-control systems, CI/CD platforms, vulnerability providers, validation integrations, build systems, languages, and remediation boundaries.

---

## 5. Business Goals

The platform is intended to achieve the following business goals:

1. Reduce the manual effort required to remediate OSS vulnerabilities.
2. Safely automate OSS vulnerability remediation while maintaining engineering quality.
3. Accelerate remediation without compromising build stability, validation, traceability, or review quality.
4. Produce remediation outcomes that developers and reviewers can understand, challenge, and continue refining.
5. Support full remediation when possible and safe partial remediation when complete remediation is outside the permitted boundary.
6. Clearly identify cases where automated remediation cannot safely proceed and human review is required.
7. Retain sufficient operational history to support auditability, future product improvements, and expansion of supported remediation scenarios.
8. Provide a stable requirements baseline against which architecture, design, implementation, testing, and release acceptance can be reviewed.

---

## 6. Users and Stakeholders

### 6.1 Primary User

The primary user is a Java developer responsible for maintaining a Java Maven Spring Boot multi-module repository.

The primary user may:

- trigger remediation through a CI/CD workflow
- start remediation through an interactive interface
- reopen an existing remediation workspace
- review findings, decisions, evidence, and validation results
- provide follow-up guidance
- request additional remediation
- review or update a related pull request

### 6.2 Additional Stakeholders

- pull-request reviewers and technical leads
- application teams
- platform and build-engineering teams
- security and compliance teams
- policy administrators
- platform administrators
- release and quality-assurance teams

---

## 7. Business Concepts and Definitions

### 7.1 Project

A broader application or product that may contain one or more source-code repositories.

### 7.2 Repository

A source-code repository containing a Java Maven Spring Boot multi-module project or a component of a broader project.

### 7.3 Reference Branch

The branch supplied as the authoritative starting point for remediation and the intended target branch for any remediation pull request.

### 7.4 Maven Multi-Module Project

A Maven project composed of a parent or aggregator project and one or more child modules that participate in a Maven reactor build and may share dependency, plugin, parent, BOM, or dependency-management configuration.

### 7.5 Vulnerability Finding

A reported OSS security issue associated with a dependency, plugin, component, version, or dependency path within the repository.

### 7.6 Severity Threshold

The minimum vulnerability severity included in a remediation workflow.

The default threshold for the initial release is **High**, which includes both Critical and High findings. A user may configure the threshold to include Medium or Low findings, in which case all higher severities are also included.

### 7.7 Policy

A configurable rule or boundary that governs what the platform may consider, modify, validate, accept, defer, or escalate during remediation.

Policies may include permitted upgrade ranges, blocked versions, allowed remediation types, accepted risk levels, excluded dependencies, and organization-specific governance rules.

### 7.8 Validation Scope

The complete set of verification activities required to evaluate whether a remediation is acceptable.

The validation scope may include Maven dependency resolution, reactor build execution, compilation, unit tests, configured integration tests, vulnerability re-scanning, dependency-conflict checks, scope-compliance checks, and repository-specific custom validations.

### 7.9 Remediation Boundary

The configured limit on the types of changes the platform is permitted to make for a repository or execution.

For the initial release, Java source-code changes and upgrades that require source-code changes are outside the default remediation boundary.

### 7.10 Remediation Workspace

A persistent record of one remediation workflow for a specific repository and reference branch.

A workspace retains the context needed to understand and continue that remediation, including:

- workflow inputs
- configured policies
- validation scope
- vulnerability findings
- remediation decisions
- applied changes
- validation results
- evidence and logs
- completion state
- remediation branch and pull-request linkage
- reviewer discussions
- subsequent remediation iterations

A repository may have multiple remediation workspaces over time. Separate branches may have separate active workspaces.

### 7.11 Remediation Iteration

One execution or revision of remediation activity within a remediation workspace.

### 7.12 Completion State

The single defined outcome assigned to a remediation workflow after the platform has completed the applicable analysis, remediation, validation, and decision activities.

The defined completion states are:

- Fully Remediated
- Partially Remediated
- Human Review Required

### 7.13 Review-Ready

A remediation is review-ready when it contains sufficient implementation detail, evidence, validation results, decision history, rationale, rejected alternatives, residual-risk information, and reviewer guidance for technical evaluation without relying on hidden workflow knowledge.

### 7.14 Reviewer Feedback

Questions, comments, constraints, recommendations, approvals, or requested changes provided after an initial remediation outcome has been produced.

### 7.15 Vulnerability Provider

An external or integrated capability that identifies OSS vulnerability findings and may be used both for initial discovery and post-remediation verification.

### 7.16 Validation Provider

An external or integrated capability that performs a configured verification activity required by the validation scope.

---

## 8. External Systems and System Context

The platform interacts with external systems and tools but does not replace them.

### 8.1 Source-Control System

The source-control system provides repository access, branch operations, commit history, and pull-request capabilities.

The initial release context is GitHub. Future platform releases may support Bitbucket and other source-control systems.

### 8.2 CI/CD Platform

The CI/CD platform provides an automated entry point for remediation execution.

The initial release context is GitHub Actions. Future platform releases may support TeamCity and other CI/CD platforms.

### 8.3 Maven Build Environment

Maven provides project-model resolution, dependency resolution, reactor build execution, plugin execution, and test-goal invocation for the Java multi-module project.

### 8.4 Vulnerability Providers

Vulnerability providers supply findings used for initial vulnerability discovery and post-remediation verification.

The initial release may use a configured default provider. The broader platform must accommodate later pluggable providers and existing vulnerability reports.

### 8.5 Validation Providers

Validation providers execute repository-specific or organization-specific checks beyond the default Maven and vulnerability-validation baseline.

### 8.6 Large Language Model Services

LLM services provide contextual reasoning where deterministic analysis alone is insufficient. Their use does not replace deterministic build, scan, validation, or repository evidence.

### 8.7 Interactive Interface

An interactive interface, such as an ADK-supported web or terminal experience, allows a user to start a new remediation or continue an existing remediation workspace.

---

## 9. User Journeys and Entry Points

### 9.1 CI/CD-Initiated Remediation

A remediation workflow may be initiated through GitHub Actions using the repository, reference branch, severity threshold, policies, and validation configuration applicable to that execution.

The workflow runs without required user interaction during execution. After completion, the resulting remediation workspace remains available for later review and continuation through an interactive interface.

### 9.2 User-Initiated Remediation

A user may initiate a new remediation workflow through an interactive interface using the same core repository and branch context used by the CI/CD entry point.

The workflow may perform autonomous analysis, remediation, and validation before the user continues with review questions or additional guidance.

### 9.3 Existing Workspace Continuation

An authorized user may reopen an existing remediation workspace, including months after the original execution, to:

- review prior findings and decisions
- inspect evidence and validation outcomes
- ask questions
- provide additional constraints or reviewer guidance
- request further remediation
- update an existing pull request
- create a pull request when one did not previously exist and a safe remediation later becomes available

### 9.4 Workspace Collaboration Context

Multiple authorized users may access the same workspace over its lifecycle. The platform must prevent conflicting active remediation updates within the same workspace.

Different users may work concurrently on:

- different repositories
- different branches of the same repository
- different remediation workspaces

Duplicate active remediation for the same repository and reference branch must be controlled. The exact behavior will be defined in a later requirement phase.

---

## 10. System Scope

### 10.1 In Scope for the Platform

The platform scope includes:

- repository and reference-branch intake
- remediation workspace creation and persistence
- vulnerability discovery or findings ingestion
- severity and policy configuration
- Maven multi-module project analysis
- dependency-origin and dependency-control analysis
- OSS dependency remediation
- Maven plugin remediation
- parent POM, BOM, dependency-management, direct-dependency, and transitive-dependency remediation
- configured validation execution
- remediation completion-state determination
- remediation branch and pull-request delivery
- technical review support
- reviewer-feedback continuation
- evidence, decision-history, validation-history, and audit retention
- operational-history collection for future product improvement

### 10.2 Outside the Initial Remediation Boundary

The initial release does not perform:

- Java source-code modifications
- business-logic changes
- API redesign
- database-schema changes
- application architecture redesign
- feature development
- functional enhancements unrelated to OSS remediation
- Java or Spring Boot major upgrades when they require source-code changes

These boundaries are configurable platform concepts and may be expanded in later releases.

---

## 11. Initial Release Scope

The initial release includes:

- GitHub repositories
- GitHub Actions as the CI/CD entry point
- an ADK-supported interactive entry point
- Java projects
- Maven builds
- Spring Boot applications
- Maven multi-module project structures
- Critical and High vulnerabilities by default
- configurable severity threshold through Low
- OSS dependency and Maven plugin remediation
- parent POM, BOM, dependency-management, direct-dependency, and transitive-dependency control analysis
- configurable remediation policies
- a default Maven and vulnerability-validation baseline
- support for repository-specific validation configuration
- remediation without Java source-code changes
- full remediation, partial remediation, and human-review-required completion states
- remediation branch and pull-request creation when safe changes are available
- persistent remediation workspaces
- interactive review and post-review continuation
- decision, evidence, validation, and review-history retention

---

## 12. Platform Evolution and Extension Scope

Future platform releases may extend support to:

- Bitbucket and other source-control systems
- TeamCity and other CI/CD platforms
- existing vulnerability reports as workflow inputs
- multiple pluggable vulnerability providers
- configurable custom validation providers
- Java source-code remediation
- major Java, Spring Boot, or framework upgrades
- additional build systems
- additional programming languages
- additional remediation types
- broader project-level coordination across multiple repositories

These extension areas form part of the long-term platform direction. Their inclusion here does not classify them as initial-release deliverables.

---

## 13. Success Definition

A remediation workflow is considered complete only when it reaches exactly one defined completion state after the applicable remediation and validation activities have concluded.

### 13.1 Fully Remediated

All in-scope vulnerability findings are resolved and all required validations pass.

A review-ready pull request may be produced.

### 13.2 Partially Remediated

A safe subset of in-scope findings is resolved. All applied changes pass their required validations. Remaining findings are explicitly documented and remain unresolved because they fall outside the permitted remediation boundary or cannot be safely addressed under current constraints.

A review-ready pull request may be produced and must clearly identify the result as partial remediation.

### 13.3 Human Review Required

The platform cannot safely produce an automated remediation under the current inputs, policies, evidence, validation results, or remediation boundary.

The platform preserves and presents the findings, attempted approaches, rejected alternatives, validation outcomes, risks, and recommended next actions. A pull request is not required when no safe change is available.

The completion state does not end the lifecycle of the workspace. Authorized users may continue the workspace through review, additional guidance, and later remediation iterations.

---

## 14. Guiding Principles

All later requirements, architecture decisions, designs, implementations, and verification activities must remain consistent with the following principles.

### 14.1 Safety Before Automation

The platform must not apply changes that violate configured policies or introduce unacceptable risk merely to maximize vulnerability reduction.

### 14.2 Validation Before Completion

The platform must not report a successful or partial remediation without completing the validation scope applicable to the changes being delivered.

### 14.3 Evidence Before Recommendation

Remediation decisions and recommendations must be supported by repository, dependency, vulnerability, build, test, policy, or validation evidence.

### 14.4 Traceability by Default

Significant decisions must remain traceable from the original finding through remediation, validation, review, and final outcome.

### 14.5 Reviewability by Default

The platform must produce outcomes that a developer or reviewer can understand, question, and evaluate without relying on hidden reasoning or unavailable execution context.

### 14.6 Transparency

The platform must not hide failed validations, rejected options, remaining vulnerabilities, assumptions, limitations, or residual risks.

### 14.7 Configurability Over Hard-Coding

Enterprise policies, remediation boundaries, severity scope, and validation scope should be configurable rather than permanently embedded in platform behavior.

### 14.8 Deterministic Where Practical

The platform should prefer deterministic repository analysis, dependency resolution, scanning, building, testing, and validation wherever practical.

LLM reasoning should be used where contextual interpretation, comparison, explanation, or engineering judgment is required.

### 14.9 Human Collaboration When Needed

When safe automated progress is not possible, the platform must support human review and later continuation rather than forcing an unsafe result.

### 14.10 Extensibility Without Fundamental Redesign

The platform should accommodate new source-control systems, CI/CD systems, vulnerability providers, validation providers, remediation boundaries, build systems, and languages without requiring a fundamental redesign of the product model.

---

## 15. Phase 1 Review Status

Phase 1 establishes the business and product foundation of the SRS.

The following areas are ready for review and approval:

- business context
- problem statement
- product vision
- business goals
- users and stakeholders
- business concepts and definitions
- external systems and system context
- system scope
- initial release scope
- platform evolution scope
- success definition
- guiding principles

Detailed functional requirements, non-functional requirements, completion-state acceptance rules, deliverables, verification methods, and traceability mappings will be authored in subsequent phases.

---

## 16. Next Phase

Phase 2 will define uniquely identified and verifiable functional requirements for:

1. repository and reference-branch inputs
2. remediation workspace lifecycle
3. GitHub Actions execution
4. interactive initiation and continuation
5. vulnerability discovery and findings ingestion
6. severity and policy configuration
7. Maven multi-module analysis
8. remediation determination and execution
9. validation and post-remediation verification
10. internal remediation improvement before completion
11. completion-state determination
12. remediation branch and pull-request lifecycle
13. reviewer questions, feedback, and post-review updates
14. evidence, decision history, and rejected alternatives
15. auditability and retention
16. roles and access control
17. operational data collection and product evolution
18. platform extension points
