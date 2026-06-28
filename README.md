# OSS Remediation ADK

A Google ADK-based multi-agent workflow for discovering, remediating, validating, and creating pull requests for Critical and High OSS vulnerabilities in Java Maven projects.

Repository: `https://github.com/AILearner365/oss-remediation-adk`

## Business Outcome

This project automates repeatable Maven dependency remediation while keeping security-sensitive changes reviewable, explainable, and bounded.

Expected outcomes:

- Reduce manual triage time for Critical and High Maven dependency vulnerabilities.
- Standardize safe dependency-version remediation decisions across teams.
- Block unsafe automation such as Java source edits, JDK upgrades, vulnerability suppressions, and unvalidated fixes.
- Produce audit artifacts: Vulnerability Assessment Report, Remediation Report, deterministic policy decision, and PR description.
- Create pull requests only when all configured severity-scope findings are fully remediated and validation passes.
- Escalate risky or out-of-scope items to manual review without creating a PR.

## Project Scope

The current workflow supports Java Maven projects, including:

- Single-module Maven projects
- Multi-module Maven projects
- Parent-child POM structures
- Projects using `dependencyManagement`
- Direct Maven dependencies
- Transitive Maven dependencies when the dependency path can be confirmed deterministically

OSV Scanner is the default scanner adapter for this implementation. Severity scope, Maven commands, transitive override behavior, and PR gating are controlled by runtime policy.

## Out of Scope

The workflow must not:

- Modify Java source code.
- Upgrade the JDK.
- Suppress or ignore vulnerabilities.
- Change Maven plugin versions or build logic unless explicitly part of a safe dependency-version remediation.
- Remediate severities outside the configured policy unless they are introduced as part of a configured remediation chain.
- Create a PR when build, tests, scan validation, or remediation evidence fails.
- Create a PR when any item requires manual review.

## Multi-Agent Workflow

```text
User Input
   |
   v
Agent 1: Discovery & Assessment
   |
   | Outputs Vulnerability Assessment Report
   v
Agent 2: Automated Remediation & Validation
   |
   | Outputs Remediation Report
   v
Agent 3: Pull Request Creation
   |
   v
Pull Request URL or Blocked PR Result
```

### Agent 1: Discovery & Assessment

Agent 1 clones the target repository, checks out the reference branch, validates that the project builds, extracts Maven project metadata, runs OSV Scanner, filters policy-selected Maven vulnerabilities, and generates the Vulnerability Assessment Report.

The scanner tool prefers `./mvnw` when present. Maven goals, Maven arguments, scanner command, and severity scope are configurable through runtime policy so the workflow is not hardcoded to one Maven command or one severity threshold for every repository.

### Agent 2: Automated Remediation & Validation

Agent 2 consumes only the Vulnerability Assessment Report from Agent 1. It updates only Maven dependency version information in `pom.xml` files, validates each candidate fixed version with Maven build, Maven tests, and scanner validation, and generates the Remediation Report.

Supported automated update targets include:

- Existing literal dependency `<version>` values
- Maven version properties used by dependencies
- Existing `dependencyManagement` versions
- Minimal `dependencyManagement` overrides for confirmed transitive dependencies

If remediation appears to require a JDK upgrade, Java source-code change, external parent change, unsupported build-logic change, imported BOM upgrade, or no candidate version passes validation, the item is marked `MANUAL_REVIEW`.

### Agent 3: Pull Request Creation

Agent 3 consumes only the Remediation Report from Agent 2. It validates report schema and PR creation policy before committing or pushing.

A PR is created only when all default gates are true:

- `buildStatus == SUCCESS`
- `testStatus == SUCCESS`
- `remediationStatus == SUCCESS`
- `manualReviewItems` is empty
- no vulnerability has `FAILED` status
- `postRemediationScan.criticalRemaining == 0`
- `postRemediationScan.highRemaining == 0`
- `postRemediationScan.newCriticalOrHighIntroduced == false`
- no remaining configured severity-scope item exists
- at least one allowed `pom.xml` file was modified
- only configured allowlisted files were modified

Manual review blocks PR creation. `PARTIAL_SUCCESS` is intentionally not eligible for PR creation by default policy.

## Architectural Hardening

This branch adds an explicit deterministic core around the existing three-agent ADK workflow:

```text
ADK agents
  -> deterministic tool contracts
  -> schema validation
  -> runtime policy
  -> Maven project metadata and POM patch helpers
  -> candidate validation
  -> PR policy decision
```

Key modules:

| Module | Purpose |
|---|---|
| `oss_remediation_agent/policy.py` | Central runtime policy for severities, Maven goals, PR gates, allowed files, transitive override behavior, and PR template configuration |
| `oss_remediation_agent/schemas.py` | Explicit report constructors, validation helpers, statuses, and stable vulnerability keys |
| `oss_remediation_agent/tools/maven_tools.py` | Maven project metadata extraction, POM target discovery, minimal POM patch helpers, snapshots, and rollback support |
| `oss_remediation_agent/tools/scanner_tools.py` | Agent 1 discovery, policy-aware Maven build and scanner execution, vulnerability normalization |
| `oss_remediation_agent/tools/remediation_tools.py` | Agent 2 remediation orchestration split into planning, candidate application, validation, transitive evidence, and reporting |
| `oss_remediation_agent/tools/validation_tools.py` | Agent 3 deterministic PR policy evaluation and PR body generation |

The implementation still performs minimal text edits to preserve POM formatting. Maven model analysis is improved through project metadata extraction and isolated target discovery helpers, but full effective-POM back-mapping remains a future production-hardening item.

## Runtime Configuration

Required local/runtime tools:

| Tool | Why it is needed |
|---|---|
| Python 3.10+ | Runs the ADK agent application |
| Git | Clones repositories, creates branches, commits, and pushes |
| JDK | Builds Java Maven projects |
| Maven or Maven Wrapper | Runs build, tests, and dependency analysis |
| OSV Scanner | Default scanner implementation |
| GitHub CLI | Creates pull requests from Agent 3 |

Useful optional environment variables:

```bash
OSS_REMEDIATION_SEVERITIES="CRITICAL,HIGH"
OSS_REMEDIATION_MAVEN_ARGS="-P security -DskipITs"
OSS_REMEDIATION_BUILD_GOALS="clean install"
OSS_REMEDIATION_TEST_GOALS="test"
OSS_REMEDIATION_OSV_COMMAND="osv-scanner scan source -r . --format json"
OSS_REMEDIATION_ALLOWED_FILE_NAMES="pom.xml"
OSS_REMEDIATION_PR_ALLOWED_STATUSES="SUCCESS"
OSS_REMEDIATION_ALLOW_DEPENDENCY_MANAGEMENT_OVERRIDES="true"
OSS_REMEDIATION_REQUIRE_TRANSITIVE_EVIDENCE="true"
OSS_REMEDIATION_BLOCK_JAVA_OR_JDK_UPGRADE="true"
OSS_REMEDIATION_PR_TITLE="OSS vulnerability remediation"
OSS_REMEDIATION_PR_TEMPLATE=".github/oss-remediation-pr-template.md"
```

`OSS_REMEDIATION_MAVEN_ARGS` is intended for non-secret flags such as profiles or test selectors. Do not use it for credentials.

## Repository Structure

```text
oss_remediation_agent/
  agent.py                         # ADK SequentialAgent entry point
  prompts.py                       # Agent instructions and contracts
  policy.py                        # Runtime policy and guardrails
  schemas.py                       # Report schemas and validation helpers
  tools/
    maven_tools.py                 # Deterministic Maven metadata and POM patch helpers
    scanner_tools.py               # Agent 1 deterministic tool
    remediation_tools.py           # Agent 2 deterministic tool
    validation_tools.py            # Agent 3 deterministic tool
scripts/
  check-prereqs.sh                 # Validates local system dependencies
  setup-local.sh                   # Creates venv and installs Python requirements
  run-adk-web.sh                   # Starts ADK Web UI
  run-adk-api-server.sh            # Starts ADK API server
  run-adk-cli.sh                   # Starts ADK CLI runner
tests/
  test_policy_and_validation.py    # Unit tests for policy, schemas, and PR gates
requirements.txt                   # Python dependencies
.env.example                       # Local environment template
```

## Local Setup Instructions

### 1. Clone this repository

```bash
git clone https://github.com/AILearner365/oss-remediation-adk.git
cd oss-remediation-adk
```

### 2. Checkout the workflow branch

```bash
git checkout <branch-name>
```

### 3. Make scripts executable

```bash
chmod +x scripts/*.sh
```

### 4. Run local setup

```bash
bash scripts/setup-local.sh
```

### 5. Configure environment variables

Open `.env` and set your Google API key:

```bash
GOOGLE_API_KEY=replace-with-your-google-api-key
```

Optional ADK values:

```bash
ADK_HOST=127.0.0.1
ADK_PORT=8000
```

For Vertex AI usage, configure Google Cloud authentication and set:

```bash
GOOGLE_GENAI_USE_ENTERPRISE=1
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

### 6. Verify required tools

```bash
bash scripts/check-prereqs.sh
```

## Run Locally with ADK CLI

```bash
bash scripts/run-adk-cli.sh
```

Example prompt:

```text
Run the OSS remediation workflow for repository https://github.com/example/spring-boot-maven-app.git using reference branch main.
```

The expected user input fields are:

```json
{
  "repositoryUrl": "https://github.com/example/spring-boot-maven-app.git",
  "referenceBranch": "main"
}
```

## Local Validation

```bash
python -m compileall oss_remediation_agent
PYTHONPATH=. python -m unittest discover -s tests -v
```
