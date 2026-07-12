# Enterprise OSS Remediation Platform
## Capability Model

**Status:** Draft  
**Version:** 0.1

---

## 1. Purpose

This document translates the approved business requirements into a concise set of platform capabilities.

It does not define components, agents, services, APIs, storage, prompts, or implementation details. Those decisions belong in the Architecture and Detailed Design documents.

Each capability must trace back to the Business Requirements Baseline and later map forward to architecture, design, implementation, and tests.

---

## 2. Capability Map

### CAP-01 Repository Intake

Accept and validate repository, reference-branch, severity, policy, and validation inputs required to start remediation.

### CAP-02 Remediation Policy Management

Resolve default, repository-level, and execution-level remediation boundaries and rules.

### CAP-03 Validation Configuration

Resolve the required default and repository-specific validation scope for an execution.

### CAP-04 Workspace Management

Create, identify, persist, reopen, and retain remediation workspaces and their execution history.

### CAP-05 Workspace Collaboration Control

Allow authorized shared access while preventing conflicting active updates and uncontrolled duplicate remediation.

### CAP-06 Workflow Initiation

Start remediation through GitHub Actions or an ADK-supported interactive interface and continue an existing workspace.

### CAP-07 Vulnerability Discovery

Obtain current vulnerability findings through a configured provider or supported findings input.

### CAP-08 Severity and Scope Filtering

Determine which findings are in scope according to severity, policy, exclusions, and remediation boundary.

### CAP-09 Maven Multi-Module Analysis

Understand the Maven reactor, module hierarchy, parent relationships, dependency management, BOMs, plugins, and effective project model.

### CAP-10 Dependency Origin and Control Analysis

Identify why a vulnerable component is present and which project control point can safely change it.

### CAP-11 Remediation Option Determination

Determine applicable remediation options within the configured policy and project context.

### CAP-12 Remediation Selection

Select the safest practical remediation using compatibility, policy, risk, and validation considerations.

### CAP-13 Remediation Application

Apply permitted changes without modifying the reference branch directly.

### CAP-14 Failure Analysis and Iteration

Analyze unsuccessful attempts, retain the failure context, avoid repeating known failed approaches, and continue toward the safest achievable outcome.

### CAP-15 Maven Build Validation

Execute the required Maven reactor resolution, compile, package, and configured test goals.

### CAP-16 Vulnerability Revalidation

Verify the post-change vulnerability state and detect new or remaining in-scope findings.

### CAP-17 Custom Validation Integration

Execute repository-specific or organization-specific validations through configurable integration points.

### CAP-18 Completion-State Determination

Assign exactly one supported completion state based on findings, applied changes, policy, and validation outcomes.

### CAP-19 Remediation Branch Management

Create and maintain a dedicated remediation branch while protecting the supplied reference branch.

### CAP-20 Pull-Request Management

Create or update a review-ready full or partial remediation pull request when safe changes exist.

### CAP-21 Evidence and Decision History

Retain findings, options considered, selected and rejected decisions, attempts, tool results, validation evidence, and residual risks.

### CAP-22 Reporting and Reviewer Guidance

Produce concise remediation, validation, risk, and reviewer-facing summaries.

### CAP-23 Interactive Review Support

Answer reviewer questions from retained evidence and explain what changed, why it changed, and why alternatives were rejected.

### CAP-24 Feedback-Driven Continuation

Accept authorized reviewer guidance, revise remediation when permitted, rerun validation, and update the same workspace and related pull request.

### CAP-25 Identity and Authorization

Restrict repository, workspace, policy, review, and administrative actions to authorized users and integrations.

### CAP-26 Security and Sensitive-Data Protection

Protect repository content, credentials, logs, reports, conversations, and model interactions according to enterprise security expectations.

### CAP-27 Auditability

Retain significant user, system, policy, remediation, validation, and delivery events for later review.

### CAP-28 Operational Resilience

Handle external-system failures, interrupted executions, stale repository state, and other recoverable conditions without falsely reporting success.

### CAP-29 Platform Configuration and Extension

Support additional source-control systems, CI/CD systems, vulnerability providers, validation providers, and remediation boundaries without fundamental redesign.

### CAP-30 Operational Insight Collection

Aggregate remediation outcomes, unsupported scenarios, failures, reviewer feedback, and execution patterns to guide later product improvements.

---

## 3. Initial Release Capability Priority

### Required for the initial release

CAP-01 through CAP-24, plus the initial GitHub-focused portions of CAP-25 through CAP-30.

### Initial implementation constraints

- GitHub and GitHub Actions
- ADK-supported interactive entry point
- Java Maven Spring Boot multi-module repositories
- dependency, plugin, parent, BOM, and dependency-management remediation
- no Java source-code modifications
- default Critical and High severity scope, configurable through Low

### Extension-oriented capabilities

CAP-07, CAP-17, CAP-29, and CAP-30 must be designed so later providers and remediation types can be added, even when the initial release implements only a limited set.

---

## 4. Capability-to-Requirement Traceability

The detailed traceability matrix will map each capability to:

- business requirement or business-goal source
- architecture component or decision
- detailed design section
- implementation issue or task
- verification test and evidence

Capability identifiers are stable and must not be renumbered after approval.

---

## 5. Review Questions Before Architecture

The capability model is ready for architecture when reviewers can answer yes to the following:

1. Does every agreed business need map to at least one capability?
2. Is each capability stated without prescribing architecture or implementation?
3. Are capability boundaries clear enough to assign architectural responsibility?
4. Are initial-release and extension expectations distinguishable?
5. Are unresolved business decisions explicitly tracked rather than silently assumed?
