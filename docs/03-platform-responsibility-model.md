# Enterprise OSS Remediation Platform
## Platform Responsibility Model

**Status:** Baselined  
**Version:** 0.4

---

## 1. Purpose

This document groups approved platform capabilities into major platform responsibilities before agents, services, storage mechanisms, APIs, or deployment choices are selected.

It defines:

- responsibility purpose
- primary capabilities
- supporting capabilities
- authoritative state or decision owned
- major interactions
- essential boundary rules

It does not redefine the business lifecycle or decide whether a responsibility is implemented by an ADK agent, multiple agents, a deterministic tool, a service, a library, or another architectural component.

The authoritative user-facing lifecycle is the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow). This document defines responsibility ownership for the capabilities required to support that workflow.

---

## 2. Traceability Flow

```text
Business Requirements and Workflow
        |
        v
Platform Capabilities
        |
        v
Platform Responsibilities
        |
        v
System Architecture
        |
        v
Detailed Design
        |
        v
Implementation and Tests
```

Every capability has exactly one primary responsibility. Supporting responsibilities may contribute without duplicating authoritative state or decision ownership.

---

## 3. Responsibility Summary

| ID | Responsibility | Primary purpose |
|---|---|---|
| RESP-01 | Engagement and Workflow Control | Start, coordinate, continue, and conclude remediation work |
| RESP-02 | Repository and Source-Control Management | Access repository state and manage branches, commits, and pull requests |
| RESP-03 | Policy and Validation Governance | Resolve the operating rules and required validation scope |
| RESP-04 | Workspace and Collaboration Management | Preserve remediation context and control shared continuation |
| RESP-05 | Vulnerability Intelligence | Obtain, normalize, filter, and re-evaluate vulnerability findings |
| RESP-06 | Maven Project and Dependency Analysis | Understand the multi-module project and dependency control structure |
| RESP-07 | Remediation Decision Management | Determine, compare, select, and explain safe remediation options |
| RESP-08 | Remediation Change Execution | Produce approved and permitted project-file modifications |
| RESP-09 | Validation and Outcome Assessment | Execute validation and determine the supported completion state |
| RESP-10 | Evidence, Reporting, and Review Support | Present evidence and support reviewer understanding and feedback |
| RESP-11 | Security, Authorization, and Audit | Protect access, sensitive information, and significant activity records |
| RESP-12 | Resilience, Extensibility, and Product Insight | Handle recoverable failures and support platform evolution |

---

## 4. Responsibility Definitions

### RESP-01 Engagement and Workflow Control

**Purpose:** Coordinate new, resumed, iterative, and feedback-driven remediation lifecycles.

**Primary capabilities:** CAP-06, CAP-14, CAP-24  
**Supporting capabilities:** CAP-18

**Authoritative ownership:** workflow state, iteration progression, continuation or termination of orchestration.

**Major interactions:** RESP-02 through RESP-10; relies on RESP-04 for durable workspace state.

**Boundary:** consumes the completion state determined by RESP-09; it does not independently determine technical success.

---

### RESP-02 Repository and Source-Control Management

**Purpose:** Provide controlled repository access and manage baseline, remediation branch, commit, push, and pull-request operations.

**Primary capabilities:** CAP-01, CAP-19, CAP-20  
**Supporting capabilities:** CAP-13

**Authoritative ownership:** repository reference, branch, commit, and pull-request state.

**Major interactions:** supplies repository state to RESP-06; receives approved file changes from RESP-08; provides delivery evidence to RESP-04 and RESP-10.

**Boundary:** does not decide or generate the remediation content applied to project files.

---

### RESP-03 Policy and Validation Governance

**Purpose:** Resolve what the platform may evaluate, change, validate, accept, defer, or escalate.

**Primary capabilities:** CAP-02, CAP-03  
**Supporting capabilities:** CAP-08

**Authoritative ownership:** effective remediation policy, severity threshold, validation scope, exclusions, and permitted change boundary for each iteration.

**Major interactions:** supplies governing rules to RESP-05 and constrains RESP-06 through RESP-09; provides policy evidence to RESP-10.

**Boundary:** defines the rules used for classification but does not own the resulting in-scope or out-of-scope vulnerability classification.

---

### RESP-04 Workspace and Collaboration Management

**Purpose:** Preserve the complete remediation context across executions, users, reviews, and later continuation.

**Primary capabilities:** CAP-04, CAP-05, CAP-21  
**Supporting capabilities:** CAP-24, CAP-27

**Authoritative ownership:** durable workspace context, iteration history, collaboration lock or active-update ownership, and evidence references.

**Major interactions:** persists and supplies context for all responsibilities.

**Boundary:** preserves evidence but does not invent technical conclusions that are absent from authoritative tools or decisions.

---

### RESP-05 Vulnerability Intelligence

**Purpose:** Obtain current findings, normalize them, apply effective scope, and evaluate post-change vulnerability status.

**Primary capabilities:** CAP-07, CAP-08, CAP-16  
**Supporting capabilities:** none

**Authoritative ownership:** normalized vulnerability findings, in-scope and out-of-scope classification, and pre-change/post-change vulnerability comparison.

**Major interactions:** receives governing rules from RESP-03; supplies classified findings to RESP-06, RESP-07, RESP-09, and RESP-10.

**Boundary:** applies approved policy rules to findings but does not define or change those rules.

---

### RESP-06 Maven Project and Dependency Analysis

**Purpose:** Understand the Maven reactor, module hierarchy, dependency relationships, origins, and control points.

**Primary capabilities:** CAP-09, CAP-10  
**Supporting capabilities:** CAP-11, CAP-15

**Authoritative ownership:** project-analysis model and dependency-origin/control-point evidence for an iteration.

**Major interactions:** consumes repository state from RESP-02 and findings from RESP-05; supplies analysis to RESP-07, RESP-09, and RESP-10.

**Boundary:** deterministic Maven evidence remains authoritative over inferred project structure.

---

### RESP-07 Remediation Decision Management

**Purpose:** Determine applicable options, compare them, select the safest practical option, and explain rejected alternatives.

**Primary capabilities:** CAP-11, CAP-12  
**Supporting capabilities:** CAP-14, CAP-21, CAP-24

**Authoritative ownership:** candidate options, selected remediation plan, rejected alternatives, decision rationale, and decision risk assessment.

**Major interactions:** consumes policy, vulnerability, project-analysis, validation-failure, and reviewer-feedback evidence; sends approved plans to RESP-08.

**Boundary:** does not directly modify repository files or approve its own result.

---

### RESP-08 Remediation Change Execution

**Purpose:** Convert an approved remediation plan into permitted project-file changes.

**Primary capabilities:** CAP-13  
**Supporting capabilities:** CAP-19

**Authoritative ownership:** proposed and applied project-file change set and boundary-compliance result.

**Major interactions:** receives the plan from RESP-07; uses repository operations from RESP-02; sends changed state to RESP-09.

**Boundary:** owns remediation content changes, while RESP-02 owns branch, commit, push, and pull-request operations.

---

### RESP-09 Validation and Outcome Assessment

**Purpose:** Execute the configured validation scope and assign exactly one supported completion state.

**Primary capabilities:** CAP-15, CAP-17, CAP-18  
**Supporting capabilities:** CAP-16

**Authoritative ownership:** normalized validation conclusion and completion-state determination.

**Major interactions:** validates changes from RESP-08, consumes vulnerability revalidation from RESP-05, returns failure evidence to RESP-01 and RESP-07, and supplies outcome evidence to RESP-10.

**Boundary:** determines technical outcome but cannot change remediation policy or the original evidence.

---

### RESP-10 Evidence, Reporting, and Review Support

**Purpose:** Produce review-ready summaries and answer reviewer questions from retained evidence.

**Primary capabilities:** CAP-22, CAP-23  
**Supporting capabilities:** CAP-21, CAP-24

**Authoritative ownership:** reviewer-facing representation of evidence, reports, explanations, and structured review feedback.

**Major interactions:** retrieves durable context from RESP-04, receives evidence from RESP-03 through RESP-09, and supplies pull-request content to RESP-02.

**Boundary:** explains from retained evidence and must not create unsupported rationale or technical results.

---

### RESP-11 Security, Authorization, and Audit

**Purpose:** Protect access, sensitive information, model interactions, and significant platform activity.

**Primary capabilities:** CAP-25, CAP-26, CAP-27  
**Supporting capabilities:** all capabilities where authorization, protection, or audit applies

**Authoritative ownership:** access decisions, sensitive-data controls, and protected audit records.

**Major interactions:** applies across RESP-01 through RESP-12.

**Boundary:** sensitive values must not be unnecessarily copied into workspace evidence or reviewer-facing output.

---

### RESP-12 Resilience, Extensibility, and Product Insight

**Purpose:** Support recoverable execution, provider extension, and evidence-based product evolution.

**Primary capabilities:** CAP-28, CAP-29, CAP-30  
**Supporting capabilities:** CAP-06 and provider-oriented capabilities

**Authoritative ownership:** recoverable-condition classification, extension requirements, and aggregated operational insights.

**Major interactions:** receives operational signals from all responsibilities and informs workflow control and future architecture decisions.

**Boundary:** operational insight does not silently alter approved runtime policy, remediation logic, or completion-state rules.

---

## 5. Capability Ownership Matrix

| Capability | Primary responsibility | Supporting responsibilities |
|---|---|---|
| CAP-01 | RESP-02 | RESP-01, RESP-11 |
| CAP-02 | RESP-03 | RESP-04, RESP-11 |
| CAP-03 | RESP-03 | RESP-09 |
| CAP-04 | RESP-04 | RESP-01, RESP-11 |
| CAP-05 | RESP-04 | RESP-01, RESP-11 |
| CAP-06 | RESP-01 | RESP-02, RESP-04, RESP-11, RESP-12 |
| CAP-07 | RESP-05 | RESP-02, RESP-11, RESP-12 |
| CAP-08 | RESP-05 | RESP-03, RESP-07 |
| CAP-09 | RESP-06 | RESP-02 |
| CAP-10 | RESP-06 | RESP-05 |
| CAP-11 | RESP-07 | RESP-06 |
| CAP-12 | RESP-07 | RESP-03, RESP-05, RESP-06, RESP-09 |
| CAP-13 | RESP-08 | RESP-02, RESP-03, RESP-06 |
| CAP-14 | RESP-01 | RESP-07, RESP-09, RESP-12 |
| CAP-15 | RESP-09 | RESP-02, RESP-06 |
| CAP-16 | RESP-05 | RESP-09 |
| CAP-17 | RESP-09 | RESP-03, RESP-12 |
| CAP-18 | RESP-09 | RESP-01, RESP-03, RESP-05 |
| CAP-19 | RESP-02 | RESP-08, RESP-11 |
| CAP-20 | RESP-02 | RESP-10, RESP-11 |
| CAP-21 | RESP-04 | RESP-03, RESP-05, RESP-06, RESP-07, RESP-08, RESP-09, RESP-10, RESP-11 |
| CAP-22 | RESP-10 | RESP-04, RESP-09 |
| CAP-23 | RESP-10 | RESP-04, RESP-07, RESP-09 |
| CAP-24 | RESP-01 | RESP-04, RESP-07, RESP-09, RESP-10 |
| CAP-25 | RESP-11 | all affected responsibilities |
| CAP-26 | RESP-11 | all affected responsibilities |
| CAP-27 | RESP-11 | RESP-04 and all event-producing responsibilities |
| CAP-28 | RESP-12 | RESP-01, RESP-02, RESP-04, RESP-05, RESP-09 |
| CAP-29 | RESP-12 | RESP-02, RESP-05, RESP-09, RESP-11 |
| CAP-30 | RESP-12 | RESP-04, RESP-10, RESP-11 |

---

## 6. Workflow Reference and Architecture Mapping

The authoritative user-facing lifecycle, including review-only access, new-iteration behavior, context refresh, retained-evidence assessment, completion states, and delivery policy, is defined only in the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow).

This responsibility model does not maintain a second lifecycle diagram. The System Architecture must map each business-workflow stage to the responsible `RESP-*` ownership and the architectural components that fulfill it.

RESP-11 applies security, authorization, and audit controls across the lifecycle. RESP-12 supports recovery, extension, and product insight without redefining the approved business workflow.

---

## 7. Required Responsibility Boundaries

1. Workflow coordination does not replace deterministic repository, scan, build, or test evidence.
2. RESP-08 creates remediation file changes; RESP-02 owns branch, commit, push, and pull-request operations.
3. RESP-03 defines the effective scope rules; RESP-05 applies them and owns finding classification.
4. RESP-09 alone owns completion-state determination; RESP-01 consumes the result.
5. Change execution does not approve its own result.
6. Validation cannot independently change remediation policy.
7. Source control remains authoritative for repository and pull-request state.
8. Workspace management owns persistent remediation context but does not invent missing technical evidence.
9. Review support explains decisions from retained evidence and does not create unsupported rationale.
10. Security and authorization apply across all responsibilities.
11. Product insight collection does not silently change approved runtime policy or remediation behavior.

---

## 8. Architecture Entry Confirmation

The responsibility model is approved for architecture because:

1. Every approved capability has exactly one primary responsibility.
2. Supporting responsibility roles are explicit.
3. Each responsibility has a clear purpose, authoritative ownership, and boundary.
4. Responsibility ownership can be mapped to the authoritative Business Remediation Workflow.
5. State ownership is visible without prescribing storage technology.
6. No responsibility is prematurely defined as an agent, service, database, API, or implementation module.
7. The model supports the initial GitHub-focused release and the agreed extension direction.

---

## 9. Next Step

Create `04-system-architecture.md` using:

- the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow)
- the [Capability Model](./02-capability-model.md)
- this responsibility ownership model

Architecture must determine which components fulfill each responsibility and record significant decisions through Architecture Decision Records.
