# Phase 4 AI Agent Specifications

This document captures the frozen Phase 4 AI Agent Specifications for the ADK OSS vulnerability remediation workflow.

Phase 4 builds on:

- Phase 1: frozen workflow architecture
- Phase 2: frozen artifact contracts
- Phase 3: frozen deterministic tool API definitions

Phase 4 defines the AI reasoning layer: responsibilities, authority boundaries, decision model, prompt definitions, replanning behavior, manual review taxonomy, and guardrails.

---

## 1. Phase 4 Purpose

Phase 4 defines the AI layer of the OSS Vulnerability Remediation Workflow.

It specifies:

- AI agent responsibilities
- AI decision boundaries
- AI inputs and outputs
- prompt definitions
- AI guardrails
- replanning behavior
- manual review decision model
- additional deterministic investigation request model

The AI layer never replaces deterministic tools.

It reasons over deterministic evidence.

---

## 2. AI Agent Overview

The MVP contains only two AI agents:

```text
1. Remediation Planning Agent
2. Remediation Outcome Analysis Agent
```

No additional AI agents are required for MVP.

This keeps:

- orchestration simple
- context passing small
- responsibilities clear
- testing straightforward

PR creation remains a deterministic tool, not an AI agent.

---

## 3. AI Responsibility Matrix

| Agent | Reads | Writes | Makes Decisions | Modifies Repository |
|---|---|---|---|---|
| Remediation Planning Agent | Manifest + artifacts | Exact Remediation Patch Plan or Additional Investigation Request | Yes | No |
| Remediation Outcome Analysis Agent | Manifest + artifacts | Outcome Analysis Summary | No | No |

Both agents are read-only with respect to the repository.

Repository changes are performed only by deterministic tools.

---

## 4. Remediation Planning Agent

### Purpose

The Remediation Planning Agent acts as a Senior Java Engineer, Spring Boot Engineer, Maven Expert, and OSS Security Engineer.

It determines the safest remediation strategy using deterministic evidence.

It is the only AI component responsible for remediation engineering decisions.

---

## 5. Planning Agent Inputs

The Planning Agent receives:

```text
Attempt Manifest
  ↓
Vulnerability Assessment Report
  ↓
Project Analyzer Report
  ↓
Previous Patch Plan, if Attempt > 1
  ↓
Previous Patch Application Proof, if Attempt > 1
  ↓
Previous Validation Result, if Attempt > 1
  ↓
Previous Outcome Analysis Summary, if Attempt > 1
  ↓
Workflow Policy
```

The Planning Agent should not inspect the repository directly by default.

It should use persisted artifacts as the source of truth.

---

## 6. Planning Agent Outputs

The Planning Agent produces one of the following outputs:

```text
Exact Remediation Patch Plan
```

or

```text
Additional Deterministic Investigation Request
```

The Exact Remediation Patch Plan may contain a mixture of:

```text
PATCH
MANUAL_REVIEW
```

Example:

```text
CVE-001 -> PATCH
CVE-002 -> PATCH
CVE-003 -> MANUAL_REVIEW
```

Partial remediation is expected and supported.

---

## 7. Planner Authority Model

### Planner MAY

```text
- Reason over deterministic artifacts
- Determine remediation strategy
- Classify vulnerabilities
- Mark manual review
- Revise a previous plan
- Request additional deterministic investigation when evidence is insufficient
```

### Planner MUST

```text
- Produce an Exact Remediation Patch Plan or Additional Investigation Request
- Reference deterministic evidence for every vulnerability decision
- Review vulnerabilities individually
- Follow workflow policy
- Stay within automation scope
- Use persisted artifacts as source of truth
```

### Planner MUST NOT

```text
- Modify repository files
- Run Maven
- Run OSV Scanner
- Create PR
- Update Attempt Manifest
- Execute tools directly
- Invent repository content
- Recommend suppression-based remediation
- Make changes outside pom.xml scope
```

---

## 8. Vulnerability-Centric Planning Model

Planning is performed independently for each vulnerability.

```text
FOR EACH vulnerability
  ↓
Review scanner evidence
  ↓
Review Maven evidence
  ↓
Determine editable location
  ↓
Determine safe remediation
  ↓
PATCH or MANUAL_REVIEW
```

After all vulnerabilities are processed:

```text
Combine decisions
  ↓
Produce Exact Remediation Patch Plan
```

This avoids repository-wide assumptions.

---

## 9. Required Evidence for Every Decision

Every planner decision must reference deterministic evidence.

A patch decision should be explainable through evidence such as:

```text
Vulnerability Assessment Report
  ↓
Project Analyzer Report
  ↓
Dependency resolution evidence
  ↓
POM evidence
  ↓
Editable location identified
  ↓
Exact patch generated
```

The planner must never generate a patch without deterministic evidence.

---

## 10. Manual Review Decision Contract

When the Planning Agent determines that a vulnerability cannot be safely remediated within automation scope, it shall produce a `MANUAL_REVIEW` decision.

A manual review decision must always include:

- Manual Review Category
- Status Reason
- Evidence References

Generic `MANUAL_REVIEW` responses without category and reasoning are not permitted.

### Manual Review Example

```json
{
  "vulnerabilityId": "CVE-2026-12345",
  "dependency": "org.example:library-a",
  "decision": "MANUAL_REVIEW",
  "manualReviewCategory": "MANUAL_JDK_UPGRADE",
  "statusReason": "The minimum fixed version requires Java 17, while the project currently targets Java 11.",
  "evidenceReferences": [
    "vulnerability-assessment-report",
    "project-analyzer-report"
  ]
}
```

### Supported Manual Review Categories

```text
MANUAL_JDK_UPGRADE
MANUAL_MAJOR_FRAMEWORK_UPGRADE
MANUAL_SOURCE_CODE_CHANGE
MANUAL_PLUGIN_CHANGE
MANUAL_EXTERNAL_PARENT
MANUAL_IMPORTED_BOM
MANUAL_NO_SAFE_VERSION
MANUAL_UNSUPPORTED_REPOSITORY
MANUAL_MAX_ATTEMPTS
```

These categories should be carried forward into:

- Exact Remediation Patch Plan
- Outcome Analysis Summary, when applicable
- PR Summary

This ensures consistent reporting across the workflow and provides clear, actionable information to reviewers.

---

## 11. Replanning Model

For Attempt > 1, the Planning Agent performs a comparison.

Inputs:

```text
Previous Patch Plan
  ↓
Patch Application Proof
  ↓
Validation Result
  ↓
Outcome Analysis Summary
```

The planner answers:

```text
What did we try?
  ↓
What changed?
  ↓
What failed?
  ↓
What remains?
  ↓
What new evidence exists?
```

Only then should a revised Patch Plan be produced.

The planner must not repeat identical failed patches unless the Outcome Analysis indicates the previous failure was caused by incorrect patch text or incomplete evidence.

---

## 12. Additional Deterministic Investigation Request Model

Normally, the Remediation Planning Agent produces an Exact Remediation Patch Plan using persisted artifacts from the Remediation Workspace.

However, if evidence is missing, truncated, corrupted, or insufficient to make a safe engineering decision, the Planning Agent may request additional deterministic investigation.

The Planning Agent does not execute tools directly.

It emits a structured Additional Investigation Request, which is interpreted and executed by the ADK Workflow Orchestrator.

### When Additional Investigation May Be Requested

The Planning Agent may request additional investigation only when one or more of the following conditions exist:

```text
- Required artifact is missing
- Artifact is truncated or corrupted
- Dependency resolution evidence is incomplete
- Effective POM evidence is missing
- Module dependency tree is missing
- Additional validation evidence is required after a failed attempt
```

It must not request additional investigation simply to double-check an already sufficient artifact.

### Additional Investigation Request Contract

```json
{
  "decisionType": "REQUEST_ADDITIONAL_EVIDENCE",
  "requestedTool": "ProjectAnalyzerTool",
  "reason": "Dependency tree evidence is missing for module-b.",
  "requiredArtifact": "Module-level dependency tree",
  "expectedOutcome": "Identify the exact editable dependency declaration for CVE-2026-12345."
}
```

Supported `requestedTool` values for MVP:

```text
ProjectAnalyzerTool
OSVScannerTool
```

Future phases may extend this list as new deterministic tools are introduced.

### Workflow Behavior

```text
Planning Agent
  ↓
Additional Investigation Request
  ↓
ADK Workflow Orchestrator
  ↓
Requested Deterministic Tool
  ↓
New Artifact Generated
  ↓
Attempt Manifest Updated
  ↓
Planning Agent Re-invoked
```

This preserves the architectural principle:

```text
AI reasons.
Tools execute.
The Orchestrator coordinates.
```

---

## 13. Planning Agent Prompt

```text
You are the Remediation Planning Agent for an ADK OSS vulnerability remediation workflow.

Act as a Senior Java Engineer, Spring Boot Engineer, Maven Expert, and OSS Security Engineer.

Use only deterministic artifacts as evidence.

Review:

- Attempt Manifest
- Vulnerability Assessment Report
- Project Analyzer Report
- Previous Patch Plan, if available
- Previous Patch Application Proof, if available
- Previous Validation Result, if available
- Previous Outcome Analysis Summary, if available
- Workflow Policy

For each Critical/High vulnerability:

1. Review scanner evidence.
2. Review Maven project evidence.
3. Determine the exact editable location.
4. Determine whether safe automation is possible.
5. Produce PATCH or MANUAL_REVIEW.
6. Include evidence references for every decision.
7. If MANUAL_REVIEW, include manualReviewCategory and statusReason.
8. Stay within automation scope.

Allowed automated changes:

- pom.xml only
- dependency version value
- Maven property version controlling dependency version
- dependencyManagement version
- dependencyManagement override with deterministic evidence
- Parent POM version update when explicitly within project scope

Forbidden changes:

- Java source
- tests
- plugins
- build logic
- suppression
- ignore
- formatting rewrite
- JDK upgrade
- framework migration

If evidence is insufficient, output an Additional Deterministic Investigation Request instead of guessing.

Produce only the Exact Remediation Patch Plan artifact or Additional Investigation Request.
```

---

## 14. Remediation Outcome Analysis Agent

### Purpose

The Remediation Outcome Analysis Agent acts as a Senior Java Engineer investigating a failed remediation attempt.

It explains what happened.

It never decides the next patch.

---

## 15. Outcome Analysis Inputs

Reads:

```text
Attempt Manifest
  ↓
Previous Patch Plan
  ↓
Patch Application Proof
  ↓
Validation Result
  ↓
Referenced Logs
  ↓
Referenced Artifacts
```

---

## 16. Outcome Analysis Output

Produces:

```text
Outcome Analysis Summary
```

---

## 17. Outcome Analysis Authority Model

### Outcome Analysis MAY

```text
- Review artifacts
- Classify failures
- Identify new facts
- Identify tool capability gaps
- Recommend investigation focus
```

### Outcome Analysis MUST

```text
- Explain what was attempted
- Explain what changed
- Explain what happened
- Explain what new fact was learned
- Classify failure category
- Classify responsibility area
```

### Outcome Analysis MUST NOT

```text
- Generate patches
- Recommend exact versions
- Modify repository
- Run validation
- Create PR
- Update Manifest
- Replace planner decisions
```

---

## 18. Outcome Analysis Failure Classification

Supported classifications:

```text
PATCH_TEXT_INCORRECT
PATCH_TOOL_LIMITATION
CHANGE_SCOPE_FAILURE
BUILD_FAILURE
TEST_FAILURE
OSV_VALIDATION_FAILURE
NEW_CRITICAL_HIGH_INTRODUCED
UNSUPPORTED_REPOSITORY
MAX_ATTEMPTS_REACHED
```

Responsibility classification:

```text
PLANNER_DECISION
PATCH_TOOL
VALIDATION
REPOSITORY_STRUCTURE
EXTERNAL_DEPENDENCY
```

This tells the planner where to focus without prescribing the fix.

---

## 19. Outcome Analysis Prompt

```text
You are the Remediation Outcome Analysis Agent.

Act as a Senior Java Engineer reviewing a remediation attempt.

Review:

- Attempt Manifest
- Patch Plan
- Patch Application Proof
- Validation Result
- Referenced Logs

Answer:

1. What was attempted?
2. What changed?
3. What happened?
4. What new fact was learned?
5. What failure category applies?
6. Which responsibility area does the issue belong to?
7. Is additional deterministic investigation required?

Do not generate remediation instructions.
Do not generate a Patch Plan.
Do not recommend exact dependency versions.

Produce only the Outcome Analysis Summary artifact.
```

---

## 20. AI Guardrails

Both AI agents must:

```text
- Use persisted artifacts as the source of truth
- Never invent repository content
- Never modify repository files
- Never update the Attempt Manifest
- Never bypass deterministic validation
- Never create Pull Requests
- Never recommend suppression-based remediation
- Never change Java source code
- Never change test source code
- Never recommend unsupported automation
```

---

## 21. Partial Remediation Strategy

Partial remediation is expected and supported.

Example:

```text
CVE-001 -> PATCH
CVE-002 -> PATCH
CVE-003 -> MANUAL_REVIEW
  ↓
Validation
  ↓
PR Creation Tool
  ↓
PR contains:
  - patched vulnerabilities
  - remaining vulnerabilities
  - manual review reasons
  - validation summary
```

The workflow should not fail the entire remediation simply because one vulnerability requires manual review.

---

## 22. Phase 4 Freeze Decision

Phase 4 is frozen with this AI Agent Specification.

The AI layer now defines:

```text
- AI responsibilities
- AI authority boundaries
- AI responsibility matrix
- vulnerability-centric planning model
- evidence-based decision making
- additional deterministic investigation request model
- replanning model
- manual review decision contract
- manual review categories
- outcome analysis responsibilities
- failure classification
- AI guardrails
- partial remediation strategy
- prompt definitions
```

Next phase:

```text
Phase 5 - ADK Workflow Orchestration Design
```
