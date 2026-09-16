# Test Coverage Guide

This guide explains what the current tests prove and why each test exists. It also documents the canonical commands for running the suite consistently in local development, Cloud Shell, and future CI.

## Test layout

```text
tests/
  __init__.py
  unit/
    __init__.py
    test_*.py
  integration/
    __init__.py
    test_*.py
  e2e/
    __init__.py
    test_*.py
  fixtures/
    */pom.xml
```

The `__init__.py` files make test discovery more predictable across Python versions and environments.

## Canonical commands

Run the full verification suite:

```bash
python run_tests.py
```

Or use Make:

```bash
make test
```

Run checks individually:

```bash
python -m compileall -q oss_remediation_agent autonomous_oss_remediation_agent
python -m unittest discover -s tests/unit -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python -m unittest discover -s tests/e2e -p "test_*.py" -v
```

Run the independent autonomous POC coverage without the legacy workflow suites:

```bash
python -m unittest tests.unit.test_autonomous_capabilities tests.unit.test_autonomous_scanner_constraints tests.unit.test_autonomous_validation_delivery -v
python -m unittest tests.integration.test_autonomous_orchestrator -v
```

The real Maven/OSV autonomous smoke profile is opt-in through `RUN_AUTONOMOUS_REAL_E2E=1` and `AUTONOMOUS_OSV_SCANNER=<absolute executable path>`.

Make targets:

```bash
make compile
make unit
make integration
make e2e
make test
make clean
```

If `python -m unittest discover -s tests -v` reports `Ran 0 tests`, use the explicit unit/integration/e2e commands above or run `python run_tests.py`.

## Current testing pyramid

```text
                   Real Repository Validation
                              ^
                              |
                  End-to-End Workflow Tests
                              ^
                              |
             Phase B Workflow Integration Tests
                              ^
                              |
        Phase A Fixture-based Integration Tests
                              ^
                              |
                    Deterministic Unit Tests
```

## Unit test scope

The current unit tests verify deterministic behavior for contracts, tools, validation, outcome analysis, PR summary generation, and orchestrator routing. These tests use temporary files and mocks where needed. They do not prove the full end-to-end workflow yet.

## Integration and E2E scope

The current non-unit tests have three layers:

1. **Phase A - Fixture-based Integration Tests**: validate deterministic tools using committed Maven fixture projects.
2. **Phase B - Workflow Integration Tests**: validate orchestrator lifecycle, manifest ownership, retry behavior, stop conditions, outcome summary generation, and final PR summary generation.
3. **Phase C - End-to-End Workflow Tests**: validate the complete MVP workflow path from checkout/baseline through assessment, project analysis, planner routing, remediation attempts, validation, outcome analysis, accepted patch set generation, and PR summary generation.

External command execution and AI planner behavior are mocked where needed so the tests remain stable across developer machines and CI.

## Unit test files

### `tests/unit/test_contracts.py`

Purpose:

- Verify Phase 2 artifact field naming.
- Verify Phase 3 `ToolResult` envelope field naming.

Important assertions:

- Artifacts contain `schemaVersion`, `artifactId`, `workflowId`, and `createdBy`.
- Artifacts do not expose internal snake_case names such as `schema_version`.
- Tool results contain `toolName`, `toolVersion`, `artifactPath`, and `failureCode`.
- Tool results do not expose internal snake_case names such as `tool_name`.

Why it matters:

- Agents, tools, and orchestrator components exchange JSON artifacts. Stable field names prevent contract drift.

### `tests/unit/test_policy_and_patch_tool.py`

Purpose:

- Verify deterministic exact-text patching behavior.
- Verify patch safety constraints.

Important assertions:

- Default remediation policy allows only safe Maven remediation scope.
- Patch dry-run succeeds when `oldText` exists with the expected occurrence count.
- Patch apply updates `pom.xml` as expected.
- Patch apply is atomic: if one patch fails, no prior patch mutation remains.
- Non-`pom.xml` files are rejected.
- `expectedOccurrences > 1` replaces all expected occurrences.

Why it matters:

- The patch tool is one of the highest-risk deterministic components. It must not silently modify source code or leave the workspace partially patched.

### `tests/unit/test_osv_scanner_tool.py`

Purpose:

- Verify OSV JSON normalization for Maven vulnerabilities.

Important assertions:

- Maven `HIGH` vulnerability findings are included.
- Dependency coordinates are normalized, for example `org.yaml:snakeyaml`.
- Fixed versions are extracted.

Why it matters:

- The workflow depends on normalized vulnerability assessment artifacts, not raw scanner output.

### `tests/unit/test_project_analyzer_tool.py`

Purpose:

- Verify Maven project analysis behavior.

Important assertions:

- Spring Boot parent detection works.
- `dependencyManagement` detection works.
- Dependency tree output is parsed into `dependencyResolutionEvidence`.
- When Maven evidence commands are unavailable or fail, the analyzer returns `PARTIAL` with warnings instead of misleading `SUCCESS`.

Why it matters:

- The planner needs project facts and dependency evidence, but the analyzer must not make remediation decisions.

### `tests/unit/test_validation_tool.py`

Purpose:

- Verify deterministic validation failure handling.

Important assertions:

- Non-POM changes fail change-scope validation.
- Maven build failure returns `BUILD_FAILURE`.
- Maven test failure returns `TEST_FAILURE`.
- OSV scanner failure returns `OSV_VALIDATION_FAILURE`.
- Newly introduced Critical/High vulnerabilities fail validation.

Why it matters:

- The remediation workflow must prove that a patch is safe before it can proceed to PR summary generation.

### `tests/unit/test_outcome_summary.py`

Purpose:

- Verify failure classification after a remediation attempt.

Important assertions:

- Patch occurrence mismatch maps to `PATCH_OCCURRENCE_MISMATCH`.
- Change-scope failure maps to `CHANGE_SCOPE_FAILURE`.
- Build failure maps to `BUILD_FAILURE`.
- Test failure maps to `TEST_FAILURE`.
- OSV validation failure maps to `OSV_VALIDATION_FAILURE`.
- Unknown patch engine issue maps to `PATCH_TOOL_LIMITATION`.

Why it matters:

- Outcome Analysis gives the planner useful context for the next attempt without overloading the planner with raw logs.

### `tests/unit/test_pr_creation_tool.py`

Purpose:

- Verify deterministic PR summary generation.

Important assertions:

- PR summary uses accepted patch metadata.
- Dependency, old version, and new version appear in the JSON summary.
- Markdown contains the dependency name.
- Markdown does not fall back to `UNKNOWN` when metadata is available.

Why it matters:

- Reviewers need a clear remediation table showing what changed and why.

### `tests/unit/test_orchestrator.py`

Purpose:

- Verify workflow routing and state handling.

Important assertions:

- Additional investigation limit is enforced per attempt.
- A new attempt gets its own investigation counter.
- `MANUAL_REVIEW` planner result generates final summary artifacts.
- `PATCH_PLAN` planner result routes to patch validation attempt.
- Accepted patch set preserves dependency, old version, and new version metadata.

Why it matters:

- The orchestrator owns workflow state and manifest updates. Tools and agents must not update the manifest directly.

## Phase A - Fixture-based Integration Tests

### Purpose

Phase A verifies the deterministic tool layer against committed Maven fixture projects.

These tests use real fixture files, generated artifacts, and tool contracts. External command execution is mocked where needed so the tests remain stable across developer machines and CI.

### `tests/integration/test_phase_a_fixture_integration.py`

Important assertions:

- Single-module fixture analysis detects Maven project facts and dependency evidence.
- Multi-module fixture analysis detects modules, Spring Boot parent, and dependency management.
- Property-managed fixture patching updates the Maven property safely.
- Validation succeeds when change scope, build, tests, and post-remediation OSV validation all pass.
- PR Summary renders accepted patch metadata from fixture manifest data.

Why it matters:

- These tests bridge the gap between isolated unit tests and workflow-level orchestrator tests.

## Phase B - Workflow Integration Tests

### Purpose

Phase B verifies the workflow orchestration layer rather than individual deterministic tools.

Unlike Phase A, which validates deterministic tools using committed Maven fixtures, Phase B validates the orchestrator's execution lifecycle, workflow state management, retry behavior, stop conditions, manifest ownership, outcome summary generation, accepted patch set generation, and final PR summary generation.

The AI planner remains mocked because these tests verify workflow orchestration rather than AI reasoning.

### `tests/integration/test_phase_b_workflow_integration.py`

Purpose:

- Validate the orchestrator's execution lifecycle using mocked planner/tool responses where appropriate while exercising real workflow state management.

Phase B scenarios:

1. Successful remediation workflow.
2. Baseline build failure stops before remediation attempts.
3. Validation failure generates Outcome Analysis and stops after max attempts.
4. Manual review generates a `NOT_ELIGIBLE` PR summary.
5. Retry succeeds on a second attempt after first validation failure.

Why it matters:

- Validates retry lifecycle, attempt isolation, stop conditions, and manifest state transitions.

## Phase C - End-to-End Workflow Tests

### Purpose

Phase C validates complete MVP workflow paths. These tests start at checkout/baseline, continue through assessment and project analysis, then exercise planner routing, remediation attempts, validation, outcome analysis, accepted patch set creation, and PR summary generation.

### `tests/e2e/test_phase_c_end_to_end_workflow.py`

Phase C scenarios:

1. Successful remediation generates an eligible PR summary.
2. Baseline build failure stops before assessment and remediation attempts.
3. Manual review produces a `NOT_ELIGIBLE` PR summary.
4. Retry succeeds on the second attempt and records attempt 2 as the accepted patch source.
5. Max attempts reached terminates without an accepted patch set.
6. Unsafe change scope is rejected and classified as `CHANGE_SCOPE_FAILURE`.
7. New Critical/High vulnerability introduced is rejected and classified as `OSV_VALIDATION_FAILURE`.

Important assertions:

- Manifest state transitions are written by the orchestrator.
- Attempt records are created, updated, and isolated correctly.
- Failed attempts create Outcome Analysis artifacts.
- Accepted Patch Set is only created after successful validation.
- Final PR Summary is eligible only for validated remediation.
- Manual review and failed workflows do not create an accepted patch set.

Why it matters:

- These tests provide MVP-level end-to-end confidence before moving to CI and real repository validation.

## Design observation captured from Phase C

### `handle_planner_result(PATCH_PLAN)` versus `run_attempt_loop(...)`

During Phase C review, we observed a design inconsistency in the successful remediation path:

- `run_attempt_loop(...)` sets the manifest status to `VALIDATION_SUCCEEDED` and generates the final PR summary after a successful validation.
- `handle_planner_result({"decisionType": "PATCH_PLAN"})` routes directly to `run_patch_validation_attempt(...)`. After a successful validation, it updates the attempt and accepted patch set, but it does not set the top-level manifest status to `VALIDATION_SUCCEEDED` and does not automatically generate the final PR summary.

This means a direct single-plan planner route can leave the top-level manifest status at the previous lifecycle state, such as `PROJECT_ANALYSIS_COMPLETE`, even though the attempt succeeded.

### Why this design adjustment is needed

The orchestrator should provide one consistent post-validation lifecycle regardless of how a patch plan is supplied. Otherwise, callers need to know whether they invoked the attempt through `run_attempt_loop(...)` or directly through `handle_planner_result(...)`, which creates inconsistent workflow behavior.

Recommended design adjustment:

- Prefer routing planner `PATCH_PLAN` decisions through the same bounded attempt lifecycle used by `run_attempt_loop(...)`; or
- Add a shared post-validation finalization method that both `handle_planner_result(PATCH_PLAN)` and `run_attempt_loop(...)` call.

Expected finalization behavior after successful validation:

1. Set top-level manifest status to `VALIDATION_SUCCEEDED`.
2. Preserve the accepted patch set.
3. Generate final PR summary artifacts.
4. Save final manifest state once.

This should be implemented as a follow-up design/implementation refinement rather than hidden inside the tests.

## Minor follow-up improvements

These are not blockers for the current passing suite, but should be addressed before production readiness:

1. Add contract/schema validation assertions for generated artifacts.
2. Refactor the orchestrator so successful `handle_planner_result(PATCH_PLAN)` and `run_attempt_loop(...)` share the same finalization path.
3. Consider changing the successful Phase C test to use `run_attempt_loop(...)` unless testing direct planner routing is intentional.
4. Add one less-mocked E2E profile that runs real Maven on fixture repositories.
5. Add GitHub Actions CI to run `python run_tests.py` on every push and pull request.
6. Add real Maven repository validation after CI is stable.

## Fixture projects

The fixture projects are committed Maven inputs for integration testing.

### `tests/fixtures/maven-single-module-direct`

Purpose:

- Represents a single-module Maven project with a direct dependency version in the dependency block.

Useful for testing:

- Direct dependency detection.
- Exact version patching inside a dependency declaration.

### `tests/fixtures/maven-property-managed-version`

Purpose:

- Represents a Maven project where the dependency version is controlled by a property.

Useful for testing:

- Maven property extraction.
- Property-based remediation plans.
- Exact patching of a Maven property value.

### `tests/fixtures/maven-dependency-management`

Purpose:

- Represents a project where the dependency version is managed in `dependencyManagement` and the dependency declaration omits the version.

Useful for testing:

- `dependencyManagement` detection.
- Managed-version remediation.

### `tests/fixtures/maven-multi-module`

Purpose:

- Represents a multi-module Maven project with a Spring Boot parent, Java version, two modules, and dependency management in the root POM.

Useful for testing:

- Multi-module POM discovery.
- Module detection.
- Spring Boot parent detection.
- Dependency management inherited by modules.

### `tests/fixtures/baseline-build-failure`

Purpose:

- Represents a fixture that intentionally fails baseline validation.

Implementation detail:

- Uses Maven Enforcer to require Java 99 or newer.

Useful for testing:

- Baseline build gate failure.
- Workflow halt behavior before remediation starts.

## Fixture sanity checks

Recommended fixture checks:

```bash
cd tests/fixtures/maven-single-module-direct && mvn validate
cd ../maven-property-managed-version && mvn validate
cd ../maven-dependency-management && mvn validate
cd ../maven-multi-module && mvn validate
cd ../baseline-build-failure && mvn validate
```

Expected behavior:

- The first four fixture projects should build successfully.
- `baseline-build-failure` should fail intentionally through Maven Enforcer.

## Current verification status

```text
Python compilation                  PASS
Unit tests                          PASS
Fixture sanity verification          PASS
Phase A fixture integration tests    PASS
Phase B workflow integration tests   PASS
Phase C end-to-end workflow tests    PASS
```

## Future CI

A future GitHub Actions workflow should run:

```bash
python run_tests.py
```

on every push and pull request.

## Next phase

The next major milestone is to implement the documented orchestrator finalization design adjustment, then add GitHub Actions CI and real repository validation.
