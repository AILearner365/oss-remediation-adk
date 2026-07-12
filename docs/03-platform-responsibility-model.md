# Enterprise OSS Remediation Platform
## Platform Responsibility Model

**Status:** Draft  
**Version:** 0.1

---

## 1. Purpose

This document groups the approved platform capabilities into major platform responsibilities before architectural components, agents, services, storage mechanisms, or deployment choices are selected.

It answers:

- What major responsibilities must the platform fulfill?
- Which capabilities belong to each responsibility?
- What information does each responsibility receive and produce?
- How do the responsibilities depend on one another?
- Which responsibilities require durable state or coordination?

This document does **not** decide whether a responsibility is implemented by an ADK agent, multiple agents, a deterministic tool, a service, a library, or another architectural component. Those decisions belong in the System Architecture and Detailed Design documents.

---

## 2. Traceability Flow

```text
Business Requirements
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

Every responsibility must own one or more capabilities. Every future architecture component must map to one or more responsibilities.

---

## 3. Responsibility Summary

| ID | Responsibility | Primary purpose |
|---|---|---|
| RESP-01 | Engagement and Workflow Control | Start, coordinate, continue, and conclude remediation work |
| RESP-02 | Repository and Source-Control Management | Access repository state and manage remediation branches and pull requests |
| RESP-03 | Policy and Validation Governance | Resolve the operating rules and required validation scope |
| RESP-04 | Workspace and Collaboration Management | Preserve remediation context and control shared continuation |
| RESP-05 | Vulnerability Intelligence | Obtain, normalize, filter, and re-evaluate vulnerability findings |
| RESP-06 | Maven Project and Dependency Analysis | Understand the multi-module project and dependency control structure |
| RESP-07 | Remediation Decision Management | Determine, compare, select, and explain safe remediation options |
| RESP-08 | Remediation Change Execution | Apply permitted repository changes safely |
| RESP-09 | Validation and Outcome Assessment | Execute validation and determine the supported completion state |
| RESP-10 | Evidence, Reporting, and Review Support | Preserve evidence and support reviewer understanding and feedback |
| RESP-11 | Security, Authorization, and Audit | Protect access, sensitive information, and significant activity records |
| RESP-12 | Resilience, Extensibility, and Product Insight | Handle recoverable failures and support platform evolution |

---

## 4. Detailed Responsibilities

### RESP-01 Engagement and Workflow Control

**Purpose**

Provide a consistent remediation lifecycle across autonomous CI/CD initiation, interactive initiation, and continuation of an existing workspace.

**Owned capabilities**

- CAP-06 Workflow Initiation
- CAP-14 Failure Analysis and Iteration
- CAP-18 Completion-State Determination, in coordination with RESP-09
- CAP-24 Feedback-Driven Continuation

**Primary inputs**

- new remediation request
- existing workspace identifier
- repository and branch context
- resolved policy and validation scope
- responsibility outcomes and failure signals
- authorized reviewer guidance

**Primary outputs**

- initiated or resumed remediation lifecycle
- ordered responsibility requests
- iteration and continuation decisions
- workflow progress and final lifecycle status

**Key interactions**

- requests workspace context from RESP-04
- requests repository operations from RESP-02
- obtains rules from RESP-03
- coordinates discovery, analysis, remediation, validation, and review responsibilities

**State expectation**

Requires durable workflow and iteration state through RESP-04. It does not independently own repository truth or validation truth.

---

### RESP-02 Repository and Source-Control Management

**Purpose**

Provide controlled access to repository state and manage source-control delivery without directly modifying the supplied reference branch.

**Owned capabilities**

- CAP-01 Repository Intake
- CAP-13 Remediation Application, repository-operation aspects shared with RESP-08
- CAP-19 Remediation Branch Management
- CAP-20 Pull-Request Management

**Primary inputs**

- repository URL
- reference branch
- workspace identifier
- approved change set
- pull-request update request

**Primary outputs**

- validated repository and branch context
- immutable baseline reference for the execution
- remediation branch
- committed changes
- created or updated pull request
- stale-baseline or source-control conflict signal

**Key interactions**

- supplies repository state to RESP-06
- accepts approved modifications from RESP-08
- supplies pull-request linkage and repository evidence to RESP-04 and RESP-10
- reports source-control failures to RESP-01 and RESP-12

**State expectation**

Source control remains authoritative for repository, branch, commit, and pull-request state. Workspace records retain references to that state.

---

### RESP-03 Policy and Validation Governance

**Purpose**

Resolve the rules that determine what the platform may evaluate, change, validate, accept, defer, or escalate.

**Owned capabilities**

- CAP-02 Remediation Policy Management
- CAP-03 Validation Configuration
- CAP-08 Severity and Scope Filtering, policy aspects shared with RESP-05

**Primary inputs**

- platform defaults
- repository configuration
- execution-level overrides
- severity threshold
- organization-specific governance rules
- remediation boundary

**Primary outputs**

- effective remediation policy
- effective validation scope
- permitted and prohibited change boundaries
- policy-decision evidence

**Key interactions**

- provides scope to RESP-05
- constrains analysis and decision making in RESP-06 and RESP-07
- constrains change execution in RESP-08
- defines required checks for RESP-09
- provides policy evidence to RESP-10

**State expectation**

Effective policy and validation scope must be versioned or snapshotted within the workspace so later review uses the rules that applied to the iteration.

---

### RESP-04 Workspace and Collaboration Management

**Purpose**

Create and preserve the complete remediation context across executions, reviews, users, and later continuation.

**Owned capabilities**

- CAP-04 Workspace Management
- CAP-05 Workspace Collaboration Control
- CAP-21 Evidence and Decision History, persistence aspects shared with RESP-10

**Primary inputs**

- workflow inputs
- policy and validation snapshots
- findings
- analysis and decisions
- attempts and changes
- validation results
- pull-request linkage
- user questions and feedback

**Primary outputs**

- workspace identifier
- current workspace context
- historical iterations
- controlled update access
- conflict or duplicate-workspace signal
- durable references to evidence and delivery artifacts

**Key interactions**

- supplies context to all responsibilities
- persists outcomes received from all responsibilities
- controls active update ownership for RESP-01
- provides review history to RESP-10

**State expectation**

This is the primary durable business-state responsibility. It must distinguish immutable historical evidence from current mutable workflow state.

---

### RESP-05 Vulnerability Intelligence

**Purpose**

Obtain current vulnerability findings, determine which findings are in scope, and verify the post-remediation vulnerability state.

**Owned capabilities**

- CAP-07 Vulnerability Discovery
- CAP-08 Severity and Scope Filtering, finding-processing aspects shared with RESP-03
- CAP-16 Vulnerability Revalidation

**Primary inputs**

- repository or dependency evidence
- configured vulnerability provider or supported report
- effective remediation policy
- severity threshold
- pre-change and post-change project state

**Primary outputs**

- normalized vulnerability findings
- in-scope and out-of-scope classification
- pre-remediation vulnerability baseline
- post-remediation vulnerability result
- provider evidence and limitations

**Key interactions**

- receives policy scope from RESP-03
- provides findings to RESP-06 and RESP-07
- provides revalidation outcomes to RESP-09
- provides evidence to RESP-10

**State expectation**

Provider responses and normalized findings must be retained with sufficient metadata to support comparison and later review.

---

### RESP-06 Maven Project and Dependency Analysis

**Purpose**

Understand the Java Maven Spring Boot multi-module project and determine why each vulnerable component is present and where it can be controlled.

**Owned capabilities**

- CAP-09 Maven Multi-Module Analysis
- CAP-10 Dependency Origin and Control Analysis

**Primary inputs**

- repository baseline
- Maven project files and effective model
- normalized vulnerability findings
- effective remediation policy

**Primary outputs**

- Maven reactor and module model
- dependency and plugin relationships
- parent, BOM, dependency-management, direct, transitive, and plugin control points
- impacted modules
- compatibility and project-context evidence

**Key interactions**

- obtains repository state from RESP-02
- receives findings from RESP-05
- supplies analysis to RESP-07
- supplies project evidence to RESP-09 and RESP-10

**State expectation**

Analysis results are iteration evidence retained in RESP-04. Deterministic Maven output remains authoritative.

---

### RESP-07 Remediation Decision Management

**Purpose**

Determine applicable remediation options, compare them, select the safest practical option, and preserve the rationale for selected and rejected alternatives.

**Owned capabilities**

- CAP-11 Remediation Option Determination
- CAP-12 Remediation Selection
- CAP-14 Failure Analysis and Iteration, decision aspects shared with RESP-01
- CAP-21 Evidence and Decision History, decision aspects shared with RESP-04 and RESP-10

**Primary inputs**

- findings and severity scope
- dependency origin and control analysis
- effective remediation policy
- prior attempts and failure evidence
- version and compatibility evidence
- validation requirements
- authorized reviewer guidance

**Primary outputs**

- candidate remediation options
- selected remediation plan
- rejected alternatives and reasons
- risk and compatibility assessment
- revised plan after failure or review feedback
- human-review recommendation when safe selection is unavailable

**Key interactions**

- consumes outputs from RESP-03, RESP-05, RESP-06, RESP-09, and RESP-10
- sends an approved plan to RESP-08
- sends rationale and evidence to RESP-04 and RESP-10
- reports no-safe-option conditions to RESP-01

**State expectation**

Decision inputs, alternatives, selection criteria, and rationale must be retained for each iteration.

---

### RESP-08 Remediation Change Execution

**Purpose**

Translate an approved remediation plan into permitted repository modifications while enforcing the remediation boundary.

**Owned capabilities**

- CAP-13 Remediation Application

**Primary inputs**

- selected remediation plan
- repository working state
- effective remediation boundary
- applicable project-analysis evidence

**Primary outputs**

- proposed or applied change set
- changed-file summary
- boundary-compliance evidence
- execution failure details

**Key interactions**

- receives the selected plan from RESP-07
- uses repository operations provided by RESP-02
- sends the changed state to RESP-09
- sends change evidence to RESP-04 and RESP-10
- reports execution failure to RESP-01 and RESP-07

**State expectation**

This responsibility does not independently approve its own changes. Validation and completion decisions remain separate.

---

### RESP-09 Validation and Outcome Assessment

**Purpose**

Execute the configured validation scope, determine whether applied changes are acceptable, and provide the evidence needed to assign a completion state.

**Owned capabilities**

- CAP-15 Maven Build Validation
- CAP-16 Vulnerability Revalidation, execution coordinated with RESP-05
- CAP-17 Custom Validation Integration
- CAP-18 Completion-State Determination

**Primary inputs**

- changed project state
- effective validation scope
- effective remediation policy
- pre-remediation findings
- post-remediation findings
- remediation boundary

**Primary outputs**

- build and test results
- vulnerability revalidation results
- custom validation results
- regression and conflict findings
- validation summary
- recommended completion state or failure feedback

**Key interactions**

- obtains changed state from RESP-02 and RESP-08
- obtains vulnerability results from RESP-05
- returns failure evidence to RESP-01 and RESP-07
- supplies validated outcome evidence to RESP-10

**State expectation**

Raw tool outputs and normalized validation conclusions must be retained. Deterministic results are authoritative.

---

### RESP-10 Evidence, Reporting, and Review Support

**Purpose**

Make remediation outcomes review-ready and support later technical questions and feedback using retained evidence rather than hidden reasoning.

**Owned capabilities**

- CAP-21 Evidence and Decision History, presentation aspects shared with RESP-04
- CAP-22 Reporting and Reviewer Guidance
- CAP-23 Interactive Review Support
- CAP-24 Feedback-Driven Continuation, review-intake aspects shared with RESP-01

**Primary inputs**

- findings and analysis
- selected and rejected options
- applied changes
- validation results
- completion state
- residual risks
- reviewer questions and guidance

**Primary outputs**

- vulnerability and remediation summaries
- validation and risk reports
- pull-request description content
- reviewer guidance
- evidence-grounded answers
- structured feedback for another iteration

**Key interactions**

- retrieves durable context from RESP-04
- receives evidence from RESP-03 through RESP-09
- supplies pull-request content to RESP-02
- sends authorized feedback to RESP-01 and RESP-07

**State expectation**

Reviewer conversations and responses must remain associated with the workspace and the evidence version used to answer them.

---

### RESP-11 Security, Authorization, and Audit

**Purpose**

Protect repository and workspace access, sensitive information, model interactions, and significant platform activity.

**Owned capabilities**

- CAP-25 Identity and Authorization
- CAP-26 Security and Sensitive-Data Protection
- CAP-27 Auditability

**Primary inputs**

- user or integration identity
- repository and workspace permissions
- secrets and credentials
- significant platform actions and policy decisions

**Primary outputs**

- access decisions
- protected secret usage
- masking or data-handling enforcement
- audit events
- security-policy violation signals

**Key interactions**

- applies across every responsibility
- protects provider and repository integrations
- records significant events from RESP-01 through RESP-10 and RESP-12

**State expectation**

Audit records must be durable and protected from unauthorized alteration. Sensitive values must not be unnecessarily copied into workspace evidence.

---

### RESP-12 Resilience, Extensibility, and Product Insight

**Purpose**

Support recoverable operation, controlled provider extension, and systematic improvement of future platform capabilities.

**Owned capabilities**

- CAP-28 Operational Resilience
- CAP-29 Platform Configuration and Extension
- CAP-30 Operational Insight Collection

**Primary inputs**

- external-system failures
- interrupted or stale executions
- unsupported scenarios
- remediation outcomes
- reviewer feedback
- execution and validation patterns
- new provider or platform requirements

**Primary outputs**

- recoverable-condition classification
- retry, refresh, or escalation signal
- extension requirements and contracts for architecture consideration
- aggregated product-improvement insights
- unsupported-scenario summaries

**Key interactions**

- receives operational signals from every responsibility
- informs RESP-01 about recoverable or terminal conditions
- informs architecture and roadmap evolution without directly changing approved business policy

**State expectation**

Operational insights must be separated from one workspace's authoritative evidence and aggregated according to security, privacy, and retention policy.

---

## 5. Responsibility Interaction Flow

The normal high-level lifecycle is:

```text
Initiate or Resume
      |
      v
RESP-01 Engagement and Workflow Control
      |
      +--> RESP-04 Workspace and Collaboration Management
      +--> RESP-03 Policy and Validation Governance
      +--> RESP-02 Repository and Source-Control Management
      |
      v
RESP-05 Vulnerability Intelligence
      |
      v
RESP-06 Maven Project and Dependency Analysis
      |
      v
RESP-07 Remediation Decision Management
      |
      v
RESP-08 Remediation Change Execution
      |
      v
RESP-09 Validation and Outcome Assessment
      |
      +--> failure evidence returns to RESP-07 and RESP-01
      |
      v
RESP-02 Branch and Pull-Request Delivery
      |
      v
RESP-10 Evidence, Reporting, and Review Support
      |
      +--> reviewer feedback may return to RESP-01 and RESP-07
```

RESP-11 applies security, authorization, and audit controls across the complete flow. RESP-12 receives operational signals across the flow and supports resilience and future extension.

---

## 6. Responsibility Boundaries

The architecture must preserve the following separation of responsibility:

1. Workflow coordination does not replace deterministic repository, scan, build, or test evidence.
2. Change execution does not approve its own result.
3. Validation determines technical outcomes but does not independently alter remediation policy.
4. Source control remains authoritative for repository and pull-request state.
5. Workspace management owns persistent remediation context but does not invent missing technical evidence.
6. Review support explains decisions from retained evidence and does not create unsupported rationale.
7. Security and authorization apply across all responsibilities rather than being isolated to one workflow step.
8. Product insight collection does not silently change approved runtime policy or remediation behavior.

---

## 7. Responsibility-to-Capability Coverage

| Responsibility | Capabilities |
|---|---|
| RESP-01 | CAP-06, CAP-14, CAP-18, CAP-24 |
| RESP-02 | CAP-01, CAP-13, CAP-19, CAP-20 |
| RESP-03 | CAP-02, CAP-03, CAP-08 |
| RESP-04 | CAP-04, CAP-05, CAP-21 |
| RESP-05 | CAP-07, CAP-08, CAP-16 |
| RESP-06 | CAP-09, CAP-10 |
| RESP-07 | CAP-11, CAP-12, CAP-14, CAP-21 |
| RESP-08 | CAP-13 |
| RESP-09 | CAP-15, CAP-16, CAP-17, CAP-18 |
| RESP-10 | CAP-21, CAP-22, CAP-23, CAP-24 |
| RESP-11 | CAP-25, CAP-26, CAP-27 |
| RESP-12 | CAP-28, CAP-29, CAP-30 |

Some capabilities intentionally span responsibilities. Architecture must identify one primary owner and any supporting components without duplicating authoritative state or decision ownership.

---

## 8. Architecture Entry Criteria

Architecture work may begin when reviewers confirm that:

1. Every approved capability is covered by at least one responsibility.
2. Each responsibility has a clear purpose and boundary.
3. Inputs and outputs are sufficient to identify major interactions.
4. Durable-state expectations are visible without prescribing storage technology.
5. Shared capabilities identify primary and supporting responsibility roles.
6. No responsibility is prematurely defined as an agent, service, database, or implementation module.
7. The model supports the initial GitHub-focused release while preserving the agreed extension direction.

---

## 9. Immediate Follow-Up

Review this model together with `02-capability-model.md`.

After approval, create the System Architecture document and decide:

- which architectural components fulfill each responsibility
- which responsibilities are implemented through ADK agents versus deterministic tools or services
- how state and evidence are owned
- how GitHub, vulnerability, validation, LLM, identity, and audit integrations are structured
- which decisions require Architecture Decision Records
