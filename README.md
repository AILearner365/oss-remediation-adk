# OSS Remediation ADK

This repository contains an ADK-based OSS vulnerability remediation workflow for Java Spring Boot Maven applications.

## Architecture Documentation

The finalized architecture, artifact contracts, deterministic tool APIs, and AI agent specifications are documented here:

- [Phase 1 Architecture: ADK OSS Remediation Workflow](docs/phase-1-architecture.md)
- [Phase 2 Artifact Contracts](docs/phase-2-artifact-contracts.md)
- [Phase 3 Deterministic Tool API Definitions](docs/phase-3-deterministic-tool-apis.md)
- [Phase 4 AI Agent Specifications](docs/phase-4-ai-agent-specifications.md)

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

## Current Architecture Principle

```text
AI Agents      = reasoning and engineering decisions
Tools          = deterministic facts and execution
Workspace      = persisted artifacts
Manifest       = artifact index and attempt status
ADK Workflow   = execution order and lifecycle control
```
