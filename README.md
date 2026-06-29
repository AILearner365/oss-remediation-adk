# OSS Remediation ADK

This repository contains an ADK-based OSS vulnerability remediation workflow for Java Spring Boot Maven applications.

## Architecture Documentation

The finalized Phase 1 architecture is documented here:

- [Phase 1 Architecture: ADK OSS Remediation Workflow](docs/phase-1-architecture.md)

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

## Current Architecture Principle

```text
AI Agents      = reasoning and engineering decisions
Tools          = deterministic facts and execution
Workspace      = persisted artifacts
Manifest       = artifact index and attempt status
ADK Workflow   = execution order and lifecycle control
```
