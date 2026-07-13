# Documentation

This directory contains the authoritative product and engineering documentation for the Enterprise OSS Remediation Platform.

The documentation is intentionally lean. Each document owns one type of information and links to other authoritative sources instead of repeating them.

## Branch responsibility

This directory belongs to the documentation-only engineering-baseline branch. The authoritative rules for permitted and prohibited branch content are maintained in the [Engineering Baseline Branch Policy](./00-engineering-roadmap.md#2-engineering-baseline-branch-policy).

## Current authoritative documents

1. [Business Requirements Baseline](./01-business-requirements.md)
   - [Approved Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow)
2. [Capability Model](./02-capability-model.md)
3. [Platform Responsibility Model](./03-platform-responsibility-model.md)
4. [System Architecture](./04-system-architecture.md) — draft under review

Supporting navigation and governance:

- [Engineering Roadmap and Documentation Tracker](./00-engineering-roadmap.md)
- [Architecture Decision Record Guidance](../decisions/README.md)

## Planned engineering documents

5. `05-detailed-design.md` — ADK agents, workflows, tools, state, APIs, data models, and failure behavior
6. `06-implementation-roadmap.md` — incremental implementation slices and delivery order
7. `07-traceability-matrix.md` — business requirement through implementation and test evidence

Architecture Decision Records use `decisions/ADR-*.md` and are not part of the numbered document sequence.

## Document ownership

| Document | Authoritative for |
|---|---|
| Business Requirements | Product intent, boundaries, business workflow, completion states, delivery behavior, and open business decisions |
| Capability Model | Architecture-neutral capabilities |
| Platform Responsibility Model | Primary and supporting capability ownership |
| System Architecture | Architectural components, boundaries, integrations, state ownership, and major interactions |
| Detailed Design | Agent, tool, API, state, data, and failure behavior |
| Implementation Roadmap | Delivery slices and implementation order |
| Traceability Matrix | Requirement-to-code-to-test evidence |
| ADRs | Significant architecture decisions, rationale, and consequences |
| Engineering Roadmap | Document sequence, versions, branch policy, milestone status, and immediate next step |

## Diagram convention

Mermaid diagrams must remain readable in both GitHub light mode and dark mode.

- Use the approved dark-canvas, high-contrast Mermaid initialization block used in the Business Workflow and System Architecture.
- Use dark node fills, white text, strong borders, and light connecting lines.
- Do not force a white diagram background.
- Keep edge-label backgrounds dark and edge-label text light.
- Use the same palette across flowcharts, state diagrams, and sequence diagrams.
- Split diagrams when their size makes labels difficult to read at normal browser zoom.
- Do not create a second diagram that redefines behavior already owned by an authoritative diagram.

The dark canvas is intentional: it provides stable contrast whether the surrounding GitHub page is using a light or dark theme.

## Governance

- Change information only in the document that owns it.
- Link to authoritative sections rather than restating their content.
- Every capability must trace to the Business Requirements Baseline.
- Every platform responsibility must trace to one or more capabilities.
- Every architecture component must trace to workflow stages, responsibilities, and capabilities.
- Every design element and implementation slice must trace to architecture and capabilities.
- Verification and release acceptance must trace delivered evidence back to the business baseline.
- Stable identifiers must not be reused after approval.
- Significant architecture choices must be recorded as ADRs.
- An ADR that changes capability ownership is not complete until the Platform Responsibility Model and traceability records are synchronized.
