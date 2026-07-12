# Enterprise OSS Remediation Platform
## Engineering Roadmap and Documentation Tracker

**Status:** Active  
**Purpose:** Preserve the agreed sequence of work and prevent requirements, capabilities, responsibilities, architecture, design, implementation, and verification from drifting apart.

---

## 1. Delivery Principle

Documentation is an engineering tool, not the end product.

The project maintains only the minimum concise artifacts needed to answer:

- What are we building?
- Which platform capabilities are required?
- Which major responsibilities fulfill those capabilities?
- How will those responsibilities be structured architecturally?
- How will each component work?
- What will be implemented next?
- How will we prove the delivered product satisfies the business requirements?

Each document must add new information and must not duplicate earlier documents unnecessarily.

---

## 2. Engineering Baseline Branch Policy

The `docs/srs-requirements-foundation` branch is the clean engineering baseline for the new platform direction.

This branch contains only:

- business requirements
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
| 1 | `01-business-requirements.md` | Business contract: goals, scope, boundaries, outcomes, and constraints | Draft baseline |
| 2 | `02-capability-model.md` | Translate business needs into architecture-neutral capabilities | Refined draft |
| 3 | `03-platform-responsibility-model.md` | Assign each capability to one primary platform responsibility | Refined draft |
| 4 | `04-system-architecture.md` | Major components, responsibility allocation, interactions, and architecture decisions | Not started |
| 5 | `05-detailed-design.md` | ADK agents, workflows, tools, state, APIs, data models, and failure behavior | Not started |
| 6 | `06-implementation-roadmap.md` | Incremental implementation slices, dependencies, and delivery order | Not started |
| 7 | `07-traceability-matrix.md` | Requirement-to-capability-to-responsibility-to-architecture-to-code-to-test evidence | Not started |
| 8 | `decisions/ADR-*.md` | Significant architecture decisions and tradeoffs | As needed |

---

## 4. Overall Engineering Milestones

### Milestone 1 — Business Baseline

**Goal:** Establish the product contract without prescribing the solution.

**Deliverable:** `01-business-requirements.md`

**Exit criteria:**

- problem and business goals are clear
- initial release scope and extension direction are distinguishable
- users, workspaces, policies, validation, and completion states are defined
- open business decisions are visible

**Status:** Draft baseline created; no further structural expansion planned.

### Milestone 2 — Capability Model

**Goal:** Translate business needs into a manageable set of architecture-neutral platform capabilities.

**Deliverable:** `02-capability-model.md`

**Exit criteria:**

- every business need maps to a capability
- capabilities remain architecture-neutral
- capability boundaries are clear
- every capability can be assigned to one primary responsibility
- initial-release priorities are identified

**Status:** Refined after review; ready for final joint review with the responsibility model.

### Milestone 3 — Platform Responsibility Model

**Goal:** Assign capabilities to major platform responsibilities and clarify authoritative ownership and boundaries before components are selected.

**Deliverable:** `03-platform-responsibility-model.md`

**Exit criteria:**

- every capability has exactly one primary responsibility
- supporting responsibilities are explicit
- CAP-13 change-content ownership is separated from source-control operations
- CAP-18 completion-state ownership belongs to Validation and Outcome Assessment
- responsibility purposes, authoritative ownership, interactions, and boundaries are clear
- responsibilities are not prematurely defined as agents, services, APIs, databases, or modules

**Status:** Refined after review; ready for final joint review with the capability model.

### Milestone 4 — System Architecture

**Goal:** Define which architectural components fulfill the approved platform responsibilities and how those components interact.

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

**Exit criteria:** Every architecture component maps to one or more approved responsibilities and capabilities.

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

**Exit criteria:** Each design section maps to architecture, responsibility, and capability identifiers.

### Milestone 6 — Implementation Roadmap

**Goal:** Break the design into small, independently verifiable implementation slices.

**Deliverable:** `06-implementation-roadmap.md`

**Expected slices:**

1. Repository intake and configuration
2. Workspace lifecycle
3. Automated and interactive initiation
4. Vulnerability discovery
5. Maven multi-module analysis
6. Remediation planning and application
7. Validation and completion-state determination
8. Branch and pull-request delivery
9. Interactive review and continuation
10. Security, auditability, resilience, and operational insights

### Milestone 7 — Implementation Branch Creation and Incremental Delivery

After Milestones 1 through 6 provide enough approved guidance for the first implementation slice, create a separate development branch for product code.

Each implementation slice follows:

`Business Requirement -> Capability -> Responsibility -> Architecture -> Design -> Code -> Test Evidence`

No product implementation is committed to the engineering-baseline branch.

### Milestone 8 — Verification and Release Acceptance

**Goal:** Prove that the delivered platform satisfies the approved business baseline and release scope.

**Deliverable:** `07-traceability-matrix.md` plus automated and review evidence.

Verification must identify satisfied, partially satisfied, deferred, and unmet requirements, together with evidence and the release decision.

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

Perform the final joint review of:

- `02-capability-model.md`
- `03-platform-responsibility-model.md`

Confirm that:

- every business need maps to a capability
- every capability has exactly one primary responsibility
- supporting roles are clear
- ownership and boundaries do not conflict
- both documents remain implementation-neutral

If the review finds no material gaps, baseline both documents and create `04-system-architecture.md`.

---

## 6. Change-Control Rules

- Keep business requirements concise and stable.
- Do not add architecture or design details to the business baseline.
- Keep capabilities and responsibilities implementation-neutral.
- Give each capability one primary responsibility.
- Do not create a new document when an existing document has the correct responsibility.
- Use stable identifiers and never reuse retired identifiers.
- Record significant architecture choices as ADRs.
- Update the roadmap whenever a milestone starts, completes, or changes materially.
- Update traceability throughout implementation rather than postponing it until release.
- Keep the engineering-baseline branch free of product implementation and legacy artifacts.

---

## 7. Current Status Summary

- Engineering-baseline branch: established and documentation-only
- Business baseline: drafted
- Capability model: refined and ready for final review
- Platform responsibility model: simplified, ownership clarified, and ready for final review
- System architecture: next after joint review and baseline approval
- Detailed design: pending architecture
- Implementation roadmap: pending detailed design
- Implementation branch: not yet created
- Product implementation: not started under the new baseline
- Traceability and verification: framework defined, detailed mapping pending
