# Phase 5 ADK Workflow Orchestration Specification

This document captures the frozen Phase 5 ADK Workflow Orchestration Specification for the OSS vulnerability remediation workflow.

Phase 5 builds on:

- Phase 1: frozen workflow architecture
- Phase 2: frozen artifact contracts
- Phase 3: frozen deterministic tool API definitions
- Phase 4: frozen AI agent specifications

Phase 5 defines the runtime behavior of the ADK Workflow Orchestrator, including execution lifecycle, state management, retries, artifact handling, additional investigation, validation handling, accepted patch set handling, and PR creation routing.

---

## 1. Purpose

Phase 5 defines how the ADK Workflow Orchestrator coordinates the complete OSS Vulnerability Remediation Workflow.

It defines:

- execution lifecycle
- workflow state transitions
- orchestration responsibilities
- retry lifecycle
- artifact lifecycle
- tool invocation
- AI agent invocation
- manifest updates
- stop conditions
- PR creation conditions

It does not define:

- AI reasoning, which is defined in Phase 4
- artifact structures, which are defined in Phase 2
- deterministic tool APIs, which are defined in Phase 3

---

## 2. Orchestrator Responsibilities

The ADK Workflow Orchestrator owns execution order.

It is responsible for:

```text
- Create Remediation Workspace
- Initialize Attempt Manifest
- Invoke deterministic tools
- Invoke AI agents
- Persist generated artifacts
- Update Attempt Manifest
- Restore clean baseline
- Manage retry lifecycle
- Enforce workflow policies
- Decide workflow transitions
- Invoke PR Creation Tool
```

The Orchestrator must never make remediation decisions.

Remediation decisions belong exclusively to the Remediation Planning Agent.

---

## 3. Runtime Ownership Matrix

| Component | Owns |
|---|---|
| Workflow Orchestrator | Execution order, lifecycle, retries, manifest updates |
| Remediation Planning Agent | Engineering remediation decisions |
| Remediation Outcome Analysis Agent | Failure investigation and classification |
| Deterministic Tools | Deterministic execution and fact generation |
| Remediation Workspace | Artifact persistence |
| Attempt Manifest | Artifact index and workflow status |

---

## 4. Workflow State Machine

Recommended non-terminal states:

```text
INITIALIZED
CHECKOUT
BASELINE_BUILD
SCANNING
PROJECT_ANALYSIS
PLANNING
ADDITIONAL_INVESTIGATION
PATCH_DRY_RUN
PATCH_APPLICATION
VALIDATION
OUTCOME_ANALYSIS
REPLANNING
PR_CREATION
COMPLETED
```

Recommended terminal states:

```text
BASELINE_BUILD_FAILED
MANUAL_REVIEW_REQUIRED
FAILED_MAX_ATTEMPTS
PR_CREATED
```

The Attempt Manifest records workflow state, but the Orchestrator controls transitions.

---

## 5. High-Level Workflow

```text
Initialize Workspace
  ↓
Checkout Repository
  ↓
Baseline Build
  ↓
OSV Scan
  ↓
Project Analyzer
  ↓
Planning Agent
  ↓
Additional Investigation?
  ↓
Patch Dry Run
  ↓
Patch Apply
  ↓
Validation
  ↓
Success?
  ↓
Yes -> PR Creation
  ↓
No
  ↓
Outcome Analysis
  ↓
Replanning
  ↓
Next Attempt
```

---

## 6. Attempt Lifecycle

Each remediation attempt is independent.

```text
Restore Clean Baseline
  ↓
Apply Accepted Patch Set
  ↓
Planning Agent
  ↓
Patch Dry Run
  ↓
Patch Apply
  ↓
Validation
  ↓
Outcome Analysis, if required
```

The repository must never continue from a partially failed workspace.

Every new attempt starts from:

```text
Clean Baseline
+
Accepted Patch Set
```

---

## 7. Attempt Counting Rules

Attempt count represents engineering remediation attempts, not investigation activities.

Attempt count does not increase when:

```text
- Planning Agent requests additional evidence
- Project Analyzer Tool is rerun
- OSV Scanner Tool is rerun
- Artifacts are regenerated
- Planner immediately returns MANUAL_REVIEW
```

Attempt count increases only after a patch execution cycle begins:

```text
- Patch Dry Run executed
- Patch Apply executed
```

This keeps retries aligned with actual remediation attempts.

---

## 8. Additional Investigation Flow

If the Planning Agent determines that evidence is insufficient, it produces an Additional Investigation Request.

The Orchestrator must:

```text
1. Validate the requested tool is allowed.
2. Invoke the requested deterministic tool.
3. Persist the new artifact in the Remediation Workspace.
4. Update the Attempt Manifest.
5. Reinvoke the Planning Agent.
```

No remediation attempt is consumed by additional investigation.

### Investigation Guard

To prevent endless investigation loops:

```text
Recommended default:
maxAdditionalInvestigationRequestsPerAttempt = 2
```

If the maximum additional investigation requests is reached, the Orchestrator must not directly force a manual review decision.

Correct behavior:

```text
1. Record investigation limit reached.
2. Reinvoke the Remediation Planning Agent with this constraint.
3. The Planning Agent must produce either:
   - an Exact Remediation Patch Plan, or
   - a MANUAL_REVIEW decision.
```

This preserves the rule that the Planning Agent owns remediation decisions.

---

## 9. Data Regeneration Policy

The Orchestrator follows a stored-artifacts-first strategy.

Default behavior:

```text
Read existing artifacts
Reuse artifacts
```

Artifacts are regenerated only when:

```text
- missing
- truncated
- corrupted
- explicitly requested by the Remediation Planning Agent
- determined insufficient by the Remediation Outcome Analysis Agent
```

This avoids unnecessary tool execution and preserves reproducibility.

---

## 10. Patch Execution Flow

Patch execution begins with the Exact Remediation Patch Plan.

```text
Patch Plan
  ↓
Patch Dry Run
```

If Patch Dry Run succeeds:

```text
Patch Apply
```

If Patch Dry Run fails:

```text
Persist Dry Run Result
  ↓
Outcome Analysis
  ↓
Replanning
```

Since no repository modification occurred during dry-run, rollback is not required.

---

## 11. Patch Application Flow

If Patch Apply succeeds:

```text
Persist Patch Application Proof
  ↓
Validation
```

If Patch Apply fails:

```text
Persist Patch Application Proof
  ↓
Outcome Analysis
  ↓
Restore Clean Baseline
  ↓
Next Attempt
```

---

## 12. Validation Flow

The Validation Tool is invoked once per remediation attempt.

Internally it performs:

```text
Change Scope Validation
  ↓
Build Validation
  ↓
Test Validation
  ↓
OSV Validation
```

If Change Scope Validation fails:

```text
Persist Validation Result
  ↓
Stop validation
  ↓
Outcome Analysis
```

---

## 13. Validation Success Semantics

Validation SUCCESS means:

```text
The applied patch set is safe.
```

It does not necessarily mean:

```text
All vulnerabilities are remediated.
```

Remaining vulnerabilities may still exist and be classified as:

```text
MANUAL_REVIEW
```

---

## 14. Accepted Patch Set Rules

A patch becomes part of the Accepted Patch Set only when all of the following are true:

```text
- Change Scope Validation passed
- Build passed
- Tests passed
- OSV Validation completed
- No new Critical/High vulnerabilities introduced
- Vulnerability status = REMEDIATED
```

Patch Application success alone is not sufficient.

---

## 15. Outcome Analysis Flow

Outcome Analysis is invoked when:

```text
- Patch Dry Run fails
- Patch Apply fails
- Validation fails
- Maximum attempts reached
```

It produces:

```text
Outcome Analysis Summary
```

The Orchestrator stores the summary and invokes the Planning Agent for replanning.

---

## 16. Failure Artifact Persistence

Whenever a workflow stage fails, the Orchestrator persists all available evidence.

Examples:

```text
- Baseline Build Result
- Patch Dry Run Result
- Patch Application Proof
- Validation Result
- Outcome Analysis Summary
- Build Logs
- Test Logs
- OSV Report
```

No failure should terminate without recorded evidence where possible.

---

## 17. Retry Lifecycle

After Outcome Analysis:

```text
Restore Clean Baseline
  ↓
Apply Accepted Patch Set
  ↓
Planning Agent
  ↓
Patch Execution
  ↓
Validation
```

The next attempt always starts from a deterministic state.

---

## 18. Stop Conditions

The workflow stops when:

```text
- Baseline Build fails
- Validation succeeds for all automatable vulnerabilities
- Planner determines all remaining vulnerabilities require MANUAL_REVIEW
- Patch application fails with no safe alternative
- Maximum remediation attempts reached
```

Recommended default:

```text
maxAttempts = 3
```

---

## 19. Manual Review Handling

### Case A: Manual review only and no accepted patches

Planner returns all remaining vulnerabilities as MANUAL_REVIEW and no vulnerabilities were remediated.

Result:

```text
Manual Review Report
No PR
```

### Case B: Manual review after accepted patches

Planner returns remaining vulnerabilities as MANUAL_REVIEW and accepted patches already exist.

Result:

```text
Partial PR
```

---

## 20. Maximum Attempt Handling

### Accepted Patch Set exists

If maximum attempts are reached and accepted patches exist:

```text
Create Partial PR
Remaining vulnerabilities are marked:
- FAILED_AFTER_MAX_ATTEMPTS, or
- MANUAL_REVIEW_REQUIRED
```

### No Accepted Patch Set exists

If maximum attempts are reached and no accepted patch set exists:

```text
FAILED_MAX_ATTEMPTS
No PR
```

---

## 21. PR Creation Conditions

The PR Creation Tool is invoked only when:

```text
- At least one vulnerability is remediated
- Accepted Patch Set exists
- Final Validation SUCCESS
- Change Scope Validation passed
- Build passed
- Tests passed
- OSV Validation completed
- No new Critical/High vulnerabilities introduced
- Remaining vulnerabilities, if any, are classified as MANUAL_REVIEW
```

The PR type is determined by remediation outcome:

```text
FULL_REMEDIATION
PARTIAL_REMEDIATION
```

---

## 22. Orchestrator Decision Rules

The Orchestrator never makes engineering remediation decisions.

It only routes execution based on structured outputs.

Examples:

```text
Planning Agent -> PATCH
  ↓
Run Patch Tool

Planning Agent -> MANUAL_REVIEW
  ↓
Stop or Create Partial PR

Planning Agent -> REQUEST_ADDITIONAL_EVIDENCE
  ↓
Run Requested Deterministic Tool

Validation -> SUCCESS
  ↓
Update Accepted Patch Set

Validation -> FAILURE
  ↓
Run Outcome Analysis
```

---

## 23. Orchestration Pseudocode

```text
Initialize Workspace
Initialize Attempt Manifest

Checkout Repository
Run Baseline Build

If Baseline Build Failed
    Persist Baseline Build Result
    Stop with BASELINE_BUILD_FAILED
EndIf

Run OSV Scanner
Run Project Analyzer

acceptedPatchSet = []
attempt = 1

While attempt <= maxAttempts

    Restore Clean Baseline
    Apply Accepted Patch Set

    Run Planning Agent

    If Additional Investigation Requested

        If investigationCount >= maxAdditionalInvestigationRequestsPerAttempt
            Record Investigation Limit Reached
            Reinvoke Planning Agent With Investigation Limit Constraint
            Continue
        Else
            Run Requested Tool
            Persist New Artifact
            Update Manifest
            Continue
        EndIf

    EndIf

    If Planner returned only MANUAL_REVIEW

        If acceptedPatchSet is empty
            Stop with MANUAL_REVIEW_REQUIRED and no PR
        Else
            Create Partial PR
            Stop with PR_CREATED
        EndIf

    EndIf

    Run Patch Dry Run

    If Dry Run Failed
        Persist Dry Run Result
        Run Outcome Analysis
        attempt++
        Continue
    EndIf

    Run Patch Apply

    If Patch Apply Failed
        Persist Patch Application Proof
        Run Outcome Analysis
        attempt++
        Continue
    EndIf

    Run Validation

    If Validation Success
        Update Accepted Patch Set

        If Remaining Vulnerabilities == 0
            Create Full PR
            Stop with PR_CREATED
        ElseIf Remaining Vulnerabilities are MANUAL_REVIEW
            Create Partial PR
            Stop with PR_CREATED
        EndIf
    EndIf

    Persist Validation Result
    Run Outcome Analysis
    attempt++

EndWhile

If acceptedPatchSet exists
    Create Partial PR
    Stop with PR_CREATED
Else
    Stop with FAILED_MAX_ATTEMPTS
EndIf
```

---

## 24. Phase 5 Freeze Decision

Phase 5 is frozen with this ADK Workflow Orchestration Specification.

Phase 5 formally defines:

```text
- workflow execution lifecycle
- runtime ownership
- state transitions
- attempt lifecycle
- attempt counting rules
- additional investigation lifecycle
- investigation guard behavior
- data regeneration policy
- patch execution lifecycle
- validation lifecycle
- validation success semantics
- accepted patch set lifecycle
- outcome analysis routing
- failure artifact persistence
- manual review handling
- maximum attempt handling
- PR creation conditions
- orchestrator decision rules
- runtime pseudocode
```

Next phase:

```text
Phase 6 - Implementation Plan and Code Structure
```
