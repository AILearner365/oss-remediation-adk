# Phase 3 Deterministic Tool API Definitions

This document captures the frozen Phase 3 deterministic tool API definitions for the ADK OSS vulnerability remediation workflow.

Phase 3 builds on:

- Phase 1: frozen architecture and workflow ownership
- Phase 2: frozen artifact contracts

The goal of Phase 3 is to define deterministic tool APIs that are modular, auditable, testable, artifact-driven, and safe for retries and partial remediation.

---

## 1. Phase 3 Core Principle

Every deterministic tool follows this pattern:

```text
Input:
  workspace path / artifact reference / manifest reference

Execution:
  deterministic action only

Output:
  structured tool result envelope
  persisted artifact in workspace

Manifest update:
  performed only by ADK Workflow Orchestrator
```

Tools must not make remediation strategy decisions.

Tools should not call AI agents.

Tools should not directly update the Attempt Manifest.

---

## 2. Common Tool Result Envelope

Every deterministic tool should return the same outer envelope.

```json
{
  "toolName": "ProjectAnalyzerTool",
  "toolVersion": "1.0.0",
  "operation": "analyze_project",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "baseline/project-analyzer-report.json",
  "capabilities": [
    "MAVEN_MULTI_MODULE",
    "DEPENDENCY_TREE",
    "EFFECTIVE_POM"
  ],
  "limitations": [],
  "payload": {},
  "errors": [],
  "warnings": []
}
```

Recommended `status` values:

```text
SUCCESS
FAILED
PARTIAL
NOT_RUN
```

### Principal Engineer Clarification: Payload Size

Tool payloads are summaries only.

Full detailed outputs must be persisted as artifacts in the Remediation Workspace and referenced by artifact paths.

This prevents large logs, dependency trees, effective POMs, and raw scanner reports from being passed through tool responses or agent context unnecessarily.

---

## 3. Manifest Update Rule

Tools do not update the Attempt Manifest directly.

Correct flow:

```text
Tool runs
  ↓
Tool writes artifact
  ↓
Tool returns artifactPath
  ↓
ADK Workflow Orchestrator updates manifest
```

Reason:

```text
Avoid concurrent manifest writes.
Keep workflow state ownership centralized.
Make execution order easier to test.
```

---

## 4. Tool Responsibility Matrix

| Tool | Reads | Writes | Modifies Repository | Uses AI |
|---|---|---|---|---|
| Repo Checkout Tool | repository URL / branch | baseline workspace / attempt workspace | Yes | No |
| Baseline Build Tool | baseline repository | Baseline Build Result | No | No |
| OSV Scanner Tool | repository workspace | Vulnerability Assessment Report / OSV report | No | No |
| Project Analyzer Tool | repository workspace + vulnerability report | Project Analyzer Report | No | No |
| Generic Patch Apply Tool | repository workspace + patch plan | Patch Application Proof / diff | Yes | No |
| Validation Tool | patched workspace + patch proof | Validation Result / logs / OSV report | No | No |
| PR Creation Tool | manifest + final artifacts | PR Summary / PR body / GitHub PR | No local repo change | No |

---

## 5. Tool Capability Metadata

Each tool should publish capabilities and limitations.

Example:

```json
{
  "toolName": "ProjectAnalyzerTool",
  "toolVersion": "1.0.0",
  "capabilities": [
    "MAVEN_SINGLE_MODULE",
    "MAVEN_MULTI_MODULE",
    "DEPENDENCY_TREE",
    "EFFECTIVE_POM",
    "MAVEN_PROPERTIES",
    "DEPENDENCY_MANAGEMENT",
    "PARENT_POM_DETECTION"
  ],
  "limitations": [
    "Does not analyze Gradle projects",
    "Does not recommend remediation strategy"
  ]
}
```

This lets future tools expose different capabilities without changing the architecture.

---

## 6. Baseline Build Result Contract

Baseline Build Result is a first-class artifact because baseline build status controls whether remediation can safely proceed.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "baseline-build-result-001",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:00:00Z",
  "createdBy": "BaselineBuildTool",
  "status": "SUCCESS",
  "policy": {
    "baselineBuildRequired": true
  },
  "command": "mvn clean install",
  "exitCode": 0,
  "durationSeconds": 120,
  "logFile": "baseline/baseline-build.log",
  "logExcerpt": "BUILD SUCCESS",
  "artifactReferences": {
    "buildLog": "baseline/baseline-build.log"
  },
  "errors": [],
  "warnings": []
}
```

Failure example:

```json
{
  "schemaVersion": "1.0",
  "artifactId": "baseline-build-result-001",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:00:00Z",
  "createdBy": "BaselineBuildTool",
  "status": "FAILED",
  "policy": {
    "baselineBuildRequired": true
  },
  "command": "mvn clean install",
  "exitCode": 1,
  "durationSeconds": 58,
  "logFile": "baseline/baseline-build.log",
  "logExcerpt": "BUILD FAILURE",
  "failureCode": "BASELINE_BUILD_FAILED",
  "artifactReferences": {
    "buildLog": "baseline/baseline-build.log"
  },
  "errors": [
    "Baseline build failed. Remediation cannot proceed."
  ],
  "warnings": []
}
```

---

## 7. Repo Checkout Tool API

### Purpose

Prepare and restore repository workspaces.

### Responsibilities

```text
- Clone repository
- Checkout reference branch
- Capture baseline commit
- Create clean baseline workspace
- Restore clean baseline before retry attempts
- Apply accepted patch set before retry when applicable
```

### Capabilities

```json
[
  "CLONE_REPOSITORY",
  "CHECKOUT_BRANCH",
  "CAPTURE_BASELINE_COMMIT",
  "RESTORE_CLEAN_BASELINE",
  "APPLY_ACCEPTED_PATCH_SET"
]
```

### Checkout Baseline API

```json
{
  "toolName": "RepoCheckoutTool",
  "toolVersion": "1.0.0",
  "operation": "checkout_baseline",
  "input": {
    "repositoryUrl": "https://github.com/org/repo",
    "referenceBranch": "main",
    "workspaceRoot": "remediation-workspace"
  }
}
```

### Checkout Baseline Result

```json
{
  "toolName": "RepoCheckoutTool",
  "toolVersion": "1.0.0",
  "operation": "checkout_baseline",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": null,
  "capabilities": [
    "CLONE_REPOSITORY",
    "CHECKOUT_BRANCH",
    "CAPTURE_BASELINE_COMMIT",
    "RESTORE_CLEAN_BASELINE",
    "APPLY_ACCEPTED_PATCH_SET"
  ],
  "limitations": [],
  "payload": {
    "repositoryPath": "baseline/repository",
    "baselineCommit": "abc123"
  },
  "errors": [],
  "warnings": []
}
```

### Restore Attempt Workspace API

```json
{
  "toolName": "RepoCheckoutTool",
  "toolVersion": "1.0.0",
  "operation": "restore_attempt_workspace",
  "input": {
    "workspaceRoot": "remediation-workspace",
    "baselinePath": "baseline/repository",
    "attemptNumber": 2,
    "acceptedPatchSet": {
      "patchSetId": "accepted-patch-set-1",
      "patchIds": ["patch-1"]
    }
  }
}
```

### Restore Attempt Workspace Result

```json
{
  "toolName": "RepoCheckoutTool",
  "toolVersion": "1.0.0",
  "operation": "restore_attempt_workspace",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": null,
  "capabilities": [
    "RESTORE_CLEAN_BASELINE",
    "APPLY_ACCEPTED_PATCH_SET"
  ],
  "limitations": [],
  "payload": {
    "attemptWorkspace": "attempt-2/repository"
  },
  "errors": [],
  "warnings": []
}
```

---

## 8. Baseline Build Tool API

### Purpose

Verify the project can build before remediation starts.

### Responsibilities

```text
- Run baseline Maven build
- Store baseline build log
- Produce Baseline Build Result
- Halt workflow if baseline build fails
```

### Capabilities

```json
[
  "MAVEN_BUILD",
  "BUILD_LOG_CAPTURE",
  "BASELINE_BUILD_GATE"
]
```

### API

```json
{
  "toolName": "BaselineBuildTool",
  "toolVersion": "1.0.0",
  "operation": "run_baseline_build",
  "input": {
    "repositoryPath": "baseline/repository",
    "command": "mvn clean install",
    "outputPath": "baseline/baseline-build-result.json",
    "logFile": "baseline/baseline-build.log"
  }
}
```

### Result

```json
{
  "toolName": "BaselineBuildTool",
  "toolVersion": "1.0.0",
  "operation": "run_baseline_build",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "baseline/baseline-build-result.json",
  "capabilities": [
    "MAVEN_BUILD",
    "BUILD_LOG_CAPTURE",
    "BASELINE_BUILD_GATE"
  ],
  "limitations": [
    "Only Maven build is supported in MVP"
  ],
  "payload": {
    "command": "mvn clean install",
    "exitCode": 0,
    "durationSeconds": 120,
    "logFile": "baseline/baseline-build.log"
  },
  "errors": [],
  "warnings": []
}
```

---

## 9. OSV Scanner Tool API

### Purpose

Run/read OSV scan results and produce normalized vulnerability artifacts.

### Responsibilities

```text
- Run initial OSV scan
- Filter Critical/High findings
- Normalize OSV findings into Vulnerability Assessment Report
- Run post-remediation OSV validation
```

### Capabilities

```json
[
  "OSV_SCAN",
  "SEVERITY_FILTERING",
  "MAVEN_ECOSYSTEM_NORMALIZATION",
  "POST_REMEDIATION_SCAN"
]
```

### Initial Scan API

```json
{
  "toolName": "OSVScannerTool",
  "toolVersion": "1.0.0",
  "operation": "generate_vulnerability_assessment",
  "input": {
    "repositoryPath": "baseline/repository",
    "severityScope": ["CRITICAL", "HIGH"],
    "command": "osv-scanner scan source -r . --format json",
    "outputPath": "baseline/vulnerability-assessment-report.json",
    "rawReportPath": "baseline/osv-report.json"
  }
}
```

### Initial Scan Result

```json
{
  "toolName": "OSVScannerTool",
  "toolVersion": "1.0.0",
  "operation": "generate_vulnerability_assessment",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "baseline/vulnerability-assessment-report.json",
  "capabilities": [
    "OSV_SCAN",
    "SEVERITY_FILTERING",
    "MAVEN_ECOSYSTEM_NORMALIZATION"
  ],
  "limitations": [
    "Only OSV Scanner is supported in MVP"
  ],
  "payload": {
    "rawReportPath": "baseline/osv-report.json",
    "criticalCount": 0,
    "highCount": 1,
    "totalInScopeCount": 1
  },
  "errors": [],
  "warnings": []
}
```

### Post-Remediation Scan API

```json
{
  "toolName": "OSVScannerTool",
  "toolVersion": "1.0.0",
  "operation": "validate_post_remediation",
  "input": {
    "repositoryPath": "attempt-1/repository",
    "severityScope": ["CRITICAL", "HIGH"],
    "baselineAssessmentPath": "baseline/vulnerability-assessment-report.json",
    "outputPath": "attempt-1/osv-report.json"
  }
}
```

### Post-Remediation Scan Result

```json
{
  "toolName": "OSVScannerTool",
  "toolVersion": "1.0.0",
  "operation": "validate_post_remediation",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "attempt-1/osv-report.json",
  "capabilities": [
    "POST_REMEDIATION_SCAN"
  ],
  "limitations": [],
  "payload": {
    "remainingCriticalCount": 0,
    "remainingHighCount": 1,
    "newCriticalHighIntroduced": false
  },
  "errors": [],
  "warnings": []
}
```

---

## 10. Project Analyzer Tool API

### Purpose

Produce Maven project facts only.

### Responsibilities

```text
- Identify Maven structure
- Locate POM files
- Detect modules
- Capture dependency tree
- Capture effective POM
- Identify Java and Spring Boot metadata
- Provide dependency resolution evidence
- Provide POM snippets/evidence
```

### Capabilities

```json
[
  "MAVEN_SINGLE_MODULE",
  "MAVEN_MULTI_MODULE",
  "POM_DISCOVERY",
  "DEPENDENCY_TREE",
  "EFFECTIVE_POM",
  "MAVEN_PROPERTIES",
  "DEPENDENCY_MANAGEMENT",
  "PARENT_POM_DETECTION",
  "JAVA_VERSION_DETECTION",
  "SPRING_BOOT_DETECTION"
]
```

### API

```json
{
  "toolName": "ProjectAnalyzerTool",
  "toolVersion": "1.0.0",
  "operation": "analyze_project",
  "input": {
    "repositoryPath": "baseline/repository",
    "vulnerabilityAssessmentPath": "baseline/vulnerability-assessment-report.json",
    "outputPath": "baseline/project-analyzer-report.json",
    "artifactOutputDir": "baseline"
  }
}
```

### Result

```json
{
  "toolName": "ProjectAnalyzerTool",
  "toolVersion": "1.0.0",
  "operation": "analyze_project",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "baseline/project-analyzer-report.json",
  "capabilities": [
    "MAVEN_SINGLE_MODULE",
    "MAVEN_MULTI_MODULE",
    "POM_DISCOVERY",
    "DEPENDENCY_TREE",
    "EFFECTIVE_POM",
    "MAVEN_PROPERTIES",
    "DEPENDENCY_MANAGEMENT",
    "PARENT_POM_DETECTION",
    "JAVA_VERSION_DETECTION",
    "SPRING_BOOT_DETECTION"
  ],
  "limitations": [
    "Does not analyze Gradle projects",
    "Does not recommend remediation strategy",
    "Does not apply patches"
  ],
  "payload": {
    "projectType": "MAVEN_SPRING_BOOT",
    "isMultiModule": true,
    "pomFilesFound": 2,
    "dependencyEvidenceCount": 1,
    "effectivePomPath": "baseline/effective-pom.xml",
    "dependencyTreePath": "baseline/dependency-tree.json"
  },
  "errors": [],
  "warnings": []
}
```

---

## 11. Generic Patch Apply Tool API

### Purpose

Apply exact patch plan generated by the Remediation Planning Agent.

### Responsibilities

```text
- Read Exact Remediation Patch Plan
- Dry-run exact replacements if requested
- Apply exact oldText -> newText replacements
- Verify expected occurrence count
- Produce Patch Application Proof
- Produce patch diff
```

### Capabilities

```json
[
  "EXACT_TEXT_REPLACEMENT",
  "EXPECTED_OCCURRENCE_VALIDATION",
  "PATCH_DRY_RUN",
  "DIFF_GENERATION",
  "POM_FILE_ONLY_GUARD"
]
```

### Dry-Run API

```json
{
  "toolName": "GenericPatchApplyTool",
  "toolVersion": "1.0.0",
  "operation": "dry_run",
  "input": {
    "attemptNumber": 1,
    "repositoryPath": "attempt-1/repository",
    "patchPlanPath": "attempt-1/remediation-patch-plan.json",
    "outputPath": "attempt-1/patch-dry-run-result.json"
  }
}
```

### Dry-Run Result

```json
{
  "toolName": "GenericPatchApplyTool",
  "toolVersion": "1.0.0",
  "operation": "dry_run",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "attempt-1/patch-dry-run-result.json",
  "capabilities": [
    "PATCH_DRY_RUN",
    "EXPECTED_OCCURRENCE_VALIDATION"
  ],
  "limitations": [
    "Does not understand Maven semantics",
    "Only validates exact text occurrence"
  ],
  "payload": {
    "patchesRequested": 1,
    "patchesReadyToApply": 1,
    "filesToChange": ["pom.xml"]
  },
  "errors": [],
  "warnings": []
}
```

### Apply API

```json
{
  "toolName": "GenericPatchApplyTool",
  "toolVersion": "1.0.0",
  "operation": "apply",
  "input": {
    "attemptNumber": 1,
    "repositoryPath": "attempt-1/repository",
    "patchPlanPath": "attempt-1/remediation-patch-plan.json",
    "outputPath": "attempt-1/patch-application-proof.json",
    "diffFile": "attempt-1/patch.diff"
  }
}
```

### Apply Result

```json
{
  "toolName": "GenericPatchApplyTool",
  "toolVersion": "1.0.0",
  "operation": "apply",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "attempt-1/patch-application-proof.json",
  "capabilities": [
    "EXACT_TEXT_REPLACEMENT",
    "DIFF_GENERATION"
  ],
  "limitations": [
    "Does not understand Maven semantics"
  ],
  "payload": {
    "patchesRequested": 1,
    "patchesApplied": 1,
    "filesChanged": ["pom.xml"],
    "diffFile": "attempt-1/patch.diff"
  },
  "errors": [],
  "warnings": []
}
```

### Failure Behavior

If `oldText` is not found or appears multiple times:

```text
- Do not apply unsafe partial changes.
- Write Patch Application Proof with status FAILED.
- Do not run validation.
- Send failure to Outcome Analysis Agent.
```

Recommended failure codes:

```text
PATCH_OLD_TEXT_NOT_FOUND
PATCH_OCCURRENCE_MISMATCH
PATCH_FILE_NOT_FOUND
PATCH_UNSUPPORTED_FILE
PATCH_WRITE_FAILED
```

---

## 12. Validation Tool API

### Purpose

Validate applied patch set.

### Responsibilities

```text
- Run Change Scope Validation
- Run Maven Build Validation
- Run Maven Test Validation
- Run OSV Validation
- Produce Validation Result
```

The Validation Tool internally orchestrates these validations. The ADK workflow should call the Validation Tool once per attempt.

### Capabilities

```json
[
  "CHANGE_SCOPE_VALIDATION",
  "MAVEN_BUILD_VALIDATION",
  "MAVEN_TEST_VALIDATION",
  "OSV_VALIDATION",
  "LOG_CAPTURE",
  "FAIL_FAST_VALIDATION"
]
```

### API

```json
{
  "toolName": "ValidationTool",
  "toolVersion": "1.0.0",
  "operation": "validate_attempt",
  "input": {
    "attemptNumber": 1,
    "repositoryPath": "attempt-1/repository",
    "patchPlanPath": "attempt-1/remediation-patch-plan.json",
    "patchApplicationProofPath": "attempt-1/patch-application-proof.json",
    "baselineAssessmentPath": "baseline/vulnerability-assessment-report.json",
    "outputPath": "attempt-1/validation-result.json",
    "artifactOutputDir": "attempt-1",
    "commands": {
      "build": "mvn clean install",
      "test": "mvn test",
      "osv": "osv-scanner scan source -r . --format json"
    }
  }
}
```

### Result

```json
{
  "toolName": "ValidationTool",
  "toolVersion": "1.0.0",
  "operation": "validate_attempt",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "attempt-1/validation-result.json",
  "capabilities": [
    "CHANGE_SCOPE_VALIDATION",
    "MAVEN_BUILD_VALIDATION",
    "MAVEN_TEST_VALIDATION",
    "OSV_VALIDATION",
    "LOG_CAPTURE",
    "FAIL_FAST_VALIDATION"
  ],
  "limitations": [
    "Only Maven validation is supported in MVP",
    "Only OSV scanner validation is supported in MVP"
  ],
  "payload": {
    "changeScopeValidation": "SUCCESS",
    "buildValidation": "SUCCESS",
    "testValidation": "SUCCESS",
    "osvValidation": "SUCCESS",
    "remainingCriticalCount": 0,
    "remainingHighCount": 1,
    "newCriticalHighIntroduced": false
  },
  "errors": [],
  "warnings": []
}
```

### Change Scope Validation Checks

```text
- only pom.xml files changed
- no Java/source code changes
- no pom formatting/rewrite
- only intended dependency/version changes
- no suppression/ignore workaround
- no JDK version change
- no plugin/build logic change unless explicitly allowed
```

### Failure Behavior

If Change Scope Validation fails:

```text
- stop validation immediately
- do not run build/test/OSV
- write Validation Result with failedStage = CHANGE_SCOPE_VALIDATION
```

Recommended failure codes:

```text
CHANGE_SCOPE_FAILURE
BUILD_FAILURE
TEST_FAILURE
OSV_SCAN_FAILURE
OSV_STILL_REPORTS_VULNERABILITY
NEW_CRITICAL_HIGH_INTRODUCED
VALIDATION_TIMEOUT
```

---

## 13. PR Creation Tool API

### Purpose

Generate and create PR using frozen artifacts.

### Responsibilities

```text
- Read manifest
- Read final patch plan
- Read validation result
- Read remediation decisions
- Generate PR Summary artifact
- Generate PR body markdown
- Create GitHub PR
```

### Capabilities

```json
[
  "PR_SUMMARY_GENERATION",
  "PR_BODY_GENERATION",
  "GITHUB_PR_CREATION"
]
```

### API

```json
{
  "toolName": "PRCreationTool",
  "toolVersion": "1.0.0",
  "operation": "create_pr",
  "input": {
    "manifestPath": "manifest.json",
    "repositoryPath": "attempt-1/repository",
    "baseBranch": "main",
    "headBranch": "oss-remediation/main-20260628",
    "outputPath": "final/pr-summary.json",
    "prDescriptionPath": "final/pr-description.md"
  }
}
```

### Result

```json
{
  "toolName": "PRCreationTool",
  "toolVersion": "1.0.0",
  "operation": "create_pr",
  "status": "SUCCESS",
  "failureCode": null,
  "artifactPath": "final/pr-summary.json",
  "capabilities": [
    "PR_SUMMARY_GENERATION",
    "PR_BODY_GENERATION",
    "GITHUB_PR_CREATION"
  ],
  "limitations": [
    "Only GitHub PR creation is supported in MVP"
  ],
  "payload": {
    "prDescriptionPath": "final/pr-description.md",
    "pullRequestUrl": "https://github.com/org/repo/pull/123",
    "prType": "PARTIAL_REMEDIATION"
  },
  "errors": [],
  "warnings": []
}
```

### PR Eligibility Checks

```text
- baseline build passed
- at least one vulnerability remediated
- final validation status is SUCCESS
- change scope validation passed
- build passed
- tests passed
- OSV scan completed
- no new Critical/High vulnerability introduced
- remaining vulnerabilities are classified as MANUAL_REVIEW_REQUIRED
```

Recommended failure codes:

```text
PR_NOT_ELIGIBLE
PR_CREATION_FAILED
MISSING_REQUIRED_ARTIFACT
GITHUB_AUTH_FAILED
```

---

## 14. Final Phase 3 Decision

Phase 3 is frozen with the deterministic tool API definitions above.

The deterministic tool layer is now:

```text
- modular
- auditable
- testable
- aligned with Phase 1 workflow
- aligned with Phase 2 artifacts
- safe for MVP implementation
```

Next phase:

```text
Phase 4 - AI Agent Prompt and Responsibility Definitions
```
