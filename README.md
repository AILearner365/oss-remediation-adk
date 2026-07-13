# OSS Remediation ADK

A Google ADK workflow for Java Spring Boot Maven repositories. It scans Critical and High OSS vulnerabilities, analyzes Maven dependency ownership, creates dependency-only remediation plans, validates the changes, and creates a Draft GitHub Pull Request when validation succeeds.

## What the workflow does

1. Clones the target repository and checks out the requested reference branch.
2. Runs a baseline Maven build.
3. Runs OSV Scanner and creates a vulnerability assessment report.
4. Analyzes Maven modules, parent POMs, `dependencyManagement`, properties, and dependency paths.
5. Uses the remediation planning agent to create a safe patch plan.
6. Applies only allowed `pom.xml` dependency-version changes.
7. Runs patch dry run, build, tests, and OSV validation.
8. Creates a Draft Pull Request when the validated patch set is safe.

The automated path does not modify Java source code, test source code, JDK versions, Maven plugin logic, suppression files, or ignore rules.

---

# Recommended setup: Google Cloud Shell Editor

These are the supported onboarding steps for team members. Run every command from Google Cloud Shell unless the step says otherwise.

## Prerequisites

Install or configure the following on the machine that will run the ADK workflow:

| Tool or access | Why it is needed | Requirement / verification |
|---|---|---|
| Google Cloud project | Hosts the Vertex AI model access used by the ADK agents | A project ID must be available and selected with `gcloud config set project YOUR_PROJECT_ID` |
| Vertex AI API | Allows the workflow to invoke Gemini through Vertex AI | Enable `aiplatform.googleapis.com` in the selected project |
| Google Cloud CLI (`gcloud`) | Selects the project, enables APIs, and creates Application Default Credentials | Verify with `gcloud --version` |
| Application Default Credentials | Authenticates the ADK workflow to Google Cloud and Vertex AI | Run `gcloud auth application-default login` and verify that an access token can be created |
| Python 3.10+ | Runs the Google ADK agent application and workflow code | Verify with `python3 --version` |
| `pip` | Installs the Python packages listed in `requirements.txt` | Verify with `python3 -m pip --version` |
| Python virtual environment | Isolates the project dependencies from the system Python installation | The setup script creates and uses `.venv` |
| Google ADK and project Python dependencies | Provide the agent runtime, model integration, and workflow libraries | Installed by `bash scripts/setup-local.sh` from `requirements.txt` |
| Git | Clones the ADK and target repositories, creates remediation branches, commits changes, and pushes them | Verify with `git --version` |
| GitHub account and repository access | Allows the workflow to read the target repository | The authenticated identity must have access to the requested repository and branch |
| GitHub write permission | Allows the workflow to push the remediation branch and create a Draft Pull Request | Required when automatic PR creation is enabled |
| GitHub CLI (`gh`) | Creates the Draft Pull Request after validation succeeds | Verify with `gh --version`, then authenticate with `gh auth login` |
| JDK | Builds and tests the target Java Spring Boot Maven project | Use a JDK version compatible with the target repository; verify with `java -version` and ensure `JAVA_HOME` is correct |
| Maven | Runs the baseline build, dependency analysis, remediation build, and tests | Use a Maven version compatible with the target repository; verify with `mvn -version` |
| Maven repository configuration | Resolves dependencies from Maven Central or private artifact repositories | Configure `~/.m2/settings.xml`, mirrors, profiles, proxies, and credentials when the target project requires them |
| OSV Scanner v2 | Scans the resolved Maven dependencies for Critical and High OSS vulnerabilities before and after remediation | The `osv-scanner` executable must be available on `PATH`; verify with `osv-scanner --version` |
| Go toolchain (conditional) | Installs OSV Scanner in Cloud Shell when it is not already available | Needed only for the documented `go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest` command |
| Network access | Downloads Maven artifacts, Python packages, Go modules, Git repositories, OSV data, and calls Google/GitHub services | Outbound access must permit the required Google Cloud, GitHub, Maven, PyPI, Go, and OSV endpoints |
| Filesystem write access | Creates `.venv`, cloned repositories, timestamped workspaces, logs, patches, validation artifacts, and temporary branches | The user running ADK must be able to write under the repository and workspace directories |
| Available disk space | Stores the target repository, Maven cache, build outputs, OSV reports, and workflow artifacts | Ensure sufficient space is available before running large multi-module repositories |
| Local port | Serves ADK Web in Cloud Shell | Port `8000` must be available, or set another value through `ADK_PORT` |

Google Cloud Shell normally includes Python, Git, Java, Maven, Google Cloud CLI, GitHub CLI, and Go. The setup script installs the Python packages used by this project. OSV Scanner must also be available on `PATH`.

## 1. Select the Google Cloud project

Check the active project:

```bash
gcloud config get-value project
```

Set it when needed:

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

Verify the credentials:

```bash
gcloud auth application-default print-access-token >/dev/null \
  && echo "Google authentication is ready"
```

## 2. Clone this repository and checkout the customer-demo branch

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

Expected output:

```text
oss-remediation-adk-customer-demo
```

If the repository already exists locally, update it instead:

```bash
cd ~/oss-remediation-adk
git fetch origin
git checkout oss-remediation-adk-customer-demo
git pull --ff-only origin oss-remediation-adk-customer-demo
```

## 3. Run the project setup script

```bash
chmod +x scripts/*.sh
bash scripts/setup-local.sh
```

The script is safe to run again. It:

- creates `.venv` when it does not exist,
- activates the virtual environment,
- upgrades `pip`,
- installs `requirements.txt`,
- creates `.env` from `.env.example` when needed.

## 4. Configure `.env`

Open `.env` in Cloud Shell Editor and update the project value:

```dotenv
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_GENAI_USE_ENTERPRISE=1
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
ADK_HOST=0.0.0.0
ADK_PORT=8000
```

Use `GOOGLE_GENAI_USE_ENTERPRISE=1` only when required by your organization. Do not commit `.env`.

## 5. Install OSV Scanner when missing

Check first:

```bash
osv-scanner --version
```

If the command is missing, Cloud Shell users can install the current OSV Scanner v2 with Go:

```bash
go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest
export PATH="$PATH:$HOME/go/bin"
osv-scanner --version
```

To keep the Go binary available in future Cloud Shell sessions:

```bash
echo 'export PATH="$PATH:$HOME/go/bin"' >> ~/.bashrc
source ~/.bashrc
```

The workflow expects the `osv-scanner` executable to be available in the same terminal used to start ADK.

## 6. Authenticate GitHub CLI

```bash
gh auth login
gh auth status
```

The authenticated GitHub identity must be able to:

- clone the target repository,
- create and push a remediation branch,
- create a Draft Pull Request.

For a private target repository, verify access before running the workflow:

```bash
gh repo view OWNER/REPOSITORY
```

## 7. Run the prerequisite check

```bash
bash scripts/check-prereqs.sh
```

Resolve every `MISSING` item before starting ADK. Review any `WARNING`, especially authentication or `.env` warnings.

---

# Run the workflow

## Option A: ADK Web in Cloud Shell

Start ADK Web:

```bash
bash scripts/run-adk-web.sh
```

Keep the terminal running. In Cloud Shell, select **Web Preview** and open port `8000`.

In ADK Web:

1. Select `oss_remediation_agent`.
2. Enter a request such as:

```text
Run the OSS remediation workflow for repository https://github.com/AILearner365/maven-multimodule-app using reference branch master.
```

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

# What a successful run produces

Each execution creates a timestamped workspace:

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

`manifest.json` is the workflow index. It records stage status, artifact paths, attempts, accepted patches, final status, and Pull Request details.

A successful happy-path run should show:

- baseline build succeeded,
- vulnerability assessment succeeded,
- project analysis succeeded,
- remediation planning returned `PATCH_PLAN`,
- patch dry run and patch application succeeded,
- validation succeeded,
- accepted patch set was created,
- Draft Pull Request was created.

---

# Before running against a new target repository

The workflow intentionally stops when the target project does not build before remediation. Confirm the target repository can build in Cloud Shell with its required JDK, Maven profile, private repository credentials, and `settings.xml` configuration.

Example:

```bash
git clone TARGET_REPOSITORY_URL /tmp/target-project
cd /tmp/target-project
mvn clean install
```

Return to the ADK repository before starting the workflow:

```bash
cd ~/oss-remediation-adk
```

---

# Troubleshooting

## `adk: command not found`

```bash
cd ~/oss-remediation-adk
source .venv/bin/activate
python -m pip show google-adk
adk --help
```

If the package is missing, rerun:

```bash
bash scripts/setup-local.sh
```

## `osv-scanner: command not found`

```bash
export PATH="$PATH:$HOME/go/bin"
osv-scanner --version
```

If it is still missing, repeat the OSV Scanner installation step above.

## GitHub authentication fails

```bash
gh auth login
gh auth status
gh repo view OWNER/REPOSITORY
```

## Google authentication fails

```bash
gcloud auth application-default login
gcloud auth application-default print-access-token
```

Also confirm the project and location in `.env`.

## Baseline Maven build fails

The workflow does not remediate a repository with a broken baseline. Manually run the target project's normal build and resolve JDK, Maven profile, `settings.xml`, or private artifact-repository issues first.

## Port 8000 is already in use

```bash
ADK_PORT=8001 bash scripts/run-adk-web.sh
```

Then open Web Preview for port `8001`.

---

# Developer verification

```bash
cd ~/oss-remediation-adk
source .venv/bin/activate
python -m compileall -q oss_remediation_agent
python -m unittest discover -s tests
```

---

# Security notes

- Never commit `.env`, API keys, tokens, or Maven credentials.
- Use `~/.m2/settings.xml` for private Maven repository credentials.
- The workflow creates Draft Pull Requests; it does not merge them automatically.
- Review the generated PR and validation artifacts before marking the PR ready for review.
