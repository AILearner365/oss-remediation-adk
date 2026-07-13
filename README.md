# OSS Remediation ADK

This repository contains a Google ADK-based, multi-agent OSS vulnerability remediation workflow for Java Spring Boot Maven applications.

The workflow scans OSS vulnerabilities, analyzes Maven project structure, creates dependency-only remediation plans, validates the resulting changes, and creates a GitHub Draft Pull Request when the remediation is safe and validated.

## Current Architecture Principle

```text
AI Agents      = reasoning and engineering decisions
Tools          = deterministic facts and execution
Workspace      = persisted artifacts
Manifest       = artifact index and attempt status
ADK Workflow   = execution order and lifecycle control
```

## Local Setup Overview

A local environment needs the following components:

| Requirement | Purpose |
|---|---|
| Python 3.11 or 3.12 | Runs the Google ADK application |
| Git | Clones target repositories and creates remediation branches |
| JDK required by the target Maven project | Compiles and tests the Java application |
| Maven or Maven Wrapper | Builds the project and resolves dependency information |
| OSV Scanner | Detects OSS vulnerabilities |
| GitHub CLI | Pushes branches and creates Draft Pull Requests |
| Google Cloud CLI or Google API key | Authenticates the ADK model runtime |

The target Maven repository may require a specific JDK version, Maven profile, settings file, or private artifact-repository credentials. Configure those requirements before running the remediation workflow.

---

# Detailed Local Setup

## 1. Clone the repository

```bash
git clone https://github.com/AILearner365/oss-remediation-adk.git
cd oss-remediation-adk
git checkout oss-remediation-adk-customer-demo
```

Confirm the active branch:

```bash
git branch --show-current
```

Expected result:

```text
oss-remediation-adk-customer-demo
```

---

## 2. Install Python

Use Python 3.11 or Python 3.12.

Verify the installation:

```bash
python --version
```

On systems where Python is exposed as `python3`:

```bash
python3 --version
```

### Windows note

During Python installation, select:

```text
Add python.exe to PATH
```

You can also verify the Python launcher with:

```powershell
py --version
```

---

## 3. Create a virtual environment

### macOS, Linux, or Google Cloud Shell

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run the following once in the same terminal and retry activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Windows Command Prompt

```cmd
py -m venv .venv
.venv\Scripts\activate.bat
```

After activation, the terminal prompt should normally show:

```text
(.venv)
```

Upgrade Python packaging tools:

```bash
python -m pip install --upgrade pip setuptools wheel
```

---

## 4. Install Python dependencies

Install the Google ADK runtime and the supporting packages used by the workflow:

```bash
python -m pip install \
  google-adk \
  google-cloud-aiplatform \
  google-genai \
  python-dotenv \
  PyYAML \
  requests
```

On Windows PowerShell, use one line:

```powershell
python -m pip install google-adk google-cloud-aiplatform google-genai python-dotenv PyYAML requests
```

Verify ADK installation:

```bash
adk --help
```

If the `adk` command is not found, verify that the virtual environment is active and run:

```bash
python -m pip show google-adk
```

---

## 5. Install Git and authenticate to GitHub

Verify Git:

```bash
git --version
```

Install GitHub CLI and verify it:

```bash
gh --version
```

Authenticate:

```bash
gh auth login
gh auth status
```

The authenticated GitHub identity must have permission to:

- clone the target repository,
- create and push a remediation branch,
- create a Draft Pull Request.

For private repositories, make sure both `git clone` and `gh repo view` work before starting the workflow.

---

## 6. Install Java and Maven

Install the JDK version required by the target Maven project. Java 17 and Java 21 are common for modern Spring Boot applications.

Verify Java:

```bash
java -version
javac -version
```

Verify Maven:

```bash
mvn -version
```

If the target repository contains a Maven Wrapper, the workflow may use:

```bash
./mvnw --version
```

On Windows:

```powershell
.\mvnw.cmd --version
```

Make sure `JAVA_HOME` points to the intended JDK.

### macOS or Linux

```bash
echo $JAVA_HOME
```

### Windows PowerShell

```powershell
$env:JAVA_HOME
```

Before running the agent, manually confirm that the target repository can execute its expected Maven build command.

Example:

```bash
mvn clean install
```

---

## 7. Install OSV Scanner

Install OSV Scanner using the installation method appropriate for your operating system, then verify that it is available on `PATH`:

```bash
osv-scanner --version
```

A typical repository scan command is:

```bash
osv-scanner scan source -r . --format json
```

The remediation workflow expects the OSV Scanner executable to be available from the same terminal used to start ADK.

---

## 8. Configure model authentication

Create a `.env` file in the repository root:

```text
oss-remediation-adk/
  .env
  Makefile
  README.md
  oss_remediation_agent/
```

Do not commit `.env` or credentials to Git.

### Option A: Vertex AI authentication

Authenticate with Google Cloud:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com
```

Add the following to `.env`:

```dotenv
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
```

Some enterprise environments use an additional organization-specific setting such as:

```dotenv
GOOGLE_GENAI_USE_ENTERPRISE=1
```

Only add that variable when it is required by your configured environment.

Verify Application Default Credentials:

```bash
gcloud auth application-default print-access-token
```

### Option B: Google API key

If the environment is configured for direct Google AI API access, add:

```dotenv
GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY
```

Use only one authentication approach that matches the runtime configuration for your environment.

---

## 9. Optional Maven runtime configuration

The workflow can be run against Maven projects that require profiles or non-secret Maven arguments.

Example `.env` values:

```dotenv
OSS_REMEDIATION_MAVEN_ARGS=-P security -DskipITs
OSS_REMEDIATION_BUILD_GOALS=clean install
OSS_REMEDIATION_TEST_GOALS=test
OSS_REMEDIATION_OSV_COMMAND=osv-scanner scan source -r . --format json
```

Do not place repository passwords, GitHub tokens, artifact-repository credentials, or other secrets directly in Maven arguments committed to the repository.

For private Maven repositories, use the normal Maven credentials mechanism, such as the local `~/.m2/settings.xml` file.

---

## 10. Verify the local environment

Run all of the following from the activated virtual environment:

```bash
python --version
git --version
java -version
mvn -version
osv-scanner --version
gh --version
gh auth status
adk --help
```

Compile the Python package:

```bash
make compile
```

Equivalent command without Make:

```bash
python -m compileall -q oss_remediation_agent
```

Run the complete test suite:

```bash
make test
```

Available Make targets:

```bash
make compile
make unit
make integration
make e2e
make test
make clean
```

---

# Running the Application Locally

## Run with ADK Web

From the repository root, with `.venv` activated:

```bash
adk web . \
  --host 127.0.0.1 \
  --port 8000 \
  --no-reload
```

Open:

```text
http://127.0.0.1:8000
```

Select the `oss_remediation_agent` application in ADK Web.

Example request:

```text
Run the OSS remediation workflow for repository https://github.com/example/spring-boot-maven-app.git using reference branch main.
```

The workflow input consists of:

```json
{
  "repositoryUrl": "https://github.com/example/spring-boot-maven-app.git",
  "referenceBranch": "main"
}
```

### Google Cloud Shell

When using Cloud Shell preview, a command similar to the following can expose ADK Web through the Cloud Shell proxy:

```bash
PORT=8000
adk web . \
  --host 0.0.0.0 \
  --port ${PORT} \
  --allow_origins "regex:https://${PORT}-cs-[^.]+\\..*\\.cloudshell\\.dev" \
  --no-reload
```

Use the Cloud Shell Web Preview for port `8000`.

---

## Run with ADK CLI

```bash
adk run oss_remediation_agent
```

Then provide the repository URL and reference branch in the prompt.

---

# Generated Workspaces and Artifacts

Each workflow execution creates a workspace using a timestamped directory name such as:

```text
oss-remediation-workspaces/oss-remediation-YYYYMMDD-HHMMSS/
```

Typical contents include:

```text
manifest.json
baseline/
  baseline-build-result.json
  vulnerability-assessment-report.json
  project-analyzer-report.json
attempt-1/
  remediation-planning-context.json
  remediation-patch-plan.json
  patch-dry-run-result.json
  patch-application-proof.json
  validation-result.json
  outcome-analysis-summary.json
final/
  accepted-patch-plan-source-attempt-N.json
  remediation-verification-report.json
  pr-summary.json
  pr-description.md
  pull-request-publication.json
```

The workspace artifacts are the source of truth for workflow progress, retry decisions, validation, manual-review routing, final status, and Pull Request reporting.

---

# Local Troubleshooting

## `adk` command not found

Confirm that `.venv` is activated:

```bash
python -m pip show google-adk
```

If needed, reinstall:

```bash
python -m pip install --upgrade google-adk
```

## Python module import errors

Run the commands from the repository root and verify the active Python executable:

### macOS or Linux

```bash
which python
```

### Windows PowerShell

```powershell
Get-Command python
```

Then reinstall the Python dependencies in the active virtual environment.

## `osv-scanner` command not found

Verify installation and `PATH`:

```bash
osv-scanner --version
```

Restart the terminal after installing OSV Scanner if the executable was added to `PATH` during installation.

## GitHub authentication failure

```bash
gh auth status
gh auth login
```

Also verify repository access:

```bash
gh repo view OWNER/REPOSITORY
```

## Maven build fails locally

Run the target repository's build command manually before starting ADK:

```bash
mvn clean install
```

Check:

- JDK version and `JAVA_HOME`,
- Maven profiles,
- `~/.m2/settings.xml`,
- access to private artifact repositories,
- proxy configuration,
- project-specific build arguments.

## Vertex AI authentication error

Re-run:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com
```

Confirm that the configured account has permission to use Vertex AI in the selected project and location.

## ADK reports a permission error for `runtime-config.json`

Some system-wide ADK installations may log a warning similar to:

```text
Permission denied: .../google/adk/cli/browser/assets/config/runtime-config.json
```

If the server continues and prints `ADK Web Server started`, this warning may not prevent local execution. Installing ADK inside the project virtual environment is preferred because it avoids writing through a system-wide Python installation.

## Port 8000 is already in use

Choose another port:

```bash
adk web . --host 127.0.0.1 --port 8001 --no-reload
```

---

# Security and Local Development Notes

- Do not commit `.env`, cloud credentials, GitHub tokens, or Maven repository credentials.
- Use GitHub CLI authentication or an approved credential manager.
- Use Application Default Credentials for Vertex AI instead of copying service-account keys into the repository.
- Run the workflow first against a non-production repository or a dedicated demo branch.
- Review generated dependency changes and workspace evidence before promoting a Draft Pull Request.
- Keep the workflow's dependency-only scope intact unless a manual-review decision explicitly requires broader engineering work.

---

# Quick Start

```bash
git clone https://github.com/AILearner365/oss-remediation-adk.git
cd oss-remediation-adk
git checkout oss-remediation-adk-customer-demo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install google-adk google-cloud-aiplatform google-genai python-dotenv PyYAML requests
gh auth login
gcloud auth application-default login
make compile
adk web . --host 127.0.0.1 --port 8000 --no-reload
```

Then open:

```text
http://127.0.0.1:8000
```
