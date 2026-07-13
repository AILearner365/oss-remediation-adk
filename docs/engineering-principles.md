# Enterprise OSS Remediation Platform
## Engineering Principles Reference Checklist

**Status:** Baselined  
**Version:** 1.1

---

## 1. Purpose

This document is a concise review checklist for architecture, detailed design, implementation, and verification.

It does not define or restate business behavior, capabilities, responsibility ownership, component boundaries, or architecture rules. Each checklist item links to the authoritative source that owns the rule.

When this checklist and an authoritative source appear inconsistent, the authoritative source and approved change-control process take precedence.

---

## 2. Reference Checklist

| ID | Review concern | Apply the authoritative source | Review question |
|---|---|---|---|
| EP-01 | Business workflow alignment | [Business Remediation Workflow](./01-business-requirements.md#8-business-remediation-workflow) | Does the design preserve every approved business stage, continuation path, and completion outcome? |
| EP-02 | Evidence before decisions | [Governing Principles](./01-business-requirements.md#13-governing-principles) and [State and Evidence Ownership](./04-system-architecture.md#13-state-and-evidence-ownership) | Is each decision grounded in retained authoritative evidence? |
| EP-03 | Deterministic execution | [ADK, LLM, and Deterministic Boundaries](./04-system-architecture.md#8-adk-llm-and-deterministic-boundaries) | Are deterministic tools used for technical facts and executable validation wherever practical? |
| EP-04 | Bounded LLM responsibility | [ADK, LLM, and Deterministic Boundaries](./04-system-architecture.md#8-adk-llm-and-deterministic-boundaries) | Is model output treated as reasoning or explanation rather than unverified technical truth? |
| EP-05 | Centralized workflow control | [Architecture Invariants](./04-system-architecture.md#3-architecture-invariants) and [Component Dependency Rules](./04-system-architecture.md#7-component-dependency-rules) | Does every stage transition return through the Workflow Orchestrator? |
| EP-06 | Singular ownership | [Platform Responsibility Model](./03-platform-responsibility-model.md) and [State and Evidence Ownership](./04-system-architecture.md#13-state-and-evidence-ownership) | Does every capability, state, and authoritative decision have one primary owner? |
| EP-07 | Explicit state transitions | [Workspace State Model](./04-system-architecture.md#9-workspace-state-model) | Are workspace and iteration transitions explicit, observable, and recoverable? |
| EP-08 | Current facts and retained history | [Continuation Rule](./01-business-requirements.md#continuation-rule) and [Workspace State Model](./04-system-architecture.md#9-workspace-state-model) | Does a continued iteration refresh current facts while retaining relevant prior evidence? |
| EP-09 | Failure-informed revision | [CAP-14](./02-capability-model.md#cap-14-failure-analysis-and-iteration) and [Failure-Informed Plan Revision](./04-system-architecture.md#114-failure-informed-plan-revision) | Are failed plans and failure evidence retained and used to avoid unsupported repetition? |
| EP-10 | Change and approval separation | [Architecture Invariants](./04-system-architecture.md#3-architecture-invariants) | Are planning, change execution, and completion-state determination kept separate? |
| EP-11 | Source-system authority | [State and Evidence Ownership](./04-system-architecture.md#13-state-and-evidence-ownership) | Does each external or deterministic source remain authoritative for the evidence it produces? |
| EP-12 | Configuration over hard-coding | [Remediation Policy](./01-business-requirements.md#remediation-policy) and [Initial Release Scope](./01-business-requirements.md#9-initial-release-scope) | Are policy, severity, validation, provider, boundary, and delivery choices configurable within approved limits? |
| EP-13 | Pluggable provider boundaries | [Integration Boundaries](./04-system-architecture.md#12-integration-boundaries) | Can providers be replaced without changing core workflow or ownership? |
| EP-14 | Security and audit | [Security and Trust Boundaries](./04-system-architecture.md#14-security-and-trust-boundaries) | Are authorization, least privilege, secrets, untrusted input, sensitive data, and audit addressed? |
| EP-15 | Reviewability | [Review-Ready](./01-business-requirements.md#review-ready) and [Evidence and Reporting responsibility](./03-platform-responsibility-model.md#resp-10-evidence-reporting-and-review-support) | Can a developer or reviewer understand the outcome, evidence, alternatives, failures, validation, and risks? |
| EP-16 | Controlled operational insight | [Future Data and Product-Improvement Requirements](./01-business-requirements.md#future-data-and-product-improvement-requirements) | Is operational insight prevented from silently changing active policy or outcomes? |
| EP-17 | Traceability | [Governance and Traceability](./01-business-requirements.md#17-governance-and-traceability) and [Engineering Roadmap](./00-engineering-roadmap.md) | Can design, code, tests, and evidence be traced back through architecture, responsibility, capability, and business need? |
| EP-18 | Lean single-source documentation | [Documentation Governance](./README.md#governance) | Is information changed only in the document that owns it, with other documents linking to that source? |

---

## 3. Usage

Use this checklist during:

- detailed-design reviews
- ADR reviews
- implementation pull-request reviews
- verification and release-readiness reviews

A checklist result is supporting review evidence. Approval remains governed by the authoritative requirements, capability model, responsibility model, system architecture, and applicable ADRs.

---

## 4. Change Control

- Principle identifiers are stable and must not be reused.
- A checklist change must not silently alter an authoritative requirement or architecture decision.
- When a checklist item reveals a required authoritative change, update the owning document through the approved review process.
