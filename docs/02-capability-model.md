# Enterprise OSS Remediation Platform
## Capability Model

**Status:** Baselined  
**Version:** 0.4

---

## 1. Purpose

This document translates the [Business Requirements Baseline](./01-business-requirements.md) into a concise set of platform capabilities.

It does not redefine business workflow, completion states, delivery policy, components, agents, services, APIs, storage, prompts, or implementation details. The authoritative user-facing lifecycle is the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow).

Each capability must trace back to the Business Requirements Baseline and later map forward to responsibilities, architecture, design, implementation, and tests.

---

## 2. Capability Map

### CAP-01 Repository and Branch Intake

Accept and validate the repository and reference branch required to establish the remediation baseline.

### CAP-02 Remediation Policy Management

Resolve default, repository-level, and execution-level remediation boundaries and rules.

### CAP-03 Validation Configuration

Resolve the required default and repository-specific validation scope for an execution.

### CAP-04 Workspace Management

Create, identify, persist, reopen, and retain remediation workspaces and their execution history.

### CAP-05 Workspace Collaboration Control

Allow authorized shared access while preventing conflicting active updates and uncontrolled duplicate remediation.

### CAP-06 Workflow Initiation

Start remediation through an automated CI/CD entry point or an authorized interactive entry point, and continue an existing workspace.

### CAP-07 Vulnerability Discovery

Obtain current vulnerability findings through a configured provider or supported findings input.

### CAP-08 Severity and Scope Filtering

Apply the effective severity threshold, policy, exclusions, and remediation boundary to classify vulnerability findings as in scope or out of scope.

### CAP-09 Maven Multi-Module Analysis

Understand the Maven reactor, module hierarchy, parent relationships, dependency management, BOMs, plugins, and effective project model.

### CAP-10 Dependency Origin and Control Analysis

Identify why a vulnerable component is present and which project control point can safely change it.

### CAP-11 Remediation Option Determination

Determine applicable remediation options within the configured policy and project context.

### CAP-12 Remediation Selection

Select the safest practical remediation using compatibility, policy, risk, and validation considerations.

### CAP-13 Remediation Application

Apply approved and permitted project-file changes while preserving the supplied reference branch.

### CAP-14 Failure Analysis and Iteration

Analyze unsuccessful attempts, retain failure context, avoid repeating known failed approaches, and continue toward the safest achievable outcome.

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

Create or update a review-ready full or partial remediation pull request for safe validated changes according to the approved delivery policy.

### CAP-21 Evidence and Decision History

Retain findings, options considered, selected and rejected decisions, attempts, tool results, validation evidence, and residual risks.

### CAP-22 Reporting and Reviewer Guidance

Produce concise remediation, validation, risk, and reviewer-facing summaries.

### CAP-23 Interactive Review Support

Answer reviewer questions from retained evidence and explain what changed, why it changed, and why alternatives were rejected.

### CAP-24 Workspace Review and Feedback-Driven Continuation

Support review-only continuation and authorized feedback-driven iterations in the same workspace, using refreshed current context and relevant retained evidence when a new iteration is requested.

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

CAP-01 through CAP-24, plus the initial-release portions of CAP-25 through CAP-30.

### Initial implementation constraints

The authoritative initial-release scope and constraints are maintained in the [Business Requirements Baseline](./01-business-requirements.md#9-initial-release-scope). This capability model does not restate or redefine them.

### Extension-oriented capabilities

CAP-07, CAP-17, CAP-29, and CAP-30 must support the extension direction defined in the [Business Requirements Baseline](./01-business-requirements.md#10-platform-extension-direction).

---

## 4. Capability Ownership Rule

Every capability has exactly one primary platform responsibility. Other responsibilities may support the capability without duplicating its authoritative state or decision ownership.

The [Platform Responsibility Model](./03-platform-responsibility-model.md) records:

- primary responsibility
- supporting responsibilities
- authoritative state or decision owned

Architecture must preserve that ownership unless an approved Architecture Decision Record changes it.

---

## 5. Capability-to-Requirement Traceability

The detailed traceability matrix will map each capability to:

- business requirement or business-workflow source
- primary and supporting platform responsibilities
- architecture component or decision
- detailed design section
- implementation issue or task
- verification test and evidence

Capability identifiers are stable and must not be renumbered after approval.

---

## 6. Architecture Entry Confirmation

The capability model is approved for architecture because:

1. Every agreed business need maps to at least one capability.
2. Capabilities remain free of architecture and implementation decisions.
3. Capability boundaries support one primary responsibility.
4. Initial-release and extension expectations are referenced from the Business Requirements Baseline.
5. Unresolved business decisions remain explicitly tracked in the Business Requirements Baseline.
