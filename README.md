# OSS Remediation ADK

This repository contains an ADK-based OSS vulnerability remediation workflow for Java Spring Boot Maven applications.

## Architecture Documentation

The finalized architecture and artifact contracts are documented here:

- [Phase 1 Architecture: ADK OSS Remediation Workflow](docs/phase-1-architecture.md)
- [Phase 2 Artifact Contracts](docs/phase-2-artifact-contracts.md)

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

## Current Architecture Principle

```text
AI Agents      = reasoning and engineering decisions
Tools          = deterministic facts and execution
Workspace      = persisted artifacts
Manifest       = artifact index and attempt status
ADK Workflow   = execution order and lifecycle control
```
