# Enterprise OSS Remediation Platform
## System Architecture

**Status:** Draft for review  
**Version:** 0.3

---

## 1. Purpose

This document defines the logical architecture that fulfills the approved platform responsibilities while preserving the authoritative [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow).

It is authoritative for:

- logical architectural components
- component boundaries and dependency direction
- major interactions and integration boundaries
- workspace, evidence, and technical-state ownership
- architecture invariants
- placement of ADK/LLM reasoning versus deterministic execution

It does not redefine business behavior, platform capabilities, or responsibility ownership. Prompts, APIs, storage schemas, classes, deployment manifests, and implementation packages belong to Detailed Design.

---

## 2. Architecture Principles

1. **Business workflow remains authoritative.** Architecture maps to the workflow; it does not replace it.
2. **Responsibility ownership is preserved.** Components follow the [Platform Responsibility Model](./03-platform-responsibility-model.md).
3. **Deterministic evidence is authoritative.** Repository state, Maven resolution, vulnerability results, builds, tests, and completion evidence come from deterministic tools or external systems.
4. **LLM reasoning is bounded.** LLMs support contextual reasoning and explanation but do not fabricate tool results or independently approve changes.
5. **Workspace continuity is explicit.** Review-only access is separate from a new remediation iteration.
6. **Current facts and retained history are distinct.** New iterations refresh current facts and reassess relevant prior evidence.
7. **Change execution and approval are separated.** The component that applies changes does not determine final completion.
8. **Provider boundaries are pluggable.** Source control, vulnerability, validation, and future providers are accessed through stable ports.
9. **Security, authorization, and audit are cross-cutting.** They apply to every entry point, component, tool call, and retained artifact.
10. **Operational insight cannot silently change runtime behavior.** Product-learning data informs later approved changes only.

---

## 3. Architecture Invariants

The following rules must remain true in every implementation:

1. Only the **Workflow Orchestrator** may start, resume, advance, pause, retry, revise, or terminate a remediation iteration.
2. Stage components return results to the Orchestrator and must not directly start the next workflow stage.
3. Only the **Validation and Outcome Engine** may assign the technical completion state.
4. The **Change Executor** may apply an approved change but may not approve or validate its own result.
5. The **Remediation Planner** may propose and select plans but may not directly modify repository files or source-control state.
6. The **Source-Control Gateway** owns repository, branch, commit, push, and pull-request operations but not remediation semantics.
7. The **Workspace Manager** preserves context and evidence references but does not invent technical evidence.
8. The **Evidence and Reporting Service** reads authoritative evidence and produces explanations; it does not change workflow or repository state.
9. Review-only access must not create a new iteration unless an authorized user explicitly requests one.
10. A continued iteration must refresh current facts before reusing prior conclusions.
11. Fully or Partially Remediated cannot be reported without the required validation evidence.
12. Provider-specific behavior must remain behind architectural gateways or ports.
13. An ADR cannot silently override business behavior, capability ownership, or responsibility ownership.

---

## 4. System Context

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#0b1220","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#93c5fd","secondaryColor":"#243447","secondaryTextColor":"#f8fafc","secondaryBorderColor":"#a7f3d0","tertiaryColor":"#312e81","tertiaryTextColor":"#f8fafc","tertiaryBorderColor":"#c4b5fd","lineColor":"#cbd5e1","textColor":"#f8fafc","edgeLabelBackground":"#0f172a","edgeLabelTextColor":"#f8fafc"}}}%%
flowchart LR
    CI[GitHub Actions] --> EP[Platform Entry Layer]
    USER[Developer / Reviewer] --> EP
    EP --> CORE[OSS Remediation Platform]
    CORE <--> GH[GitHub]
    CORE <--> VULN[Vulnerability Providers]
    CORE <--> ART[Artifact Repositories]
    CORE <--> BUILD[Maven / Build Environment]
    CORE <--> CUSTOM[Custom Validation Providers]
    CORE <--> LLM[Approved LLM Service]
    CORE <--> IAM[Identity / Secrets / Audit Services]
```

Inside the platform boundary are workflow coordination, workspace management, policy resolution, vulnerability classification, Maven analysis, remediation planning, change execution, validation, reporting, and review support.

External systems remain authoritative for source control, CI/CD execution, vulnerability-source data, artifact repositories, build infrastructure, identity, secrets, audit, and the approved LLM service.

---

## 5. Logical Component Model

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#0b1220","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#93c5fd","secondaryColor":"#243447","secondaryTextColor":"#f8fafc","secondaryBorderColor":"#a7f3d0","tertiaryColor":"#312e81","tertiaryTextColor":"#f8fafc","tertiaryBorderColor":"#c4b5fd","lineColor":"#cbd5e1","textColor":"#f8fafc","edgeLabelBackground":"#0f172a","edgeLabelTextColor":"#f8fafc"}}}%%
flowchart TB
    subgraph Entry[Entry and Interaction]
        EA[Entry Adapters]
        RI[Review Interface]
    end

    subgraph Control[Workflow and Governance]
        WO[Workflow Orchestrator]
        PR[Policy and Validation Resolver]
        WS[Workspace Manager]
    end

    subgraph Analysis[Evidence and Analysis]
        SC[Source-Control Gateway]
        VI[Vulnerability Intelligence]
        MA[Maven Analysis Engine]
    end

    subgraph Remediation[Decision and Change]
        RP[Remediation Planner]
        CE[Change Executor]
        VE[Validation and Outcome Engine]
    end

    subgraph Evidence[Evidence and Operations]
        ER[Evidence and Reporting Service]
        SA[Security and Audit Control]
        OI[Resilience, Extension and Insight Services]
    end

    EA --> WO
    RI --> WO
    WO <--> WS
    WO <--> PR
    WO <--> SC
    WO <--> VI
    WO <--> MA
    WO <--> RP
    WO <--> CE
    WO <--> VE
    WO <--> ER
    ER --> RI
    SA -. cross-cutting .-> Control
    SA -. cross-cutting .-> Analysis
    SA -. cross-cutting .-> Remediation
    OI -. recovery and extension .-> WO
```

Stage components exchange evidence through Orchestrator-controlled calls or authoritative evidence references. They do not advance the workflow by invoking the next stage directly.

---

## 6. Component Responsibilities

| Component | Architectural purpose | Responsibility mapping | Key capabilities |
|---|---|---|---|
| Entry Adapters | Normalize CI/CD and interactive requests into platform commands | RESP-01; supports RESP-02, RESP-11 | CAP-01, CAP-06, CAP-25 |
| Review Interface | Present evidence, accept questions and feedback, and distinguish review-only from new iteration | RESP-10; supports RESP-01, RESP-04 | CAP-22, CAP-23, CAP-24 |
| Workflow Orchestrator | Coordinate stages, iterations, retries, revision, continuation, and termination | RESP-01 | CAP-06, CAP-14, CAP-24 |
| Policy and Validation Resolver | Resolve effective policy, scope, boundaries, delivery policy, and validation configuration | RESP-03 | CAP-02, CAP-03; supports CAP-08 |
| Workspace Manager | Own workspace identity, lifecycle, iteration history, collaboration control, and evidence references | RESP-04 | CAP-04, CAP-05, CAP-21 |
| Source-Control Gateway | Read repository state and manage branch, commit, push, and pull-request operations | RESP-02 | CAP-01, CAP-19, CAP-20 |
| Vulnerability Intelligence | Obtain, normalize, classify, and re-evaluate vulnerability findings | RESP-05 | CAP-07, CAP-08, CAP-16 |
| Maven Analysis Engine | Produce deterministic reactor, effective-model, origin, and control-point evidence | RESP-06 | CAP-09, CAP-10 |
| Remediation Planner | Determine, compare, select, revise, and explain remediation options | RESP-07 | CAP-11, CAP-12; supports CAP-14 |
| Change Executor | Convert an approved plan into permitted project-file changes | RESP-08 | CAP-13 |
| Validation and Outcome Engine | Execute validation and assign exactly one completion state | RESP-09 | CAP-15, CAP-17, CAP-18; consumes CAP-16 |
| Evidence and Reporting Service | Produce reviewer-facing reports and evidence-grounded explanations | RESP-10; supports RESP-04 | CAP-22, CAP-23 |
| Security and Audit Control | Enforce identity, authorization, data protection, and audit capture | RESP-11 | CAP-25, CAP-26, CAP-27 |
| Resilience, Extension and Insight Services | Support recovery, provider extension, and aggregated product insight | RESP-12 | CAP-28, CAP-29, CAP-30 |

A component may support a capability owned elsewhere but must not assume that capability's authoritative decision or state ownership.

---

## 7. Component Dependency Rules

### Allowed control dependency direction

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#0b1220","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#93c5fd","secondaryColor":"#243447","secondaryTextColor":"#f8fafc","secondaryBorderColor":"#a7f3d0","tertiaryColor":"#312e81","tertiaryTextColor":"#f8fafc","tertiaryBorderColor":"#c4b5fd","lineColor":"#cbd5e1","textColor":"#f8fafc","edgeLabelBackground":"#0f172a","edgeLabelTextColor":"#f8fafc"}}}%%
flowchart LR
    Entry[Entry / Review] --> Orchestrator[Workflow Orchestrator]
    Orchestrator <--> Policy[Policy Resolver]
    Orchestrator <--> Workspace[Workspace Manager]
    Orchestrator <--> Source[Source-Control Gateway]
    Orchestrator <--> Vulnerability[Vulnerability Intelligence]
    Orchestrator <--> Maven[Maven Analysis Engine]
    Orchestrator <--> Planner[Remediation Planner]
    Orchestrator <--> Executor[Change Executor]
    Orchestrator <--> Validator[Validation and Outcome Engine]
    Orchestrator <--> Reporting[Evidence and Reporting]
    Reporting --> Review[Review Interface]
```

### Dependency rules

- Orchestrator invokes each workflow stage and receives its result before deciding the next action.
- Components may return evidence directly or return an authoritative evidence reference.
- Planner must not call GitHub or modify files directly.
- Change Executor must not invoke Validation directly or determine completion state.
- Validation must not change policy or remediation plans.
- Reporting must not invoke Maven, scanners, or repository mutation operations.
- Workspace Manager must not invoke LLMs or deterministic analysis tools to create evidence.
- Review Interface must not bypass the Orchestrator to start a remediation iteration.
- Provider adapters must not call one another or own core workflow decisions.
- Operational-insight processing must not update active policy or workspace outcomes.

Detailed call contracts belong to Detailed Design.

---

## 8. ADK, LLM, and Deterministic Boundaries

### ADK-coordinated logical areas

The initial implementation may use ADK for the Workflow Orchestrator, Remediation Planner, review orchestration, and evidence-grounded explanation. The architecture intentionally does not define individual agents; that belongs to Detailed Design.

### LLM-assisted reasoning

LLM reasoning may interpret context, generate and compare candidate plans, explain tradeoffs, analyze failure evidence, and answer reviewer questions. LLM output remains a proposal or explanation until grounded by policy and deterministic evidence.

### Deterministic authority

Deterministic execution is required for repository state, Maven analysis, vulnerability-provider responses, project-file changes, builds, tests, custom validations, vulnerability revalidation, completion-state rules, and source-control delivery state.

---

## 9. Workspace State Model

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#0b1220","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#93c5fd","secondaryColor":"#243447","secondaryTextColor":"#f8fafc","secondaryBorderColor":"#a7f3d0","tertiaryColor":"#312e81","tertiaryTextColor":"#f8fafc","tertiaryBorderColor":"#c4b5fd","lineColor":"#cbd5e1","textColor":"#f8fafc"}}}%%
stateDiagram-v2
    [*] --> Created
    Created --> Running: iteration starts
    Running --> WaitingExternal: recoverable external wait
    WaitingExternal --> Running: dependency available
    Running --> Revising: validation or plan failure
    Revising --> Running: revised plan approved
    Running --> OutcomeRecorded: completion state assigned
    OutcomeRecorded --> UnderReview: outcome presented
    UnderReview --> Retained: no new iteration requested
    UnderReview --> IterationRequested: authorized continuation
    IterationRequested --> Running: refreshed context established
    Running --> Paused: controlled interruption
    Paused --> Running: resume
    Retained --> UnderReview: workspace reopened
```

### State rules

- `Created` exists before any technical execution begins.
- `Running` represents an active iteration, not the whole workspace lifetime.
- `WaitingExternal`, `Paused`, and `Revising` are not completion states.
- `Revising` preserves the failed plan and failure evidence before another plan is selected.
- `OutcomeRecorded` requires exactly one business completion state from the Validation and Outcome Engine.
- `UnderReview` supports questions without creating a new iteration.
- `IterationRequested` is entered only through an authorized explicit request.
- A workspace may cycle through multiple attempts and iterations while retaining previous evidence.

Exact enums, persistence fields, timeouts, and transition APIs belong to Detailed Design.

---

## 10. Component Interaction Matrix

| Component | Reads | Writes / owns | Must not own |
|---|---|---|---|
| Entry Adapters | User or CI request, identity context | Normalized command | Workflow state, evidence |
| Workflow Orchestrator | Commands, policy result, component outcomes, workspace state | Iteration progression and coordination state | Completion decision, repository truth |
| Policy Resolver | Defaults, repository policy, execution overrides | Effective policy and validation scope | Finding classification |
| Workspace Manager | Commands and evidence references | Workspace lifecycle, iteration history, collaboration state | Technical evidence generation |
| Source-Control Gateway | Provider repository state | Branch, commit, push, PR operations | Remediation decision |
| Vulnerability Intelligence | Provider results and effective scope rules | Normalized findings and classification | Policy definition |
| Maven Analysis Engine | Repository snapshot, in-scope findings | Maven structure and origin evidence | Remediation selection |
| Remediation Planner | Policy, findings, Maven evidence, failed plans, failure evidence | Candidate plans, selected plan, revised plan, rationale | File mutation, completion state |
| Change Executor | Approved plan and repository snapshot | Applied project-file change set | Validation approval, next-stage control |
| Validation and Outcome Engine | Changed or unchanged state, validation configuration, re-scan evidence | Validation results and completion state | Policy or plan changes |
| Evidence and Reporting | Authoritative evidence references | Reports and explanations | Workflow or repository state |
| Review Interface | Reports, workspace state | Questions, feedback, iteration request | Direct workflow execution |
| Security and Audit | Identity, action context, security events | Authorization decisions and audit records | Business completion state |
| Insight Services | Aggregated operational events | Approved operational insights | Active remediation behavior |

---

## 11. Major Runtime Flows

### 11.1 New remediation and no-safe-plan outcome

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#0b1220","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#93c5fd","lineColor":"#cbd5e1","textColor":"#f8fafc","actorBkg":"#1e293b","actorBorder":"#93c5fd","actorTextColor":"#f8fafc","signalColor":"#cbd5e1","signalTextColor":"#f8fafc","labelBoxBkgColor":"#0f172a","labelTextColor":"#f8fafc","noteBkgColor":"#312e81","noteTextColor":"#f8fafc","activationBkgColor":"#243447","activationBorderColor":"#a7f3d0"}}}%%
sequenceDiagram
    actor Initiator
    participant Entry
    participant Orchestrator
    participant Workspace
    participant Policy
    participant Source
    participant Vulnerability
    participant Maven
    participant Planner
    participant Change
    participant Validation
    participant Reporting

    Initiator->>Entry: Start remediation
    Entry->>Orchestrator: Normalized request
    Orchestrator->>Workspace: Create workspace and iteration
    Workspace-->>Orchestrator: Workspace reference
    Orchestrator->>Policy: Resolve effective rules
    Policy-->>Orchestrator: Effective policy and validation scope
    Orchestrator->>Source: Establish repository baseline
    Source-->>Orchestrator: Repository snapshot reference
    Orchestrator->>Vulnerability: Discover and classify findings
    Vulnerability-->>Orchestrator: Current classified findings
    Orchestrator->>Maven: Analyze project and control points
    Maven-->>Orchestrator: Maven analysis evidence
    Orchestrator->>Planner: Determine safest remediation option
    Planner-->>Orchestrator: Plan decision and rationale

    alt Safe plan available
        Orchestrator->>Change: Apply approved plan
        Change-->>Orchestrator: Changed project state
        Orchestrator->>Validation: Validate changed state
        Validation->>Vulnerability: Request post-change revalidation
        Vulnerability-->>Validation: Revalidation evidence
        Validation-->>Orchestrator: Completion state and validation evidence
        Orchestrator->>Source: Deliver according to policy
    else No safe plan available
        Orchestrator->>Validation: Assess no-change outcome with plan evidence
        Validation-->>Orchestrator: Human Review Required
    end

    Orchestrator->>Reporting: Produce review-ready outcome
    Reporting-->>Orchestrator: Report reference
    Orchestrator->>Workspace: Retain outcome and evidence references
```

### 11.2 Review-only access

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#0b1220","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#93c5fd","lineColor":"#cbd5e1","textColor":"#f8fafc","actorBkg":"#1e293b","actorBorder":"#93c5fd","actorTextColor":"#f8fafc","signalColor":"#cbd5e1","signalTextColor":"#f8fafc","labelBoxBkgColor":"#0f172a","labelTextColor":"#f8fafc"}}}%%
sequenceDiagram
    actor Reviewer
    participant Review
    participant Workspace
    participant Reporting

    Reviewer->>Review: Open workspace or ask question
    Review->>Workspace: Read outcome and retained evidence
    Workspace-->>Review: Evidence references and current outcome
    Review->>Reporting: Request evidence-grounded answer
    Reporting-->>Review: Answer or summary
    Review-->>Reviewer: Present answer without starting iteration
```

### 11.3 Feedback-driven iteration

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#0b1220","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#93c5fd","lineColor":"#cbd5e1","textColor":"#f8fafc","actorBkg":"#1e293b","actorBorder":"#93c5fd","actorTextColor":"#f8fafc","signalColor":"#cbd5e1","signalTextColor":"#f8fafc","labelBoxBkgColor":"#0f172a","labelTextColor":"#f8fafc","noteBkgColor":"#312e81","noteTextColor":"#f8fafc"}}}%%
sequenceDiagram
    actor Reviewer
    participant Review
    participant Orchestrator
    participant Workspace
    participant Policy
    participant Source
    participant Vulnerability

    Reviewer->>Review: Provide guidance and request iteration
    Review->>Workspace: Retain approved feedback
    Review->>Orchestrator: Request continuation iteration
    Orchestrator->>Source: Refresh repository and branch state
    Source-->>Orchestrator: Current repository snapshot
    Orchestrator->>Policy: Refresh policy and validation scope
    Policy-->>Orchestrator: Current policy context
    Orchestrator->>Workspace: Load relevant prior evidence
    Workspace-->>Orchestrator: Retained evidence references
    Orchestrator->>Vulnerability: Obtain current findings
    Vulnerability-->>Orchestrator: Current vulnerability evidence
    Orchestrator->>Workspace: Record refreshed context
    Note over Orchestrator,Vulnerability: Orchestrator continues through analysis, planning, change, validation, and delivery
```

### 11.4 Failure-informed plan revision

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#0b1220","primaryColor":"#1e293b","primaryTextColor":"#f8fafc","primaryBorderColor":"#93c5fd","lineColor":"#cbd5e1","textColor":"#f8fafc","actorBkg":"#1e293b","actorBorder":"#93c5fd","actorTextColor":"#f8fafc","signalColor":"#cbd5e1","signalTextColor":"#f8fafc","labelBoxBkgColor":"#0f172a","labelTextColor":"#f8fafc","noteBkgColor":"#312e81","noteTextColor":"#f8fafc"}}}%%
sequenceDiagram
    participant Orchestrator
    participant Workspace
    participant Planner
    participant Change
    participant Validation

    Validation-->>Orchestrator: Validation failure and evidence
    Orchestrator->>Workspace: Retain failed plan and failure evidence
    Orchestrator->>Planner: Revise using prior plan and failure evidence
    Planner-->>Orchestrator: Different safe candidate or no safe option

    alt Revised safe plan available
        Orchestrator->>Change: Apply revised plan
        Change-->>Orchestrator: Revised changed state
        Orchestrator->>Validation: Re-run required validation
    else No further safe plan available
        Orchestrator->>Validation: Assess Human Review Required outcome
        Validation-->>Orchestrator: Completion state and evidence
    end
```

The Planner must not repeat a failed strategy unless current facts, policy, or evidence have materially changed and the rationale for reconsideration is retained.

---

## 12. Integration Boundaries

| Integration | Initial implementation | Architectural boundary |
|---|---|---|
| Source control | GitHub | Source-Control Gateway hides provider-specific repository and PR operations |
| CI/CD | GitHub Actions | Entry Adapter converts workflow inputs to normalized commands |
| Interactive access | ADK-supported web or terminal interface | Review and Entry interfaces do not own workflow or evidence state |
| Vulnerability source | Configured provider or supported findings input | Vulnerability Intelligence normalizes provider-specific results |
| Build and dependency analysis | Maven and configured artifact repositories | Maven Analysis and Validation invoke deterministic tools |
| Custom validation | Repository or organization-defined providers | Validation Engine invokes configured validation ports |
| LLM | Approved enterprise LLM service | LLM use is limited to bounded reasoning and explanation |
| Identity, secrets, audit | Enterprise services | Security and Audit applies consistent access and protection rules |

Future Bitbucket, TeamCity, vulnerability, and validation integrations must implement these boundaries without changing core responsibility ownership.

---

## 13. State and Evidence Ownership

| State or evidence | Authoritative component |
|---|---|
| Repository, branch, commit, and pull-request state | Source-Control Gateway / provider |
| Effective policy and validation scope | Policy and Validation Resolver |
| Workspace lifecycle, iteration history, and evidence references | Workspace Manager |
| Normalized findings and classification | Vulnerability Intelligence |
| Maven project, origin, and control-point evidence | Maven Analysis Engine |
| Candidate plans, selected plan, revised plans, rejected alternatives, and rationale | Remediation Planner |
| Applied project-file changes | Change Executor |
| Build, test, custom validation, and completion state | Validation and Outcome Engine |
| Reports and evidence-grounded explanations | Evidence and Reporting Service |
| Access decisions and protected audit records | Security and Audit Control |
| Aggregated operational insights | Resilience, Extension and Insight Services |

Workspace storage may retain copies or references for continuity but does not replace the technical authority of the producing component.

---

## 14. Security and Trust Boundaries

The architecture must enforce authenticated and authorized access, least-privilege credentials, separation of user input from tool evidence and model output, secret redaction, protected audit capture, controlled execution of repository-provided commands, and protection against untrusted repository content influencing privileged operations.

Specific controls, roles, sandboxing choices, and retention periods belong to Detailed Design or unresolved business decisions.

---

## 15. Resilience and Recovery

The Orchestrator and Workspace Manager support resumable iterations with explicit states. Recoverable conditions include provider interruption, build interruption, stale branch state, temporary artifact-repository failure, interrupted orchestration, and LLM unavailability for a reasoning step.

Recovery must preserve completed evidence, identify the failed stage, and resume or restart only the affected work where safe. A process ending is never sufficient evidence of successful remediation.

---

## 16. Workflow-to-Architecture Mapping

| Business workflow stage | Primary components | Primary responsibilities |
|---|---|---|
| Start or resume | Entry Adapters, Orchestrator, Workspace Manager | RESP-01, RESP-04 |
| Review existing workspace | Review Interface, Workspace Manager, Reporting | RESP-10, RESP-04 |
| Capture feedback | Review Interface, Workspace Manager, Orchestrator | RESP-10, RESP-04, RESP-01 |
| Refresh context | Orchestrator, Source-Control Gateway, Policy Resolver | RESP-01, RESP-02, RESP-03 |
| Load retained context | Workspace Manager, coordinated by Orchestrator | RESP-04, RESP-01 |
| Vulnerability discovery | Vulnerability Intelligence, coordinated by Orchestrator | RESP-05, RESP-01 |
| Assess current and retained evidence | Orchestrator, Vulnerability Intelligence, Maven Analysis, Planner | RESP-01, RESP-05, RESP-06, RESP-07 |
| Scope classification | Vulnerability Intelligence using Policy Resolver output | RESP-05; RESP-03 supporting |
| Project analysis | Maven Analysis Engine, coordinated by Orchestrator | RESP-06, RESP-01 |
| Remediation decision | Remediation Planner, coordinated by Orchestrator | RESP-07, RESP-01 |
| Change execution | Change Executor, coordinated by Orchestrator; Source-Control Gateway supports | RESP-08; RESP-01 and RESP-02 supporting |
| Validation | Validation Engine, coordinated by Orchestrator; Vulnerability Intelligence supports | RESP-09; RESP-01 and RESP-05 supporting |
| Completion | Validation Engine; Orchestrator consumes | RESP-09; RESP-01 supporting |
| Delivery | Source-Control Gateway and Reporting, coordinated by Orchestrator | RESP-02, RESP-10; RESP-01 supporting |
| Retention | Workspace Manager, Security and Audit | RESP-04, RESP-11 |

---

## 17. Architecture Decisions Requiring ADRs

1. workspace persistence and evidence-storage strategy
2. ADK orchestration topology and agent boundaries
3. deterministic tool-execution isolation and sandboxing
4. vulnerability-provider interface and initial provider
5. completion-state rule implementation
6. concurrency and duplicate-workspace control
7. branch and commit-history strategy across iterations
8. authentication, authorization, and role model
9. operational-insight aggregation and privacy boundary
10. deployment topology and recovery model

An ADR does not override the Business Requirements, Capability Model, or Responsibility Model unless those documents are also updated through the approved change process.

---

## 18. Architecture Review Criteria

The architecture is ready for baselining when reviewers confirm that:

1. every workflow stage maps to components
2. every component maps to approved capabilities and responsibilities
3. every stage transition is Orchestrator-mediated
4. no-safe-plan and failure-revision paths are represented
5. dependency direction and prohibited calls are clear
6. architectural invariants are testable
7. workspace states support review-only, retries, revision, and repeated iterations
8. state and evidence ownership are unambiguous
9. LLM reasoning is bounded by deterministic evidence and policy
10. unresolved decisions are assigned to ADRs or Detailed Design

---

## 19. Next Step

Review this architecture against the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow), [Capability Model](./02-capability-model.md), and [Platform Responsibility Model](./03-platform-responsibility-model.md).

After approval, create `05-detailed-design.md` and the ADRs required before implementation.
