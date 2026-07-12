# Documentation

This directory contains the authoritative product and engineering documentation for the Enterprise OSS Remediation Platform.

The documentation is intentionally lean. Each document has one responsibility and adds detail without duplicating the documents before it.

## Branch responsibility

The `docs/srs-requirements-foundation` branch is the clean engineering-baseline branch.

It contains only requirements, capability, responsibility, architecture, detailed-design, roadmap, traceability, and architecture-decision documentation. Product implementation, prototypes, generated artifacts, and legacy implementation material must not be added to this branch.

Implementation must occur on a separate development branch after the applicable engineering baseline has been reviewed.

## Start here

1. [Engineering Roadmap and Documentation Tracker](./00-engineering-roadmap.md)
2. [Business Requirements Baseline](./01-business-requirements.md)
3. [Capability Model](./02-capability-model.md)
4. [Platform Responsibility Model](./03-platform-responsibility-model.md)
5. [Architecture Decision Record Guidance](../decisions/README.md)

## Planned engineering documents

6. `04-system-architecture.md` — major components, responsibilities, integrations, and architecture decisions
7. `05-detailed-design.md` — ADK agents, workflows, tools, state, APIs, data models, and failure behavior
8. `06-implementation-roadmap.md` — incremental implementation slices and delivery order
9. `07-traceability-matrix.md` — business requirement through implementation and test evidence
10. `decisions/ADR-*.md` — significant architecture decisions and tradeoffs

## Document responsibilities

| Document | Answers |
|---|---|
| Business Requirements | What are we building, why, and within which boundaries? |
| Capability Model | What must the platform be capable of doing? |
| Platform Responsibility Model | Which major platform responsibilities fulfill the capabilities, and how do they interact? |
| System Architecture | Which architectural components fulfill those responsibilities? |
| Detailed Design | How does each architectural part behave and interact? |
| Implementation Roadmap | What is implemented next and in what order? |
| Traceability Matrix | How do we prove the implementation satisfies the business requirements? |
| ADRs | Which significant architecture decisions were made, why, and with what consequences? |

## Governance

- The Business Requirements Baseline is the primary product contract.
- Every capability must trace to the business baseline.
- Every platform responsibility must trace to one or more capabilities.
- Every architecture component must trace to one or more responsibilities and capabilities.
- Every design element and implementation slice must trace to architecture and capabilities.
- Verification and release acceptance must trace delivered evidence back to the business baseline.
- Stable identifiers must not be reused after approval.
- Significant architecture choices must be recorded as ADRs.
- The current sequence and immediate next step are maintained in `00-engineering-roadmap.md`.
- No product implementation is permitted on this engineering-baseline branch.
