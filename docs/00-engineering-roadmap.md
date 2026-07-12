# Enterprise OSS Remediation Platform
## Engineering Roadmap and Documentation Tracker

**Status:** Active  
**Purpose:** Preserve the agreed sequence of work and prevent requirements, capabilities, responsibilities, architecture, design, implementation, and verification from drifting apart.

---

## 1. Delivery Principle

Documentation is an engineering tool, not the end product.

The project maintains only the minimum concise artifacts needed to answer:

- What are we building?
- What is the approved business workflow?
- Which platform capabilities are required?
- Which major responsibilities fulfill those capabilities?
- How will those responsibilities be structured architecturally?
- How will each component work?
- What will be implemented next?
- How will we prove the delivered product satisfies the business requirements?

Each document must add new information and must not duplicate earlier documents unnecessarily.

The main business flow should remain visible and easy to reference. Supporting detail may exist underneath it, but future architecture, design, implementation, and verification must be traceable back to the approved Business Remediation Workflow in `01-business-requirements.md`.

---

## 2. Engineering Baseline Branch Policy

The `docs/srs-requirements-foundation` branch is the clean engineering baseline for the new platform direction.

This branch contains only:

- business requirements and approved business workflow
- capability definitions
- platform responsibility definitions
- system architecture
- detailed design
- implementation planning
- requirements traceability
- architecture decision records

This branch must not contain product code, prototypes, generated artifacts, product CI/CD workflows, legacy implementation documents, or copied implementation from earlier branches.

After the applicable engineering documents are reviewed, implementation must begin on a separate development branch. The approved baseline may be merged into that branch so code and tests remain traceable to the approved documentation.

---

## 3. Authoritative Document Set

| Order | Document | Purpose | Status |
|---|---|---|---|
| 1 | `01-business-requirements.md` | Business contract and approved user-facing remediation workflow | Baselined |
| 2 | `02-capability-model.md` | Translate business needs into architecture-neutral capabilities | Baselined |
| 3 | `03-platform-responsibility-model.md` | Assign each capability to one primary platform responsibility | Baselined |
| 4 | `04-system-architecture.md` | Major components, responsibility allocation, interactions, and architecture decisions | Next |
| 5 | `05-detailed-design.md` | ADK agents, workflows, tools, state, APIs, data models, and failure behavior | Not started |
| 6 | `06-implementation-roadmap.md` | Incremental implementation slices, dependencies, and delivery order | Not started |
| 7 | `07-traceability-matrix.md` | Business workflow and requirement through code and test evidence | Not started |
| 8 | `decisions/ADR-*.md` | Significant architecture decisions and tradeoffs | As needed |

---

## 4. Overall Engineering Milestones

### Milestone 1 — Business Baseline

**Goal:** Establish the product contract and approved business workflow without prescribing the solution.

**Deliverable:** `01-business-requirements.md`

**Exit criteria:**

- problem and business goals are clear
- initial release scope and extension direction are distinguishable
- users, workspaces, policies, validation, and completion states are defined
- the complete user-facing remediation workflow is visible in one activity diagram
- each business stage identifies the information produced or retained
- open business decisions are visible

**Status:** Completed and baselined as version 1.1.

### Milestone 2 — Capability Model

**Goal:** Translate business needs into a manageable set of architecture-neutral platform capabilities.

**Deliverable:** `02-capability-model.md`

**Exit criteria:**

- every business need maps to a capability
- capabilities remain architecture-neutral
- capability boundaries are clear
- every capability has one primary responsibility
- initial-release priorities are identified

**Status:** Completed and baselined as version 0.3.

### Milestone 3 — Platform Responsibility Model

**Goal:** Assign capabilities to major platform responsibilities and clarify authoritative ownership and boundaries before components are selected.

**Deliverable:** `03-platform-responsibility-model.md`

**Exit criteria:**

- every capability has exactly one primary responsibility
- supporting responsibilities are explicit
- RESP-03 defines scope rules and RESP-05 owns finding classification
- CAP-13 change-content ownership is separated from source-control operations
- CAP-18 completion-state ownership belongs to Validation and Outcome Assessment
- responsibility purposes, authoritative ownership, interactions, and boundaries are clear
- responsibilities are not prematurely defined as agents, services, APIs, databases, or modules

**Status:** Completed and baselined as version 0.3.

### Milestone 4 — System Architecture

**Goal:** Define which architectural components fulfill the approved platform responsibilities and how those components interact while preserving the approved business workflow.

**Deliverable:** `04-system-architecture.md`

**Must cover:**

- system context and boundaries
- component allocation for each responsibility
- ADK and multi-agent orchestration at a high level
- deterministic tools and service boundaries
- workspace and execution-state ownership
- GitHub and GitHub Actions integration
- vulnerability and validation provider boundaries
- security and audit boundaries
- major data flows
- key architecture decisions and tradeoffs
- explicit mapping from the Business Remediation Workflow to architectural components and interactions

**Exit criteria:**

- every architecture component maps to one or more approved responsibilities and capabilities
- every business workflow stage maps to one or more architecture components
- no business workflow stage or completion outcome is removed, bypassed, or redefined

**Status:** Immediate next milestone.

### Milestone 5 — Detailed Design

**Goal:** Define how each architecture component behaves and interacts.

**Deliverable:** `05-detailed-design.md`

**Must cover:**

- agent responsibilities and boundaries
- deterministic tools versus LLM decisions
- workflow and state transitions
- remediation planning and iteration behavior
- provider and tool contracts
- workspace data model
- validation and completion logic
- review-continuation behavior
- error and recovery behavior

**Exit criteria:** Each design section maps to architecture, responsibility, capability, and applicable business workflow stages.

### Milestone 6 — Implementation Roadmap

**Goal:** Break the design into small, independently verifiable implementation slices.

**Deliverable:** `06-implementation-roadmap.md`

**Expected slices:**

1. Repository intake and configuration
2. Workspace lifecycle
3. Automated and interactive initiation
4. Vulnerability discovery and scope classification
5. Maven multi-module analysis
6. Remediation planning and application
7. Validation and completion-state determination
8. Branch and pull-request delivery
9. Interactive review and continuation
10. Security, auditability, resilience, and operational insights

### Milestone 7 — Implementation Branch Creation and Incremental Delivery

After Milestones 1 through 6 provide enough approved guidance for the first implementation slice, create a separate development branch for product code.

Each implementation slice follows:

`Business Workflow / Requirement -> Capability -> Responsibility -> Architecture -> Design -> Code -> Test Evidence`

No product implementation is committed to the engineering-baseline branch.

### Milestone 8 — Verification and Release Acceptance

**Goal:** Prove that the delivered platform satisfies the approved business baseline and release scope.

**Deliverable:** `07-traceability-matrix.md` plus automated and review evidence.

Verification must identify satisfied, partially satisfied, deferred, and unmet requirements, together with evidence and the release decision. It must also confirm that each approved business workflow stage and completion outcome is represented in the delivered implementation.

### Milestone 9 — Platform Evolution

Prioritized after the initial release:

- additional vulnerability providers
- custom validation providers
- Bitbucket integration
- TeamCity integration
- source-code remediation
- major Java and Spring Boot upgrades
- other build systems and languages

---

## 5. Immediate Next Step

Create `04-system-architecture.md` using:

- the approved Business Remediation Workflow in `01-business-requirements.md`
- the baselined Capability Model
- the baselined Platform Responsibility Model

The architecture work must determine:

- which components fulfill each platform responsibility
- which responsibilities use ADK agents, deterministic tools, services, or combinations
- orchestration and major component interactions
- workspace, execution-state, evidence, and audit ownership
- GitHub and GitHub Actions integration boundaries
- vulnerability-provider and validation-provider boundaries
- security and authorization boundaries
- significant decisions that require ADRs

The System Architecture shall preserve the approved Business Remediation Workflow. Technical decomposition may add internal steps, but it must not remove, bypass, or redefine an approved business stage or completion outcome without an approved change to the Business Requirements Baseline.

Architecture decisions must remain traceable to the applicable business workflow stages, `CAP-*`, and `RESP-*` identifiers.

---

## 6. Change-Control Rules

- Keep business requirements concise and stable.
- Keep the main business workflow easy to locate and understand.
- Treat the baselined business workflow, capability identifiers, and responsibility identifiers as stable.
- Do not renumber or reuse retired identifiers.
- Do not add architecture or implementation details back into the business, capability, or responsibility baselines.
- Record material architecture ownership changes through an ADR and update traceability.
- Do not create a new document when an existing document has the correct responsibility.
- Update the roadmap whenever a milestone starts, completes, or changes materially.
- Update traceability throughout implementation rather than postponing it until release.
- Keep the engineering-baseline branch free of product implementation and legacy artifacts.

---

## 7. Current Status Summary

- Engineering-baseline branch: established and documentation-only
- Business baseline and user-facing remediation workflow: baselined
- Capability model: baselined
- Platform responsibility model: baselined
- System architecture: immediate next step
- Detailed design: pending architecture
- Implementation roadmap: pending detailed design
- Implementation branch: not yet created
- Product implementation: not started under the new baseline
- Traceability and verification: framework defined, detailed mapping pending
