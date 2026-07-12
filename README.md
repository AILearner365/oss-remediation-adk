# Enterprise OSS Remediation Platform

This branch is the clean engineering baseline for the new platform direction.

It intentionally contains only business requirements, capability definitions, platform responsibilities, architecture, detailed design, implementation planning, traceability, and architecture-decision records.

## Branch policy

This branch must not contain:

- application implementation code
- experiments or prototypes
- generated artifacts
- CI/CD workflows intended to run the product
- legacy implementation documents
- copied code from earlier branches

Implementation begins only after the applicable business requirements, capability model, platform responsibility model, architecture, and detailed design are reviewed.

Implementation work must occur on a separate development branch created from an approved engineering baseline or on a branch where the approved baseline documents have been merged.

## Start here

1. [`docs/00-engineering-roadmap.md`](./docs/00-engineering-roadmap.md) — sequence, versions, milestone status, and next step
2. [`docs/01-business-requirements.md`](./docs/01-business-requirements.md) — authoritative business baseline
3. [Approved Business Remediation Workflow](./docs/01-business-requirements.md#8-business-remediation-workflow) — authoritative user-facing lifecycle
4. [`docs/02-capability-model.md`](./docs/02-capability-model.md) — architecture-neutral capabilities
5. [`docs/03-platform-responsibility-model.md`](./docs/03-platform-responsibility-model.md) — capability ownership
6. [`docs/README.md`](./docs/README.md) — documentation responsibilities and navigation
7. [`decisions/README.md`](./decisions/README.md) — Architecture Decision Record guidance
