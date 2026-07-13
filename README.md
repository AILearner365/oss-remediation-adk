# OSS Remediation ADK

A Google ADK-based workflow that scans Java Spring Boot Maven repositories for Critical and High OSS vulnerabilities, plans dependency-only fixes, validates the changes, and creates a Draft GitHub Pull Request when validation succeeds.

## What the workflow does

1. Clones the target repository and checks the reference branch.
2. Runs a baseline Maven build.
3. Runs OSV Scanner and creates a vulnerability assessment report.
4. Analyzes the Maven project structure and dependency ownership.
5. Uses the remediation planning agent to create a safe patch plan.
6. Applies only allowed `pom.xml` dependency-version changes.
7. Runs build, tests, and OSV validation.
8. Creates a Draft Pull Request when the validated patch set is safe.

## Supported project type

- Java Spring Boot applications
- Maven single-module or multi-module repositories
- Direct and transitive Maven dependencies
- `dependencyManagement` and Maven properties

The automated path does not modify Java source code, test source code, JDK versions, Maven plugin logic, suppressions, or ignore rules.

---

# Quick setup in Google Cloud Shell

These instructions are the recommended path for team members using Cloud Shell Editor.

## 1. Open Cloud Shell

Open Google Cloud Shell and make sure the correct Google Cloud project is selected.

Verify:

```bash
gcloud config get-value project
```

Set the project if needed:

```bash
gcloud config set project YOUR_PROJECT_ID
```

Enable Vertex AI once for the project:

```bash
gcloud services enable aiplatform.googleapis.com
```

Create Application Default Credentials:

```bash
gcloud auth application-default login
```

Verify authentication:

```bash
gcloud auth application-default print-access-token >/dev/null && echo "Google authentication is ready"
```

## 2. Clone this repository and checkout the demo branch

```bash
cd ~
git clone https://github.com/AILearner365/oss-remediation-adk.git
cd oss-remediation-adk
git checkout oss-remediation-adk-customer-demo
```

Confirm the branch:

```bash
git branch --show-current
```

Expected:

```text
oss-remediation-adk-customer-demo
```

## 3. Run the setup script

```bash
chmod +x scripts/*.sh
bash scripts/setup-local.sh
```

The setup script:

- creates `.venv`,
- installs Python dependencies from `requirements.txt`,
- creates `.env` from `.env.example` when missing,
- runs prerequisite checks.

## 4. Configure `.env`

Open `.env` and update the project value:

```dotenv
GOOGLE_GENAI_USE_ENTERPRISE=1
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
ADK_HOST=0.0.0.0
ADK_PORT=8000
```

Do not commit `.env`.

## 5. Authenticate GitHub CLI

The workflow needs GitHub access to clone repositories, push a remediation branch, and create a Draft Pull Request.

```bash
gh auth login
gh auth status
```

The authenticated user must have write access to the target repository.

## 6. Verify the environment

```bash
bash scripts/check-prereqs.sh
```

The script checks:

- Python 3.11+
- Git
- Java and `javac`
- Maven
- OSV Scanner
- GitHub CLI authentication
- Google Application Default Credentials
- `.env`
- ADK installation

Resolve any reported `MISSING` item before starting the workflow.

---

# Run the workflow

## Option A: ADK Web in Cloud Shell

Start ADK Web:

```bash
bash scripts/run-adk-web.sh
```

Then open Cloud Shell **Web Preview** for port `8000`.

Select the `oss_remediation_agent` application and enter a prompt such as:

```text
Run the OSS remediation workflow for repository https://github.com/AILearner365/maven-multimodule-app using reference branch master.
```

Keep the terminal running while using ADK Web.

## Option B: ADK CLI

```bash
bash scripts/run-adk-cli.sh
```

Then enter:

```text
repository url: https://github.com/AILearner365/maven-multimodule-app
reference branch: master
```

---

# Required tools

Cloud Shell already includes several tools, but verify all of the following:

| Tool | Purpose |
|---|---|
| Python 3.11 or 3.12 | Runs Google ADK |
| Git | Clones repositories and manages branches |
| JDK | Builds the target Maven project |
| Maven | Runs build, tests, and dependency analysis |
| OSV Scanner | Detects OSS vulnerabilities |
| GitHub CLI | Pushes branches and creates Draft PRs |
| Google Cloud CLI | Authenticates Vertex AI |

Verify manually:

```bash
python3 --version
git --version
java -version
javac -version
mvn -version
osv-scanner --version
gh --version
adk --help
```

If OSV Scanner is missing, install it using the official OSV Scanner installation instructions for your environment, then confirm:

```bash
osv-scanner --version
```

The `osv-scanner` executable must be available on `PATH` in the same terminal used to run ADK.

---

# Generated output

Each workflow run creates a timestamped workspace:

```text
oss-remediation-workspaces/oss-remediation-YYYYMMDD-HHMMSS/
```

Important artifacts include:

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
final/
  pr-summary.json
  pr-description.md
  pull-request-publication.json
```

`manifest.json` is the workflow index and records stage status, artifact paths, attempts, accepted patches, and Pull Request details.

---

# Expected successful result

A successful run should show:

- baseline build succeeded,
- vulnerability assessment succeeded,
- project analysis succeeded,
- remediation planning returned `PATCH_PLAN`,
- patch dry run and patch application succeeded,
- validation succeeded,
- accepted patch set was created,
- Draft Pull Request was created.

The final response includes the workspace path and Draft Pull Request URL.

---

# Common troubleshooting

## `adk: command not found`

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Then verify:

```bash
python -m pip show google-adk
adk --help
```

## `osv-scanner: command not found`

Install OSV Scanner and ensure it is available on `PATH`:

```bash
osv-scanner --version
```

## GitHub authentication failure

```bash
gh auth login
gh auth status
```

Also confirm repository access:

```bash
gh repo view OWNER/REPOSITORY
```

## Google authentication failure

```bash
gcloud auth application-default login
gcloud auth application-default print-access-token
```

Confirm that `.env` contains the correct Google Cloud project and location.

## Baseline Maven build fails

The workflow intentionally stops when the target repository does not build before remediation. Clone the target repository manually and run its normal Maven build first:

```bash
mvn clean install
```

Resolve project-specific JDK, Maven profile, `settings.xml`, or private artifact-repository requirements before rerunning the agent.

## Port 8000 is already in use

```bash
ADK_PORT=8001 bash scripts/run-adk-web.sh
```

Open the Cloud Shell Web Preview for the same port.

---

# Developer validation

Activate the environment:

```bash
source .venv/bin/activate
```

Compile the Python package:

```bash
python -m compileall -q oss_remediation_agent
```

Run tests:

```bash
python -m unittest discover -s tests
```

---

# Security notes

- Never commit `.env`, API keys, tokens, or Maven credentials.
- Use `~/.m2/settings.xml` for private Maven repository credentials.
- The workflow creates Draft Pull Requests for human review; it does not merge them automatically.
- Review the generated PR and validation artifacts before marking the PR ready for review.
