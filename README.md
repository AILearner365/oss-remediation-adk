# OSS Remediation ADK

A Google ADK-based multi-agent workflow for discovering, remediating, validating, and creating pull requests for Critical and High OSS vulnerabilities in Java Spring Boot Maven projects.

Repository: `https://github.com/AILearner365/oss-remediation-adk`

---

## Business Outcome

This project automates the repetitive engineering workflow required to keep Java Spring Boot Maven applications safer from known OSS dependency vulnerabilities.

Expected outcomes:

- Reduce manual triage time for Critical and High dependency vulnerabilities.
- Standardize Maven dependency remediation decisions across teams.
- Prevent unsafe automation by blocking source-code changes, JDK upgrades, and unvalidated fixes.
- Produce clear audit artifacts: Vulnerability Assessment Report, Remediation Report, and PR description.
- Create reviewable pull requests containing only allowed Maven dependency updates.
- Escalate risky or out-of-scope remediations to manual review with documented reasons.

---

## Project Scope

This workflow supports Java Spring Boot applications that use Maven, including:

- Single-module Maven projects
- Multi-module Maven projects
- Parent-child Maven structures
- Projects using `dependencyManagement`
- Projects with direct or transitive Maven dependencies

Security scanning is performed with OSV Scanner.

The agents are designed to behave like senior software engineers with strong knowledge of:

- Java
- Spring Boot
- Maven
- Maven dependency management
- OSS vulnerability analysis
- Secure dependency remediation
- Build and test validation
- GitHub pull request workflows

---

## Out of Scope

The workflow must not perform the following actions:

- Modify Java source code.
- Upgrade the JDK.
- Suppress or ignore vulnerabilities.
- Change build logic unless the change is strictly a Maven dependency version update.
- Remediate Medium, Low, or Informational vulnerabilities unless they are introduced as part of a Critical or High remediation chain.
- Create a PR when build, tests, or remediation validation fails.

---

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

Agent 1 clones the target repository, checks out the reference branch, validates that the project builds, runs OSV Scanner, filters only Critical and High Maven dependency vulnerabilities, and generates the Vulnerability Assessment Report.

If the reference branch does not build, Agent 1 stops immediately and does not scan or create a remediation branch.

### Agent 2: Automated Remediation & Validation

Agent 2 consumes only the Vulnerability Assessment Report from Agent 1. It updates only Maven dependency versions in `pom.xml` files, runs build and tests, reruns OSV Scanner, and generates the Remediation Report.

If remediation requires a JDK upgrade or Java source-code changes, the item is marked `MANUAL_REVIEW`.

### Agent 3: Pull Request Creation

Agent 3 consumes only the Remediation Report from Agent 2. It validates that PR creation is safe, commits allowed `pom.xml` changes, pushes the feature branch, and creates a GitHub pull request.

Manual review does not automatically block PR creation. A PR may be created for `PARTIAL_SUCCESS` when all unresolved Critical or High vulnerabilities are explicitly marked `MANUAL_REVIEW`, build and tests passed, and only `pom.xml` files were modified.

---

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

---

## Local Setup Prerequisites

Install these tools on the machine that will run the ADK workflow:

| Tool | Why it is needed |
|---|---|
| Python 3.10+ | Runs the ADK agent application |
| Git | Clones repositories, creates branches, commits, and pushes |
| JDK | Builds Java Spring Boot Maven projects |
| Maven | Runs `mvn clean install`, `mvn test`, and dependency analysis |
| OSV Scanner | Scans Maven dependencies for OSS vulnerabilities |
| GitHub CLI | Creates pull requests from Agent 3 |

OSV Scanner is not vendored into this repository. It must be installed on the runtime machine and available on `PATH` as `osv-scanner`.

```bash
cd ~/oss-remediation-adk
source .venv/bin/activate
python -m pip install osv-scanner
```

GitHub CLI must be authenticated before Agent 3 can create pull requests:

```bash
gh auth login
gh auth status
```

---

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

GitHub file creation may not preserve executable permissions. Run:

```bash
chmod +x scripts/*.sh
```

### 4. Run local setup

```bash
bash scripts/setup-local.sh
```

This script:

- Creates `.venv`
- Installs `requirements.txt`
- Creates `.env` from `.env.example` if missing
- Runs prerequisite checks

### 5. Configure environment variables

Open `.env` and set your Google API key:

```bash
GOOGLE_API_KEY=replace-with-your-google-api-key
```

Optional values:

```bash
ADK_HOST=127.0.0.1
ADK_PORT=8000
```
or

```bash
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com
```

```bash
create .env file under the oss-remediation-adk if it doesnt not already exists

GOOGLE_GENAI_USE_ENTERPRISE=1
GOOGLE_CLOUD_PROJECT=deutschebank-aipocs
GOOGLE_CLOUD_LOCATION=us-central1
```

### 6. Verify required tools

```bash
bash scripts/check-prereqs.sh
```

The script checks:

- `python3`
- `git`
- `java`
- `mvn`
- `osv-scanner`
- `gh`
- GitHub CLI authentication status

---

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

---

## Start ADK Web UI

```bash
bash scripts/run-adk-web.sh
```

Default URL:

```text
http://127.0.0.1:8000
```

Use the Web UI for local development, prompt testing, and observing agent behavior.

---

## Start ADK API Server

```bash
bash scripts/run-adk-api-server.sh
```

Default API server URL:

```text
http://127.0.0.1:8000
```

Swagger/OpenAPI documentation is typically available at:

```text
http://127.0.0.1:8000/docs
```

Use the API server mode when integrating this workflow with another service or UI.

---

## Required Runtime Tools Are External

This repository does not download or bundle these binaries:

- `git`
- `java`
- `mvn`
- `osv-scanner`
- `gh`

They are treated as deterministic runtime tools and must be installed on the local machine, CI runner, or server/container where the agent runs.

Recommended production runtime image should include:

- Python 3.10+
- Java/JDK
- Maven
- Git
- OSV Scanner
- GitHub CLI

---

## Example Workflow Output Contracts

### Agent 1 Output: Vulnerability Assessment Report

```json
{
  "repositoryUrl": "https://github.com/example/project.git",
  "referenceBranch": "main",
  "latestCommitId": "abc123456789",
  "featureBranch": "oss-remediation-main-abc1-20260623T103000",
  "buildStatus": "SUCCESS",
  "scanTool": "OSV Scanner",
  "projectType": "MAVEN_SPRING_BOOT",
  "isMultiModuleProject": true,
  "criticalCount": 0,
  "highCount": 1,
  "vulnerabilities": [
    {
      "dependencyName": "org.example:example-library",
      "currentVersion": "1.0.0",
      "severity": "HIGH",
      "vulnerabilityIds": ["GHSA-xxxx-yyyy-zzzz"],
      "summary": "Example vulnerability summary",
      "suggestedFixVersions": ["1.0.5", "1.1.0"],
      "affectedPomFile": "pom.xml",
      "dependencyScope": "compile",
      "isDirectDependency": true,
      "manualReviewRequired": false,
      "manualReviewReason": null
    }
  ]
}
```

### Agent 2 Output: Remediation Report

```json
{
  "repositoryUrl": "https://github.com/example/project.git",
  "referenceBranch": "main",
  "featureBranch": "oss-remediation-main-abc1-20260623T103000",
  "remediationStatus": "PARTIAL_SUCCESS",
  "buildStatus": "SUCCESS",
  "testStatus": "SUCCESS",
  "modifiedFiles": ["pom.xml"],
  "remediatedVulnerabilities": [],
  "manualReviewItems": [
    {
      "dependencyName": "org.example:legacy-library",
      "currentVersion": "2.1.0",
      "severity": "HIGH",
      "status": "MANUAL_REVIEW",
      "manualReviewReason": "Fixed version requires JDK 21. JDK upgrades are out of scope."
    }
  ],
  "postRemediationScan": {
    "criticalRemaining": 0,
    "highRemaining": 1,
    "newCriticalOrHighIntroduced": false,
    "remainingCriticalOrHighItems": [
      {
        "dependencyName": "org.example:legacy-library",
        "severity": "HIGH",
        "status": "MANUAL_REVIEW"
      }
    ]
  }
}
```

### Agent 3 Output: PR Result

```json
{
  "pullRequestCreated": true,
  "repositoryUrl": "https://github.com/example/project.git",
  "sourceBranch": "oss-remediation-main-abc1-20260623T103000",
  "targetBranch": "main",
  "pullRequestUrl": "https://github.com/example/project/pull/123",
  "status": "SUCCESS"
}
```

---

## PR Description Content

Agent 3 generates a PR description containing:

- Summary
- Validation table
- Remediation details table
- Modified files
- Notes confirming that no Java source code was changed

The remediation details table includes:

| Dependency Name | Severity | Current Version | Suggested Fix Versions | Fixed Version | Status | Comments |
|---|---|---|---|---|---|---|
| org.example:example-library | HIGH | 1.0.0 | 1.0.5, 1.1.0 | 1.0.5 | FIXED | Selected the lowest fixed version to reduce compatibility risk. |
| org.example:legacy-library | HIGH | 2.1.0 | 3.0.0 | N/A | MANUAL_REVIEW | Fixed version requires JDK upgrade, which is out of scope. |

---

## Troubleshooting

### `osv-scanner` command not found

Install OSV Scanner and ensure the binary is available on `PATH`:

```bash
osv-scanner --version
```

Then rerun:

```bash
bash scripts/check-prereqs.sh
```

### `gh` is not authenticated

Run:

```bash
gh auth login
gh auth status
```

### Maven build fails on the reference branch

Agent 1 terminates early by design. The reference branch must build successfully before scanning or remediation starts.

### PR is blocked

Agent 3 blocks PR creation when:

- Build failed
- Tests failed
- Remediation status is `FAILED`
- A vulnerability has `FAILED` status
- A remaining Critical or High vulnerability is not marked `MANUAL_REVIEW`
- Files other than `pom.xml` were modified

---

## Development Notes

The deterministic tools are intentionally separated from agent reasoning:

- Agent prompts define role, scope, constraints, and handoff contracts.
- Tools execute bounded Git, Maven, OSV Scanner, XML, and GitHub CLI operations.
- Reports are JSON-compatible dictionaries passed between agents.

This keeps the workflow auditable, testable, and safer for security-sensitive automation.
