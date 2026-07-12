# Documentation

This directory contains the authoritative product and engineering documentation for the Enterprise OSS Remediation Platform.

The documentation is intentionally lean. Each document owns one type of information and links to other authoritative sources instead of repeating them.

## Branch responsibility

The `docs/srs-requirements-foundation` branch is the clean engineering-baseline branch.

It contains only requirements, capability, responsibility, architecture, detailed-design, roadmap, traceability, and Architecture Decision Record documentation. Product implementation, prototypes, generated artifacts, and legacy implementation material must not be added to this branch.

Implementation must occur on a separate development branch after the applicable engineering baseline has been reviewed.

## Start here

1. [Engineering Roadmap and Documentation Tracker](./00-engineering-roadmap.md)
2. [Business Requirements Baseline](./01-business-requirements.md)
3. [Approved Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow)
4. [Capability Model](./02-capability-model.md)
5. [Platform Responsibility Model](./03-platform-responsibility-model.md)
6. [Architecture Decision Record Guidance](../decisions/README.md)

## Planned engineering documents

7. `04-system-architecture.md` — architectural components, boundaries, integrations, and major data flows
8. `05-detailed-design.md` — ADK agents, workflows, tools, state, APIs, data models, and failure behavior
9. `06-implementation-roadmap.md` — incremental implementation slices and delivery order
10. `07-traceability-matrix.md` — business requirement through implementation and test evidence
11. `decisions/ADR-*.md` — significant architecture decisions and tradeoffs

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
| Engineering Roadmap | Document sequence, versions, milestone status, and immediate next step |

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
- No product implementation is permitted on this engineering-baseline branch.
