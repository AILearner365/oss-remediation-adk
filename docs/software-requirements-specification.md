# Enterprise OSS Remediation Platform
## Software Requirements Specification (SRS)

**Status:** Draft  
**Version:** 0.3  
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

This document establishes the business, product, functional, non-functional, operational, security, verification, and traceability requirements for the Enterprise OSS Remediation Platform.

This specification defines the foundation for:

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
- assumptions
- business dependencies
- technology constraints

Sections or requirements that are not yet complete shall be explicitly marked as **Draft** or **TBD**. Detailed requirements shall use uniquely identified, atomic, testable, and traceable statements.

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

Duplicate active remediation for the same repository and reference branch must be controlled. The exact duplicate-workspace handling behavior remains **TBD** and must be resolved before the related requirement is baselined.

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

The following principles guide all requirements, architecture decisions, designs, implementations, and verification activities.

### 14.1 Safety Before Automation

The platform prioritizes safe remediation over maximizing vulnerability reduction through changes that exceed configured policies or acceptable risk.

### 14.2 Validation Before Completion

A remediation outcome is not considered complete until the applicable validation scope has been executed and its results are available.

### 14.3 Evidence Before Recommendation

Recommendations are grounded in repository, dependency, vulnerability, build, test, policy, and validation evidence.

### 14.4 Traceability by Default

Significant decisions remain traceable from the original finding through remediation, validation, review, and final outcome.

### 14.5 Reviewability by Default

Remediation outcomes are understandable, question-ready, and evaluable without reliance on hidden reasoning or unavailable execution context.

### 14.6 Transparency

Failures, rejected options, remaining vulnerabilities, assumptions, limitations, and residual risks remain visible to authorized users.

### 14.7 Configurability Over Hard-Coding

Enterprise policies, remediation boundaries, severity scope, and validation scope are treated as configurable platform concerns rather than fixed product behavior.

### 14.8 Deterministic Where Practical

Deterministic repository analysis, dependency resolution, scanning, building, testing, and validation are preferred wherever practical.

LLM reasoning supports contextual interpretation, comparison, explanation, and engineering judgment where deterministic methods are insufficient.

### 14.9 Human Collaboration When Needed

Human review and later continuation are supported when safe automated progress is not available.

### 14.10 Extensibility Without Fundamental Redesign

The platform is intended to accommodate new source-control systems, CI/CD systems, vulnerability providers, validation providers, remediation boundaries, build systems, and languages without fundamental redesign of the product model.

---

## 15. Assumptions

The specification currently assumes:

- the repository URL and reference branch identify an accessible and authorized repository state
- the supplied reference branch represents the intended remediation baseline
- the repository contains a valid Maven multi-module project structure
- the Maven build can be invoked in an available build environment
- required source-control, CI/CD, vulnerability-provider, validation-provider, and LLM credentials are available through approved enterprise mechanisms
- required network access to configured repositories, artifact sources, vulnerability providers, and validation systems is available
- repository-specific build prerequisites that cannot be discovered automatically are documented or configured by the owning team
- the owning team provides valid remediation policies and custom validation configuration when defaults are insufficient
- external systems return sufficiently accurate and timely information for the platform to use as evidence

If an assumption is not satisfied, the affected workflow may require configuration correction, retry, or human review rather than being treated as a successful remediation.

---

## 16. Business Dependencies

The platform's ability to execute and verify remediation depends on the availability and authorized use of:

- the source-control system hosting the repository
- the CI/CD platform used to initiate or execute remediation
- the Maven build environment and configured artifact repositories
- vulnerability providers used for discovery and post-remediation verification
- validation providers used for repository-specific or organization-specific checks
- approved LLM services used for contextual reasoning and interactive support
- enterprise identity, authorization, secret-management, network, and audit services
- repository-owner participation when configuration, policy, or human review is required

The platform does not control the correctness, availability, latency, or service limits of these external dependencies. Related functional and non-functional requirements shall define expected handling of dependency failures.

---

## 17. Technology Constraints

The following technology constraints apply to the current platform direction:

- the initial implementation uses the Agent Development Kit (ADK)
- the solution uses a multi-agent workflow model
- LLM capabilities are used for contextual reasoning, planning, explanation, and interactive review support
- deterministic tools and verifiable evidence remain authoritative for repository state, dependency resolution, vulnerability findings, builds, tests, and validation outcomes

These constraints identify mandated technology choices without prescribing the detailed architecture or agent design.

---

## 18. Open Items and TBDs

The following unresolved business and operational decisions must be completed before their related requirements are approved as part of a release baseline:

- exact duplicate-workspace behavior: block, warn, queue, or resume
- final role and permission model
- organization-specific workspace and audit retention duration
- numerical availability target
- supported concurrent active workspaces
- maximum supported repository and Maven reactor size
- maximum remediation execution duration
- recovery-time and recovery-point objectives
- branch commit-history policy across review iterations
