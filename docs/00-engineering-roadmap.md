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
- architecture components and interactions: `04-system-architecture.md`
- detailed behavior and contracts: `05-detailed-design.md`
- delivery order: `06-implementation-roadmap.md`
- verification evidence: `07-traceability-matrix.md`
- significant architecture decisions: `decisions/ADR-*.md`

Documents must link to the authoritative source instead of restating its content.

The approved user-facing lifecycle is maintained only in the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow).

---

## 2. Engineering Baseline Branch Policy

The `docs/srs-requirements-foundation` branch is the clean engineering baseline.

It may contain requirements, capabilities, responsibility ownership, architecture, design, implementation planning, traceability, and Architecture Decision Records.

It must not contain product code, prototypes, generated artifacts, product CI/CD workflows, legacy implementation documents, or copied implementation from earlier branches.

Implementation begins on a separate development branch after the applicable baseline documents are reviewed.

---

## 3. Authoritative Document Set

| Order | Document | Authoritative responsibility | Status |
|---|---|---|---|
| 1 | [`01-business-requirements.md`](./01-business-requirements.md) | Product intent, boundaries, business workflow, outcomes, and open business decisions | Baselined v1.4 |
| 2 | [`02-capability-model.md`](./02-capability-model.md) | Architecture-neutral platform capabilities | Baselined v0.5 |
| 3 | [`03-platform-responsibility-model.md`](./03-platform-responsibility-model.md) | Primary and supporting responsibility ownership | Baselined v0.4 |
| 4 | `04-system-architecture.md` | Architectural components, boundaries, integrations, and major data flows | Next |
| 5 | `05-detailed-design.md` | Agent, tool, state, API, data, and failure behavior | Not started |
| 6 | `06-implementation-roadmap.md` | Incremental implementation slices and delivery order | Not started |
| 7 | `07-traceability-matrix.md` | Requirement through implementation and verification evidence | Not started |

Architecture Decision Records use `decisions/ADR-*.md` and are maintained outside the numbered document sequence.

---

## 4. Milestone Status

### Milestone 1 — Business Baseline

**Deliverable:** [`01-business-requirements.md`](./01-business-requirements.md)  
**Status:** Completed and baselined as version 1.4.

The business workflow, continuation behavior, completion states, delivery policy, scope, and open business decisions are maintained in that document and are not repeated here.

### Milestone 2 — Capability Model

**Deliverable:** [`02-capability-model.md`](./02-capability-model.md)  
**Status:** Completed and baselined as version 0.5.

### Milestone 3 — Platform Responsibility Model

**Deliverable:** [`03-platform-responsibility-model.md`](./03-platform-responsibility-model.md)  
**Status:** Completed and baselined as version 0.4.

### Milestone 4 — System Architecture

**Deliverable:** `04-system-architecture.md`  
**Status:** Immediate next milestone.

**Purpose:** Define the architectural components that fulfill the approved platform responsibilities while preserving the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow).

**Exit criteria:**

- every business-workflow stage maps to one or more architecture components
- every architecture component maps to approved `CAP-*` and `RESP-*` identifiers
- component, state, evidence, integration, security, and audit ownership is explicit
- significant tradeoffs are recorded as ADRs
- any approved capability-ownership change is synchronized into the Platform Responsibility Model and traceability records
- no approved business stage or completion outcome is removed or redefined

### Milestone 5 — Detailed Design

**Deliverable:** `05-detailed-design.md`  
**Status:** Pending architecture.

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

Create `04-system-architecture.md` using:

1. the [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow)
2. the [Capability Model](./02-capability-model.md)
3. the [Platform Responsibility Model](./03-platform-responsibility-model.md)

The architecture document must map workflow stages to capabilities, responsibilities, and architectural components. It must reference the business baseline for behavior and outcomes rather than restating or redefining them.

---

## 6. Change-Control Rules

- Change authoritative information only in the document that owns it.
- Use links and identifiers when another document needs that information.
- Keep the approved workflow and stable identifiers unchanged unless a reviewed baseline change requires otherwise.
- Record significant architecture decisions in ADRs.
- An ADR that changes capability ownership is incomplete until the Platform Responsibility Model and traceability records are synchronized.
- Update this roadmap only for document versions, milestone status, sequence, branch policy, or next-step changes.
- Keep product implementation off the engineering-baseline branch.
