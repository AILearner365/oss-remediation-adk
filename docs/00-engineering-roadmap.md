# Enterprise OSS Remediation Platform
## Engineering Roadmap and Documentation Tracker

**Status:** Active  
**Purpose:** Maintain document order, ownership, milestone status, and the immediate next engineering step without repeating requirements owned by other documents.

---

## 1. Documentation Rule

Documentation is an engineering reference, not the end product.

Each document has one authoritative responsibility:

- business behavior and outcomes: [Business Requirements Baseline](./01-business-requirements.md)
- platform capabilities: [Capability Model](./02-capability-model.md)
- capability ownership: [Platform Responsibility Model](./03-platform-responsibility-model.md)
- architecture components and interactions: [System Architecture](./04-system-architecture.md)
- cross-cutting review checklist: [Engineering Principles Reference Checklist](./engineering-principles.md)
- detailed behavior and contracts: `05-detailed-design.md`
- delivery order: `06-implementation-roadmap.md`
- verification evidence: `07-traceability-matrix.md`
- significant architecture decisions: `decisions/ADR-*.md`

Documents must link to the authoritative source instead of restating its content.

The approved user-facing lifecycle remains one authoritative diagram in the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow). It is not split into separate workflow definitions.

---

## 2. Engineering Baseline Branch Policy

The `docs/srs-requirements-foundation` branch is the clean engineering baseline.

It may contain requirements, capabilities, responsibility ownership, architecture, design, implementation planning, traceability, Engineering Principles, and Architecture Decision Records.

It must not contain product code, prototypes, generated artifacts, product CI/CD workflows, legacy implementation documents, or copied implementation from earlier branches.

Implementation begins on a separate development branch after the applicable baseline documents are reviewed.

---

## 3. Authoritative Document Set

| Order | Document | Authoritative responsibility | Status |
|---|---|---|---|
| 1 | [`01-business-requirements.md`](./01-business-requirements.md) | Product intent, boundaries, business workflow, outcomes, and open business decisions | Baselined v1.5 |
| 2 | [`02-capability-model.md`](./02-capability-model.md) | Architecture-neutral platform capabilities | Baselined v0.5 |
| 3 | [`03-platform-responsibility-model.md`](./03-platform-responsibility-model.md) | Primary and supporting responsibility ownership | Baselined v0.4 |
| 4 | [`04-system-architecture.md`](./04-system-architecture.md) | Architectural components, boundaries, integrations, state ownership, and major data flows | Baselined v0.4 |
| 5 | `05-detailed-design.md` | Agent, tool, state, API, data, and failure behavior | Next |
| 6 | `06-implementation-roadmap.md` | Incremental implementation slices and delivery order | Not started |
| 7 | `07-traceability-matrix.md` | Requirement through implementation and verification evidence | Not started |

Supporting governance documents outside the numbered sequence:

- [`engineering-principles.md`](./engineering-principles.md) — baselined checklist v1.1
- `decisions/ADR-*.md` — created as significant decisions are resolved

---

## 4. Milestone Status

### Milestone 1 — Business Baseline

**Deliverable:** [`01-business-requirements.md`](./01-business-requirements.md)  
**Status:** Completed and baselined as version 1.5.

### Milestone 2 — Capability Model

**Deliverable:** [`02-capability-model.md`](./02-capability-model.md)  
**Status:** Completed and baselined as version 0.5.

### Milestone 3 — Platform Responsibility Model

**Deliverable:** [`03-platform-responsibility-model.md`](./03-platform-responsibility-model.md)  
**Status:** Completed and baselined as version 0.4.

### Milestone 4 — System Architecture

**Deliverable:** [`04-system-architecture.md`](./04-system-architecture.md)  
**Status:** Completed and baselined as version 0.4.

The architecture preserves the approved workflow, responsibility ownership, centralized orchestration, no-safe-plan handling, failure-informed revision, explicit state ownership, and bounded LLM usage.

### Supporting Baseline — Engineering Principles Reference Checklist

**Deliverable:** [`engineering-principles.md`](./engineering-principles.md)  
**Status:** Completed and baselined as version 1.1.

The checklist provides concise review questions and links to authoritative requirements and architecture without redefining their rules.

### Milestone 5 — Detailed Design

**Deliverable:** `05-detailed-design.md`  
**Status:** Immediate next milestone.

**Purpose:** Define agent boundaries, deterministic tools, workflow contracts, state transitions, provider ports, data structures, validation behavior, failure handling, and evidence contracts required to implement the baselined architecture.

**Exit criteria:**

- every design element maps to approved architecture components, `RESP-*`, and `CAP-*`
- ADK agent boundaries are defined without changing logical component ownership
- deterministic tool and provider contracts are explicit
- workspace and iteration state transitions are fully specified
- failure-informed revision and completion-state rules are implementable and testable
- security, audit, resilience, and evidence behavior are specified
- decisions requiring ADRs are resolved or explicitly sequenced before implementation

### Milestone 6 — Implementation Roadmap

**Deliverable:** `06-implementation-roadmap.md`  
**Status:** Pending detailed design.

### Milestone 7 — Incremental Implementation

**Status:** Not started.

Implementation must occur on a separate development branch and follow:

`Business Requirement / Workflow -> Capability -> Responsibility -> Architecture -> Design -> Code -> Test Evidence`

### Milestone 8 — Verification and Release Acceptance

**Deliverable:** `07-traceability-matrix.md` plus automated and review evidence.  
**Status:** Not started.

### Milestone 9 — Platform Evolution

Future scope is maintained in the [Platform Extension Direction](./01-business-requirements.md#10-platform-extension-direction), not duplicated in this roadmap.

---

## 5. Immediate Next Step

Create `05-detailed-design.md` using:

1. the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow)
2. the [Capability Model](./02-capability-model.md)
3. the [Platform Responsibility Model](./03-platform-responsibility-model.md)
4. the [System Architecture](./04-system-architecture.md)
5. the [Engineering Principles Reference Checklist](./engineering-principles.md)

Create the ADRs required to settle design-blocking decisions before implementation. Detailed Design must reference authoritative sources rather than restating or redefining their content.

---

## 6. Change-Control Rules

- Change authoritative information only in the document that owns it.
- Use links and identifiers when another document needs that information.
- Keep the single approved Business Remediation Workflow intact unless a reviewed baseline change requires otherwise.
- Record significant architecture decisions in ADRs.
- An ADR that changes capability ownership is incomplete until the Platform Responsibility Model and traceability records are synchronized.
- Update this roadmap only for document versions, milestone status, sequence, branch policy, or next-step changes.
- Keep product implementation off the engineering-baseline branch.
