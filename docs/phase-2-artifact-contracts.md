# Phase 2 Artifact Contracts

This document captures the frozen Phase 2 artifact contracts for the ADK OSS vulnerability remediation workflow.

Phase 2 builds on the Phase 1 architecture and defines the artifacts exchanged between the ADK workflow, AI agents, deterministic tools, remediation workspace, and PR creation tool.

## 1. Contract Design Principles

The contracts are designed for:

- traceability
- auditability
- retry support
- partial remediation support
- manual review support
- validation evidence
- deterministic PR generation

Artifact flow:

```text
Attempt Manifest
  -> Vulnerability Assessment Report
  -> Project Analyzer Report
  -> Exact Remediation Patch Plan
  -> Patch Application Proof
  -> Validation Result
  -> Outcome Analysis Summary
  -> PR Summary
```

Every artifact should include consistent metadata:

```json
{
  "schemaVersion": "1.0",
  "artifactId": "unique-artifact-id",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:00:00Z",
  "createdBy": "ToolOrAgentName",
  "status": "SUCCESS",
  "policy": {},
  "artifactReferences": {},
  "errors": [],
  "warnings": []
}
```

Important principle:

> Every deterministic tool output and every AI agent output must be persisted in the Remediation Workspace and referenced from the Attempt Manifest.

---

## 2. Contract Order

Recommended implementation order:

1. Attempt Manifest
2. Vulnerability Assessment Report
3. Project Analyzer Report
4. Exact Remediation Patch Plan
5. Patch Application Proof
6. Validation Result
7. Outcome Analysis Summary
8. PR Summary

---

## 3. Attempt Manifest Contract

Purpose: index all remediation workspace artifacts and track workflow/attempt status.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "manifest-oss-remediation-20260628-001",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:00:00Z",
  "createdBy": "ADKWorkflowOrchestrator",
  "status": "IN_PROGRESS",
  "policy": {
    "severityScope": ["CRITICAL", "HIGH"],
    "maxAttempts": 3,
    "allowPartialPr": true,
    "allowedFilePatterns": ["**/pom.xml"],
    "blockedChangeTypes": [
      "JAVA_SOURCE_CHANGE",
      "TEST_SOURCE_CHANGE",
      "JDK_VERSION_CHANGE",
      "PLUGIN_BUILD_LOGIC_CHANGE",
      "SUPPRESSION_OR_IGNORE_WORKAROUND",
      "FULL_POM_FORMATTING_REWRITE"
    ]
  },
  "repository": {
    "repositoryUrl": "https://github.com/org/repo",
    "referenceBranch": "main",
    "baselineCommit": "abc123"
  },
  "workspace": {
    "workspaceRoot": "remediation-workspace",
    "baselinePath": "baseline",
    "finalPath": "final"
  },
  "baseline": {
    "repositoryPath": "baseline/repository",
    "baselineBuildResult": "baseline/baseline-build-result.json",
    "vulnerabilityAssessmentReport": "baseline/vulnerability-assessment-report.json",
    "projectAnalyzerReport": "baseline/project-analyzer-report.json"
  },
  "attempts": [
    {
      "attemptNumber": 1,
      "status": "VALIDATION_SUCCEEDED",
      "startedAt": "2026-06-28T12:05:00Z",
      "completedAt": "2026-06-28T12:12:00Z",
      "patchPlan": "attempt-1/remediation-patch-plan.json",
      "patchApplicationProof": "attempt-1/patch-application-proof.json",
      "validationResult": "attempt-1/validation-result.json",
      "outcomeAnalysisSummary": null
    }
  ],
  "acceptedPatchSet": {
    "patchSetId": "accepted-patch-set-1",
    "status": "VALIDATED",
    "sourceAttempts": [1],
    "patchIds": ["patch-1"],
    "vulnerabilityIds": ["GHSA-xxxx-yyyy-zzzz"],
    "appliesOnBaselineCommit": "abc123"
  },
  "final": {
    "remediationSummary": "final/remediation-summary.json",
    "prSummary": "final/pr-summary.json",
    "prDescription": "final/pr-description.md",
    "pullRequestUrl": null
  },
  "artifactReferences": {
    "manifestFile": "manifest.json"
  },
  "errors": [],
  "warnings": []
}
```

Recommended workflow status values:

```text
INITIALIZED
BASELINE_BUILD_FAILED
IN_PROGRESS
VALIDATION_SUCCEEDED
PARTIAL_REMEDIATION_READY_FOR_PR
MANUAL_REVIEW_REQUIRED
PATCH_APPLICATION_FAILED
FAILED_MAX_ATTEMPTS
PR_CREATED
```

---

## 4. Vulnerability Assessment Report Contract

Purpose: normalized Critical/High OSV findings used by the planner.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "vulnerability-assessment-001",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:01:00Z",
  "createdBy": "OSVScannerTool",
  "status": "SUCCESS",
  "policy": {
    "severityScope": ["CRITICAL", "HIGH"]
  },
  "reportType": "VULNERABILITY_ASSESSMENT",
  "scanner": {
    "name": "OSV",
    "command": "osv-scanner scan source -r . --format json",
    "rawReportPath": "baseline/osv-report.json"
  },
  "repository": {
    "repositoryUrl": "https://github.com/org/repo",
    "referenceBranch": "main",
    "baselineCommit": "abc123"
  },
  "baselineBuildStatus": "SUCCESS",
  "vulnerabilities": [
    {
      "vulnerabilityId": "GHSA-xxxx-yyyy-zzzz",
      "aliases": ["CVE-2026-0001"],
      "severity": "HIGH",
      "dependency": {
        "groupId": "org.yaml",
        "artifactId": "snakeyaml",
        "packageName": "org.yaml:snakeyaml",
        "ecosystem": "Maven",
        "currentVersion": "1.33"
      },
      "fixedVersions": ["2.0", "2.2"],
      "scannerEvidence": {
        "rawFindingPath": "baseline/osv-report.json",
        "summary": "OSV reported org.yaml:snakeyaml 1.33 as HIGH."
      },
      "status": "OPEN"
    }
  ],
  "summary": {
    "criticalCount": 0,
    "highCount": 1,
    "totalInScopeCount": 1
  },
  "artifactReferences": {
    "rawOsvReport": "baseline/osv-report.json"
  },
  "errors": [],
  "warnings": []
}
```

Recommended status values:

```text
SUCCESS
FAILED
PARTIAL
```

---

## 5. Project Analyzer Report Contract

Purpose: Maven project facts only. The Project Analyzer Tool must not recommend remediation.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "project-analyzer-001",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:02:00Z",
  "createdBy": "ProjectAnalyzerTool",
  "status": "SUCCESS",
  "policy": {
    "analysisScope": "MAVEN_PROJECT_FACTS_ONLY"
  },
  "reportType": "PROJECT_ANALYZER",
  "projectFacts": {
    "projectType": "MAVEN_SPRING_BOOT",
    "isMultiModule": true,
    "rootPom": "pom.xml",
    "pomFiles": ["pom.xml", "service-a/pom.xml"],
    "modules": [
      {
        "moduleName": "service-a",
        "modulePath": "service-a",
        "pomFile": "service-a/pom.xml"
      }
    ],
    "java": {
      "detectedVersions": ["17"],
      "source": "maven.compiler.release"
    },
    "springBoot": {
      "detected": true,
      "version": "3.2.4",
      "source": "parent"
    },
    "parentHierarchy": [
      {
        "groupId": "org.springframework.boot",
        "artifactId": "spring-boot-starter-parent",
        "version": "3.2.4",
        "declaredIn": "pom.xml"
      }
    ]
  },
  "dependencyResolutionEvidence": [
    {
      "dependency": "org.yaml:snakeyaml",
      "resolvedVersion": "1.33",
      "modulesAffected": ["service-a"],
      "dependencyType": "TRANSITIVE",
      "scope": "compile",
      "dependencyPaths": [
        "service-a -> org.springframework.boot:spring-boot-starter -> org.yaml:snakeyaml:1.33"
      ],
      "evidenceFile": "baseline/dependency-tree-service-a.json"
    }
  ],
  "pomEvidence": [
    {
      "file": "pom.xml",
      "lineStart": 25,
      "lineEnd": 31,
      "snippetType": "POM_SNIPPET",
      "snippet": "<snakeyaml.version>1.33</snakeyaml.version>",
      "occurrenceCount": 1
    }
  ],
  "artifactReferences": {
    "effectivePom": "baseline/effective-pom.xml",
    "dependencyTree": "baseline/dependency-tree.json",
    "pomIndex": "baseline/pom-index.json"
  },
  "limitations": [],
  "errors": [],
  "warnings": []
}
```

Recommended status values:

```text
SUCCESS
PARTIAL
FAILED
```

---

## 6. Exact Remediation Patch Plan Contract

Purpose: planner output. Contains per-vulnerability patch or manual-review decisions.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "remediation-patch-plan-attempt-1",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:05:00Z",
  "createdBy": "RemediationPlanningAgent",
  "status": "MIXED_PATCH_AND_MANUAL_REVIEW",
  "policy": {
    "allowedFilePatterns": ["**/pom.xml"],
    "allowPartialPr": true
  },
  "planId": "plan-attempt-1",
  "attemptNumber": 1,
  "appliesOn": {
    "baselineCommit": "abc123",
    "acceptedPatchSetId": null
  },
  "basedOnArtifacts": {
    "vulnerabilityAssessmentReport": "baseline/vulnerability-assessment-report.json",
    "projectAnalyzerReport": "baseline/project-analyzer-report.json",
    "previousOutcomeAnalysisSummary": null
  },
  "vulnerabilityDecisions": [
    {
      "vulnerabilityId": "GHSA-xxxx-yyyy-zzzz",
      "aliases": ["CVE-2026-0001"],
      "dependency": "org.yaml:snakeyaml",
      "decision": "PATCH",
      "oldVersion": "1.33",
      "newVersion": "2.2",
      "statusReason": "Selected fixed version 2.2 because it is listed by OSV and can be applied through an existing Maven property in pom.xml.",
      "expectedValidation": {
        "resolvedVersionAfterPatch": "2.2",
        "osvShouldNoLongerReport": true,
        "noNewCriticalHigh": true
      },
      "patches": [
        {
          "patchId": "patch-1",
          "file": "pom.xml",
          "oldText": "<snakeyaml.version>1.33</snakeyaml.version>",
          "newText": "<snakeyaml.version>2.2</snakeyaml.version>",
          "expectedOccurrences": 1,
          "changeType": "MAVEN_PROPERTY_VERSION_VALUE"
        }
      ]
    },
    {
      "vulnerabilityId": "GHSA-abcd-efgh-ijkl",
      "aliases": ["CVE-2026-0002"],
      "dependency": "example:library",
      "decision": "MANUAL_REVIEW",
      "oldVersion": "1.0.0",
      "newVersion": null,
      "statusReason": "Only available fix appears to require Java source changes or framework migration, which is outside automation scope.",
      "expectedValidation": null,
      "patches": []
    }
  ],
  "summary": {
    "patchableCount": 1,
    "manualReviewCount": 1,
    "totalDecisionCount": 2
  },
  "artifactReferences": {
    "planFile": "attempt-1/remediation-patch-plan.json"
  },
  "errors": [],
  "warnings": []
}
```

Recommended plan-level status values:

```text
PATCH_AVAILABLE
MANUAL_REVIEW_ONLY
MIXED_PATCH_AND_MANUAL_REVIEW
NO_ACTION_REQUIRED
```

Recommended per-vulnerability decision values:

```text
PATCH
MANUAL_REVIEW
```

Recommended change type values:

```text
DEPENDENCY_VERSION_VALUE
MAVEN_PROPERTY_VERSION_VALUE
DEPENDENCY_MANAGEMENT_VERSION_VALUE
DEPENDENCY_MANAGEMENT_OVERRIDE
PARENT_POM_VERSION_VALUE
```

---

## 7. Patch Application Proof Contract

Purpose: prove exact patch application result.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "patch-application-proof-attempt-1",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:06:00Z",
  "createdBy": "GenericPatchApplyTool",
  "status": "SUCCESS",
  "policy": {
    "allowedFilePatterns": ["**/pom.xml"]
  },
  "attemptNumber": 1,
  "planId": "plan-attempt-1",
  "appliesOn": {
    "baselineCommit": "abc123",
    "acceptedPatchSetId": null
  },
  "patchesRequested": 1,
  "patchesApplied": 1,
  "filesChanged": ["pom.xml"],
  "patchResults": [
    {
      "patchId": "patch-1",
      "file": "pom.xml",
      "status": "APPLIED",
      "expectedOccurrences": 1,
      "actualOccurrences": 1,
      "oldTextMatched": true,
      "diffSummary": [
        "- <snakeyaml.version>1.33</snakeyaml.version>",
        "+ <snakeyaml.version>2.2</snakeyaml.version>"
      ]
    }
  ],
  "artifactReferences": {
    "diffFile": "attempt-1/patch.diff",
    "patchedWorkspace": "attempt-1/patched-workspace"
  },
  "errors": [],
  "warnings": []
}
```

Recommended top-level status values:

```text
SUCCESS
FAILED
PARTIAL
```

Recommended patch result status values:

```text
APPLIED
FAILED
SKIPPED
```

---

## 8. Validation Result Contract

Purpose: deterministic validation after patch application.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "validation-result-attempt-1",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:10:00Z",
  "createdBy": "ValidationTool",
  "status": "SUCCESS",
  "policy": {
    "changeScopeValidationRequired": true,
    "allowedFilePatterns": ["**/pom.xml"],
    "severityScope": ["CRITICAL", "HIGH"]
  },
  "attemptNumber": 1,
  "planId": "plan-attempt-1",
  "patchApplicationProof": "attempt-1/patch-application-proof.json",
  "changeScopeValidation": {
    "status": "SUCCESS",
    "onlyPomFilesChanged": true,
    "noSourceCodeChanges": true,
    "noPomFormattingRewrite": true,
    "onlyIntendedDependencyVersionChanges": true,
    "noSuppressionOrIgnoreAdded": true,
    "noJdkVersionChange": true,
    "noPluginBuildLogicChange": true,
    "changedFiles": ["pom.xml"],
    "diffFile": "attempt-1/patch.diff",
    "failureSummary": null
  },
  "buildValidation": {
    "status": "SUCCESS",
    "command": "mvn clean install",
    "exitCode": 0,
    "durationSeconds": 120,
    "logFile": "attempt-1/build.log",
    "logExcerpt": "BUILD SUCCESS"
  },
  "testValidation": {
    "status": "SUCCESS",
    "command": "mvn test",
    "exitCode": 0,
    "durationSeconds": 45,
    "logFile": "attempt-1/test.log",
    "logExcerpt": "Tests run successfully."
  },
  "osvValidation": {
    "status": "SUCCESS",
    "command": "osv-scanner scan source -r . --format json",
    "exitCode": 0,
    "durationSeconds": 15,
    "scanResultFile": "attempt-1/osv-report.json",
    "remainingCriticalCount": 0,
    "remainingHighCount": 1,
    "newCriticalHighIntroduced": false,
    "remainingVulnerabilities": [
      {
        "vulnerabilityId": "GHSA-abcd-efgh-ijkl",
        "dependency": "example:library",
        "severity": "HIGH",
        "status": "MANUAL_REVIEW_REQUIRED"
      }
    ]
  },
  "summary": {
    "failedStage": null,
    "failureSummary": null
  },
  "artifactReferences": {
    "buildLog": "attempt-1/build.log",
    "testLog": "attempt-1/test.log",
    "osvReport": "attempt-1/osv-report.json",
    "diffFile": "attempt-1/patch.diff"
  },
  "errors": [],
  "warnings": []
}
```

Recommended validation status values:

```text
SUCCESS
FAILED
NOT_RUN
```

### Principal Engineer Clarification: Validation Success with Remaining Findings

Validation `SUCCESS` means the applied patch set is valid:

- change scope passed
- Maven build passed
- Maven tests passed
- OSV scan completed
- no new Critical/High vulnerabilities were introduced

Validation `SUCCESS` does not necessarily mean all original vulnerabilities are fully remediated.

Remaining vulnerabilities may exist when they are clearly classified as `MANUAL_REVIEW_REQUIRED` and partial PR is allowed.

---

## 9. Outcome Analysis Summary Contract

Purpose: concise failed-attempt analysis for replanning.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "outcome-analysis-summary-attempt-1",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:13:00Z",
  "createdBy": "RemediationOutcomeAnalysisAgent",
  "status": "COMPLETED",
  "policy": {
    "dataRegenerationPolicy": "USE_STORED_ARTIFACTS_FIRST"
  },
  "attemptNumber": 1,
  "basedOnArtifacts": {
    "patchPlan": "attempt-1/remediation-patch-plan.json",
    "patchApplicationProof": "attempt-1/patch-application-proof.json",
    "validationResult": "attempt-1/validation-result.json"
  },
  "failureCategory": "OSV_STILL_REPORTS_VULNERABILITY",
  "whatWeTried": "Updated org.yaml:snakeyaml from 1.33 to 2.2 through the snakeyaml.version Maven property.",
  "whatChanged": [
    {
      "file": "pom.xml",
      "summary": "Updated snakeyaml.version from 1.33 to 2.2."
    }
  ],
  "whatHappened": {
    "patchApplication": "SUCCESS",
    "changeScopeValidation": "SUCCESS",
    "buildValidation": "SUCCESS",
    "testValidation": "SUCCESS",
    "osvValidation": "FAILED"
  },
  "newFactsLearned": [
    "OSV still reports org.yaml:snakeyaml 1.33.",
    "The first patch did not affect the resolved vulnerable version."
  ],
  "recommendedFocusForPlanner": [
    "Inspect dependency resolution evidence for modules still resolving org.yaml:snakeyaml 1.33.",
    "Avoid repeating the same patch unless patch application failed."
  ],
  "capabilityGaps": [],
  "artifactReferences": {
    "validationResult": "attempt-1/validation-result.json",
    "patchDiff": "attempt-1/patch.diff",
    "buildLog": "attempt-1/build.log",
    "testLog": "attempt-1/test.log",
    "osvReport": "attempt-1/osv-report.json"
  },
  "errors": [],
  "warnings": []
}
```

Recommended status values:

```text
COMPLETED
INSUFFICIENT_EVIDENCE
FAILED
```

Recommended failure category values:

```text
PATCH_TEXT_INCORRECT
PATCH_TOOL_LIMITATION
CHANGE_SCOPE_VIOLATION
BUILD_FAILED
TEST_FAILED
OSV_STILL_REPORTS_VULNERABILITY
NEW_CRITICAL_HIGH_INTRODUCED
WORKSPACE_INCONSISTENT
UNSUPPORTED_REPOSITORY_STRUCTURE
MAX_ATTEMPTS_REACHED
```

### Principal Engineer Clarification: Outcome Analysis Boundaries

Outcome Analysis should explain and classify what happened. It should not create the next remediation plan.

Acceptable wording:

```text
Inspect dependency resolution evidence for modules still resolving org.yaml:snakeyaml 1.33.
```

Avoid direct remediation instructions:

```text
Update module-b to org.yaml:snakeyaml 2.2.
```

The planner owns remediation decisions.

---

## 10. PR Summary Contract

Purpose: source artifact for PR title/body.

```json
{
  "schemaVersion": "1.0",
  "artifactId": "pr-summary-001",
  "workflowId": "oss-remediation-20260628-001",
  "createdAt": "2026-06-28T12:20:00Z",
  "createdBy": "PRCreationTool",
  "status": "ELIGIBLE",
  "policy": {
    "allowPartialPr": true
  },
  "prTitle": "OSS vulnerability remediation",
  "prType": "PARTIAL_REMEDIATION",
  "pullRequestEligibility": {
    "eligible": true,
    "type": "PARTIAL_REMEDIATION",
    "reason": "1 vulnerability remediated; 1 vulnerability requires manual review."
  },
  "remediationSummary": [
    {
      "vulnerabilityId": "GHSA-xxxx-yyyy-zzzz",
      "aliases": ["CVE-2026-0001"],
      "dependency": "org.yaml:snakeyaml",
      "oldVersion": "1.33",
      "newVersion": "2.2",
      "status": "REMEDIATED",
      "statusReason": "Updated Maven property snakeyaml.version to 2.2 and validation passed."
    },
    {
      "vulnerabilityId": "GHSA-abcd-efgh-ijkl",
      "aliases": ["CVE-2026-0002"],
      "dependency": "example:library",
      "oldVersion": "1.0.0",
      "newVersion": null,
      "status": "MANUAL_REVIEW_REQUIRED",
      "statusReason": "Fix requires Java source changes or framework migration, which is outside automation scope."
    }
  ],
  "validationSummary": {
    "baselineBuild": "SUCCESS",
    "changeScopeValidation": "SUCCESS",
    "buildValidation": "SUCCESS",
    "testValidation": "SUCCESS",
    "osvValidation": "SUCCESS",
    "remainingCriticalCount": 0,
    "remainingHighCount": 1,
    "newCriticalHighIntroduced": 0
  },
  "artifactReferences": {
    "manifest": "manifest.json",
    "patchPlan": "attempt-1/remediation-patch-plan.json",
    "patchApplicationProof": "attempt-1/patch-application-proof.json",
    "validationResult": "attempt-1/validation-result.json",
    "outcomeAnalysisSummary": "attempt-1/outcome-analysis-summary.json",
    "prDescription": "final/pr-description.md"
  },
  "prBodyMarkdown": "## OSS Vulnerability Remediation\n\n| Vulnerability ID | Dependency | Old Version | New Version | Status | Status Reason |\n|---|---|---|---|---|---|\n| GHSA-xxxx-yyyy-zzzz | org.yaml:snakeyaml | 1.33 | 2.2 | REMEDIATED | Updated Maven property snakeyaml.version to 2.2 and validation passed. |\n| GHSA-abcd-efgh-ijkl | example:library | 1.0.0 | N/A | MANUAL_REVIEW_REQUIRED | Fix requires Java source changes or framework migration, which is outside automation scope. |\n\n## Validation Summary\n\n- Baseline Build: SUCCESS\n- Change Scope Validation: SUCCESS\n- Maven Build: SUCCESS\n- Maven Tests: SUCCESS\n- OSV Scan: SUCCESS\n- Remaining Critical/High: 1\n- New Critical/High Introduced: 0\n",
  "errors": [],
  "warnings": []
}
```

Recommended PR summary status values:

```text
ELIGIBLE
NOT_ELIGIBLE
PR_CREATED
```

Recommended PR type values:

```text
FULL_REMEDIATION
PARTIAL_REMEDIATION
NOT_ELIGIBLE
```

---

## 11. Principal Engineer Recommendations

### 11.1 Validation Success Does Not Always Mean Full Remediation

For partial remediation, validation can be `SUCCESS` while some Critical/High vulnerabilities remain.

This is acceptable only when:

- at least one vulnerability was successfully remediated
- final build and tests pass
- change scope validation passes
- OSV scan completed
- no new Critical/High vulnerabilities were introduced
- remaining vulnerabilities are clearly classified as `MANUAL_REVIEW_REQUIRED`

### 11.2 Controlled Direct Patching Boundary

If a patch tool limitation is encountered, controlled direct patching is allowed only when:

- the intended change is exact and POM-only
- the patch is dependency-version related
- no source/build/plugin/JDK changes are introduced
- Change Scope Validation still runs afterward
- the capability gap is recorded

This prevents tool bypass from becoming an unsafe escape hatch.

### 11.3 Outcome Analysis Must Not Become Planning

Outcome Analysis should explain and classify failure. It can provide recommended investigation focus, but it must not produce the next patch plan.

### 11.4 Artifacts Are the Source of Truth

Agents and tools should use persisted workspace artifacts first. Data regeneration should occur only when artifacts are missing, truncated, corrupted, explicitly requested by the planner, or deemed insufficient by outcome analysis.

---

## 12. Final Phase 2 Decision

Phase 2 is frozen with the eight artifact contracts above.

Next phase:

```text
Phase 3 - Deterministic Tool API Definitions
```

Recommended Phase 3 order:

1. Repo Checkout Tool
2. Baseline Build Tool
3. OSV Scanner Tool
4. Project Analyzer Tool
5. Generic Patch Apply Tool
6. Validation Tool
7. PR Creation Tool
