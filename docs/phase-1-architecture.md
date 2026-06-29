# Phase 1 Architecture: ADK OSS Remediation Workflow

This document captures the frozen Phase 1 architecture for the ADK OSS vulnerability remediation workflow.

## 1. Project Goal

Build an enterprise-grade ADK multi-agent workflow that performs OSS vulnerability remediation for Java Spring Boot Maven applications.

The MVP focuses on Maven-based Java/Spring Boot projects and Critical/High vulnerabilities identified by OSV Scanner.

Supported project scope:

- Maven single-module projects
- Maven multi-module projects
- Parent-child POM hierarchies
- `dependencyManagement`
- Maven properties
- Direct dependencies
- Transitive dependencies when deterministic evidence exists

Primary automation goal:

- Resolve Critical and High OSS vulnerabilities where remediation can be performed safely through POM-only dependency version changes.
- Preserve source code, build behavior, and formatting safety.
- Create a PR with clear remediation and validation evidence, including partial remediation when some vulnerabilities require manual review.

---

## 2. Core Architecture Principle

The architecture separates reasoning, execution, and artifact storage.

```text
AI Agents      = reasoning and engineering decisions
Tools          = deterministic facts and execution
Workspace      = persisted artifacts
Manifest       = artifact index and attempt status
ADK Workflow   = execution order and lifecycle control
```

Important rule:

> Tools provide facts and execute exact instructions. AI agents make engineering decisions.

No deterministic tool should independently decide the remediation strategy.

---

## 3. High-Level Workflow

```text
Clone repository
  ↓
Baseline build
  ↓
OSV scan
  ↓
Project analysis
  ↓
Remediation planning
  ↓
Patch application
  ↓
Validation
  ↓
Outcome analysis if needed
  ↓
Replan / manual review / PR
```

---

## 4. AI Agent Responsibilities

### 4.1 Remediation Planning Agent

Responsible for:

- Reviewing the Vulnerability Assessment Report.
- Reviewing Maven/project facts from the Project Analyzer Report.
- Deciding which vulnerabilities are automatable.
- Deciding which vulnerabilities require manual review.
- Producing an Exact Remediation Patch Plan for patchable vulnerabilities.
- Replanning after failed validation attempts.
- Ensuring all remediation decisions remain within the allowed automation scope.

The planning decision is per vulnerability. A single remediation plan may contain both:

- patchable vulnerabilities
- manual-review vulnerabilities

The Remediation Planning Agent must not:

- directly run build/test/OSV validation
- directly create pull requests
- modify Java source code
- modify files outside allowed scope
- invent file content not present in repository/workspace artifacts

### 4.2 Remediation Outcome Analysis Agent

Responsible for analyzing failed attempts.

It answers:

- What did we try?
- What changed?
- What happened?
- What new facts did we learn?
- Which failure category applies?
- Is there a deterministic tool capability gap?

It must not:

- create remediation patches
- apply patches
- run validation
- create pull requests

---

## 5. Deterministic Tool Responsibilities

### 5.1 Repo Checkout Tool

Responsible for:

- cloning the repository
- checking out the reference branch
- preserving a clean baseline workspace
- restoring the clean baseline before each retry attempt

### 5.2 Baseline Build Tool

Responsible for:

- running the baseline Maven build before remediation starts
- storing the baseline build result and logs

If baseline build fails, the workflow stops. Remediation must not proceed because post-remediation validation would not be trustworthy.

### 5.3 OSV Scanner Tool

Responsible for:

- running or reading the initial OSV scan
- filtering configured severities, defaulting to Critical and High
- running post-remediation OSV validation
- storing scanner reports in the workspace

### 5.4 Project Analyzer Tool

Responsible for Maven facts only.

It may collect:

- Maven modules
- POM file locations
- dependency tree evidence
- effective POM evidence
- Maven properties
- `dependencyManagement`
- parent hierarchy
- Java version
- Spring Boot version
- potential editable POM locations

It must not recommend how to remediate.

### 5.5 Generic Patch Apply Tool

Responsible for applying exact patch instructions only.

Input is the Exact Remediation Patch Plan.

The patch tool does not understand Maven strategy. It only applies exact replacements:

```text
file + oldText + newText + expectedOccurrences
```

It produces Patch Application Proof containing:

- patch status
- changed files
- occurrence counts
- diff summary
- errors, if any

### 5.6 Validation Tool

Responsible for four validation groups:

1. Change Scope Validation
2. Maven Build Validation
3. Maven Test Validation
4. OSV Validation

The Validation Tool stores the Validation Result, logs, and related artifacts in the workspace.

### 5.7 PR Creation Tool

This is a tool, not an AI agent.

Reason: by PR creation time, all decisions have already been made by the Planning Agent and validated by deterministic tools.

Responsible for:

- generating PR title
- generating PR body from workspace artifacts
- creating the GitHub PR
- linking or referencing relevant remediation artifacts when needed

---

## 6. Final Automation Scope

Allowed automated changes:

- `pom.xml` files only
- dependency version value changes
- Maven property value changes when the property controls a vulnerable dependency version
- `dependencyManagement` version value changes
- `dependencyManagement` override additions when deterministic transitive dependency evidence exists
- Parent POM version updates only when explicitly within safe scope

Parent POM version updates are allowed only when they do not require:

- JDK upgrade
- Java/source code changes
- Spring Boot major migration
- plugin/build logic changes
- broad framework migration

Otherwise, parent POM version changes require manual review.

Blocked or manual-review scenarios:

- Java source code changes
- test source changes
- JDK upgrades
- Spring Boot major migrations
- plugin/build logic changes
- vulnerability suppression or ignore workarounds
- full `pom.xml` formatting rewrite
- changes outside POM files

---

## 7. Remediation Workspace

The Remediation Workspace is a folder/artifact store.

It does not control workflow.

Example structure:

```text
remediation-workspace/
  manifest.json
  baseline/
    baseline-build-result.json
    vulnerability-assessment-report.json
    project-analyzer-report.json
  attempt-1/
    remediation-patch-plan.json
    patch-application-proof.json
    validation-result.json
    outcome-analysis-summary.json
    build.log
    test.log
    osv-report.json
    patch.diff
  attempt-2/
    ...
  final/
    remediation-summary.json
    pr-description.md
```

Every tool and agent output should be persisted in the Remediation Workspace.

---

## 8. Remediation Attempt Manifest

The manifest is an index of workspace artifacts and attempt status.

It is not an active workflow controller.

Responsibilities:

- index artifact paths
- track current attempt number
- track attempt status
- track workflow status
- avoid hardcoded artifact paths
- support auditability, reproducibility, and debugging

Example:

```json
{
  "workflowStatus": "VALIDATION_FAILED",
  "maxAttempts": 3,
  "baseline": {
    "buildResult": "baseline/baseline-build-result.json",
    "vulnerabilityReport": "baseline/vulnerability-assessment-report.json",
    "projectAnalyzerReport": "baseline/project-analyzer-report.json"
  },
  "attempts": [
    {
      "attemptNumber": 1,
      "status": "VALIDATION_FAILED",
      "patchPlan": "attempt-1/remediation-patch-plan.json",
      "patchProof": "attempt-1/patch-application-proof.json",
      "validationResult": "attempt-1/validation-result.json",
      "outcomeSummary": "attempt-1/outcome-analysis-summary.json"
    }
  ]
}
```

---

## 9. Validation Model

Validation runs after patch application and before PR creation.

Validation groups:

```text
Change Scope Validation
  ↓
Maven Build Validation
  ↓
Maven Test Validation
  ↓
OSV Validation
```

### 9.1 Change Scope Validation

Must verify:

- no Java/source code changes
- only `pom.xml` files changed
- no full `pom.xml` formatting/rewrite
- only intended dependency/version text changed
- no suppression/ignore/config workaround added
- no JDK version change
- no plugin/build logic change unless explicitly allowed

If Change Scope Validation fails, build/test/OSV validation should not continue for that attempt.

---

## 10. Patch Application Failure Classification

If patch application fails, the Outcome Analysis Agent classifies the failure.

Categories:

### Planner issue

The planner generated incorrect patch text or an invalid exact replacement.

Expected action:

- Planner creates a revised patch plan.

### Patch Tool limitation

The patch plan is valid, but the generic patch tool cannot apply it because of tool limitations.

Expected action:

- Agent may apply a controlled direct patch only if the change remains within automation scope.
- Record the tool capability gap for future tool improvement.

### Workspace inconsistency

Unexpected workspace state issue, such as rollback failure or missing expected files.

Expected action:

- Stop or manual review depending on severity.

### Unsupported repository structure

Repository or Maven structure prevents safe automated patching.

Expected action:

- Manual review.

---

## 11. Data Regeneration Policy

Default behavior:

- Never regenerate evidence by default.
- Use existing artifacts from the Remediation Workspace.

Regenerate evidence only when:

- an artifact is missing
- an artifact is truncated
- an artifact is corrupted
- the Remediation Planning Agent explicitly requests updated evidence
- the Remediation Outcome Analysis Agent determines existing evidence is insufficient

Regeneration is targeted, not global.

---

## 12. Remediation Attempt Lifecycle

Each attempt starts from a clean baseline plus any accepted successful patches.

Lifecycle:

```text
Clean baseline
  ↓
Planning
  ↓
Patch application
  ↓
Validation
  ↓
Outcome analysis if failed
  ↓
Rollback
  ↓
Next attempt
```

Exit conditions:

- validation succeeds
- planner decides remaining vulnerabilities require manual review
- patch application fails with no safe alternative
- max attempts reached

Recommended default:

```text
maxAttempts = 3
```

---

## 13. Partial Remediation and PR Strategy

Partial PRs are allowed.

A PR may be created when:

- at least one vulnerability is successfully remediated
- final validation passes for applied changes
- remaining vulnerabilities are clearly classified
- no new Critical/High vulnerability is introduced

The PR must make partial remediation explicit.

---

## 14. PR Summary Requirements

The PR body should include a remediation summary table:

| Vulnerability ID | Dependency | Old Version | New Version | Status | Status Reason |
|---|---|---|---|---|---|

Status examples:

- `REMEDIATED`
- `MANUAL_REVIEW_REQUIRED`
- `FAILED_AFTER_MAX_ATTEMPTS`

The PR should also include a validation summary:

- Baseline Build
- Change Scope Validation
- Maven Build
- Maven Tests
- OSV Scan
- Remaining Critical/High vulnerability count
- New Critical/High introduced count

Optional artifact references:

- Patch Plan
- Patch Application Proof
- Validation Result
- Outcome Analysis Summary
- Logs

---

## 15. Final Phase 1 Decision

Phase 1 is frozen with this architecture:

```text
ADK Workflow Orchestrator = controls sequence
Remediation Workspace = stores artifacts
Attempt Manifest = indexes artifacts and statuses
AI Agents = reasoning and decisions
Deterministic Tools = facts and execution
PR Creation Tool = deterministic PR generation
```

Next phase: define artifact contracts.

Recommended Phase 2 order:

1. Attempt Manifest
2. Vulnerability Assessment Report
3. Project Analyzer Report
4. Exact Remediation Patch Plan
5. Patch Application Proof
6. Validation Result
7. Outcome Analysis Summary
8. PR Summary
