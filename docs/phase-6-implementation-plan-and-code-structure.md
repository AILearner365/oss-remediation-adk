# Phase 6 Implementation Plan and Code Structure

This document captures the frozen Phase 6 implementation plan and code structure for the ADK OSS vulnerability remediation workflow.

Phase 6 converts the frozen architecture into an implementation-ready project structure.

It is based on:

- Phase 1: Workflow architecture
- Phase 2: Artifact contracts
- Phase 3: Deterministic tool APIs
- Phase 4: AI agent specifications
- Phase 5: ADK workflow orchestration

---

## 1. Implementation Principle

```text
Implement contracts first.
Implement workspace and manifest storage second.
Implement deterministic tools third.
Implement AI agents fourth.
Implement orchestrator last.
```

Reason:

```text
The orchestrator depends on stable artifacts, tool APIs, policy config, prompts, and workspace behavior.
```

---

## 2. Final Recommended Project Structure

```text
oss_remediation_adk/
  agent.py
  cli.py

  workflow/
    orchestrator.py
    workflow_state.py
    attempt_manager.py

  contracts/
    tool_result.py
    manifest.py
    baseline_build_result.py
    vulnerability_assessment.py
    project_analyzer_report.py
    remediation_patch_plan.py
    patch_application_proof.py
    validation_result.py
    outcome_analysis_summary.py
    pr_summary.py

  schemas/
    attempt-manifest.schema.json
    baseline-build-result.schema.json
    vulnerability-assessment.schema.json
    project-analyzer-report.schema.json
    remediation-patch-plan.schema.json
    patch-application-proof.schema.json
    validation-result.schema.json
    outcome-analysis-summary.schema.json
    pr-summary.schema.json

  tools/
    repo_checkout_tool.py
    baseline_build_tool.py
    osv_scanner_tool.py
    project_analyzer_tool.py
    generic_patch_apply_tool.py
    validation_tool.py
    pr_creation_tool.py

  agents/
    remediation_planning_agent.py
    remediation_outcome_analysis_agent.py

  prompts/
    remediation_planning_agent.md
    remediation_outcome_analysis_agent.md

  workspace/
    workspace_manager.py
    artifact_store.py
    manifest_store.py

  policies/
    remediation_policy.py

  config/
    remediation-policy.yaml

  utils/
    command_runner.py
    git_utils.py
    maven_utils.py
    json_utils.py
    diff_utils.py

  examples/
    artifacts/
    sample-workspace/

  tests/
    unit/
    integration/
    fixtures/
      maven-single-module-direct/
      maven-multi-module-property/
      maven-dependency-management/
      maven-transitive-override/
      baseline-build-failure/
```

---

## 3. Contracts Layer

Implement typed models first.

```text
contracts/
  tool_result.py
  manifest.py
  baseline_build_result.py
  vulnerability_assessment.py
  project_analyzer_report.py
  remediation_patch_plan.py
  patch_application_proof.py
  validation_result.py
  outcome_analysis_summary.py
  pr_summary.py
```

Each contract should support:

```text
from_dict
to_dict
validate
read_json
write_json
schema_version
artifact_id
workflow_id
created_at
created_by
status
errors
warnings
artifact_references
```

Important addition:

```text
tool_result.py
```

This is the shared Phase 3 Tool Result Envelope used by every deterministic tool.

---

## 4. JSON Schemas

Add schema files for artifact validation.

```text
schemas/
  attempt-manifest.schema.json
  baseline-build-result.schema.json
  vulnerability-assessment.schema.json
  project-analyzer-report.schema.json
  remediation-patch-plan.schema.json
  patch-application-proof.schema.json
  validation-result.schema.json
  outcome-analysis-summary.schema.json
  pr-summary.schema.json
```

Purpose:

```text
- validate tool outputs
- validate agent outputs
- catch malformed artifacts early
- allow test fixtures to be schema-checked
- support future external integrations
```

---

## 5. Policy Configuration

Do not hardcode workflow policy.

Use:

```text
config/remediation-policy.yaml
```

Recommended fields:

```yaml
severityScope:
  - CRITICAL
  - HIGH

maxAttempts: 3
maxAdditionalInvestigationRequestsPerAttempt: 2
allowPartialPr: true

allowedFilePatterns:
  - "**/pom.xml"

blockedChangeTypes:
  - JAVA_SOURCE_CHANGE
  - TEST_SOURCE_CHANGE
  - JDK_VERSION_CHANGE
  - PLUGIN_BUILD_LOGIC_CHANGE
  - SUPPRESSION_OR_IGNORE_WORKAROUND
  - FULL_POM_FORMATTING_REWRITE

allowedPatchChangeTypes:
  - DEPENDENCY_VERSION_VALUE
  - MAVEN_PROPERTY_VERSION_VALUE
  - DEPENDENCY_MANAGEMENT_VERSION_VALUE
  - DEPENDENCY_MANAGEMENT_OVERRIDE
  - PARENT_POM_VERSION_VALUE
```

Load this using:

```text
policies/remediation_policy.py
```

---

## 6. Prompt Files

Prompts should not be buried directly inside Python code.

Use:

```text
prompts/
  remediation_planning_agent.md
  remediation_outcome_analysis_agent.md
```

Benefits:

```text
- versionable
- reviewable
- easier prompt iteration
- separates prompt engineering from orchestration logic
```

---

## 7. Workspace Layer

Implement:

```text
workspace/
  workspace_manager.py
  artifact_store.py
  manifest_store.py
```

Responsibilities:

```text
WorkspaceManager:
- create workspace
- create baseline folder
- create attempt folders
- create final folder
- restore baseline workspace references

ArtifactStore:
- write JSON artifacts
- read JSON artifacts
- write logs
- write diffs
- resolve artifact paths

ManifestStore:
- load manifest
- save manifest
- update manifest only when called by orchestrator
```

Important rule:

```text
Only the orchestrator updates the manifest.
```

---

## 8. Deterministic Tools

Implement in Phase 3 order:

```text
1. Repo Checkout Tool
2. Baseline Build Tool
3. OSV Scanner Tool
4. Project Analyzer Tool
5. Generic Patch Apply Tool
6. Validation Tool
7. PR Creation Tool
```

Every tool must:

```text
- accept structured input
- perform deterministic work only
- write full artifact to workspace
- return ToolResult envelope
- include toolName, toolVersion, operation, status, failureCode
- include capabilities and limitations
- never update manifest directly
- never call AI agents
```

---

## 9. AI Agents

Implement:

```text
agents/
  remediation_planning_agent.py
  remediation_outcome_analysis_agent.py
```

Agents should:

```text
- read workspace artifacts
- use external prompt files
- output Phase 2 contract artifacts
- validate output against schemas
```

Agents must not:

```text
- edit repository files
- run Maven
- run OSV
- update manifest
- create PR
- bypass validation
```

---

## 10. Orchestrator

Implement Phase 5 lifecycle in:

```text
workflow/orchestrator.py
```

Core methods:

```python
initialize()
run_baseline()
run_assessment()
run_attempt_loop()
handle_planner_result(planning_result)
handle_additional_investigation(request)
run_patch_cycle(plan)
run_validation_cycle()
run_outcome_analysis()
handle_pr_creation()
```

Most important implementation rule:

```text
All planner outputs must route through the same handle_planner_result() method.
```

This includes planner outputs after:

```text
- normal planning
- additional investigation
- investigation-limit constraint
- replanning after failed attempt
```

---

## 11. CLI and ADK Entrypoint

Keep ADK and local testing cleanly separated.

```text
agent.py
```

Should remain the ADK entrypoint.

```text
cli.py
```

Supports local execution and testing.

Example:

```text
python -m oss_remediation_adk.cli run --repo <repo-url> --branch main
```

Do not place orchestration logic directly inside `agent.py`.

---

## 12. Examples and Fixtures

Add sample artifacts:

```text
examples/
  artifacts/
  sample-workspace/
```

Add controlled Maven fixture repositories:

```text
tests/fixtures/
  maven-single-module-direct/
  maven-multi-module-property/
  maven-dependency-management/
  maven-transitive-override/
  baseline-build-failure/
```

These support repeatable integration tests.

---

## 13. Testing Strategy

### Unit Tests

```text
- contract validation
- JSON schema validation
- ToolResult envelope validation
- policy loading
- manifest updates
- workspace path resolution
- patch dry-run
- patch apply
- change scope validation
- PR eligibility logic
- manual review logic
```

### Integration Tests

```text
- single-module direct dependency remediation
- multi-module Maven property remediation
- dependencyManagement remediation
- transitive dependency override
- baseline build failure
- patch dry-run failure
- patch application failure
- validation failure
- partial remediation
- max attempts behavior
- additional investigation limit behavior
```

---

## 14. MVP Implementation Priority

### Critical

```text
- contracts
- JSON schemas
- ToolResult contract
- remediation policy config
- workspace manager
- artifact store
- manifest store
- repo checkout tool
- baseline build tool
- generic patch apply tool
- validation tool
- orchestrator skeleton
```

### High

```text
- OSV scanner normalization
- project analyzer
- planning agent
- outcome analysis agent
- prompt files
- PR summary generation
```

### Medium

```text
- GitHub PR creation
- additional investigation loop
- accepted patch set replay
- manual review report
- CLI runner
- examples and fixtures
```

### Low

```text
- advanced Maven edge cases
- remote parent analysis
- BOM intelligence
- multi-scanner support
- Gradle support
```

---

## 15. Phase 6 Freeze Decision

Phase 6 is frozen with these refinements:

```text
- JSON schemas
- shared ToolResult contract
- external policy config
- prompt files
- sample artifacts
- Maven fixture repositories
- CLI and local runner
```

Next phase:

```text
Phase 7 - MVP Implementation Tasks and Milestones
```
