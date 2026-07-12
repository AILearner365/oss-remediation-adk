# Documentation

This directory contains the authoritative product and engineering documentation for the Enterprise OSS Remediation Platform.

The documentation is intentionally lean. Each document has one responsibility and adds detail without duplicating the documents before it.

## Start here

1. [Engineering Roadmap and Documentation Tracker](./00-engineering-roadmap.md)
2. [Business Requirements Baseline](./01-business-requirements.md)
3. [Capability Model](./02-capability-model.md)

## Planned engineering documents

4. `03-system-architecture.md` — major components, responsibilities, integrations, and architecture decisions
5. `04-detailed-design.md` — ADK agents, workflows, tools, state, APIs, data models, and failure behavior
6. `05-implementation-roadmap.md` — incremental implementation slices and delivery order
7. `06-traceability-matrix.md` — business requirement through implementation and test evidence
8. `decisions/ADR-*.md` — significant architecture decisions and tradeoffs

## Document responsibilities

| Document | Answers |
|---|---|
| Business Requirements | What are we building, why, and within which boundaries? |
| Capability Model | What must the platform be capable of doing? |
| System Architecture | How are those capabilities organized into major architectural responsibilities? |
| Detailed Design | How does each architectural part behave and interact? |
| Implementation Roadmap | What is implemented next and in what order? |
| Traceability Matrix | How do we prove the implementation satisfies the business requirements? |

## Governance

- The Business Requirements Baseline is the primary product contract.
- Every capability must trace to the business baseline.
- Every architecture component must trace to one or more capabilities.
- Every design element and implementation slice must trace to architecture and capabilities.
- Verification and release acceptance must trace delivered evidence back to the business baseline.
- Stable identifiers must not be reused after approval.
- The current sequence and next step are maintained in `00-engineering-roadmap.md` so the project does not lose track of progress.
