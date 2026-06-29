# Test Coverage Guide

This guide explains what the current tests prove and why each test exists. The goal is to make the test suite easy to understand before adding fixture-based integration tests.

## Unit test scope

The current unit tests verify deterministic behavior for contracts, tools, validation, outcome analysis, PR summary generation, and orchestrator routing. These tests use temporary files and mocks where needed. They do not prove the full end-to-end workflow yet.

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

## Fixture projects

The fixture projects are committed Maven inputs for the next integration-test phase.

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

## Current verification status

Current unit tests and fixture sanity checks have passed in Cloud Shell.

Recommended commands:

```bash
python -m compileall -q oss_remediation_agent
python -m unittest discover -s tests -v
find tests/fixtures -name pom.xml
```

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

## Next phase

After this documentation, the next step is Phase A fixture-based integration testing:

1. Project Analyzer on single-module fixture.
2. Project Analyzer on multi-module fixture.
3. Patch Tool against property-managed fixture POM.
4. Validation Tool against fixture-generated artifacts.
5. PR Summary from fixture manifest.
