# Enterprise OSS Remediation Platform
## Engineering Principles

**Status:** Baselined  
**Version:** 1.0

---

## 1. Purpose

This document records the cross-cutting engineering principles that guide architecture, detailed design, implementation, review, and verification.

It does not redefine business behavior, capabilities, responsibility ownership, or architecture. Those remain authoritative in their respective documents. When a principle appears to conflict with an authoritative requirement or architecture decision, the authoritative document and approved change-control process take precedence.

---

## 2. Authoritative References

- Business behavior and outcomes: [Business Requirements Baseline](./01-business-requirements.md)
- User-facing lifecycle: [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow)
- Platform capabilities: [Capability Model](./02-capability-model.md)
- Capability ownership: [Platform Responsibility Model](./03-platform-responsibility-model.md)
- Component boundaries and interactions: [System Architecture](./04-system-architecture.md)
- Significant architecture decisions: `../decisions/ADR-*.md`

---

## 3. Engineering Principles

### EP-01 Business workflow is authoritative

Design and implementation must preserve the approved Business Remediation Workflow. Internal decomposition may add technical steps but must not remove, bypass, or redefine approved business stages or completion outcomes.

### EP-02 Evidence precedes decisions

Repository state, Maven analysis, vulnerability findings, build results, tests, and validations must be obtained before dependent decisions are treated as authoritative. Explanations must remain traceable to retained evidence.

### EP-03 Deterministic execution is preferred

Use deterministic tools and rules wherever practical for repository operations, dependency resolution, vulnerability evaluation, file changes, builds, tests, validation, and completion-state evaluation.

### EP-04 LLM responsibility is bounded

LLMs may support contextual interpretation, candidate generation, comparison, revision, and explanation. They must not fabricate evidence, directly approve their own changes, or replace deterministic technical authority.

### EP-05 Workflow control is centralized

The Workflow Orchestrator controls stage progression, retries, pauses, revisions, continuation, and termination. Stage components return results and must not independently advance the workflow.

### EP-06 Ownership is singular and explicit

Each capability, state, and authoritative decision has one primary owner. Supporting components may contribute but must not duplicate or override ownership.

### EP-07 State transitions are explicit

Workspace and iteration transitions must be deliberate, observable, auditable, and recoverable. Process completion alone must never be interpreted as successful remediation.

### EP-08 Current facts and retained history are distinct

A continued iteration refreshes current repository, policy, validation, and vulnerability facts while retaining relevant prior evidence. Historical conclusions are reassessed rather than blindly reused or discarded.

### EP-09 Failure informs revision

Failed plans, validation failures, rejected options, and their evidence must be retained. A failed strategy must not be repeated unless facts or constraints materially change and the reconsideration rationale is recorded.

### EP-10 Change and approval are separated

The component that plans or applies a remediation must not determine its final technical completion state. Validation and outcome assessment remain independent.

### EP-11 Source systems remain authoritative

GitHub remains authoritative for repository and pull-request state. Vulnerability providers, Maven tools, validation systems, identity systems, and other external authorities remain authoritative for the evidence they produce.

### EP-12 Configuration is preferred over hard-coding

Severity thresholds, policies, validation scope, remediation boundaries, provider selection, and delivery behavior must be configurable within approved constraints.

### EP-13 Provider boundaries are pluggable

Source control, CI/CD, vulnerability, validation, LLM, and other integrations must remain behind stable ports or gateways so provider changes do not redefine core workflow ownership.

### EP-14 Security and audit are cross-cutting

Authorization, least privilege, secret protection, untrusted-input handling, audit capture, and sensitive-data controls apply across every component and workflow stage.

### EP-15 Reviewability is a product requirement

Every outcome must preserve sufficient evidence, decisions, failures, alternatives, validation results, risks, and guidance for a developer or reviewer to understand and continue the work.

### EP-16 Operational insight does not silently change behavior

Aggregated operational data may guide future approved improvements. It must not silently alter active policy, remediation decisions, completion rules, or workspace outcomes.

### EP-17 Changes remain traceable

Implementation and tests must trace through architecture, responsibility, capability, and business requirement or workflow stage. Significant architecture changes require ADRs and synchronization of authoritative documents.

### EP-18 Documentation remains lean and single-source

Change information only in the document that owns it. Other documents must link to the authoritative source rather than restating the same behavior or rule.

---

## 4. Application During Delivery

Architecture and design reviews should use these principles as a checklist, but approval must still be based on the authoritative requirements, capability ownership, architecture, and applicable ADRs.

Implementation work should demonstrate these principles through component boundaries, explicit state transitions, deterministic evidence, tests, audit events, and traceability rather than through documentation statements alone.

---

## 5. Change Control

- Principle identifiers are stable and must not be reused.
- A principle change must not silently alter an authoritative business requirement, capability, responsibility, or architecture decision.
- When a principle reveals a required authoritative change, update the owning document through the approved review process.
