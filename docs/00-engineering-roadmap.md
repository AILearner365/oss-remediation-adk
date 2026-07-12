# Enterprise OSS Remediation Platform
## Engineering Roadmap and Documentation Tracker

**Status:** Active  
**Purpose:** Preserve the agreed sequence of work and prevent requirements, architecture, design, implementation, and verification from drifting apart.

---

## 1. Delivery Principle

Documentation is an engineering tool, not the end product.

The project will maintain only the minimum set of concise artifacts needed to answer:

- What are we building?
- Which platform capabilities are required?
- How will those capabilities be structured?
- How will each component work?
- What will be implemented next?
- How will we prove the delivered product satisfies the business requirements?

Each document must add new information and must not duplicate earlier documents unnecessarily.

---

## 2. Authoritative Document Set

| Order | Document | Purpose | Status |
|---|---|---|---|
| 1 | `01-business-requirements.md` | Business contract: goals, scope, boundaries, outcomes, and constraints | Draft baseline |
| 2 | `02-capability-model.md` | Bridge from business requirements to architecture | Draft |
| 3 | `03-system-architecture.md` | Major components, responsibilities, interactions, and architecture decisions | Not started |
| 4 | `04-detailed-design.md` | ADK agents, workflows, tools, state, APIs, data models, and failure behavior | Not started |
| 5 | `05-implementation-roadmap.md` | Incremental implementation slices, dependencies, and delivery order | Not started |
| 6 | `06-traceability-matrix.md` | Requirement-to-capability-to-architecture-to-code-to-test evidence | Not started |
| 7 | `decisions/ADR-*.md` | Significant architecture decisions and tradeoffs | As needed |

---

## 3. Overall Engineering Milestones

### Milestone 1 — Business Baseline

**Goal:** Establish the product contract without prescribing the solution.

**Deliverable:** `01-business-requirements.md`

**Exit criteria:**

- problem and business goals are clear
- initial release scope and extension direction are distinguishable
- users, workspaces, policies, validation, and completion states are defined
- open business decisions are visible

**Status:** Draft baseline created; review and approve without further structural expansion.

### Milestone 2 — Capability Model

**Goal:** Translate business needs into a manageable set of platform capabilities.

**Deliverable:** `02-capability-model.md`

**Exit criteria:**

- every business need maps to a capability
- capabilities remain architecture-neutral
- capability boundaries are clear
- initial-release priorities are identified

**Status:** Draft created; immediate next review target.

### Milestone 3 — System Architecture

**Goal:** Define how the approved capabilities are organized into major architectural responsibilities and integrations.

**Deliverable:** `03-system-architecture.md`

**Must cover:**

- system context and boundaries
- major components and responsibilities
- ADK and multi-agent orchestration at a high level
- workspace and execution-state ownership
- GitHub and GitHub Actions integration
- vulnerability and validation provider boundaries
- security and audit boundaries
- major data flows
- key architecture decisions and tradeoffs

**Exit criteria:** Every architecture component maps to one or more approved capabilities.

### Milestone 4 — Detailed Design

**Goal:** Define how each architecture component behaves and interacts.

**Deliverable:** `04-detailed-design.md`

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

**Exit criteria:** Each design section maps to architecture and capability identifiers.

### Milestone 5 — Implementation Roadmap

**Goal:** Break the design into small, independently verifiable implementation slices.

**Deliverable:** `05-implementation-roadmap.md`

**Expected slices:**

1. Repository intake and configuration
2. Workspace lifecycle
3. GitHub Actions and interactive initiation
4. Vulnerability discovery
5. Maven multi-module analysis
6. Remediation planning and application
7. Validation and completion-state determination
8. Branch and pull-request delivery
9. Interactive review and continuation
10. Security, auditability, and operational insights

### Milestone 6 — Incremental Implementation

Each slice follows this chain:

`Business Requirement -> Capability -> Architecture -> Design -> Code -> Test Evidence`

A slice is not complete until the chain is traceable and its applicable tests pass.

### Milestone 7 — Verification and Release Acceptance

**Goal:** Prove that the delivered platform satisfies the approved business baseline and release scope.

**Deliverable:** `06-traceability-matrix.md` plus automated and review evidence.

Verification must identify:

- satisfied requirements
- partially satisfied requirements
- deferred requirements
- unmet requirements
- evidence location
- release decision

### Milestone 8 — Platform Evolution

Prioritized after the initial release:

- additional vulnerability providers
- custom validation providers
- Bitbucket integration
- TeamCity integration
- source-code remediation
- major Java and Spring Boot upgrades
- other build systems and languages

---

## 4. Immediate Next Step

Review and finalize `02-capability-model.md`.

The review should focus only on whether the capability list completely and accurately represents the business baseline. It should not introduce agents, services, databases, APIs, or other design decisions.

After capability approval, create `03-system-architecture.md` and begin architecture work.

---

## 5. Change-Control Rules

- Keep business requirements concise and stable.
- Do not add architecture or design details to the business baseline.
- Do not create a new document when an existing document has the correct responsibility.
- Use stable identifiers for capabilities, architecture decisions, design sections, tasks, and tests.
- Never reuse retired identifiers.
- Record significant architecture choices as ADRs.
- Update the roadmap status whenever a milestone starts, completes, or changes materially.
- Update traceability as implementation proceeds; do not postpone it until release.

---

## 6. Current Status Summary

- Business baseline: drafted
- Capability model: drafted
- System architecture: next after capability review
- Detailed design: pending architecture
- Implementation roadmap: pending detailed design
- Implementation: not started under the new baseline
- Traceability and verification: framework defined, detailed mapping pending
