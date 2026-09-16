# OSS Remediation ADK

This repository contains an ADK-based OSS vulnerability remediation workflow for Java Spring Boot Maven applications.

## Autonomous Remediation POC

The approved independent single-agent POC is implemented in `autonomous_oss_remediation_agent`. Its operating instructions and fail-closed deployment requirements are in `autonomous_oss_remediation_agent/README.md`; implementation evidence and remaining deployment prerequisites are in `docs/AUTONOMOUS_OSS_REMEDIATION_IMPLEMENTATION_REVIEW.md`.

## Architecture Documentation

The finalized architecture, artifact contracts, deterministic tool APIs, AI agent specifications, workflow orchestration, and implementation plan are documented here:

- [Phase 1 Architecture: ADK OSS Remediation Workflow](docs/phase-1-architecture.md)
- [Phase 2 Artifact Contracts](docs/phase-2-artifact-contracts.md)
- [Phase 3 Deterministic Tool API Definitions](docs/phase-3-deterministic-tool-apis.md)
- [Phase 4 AI Agent Specifications](docs/phase-4-ai-agent-specifications.md)
- [Phase 5 ADK Workflow Orchestration Specification](docs/phase-5-workflow-orchestration-specification.md)
- [Phase 6 Implementation Plan and Code Structure](docs/phase-6-implementation-plan-and-code-structure.md)

The Phase 1 document captures:

- AI agent responsibilities
- deterministic tool responsibilities
- remediation workspace and attempt manifest design
- baseline build gate
- exact patch planning model
- validation model
- retry lifecycle
- partial PR strategy
- PR summary requirements

The Phase 2 document captures:

- Attempt Manifest contract
- Vulnerability Assessment Report contract
- Project Analyzer Report contract
- Exact Remediation Patch Plan contract
- Patch Application Proof contract
- Validation Result contract
- Outcome Analysis Summary contract
- PR Summary contract
- Principal Engineer clarifications for validation success, controlled direct patching, and outcome analysis boundaries

The Phase 3 document captures:

- common deterministic tool result envelope
- tool responsibility matrix
- capabilities and limitations metadata
- orchestrator-only manifest update rule
- Baseline Build Result as a first-class artifact
- Repo Checkout Tool API
- Baseline Build Tool API
- OSV Scanner Tool API
- Project Analyzer Tool API
- Generic Patch Apply Tool API
- Validation Tool API
- PR Creation Tool API
- Principal Engineer clarification that tool payloads are summaries only and full outputs must be persisted as workspace artifacts

The Phase 4 document captures:

- AI agent responsibility matrix
- Remediation Planning Agent authority model
- vulnerability-centric planning model
- evidence-based planning requirements
- manual review decision contract and categories
- replanning model
- additional deterministic investigation request model
- Remediation Outcome Analysis Agent authority model
- outcome failure and responsibility classifications
- AI guardrails
- partial remediation strategy
- prompt definitions

The Phase 5 document captures:

- ADK workflow execution lifecycle
- runtime ownership model
- workflow state transitions
- remediation attempt lifecycle
- attempt counting rules
- additional investigation lifecycle and guard behavior
- stored-artifacts-first data regeneration policy
- patch dry-run and patch application lifecycle
- validation lifecycle and validation success semantics
- accepted patch set lifecycle
- outcome analysis routing
- failure artifact persistence
- manual review and max-attempt handling
- PR creation conditions
- orchestrator decision rules
- runtime pseudocode

The Phase 6 document captures:

- implementation order and principles
- final recommended project structure
- contract model implementation plan
- JSON schema folder and validation strategy
- external remediation policy configuration
- prompt file organization
- workspace, artifact, and manifest storage layers
- deterministic tool implementation plan
- AI agent implementation boundaries
- orchestrator method structure
- CLI and ADK entrypoint separation
- examples and Maven fixture repositories
- unit and integration testing strategy
- MVP implementation priority

## Current Architecture Principle

```text
AI Agents      = reasoning and engineering decisions
Tools          = deterministic facts and execution
Workspace      = persisted artifacts
Manifest       = artifact index and attempt status
ADK Workflow   = execution order and lifecycle control
```
