# OSS Remediation ADK

A Google ADK-based multi-agent workflow for discovering, remediating, validating, and creating pull requests for Critical and High OSS vulnerabilities in Java Spring Boot Maven projects.

Repository: `https://github.com/AILearner365/oss-remediation-adk`

## Business Outcome

This project automates repeatable Maven dependency remediation while keeping security-sensitive changes reviewable and bounded.

Expected outcomes:

- Reduce manual triage time for Critical and High Maven dependency vulnerabilities.
- Standardize safe dependency-version remediation decisions across teams.
- Block unsafe automation such as Java source edits, JDK upgrades, vulnerability suppressions, and unvalidated fixes.
- Produce audit artifacts: Vulnerability Assessment Report, Remediation Report, and PR description.
- Create pull requests only when all Critical and High findings are fully remediated and validation passes.
- Escalate risky or out-of-scope items to manual review without creating a PR.

## Project Scope

The workflow supports Java Spring Boot Maven projects, including:

- Single-module Maven projects
- Multi-module Maven projects
- Parent-child POM structures
- Projects using `dependencyManagement`
- Direct Maven dependencies
- Transitive Maven dependencies when the dependency path can be confirmed deterministically

Security scanning is performed with OSV Scanner.

## Out of Scope

The workflow must not:

- Modify Java source code.
- Upgrade the JDK.
- Suppress or ignore vulnerabilities.
- Change Maven plugin versions or build logic unless explicitly part of a safe dependency-version remediation.
- Remediate Medium, Low, or Informational vulnerabilities unless they are introduced as part of a Critical or High remediation chain.
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

Agent 1 clones the target repository, checks out the reference branch, validates that the project builds, runs OSV Scanner, filters Critical and High Maven vulnerabilities, and generates the Vulnerability Assessment Report.

The scanner tool prefers `./mvnw` when present. Maven goals and arguments can be configured through runtime environment variables so the workflow is not hardcoded to one Maven command for every repository.

### Agent 2: Automated Remediation & Validation

Agent 2 consumes only the Vulnerability Assessment Report from Agent 1. It updates only Maven dependency version information in `pom.xml` files, validates each candidate fixed version with Maven build, Maven tests, and OSV Scanner, and generates the Remediation Report.

Supported automated update targets include:

- Existing literal dependency `<version>` values
- Maven version properties used by dependencies
- Existing `dependencyManagement` versions
- Minimal `dependencyManagement` overrides for confirmed transitive dependencies

If remediation appears to require a JDK upgrade, Java source-code change, external parent change, unsupported build-logic change, or no candidate version passes validation, the item is marked `MANUAL_REVIEW`.

### Agent 3: Pull Request Creation

Agent 3 consumes only the Remediation Report from Agent 2. It validates PR creation safety before committing or pushing.

A PR is created only when all of the following are true:

- `buildStatus == SUCCESS`
- `testStatus == SUCCESS`
- `remediationStatus == SUCCESS`
- `manualReviewItems` is empty
- no vulnerability has `FAILED` status
- `postRemediationScan.criticalRemaining == 0`
- `postRemediationScan.highRemaining == 0`
- `postRemediationScan.newCriticalOrHighIntroduced == false`
- no remaining Critical or High item exists
- at least one `pom.xml` file was modified
- only `pom.xml` files were modified

Manual review now blocks PR creation. `PARTIAL_SUCCESS` is intentionally not eligible for PR creation.

## Runtime Configuration

Required local/runtime tools:

| Tool | Why it is needed |
|---|---|
| Python 3.10+ | Runs the ADK agent application |
| Git | Clones repositories, creates branches, commits, and pushes |
| JDK | Builds Java Spring Boot Maven projects |
| Maven or Maven Wrapper | Runs build, tests, and dependency analysis |
| OSV Scanner | Scans Maven dependencies for OSS vulnerabilities |
| GitHub CLI | Creates pull requests from Agent 3 |

Useful optional environment variables:

```bash
OSS_REMEDIATION_MAVEN_ARGS="-P security -DskipITs"
OSS_REMEDIATION_BUILD_GOALS="clean install"
OSS_REMEDIATION_TEST_GOALS="test"
OSS_REMEDIATION_OSV_COMMAND="osv-scanner scan source -r . --format json"
```

`OSS_REMEDIATION_MAVEN_ARGS` is intended for non-secret flags such as profiles or test selectors. Do not use it for credentials.

## Repository Structure

```text
oss_remediation_agent/
  agent.py                         # ADK SequentialAgent entry point
  prompts.py                       # Agent instructions and contracts
  tools/
    scanner_tools.py               # Agent 1 deterministic tool
    remediation_tools.py           # Agent 2 deterministic tool
    validation_tools.py            # Agent 3 deterministic tool
scripts/
  check-prereqs.sh                 # Validates local system dependencies
  setup-local.sh                   # Creates venv and installs Python requirements
  run-adk-web.sh                   # Starts ADK Web UI
  run-adk-api-server.sh            # Starts ADK API server
  run-adk-cli.sh                   # Starts ADK CLI runner
requirements.txt                   # Python dependencies
.env.example                       # Local environment template
```

## Run Locally

```bash
git clone https://github.com/AILearner365/oss-remediation-adk.git
cd oss-remediation-adk
git checkout <branch-name>
bash scripts/setup-local.sh
bash scripts/run-adk-cli.sh
```

Example prompt:

```text
Run the OSS remediation workflow for repository https://github.com/example/spring-boot-maven-app.git using reference branch main.
```

Expected user input fields:

```json
{
  "repositoryUrl": "https://github.com/example/spring-boot-maven-app.git",
  "referenceBranch": "main"
}
```

## Local Validation

```bash
python -m compileall oss_remediation_agent
```

Agent 2 and Agent 3 intentionally use deterministic tools for repository-changing operations. The LLM agents provide orchestration and reasoning, while Git, Maven, OSV Scanner, and GitHub CLI provide auditable execution.
