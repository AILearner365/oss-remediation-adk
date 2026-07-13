# OSS Remediation ADK

This repository contains an ADK-based OSS vulnerability remediation workflow for Java Spring Boot Maven applications.

## Local Setup Prerequisites

Install and configure the following prerequisites on the machine that will run the ADK workflow.

| Prerequisite | Requirement | Why it is needed | Required when |
|---|---|---|---|
| Python | Python 3.10 or later | Runs the ADK agent application and workflow orchestration code. | Always |
| `pip` | A version compatible with the installed Python runtime | Installs Google ADK and the Python dependencies used by the project. | Always |
| Python virtual environment | `venv`, Conda, or an equivalent isolated environment | Keeps the workflow dependencies isolated from the system Python installation. | Strongly recommended |
| Google ADK | Installed in the active Python environment | Provides the agent runtime used by `oss_remediation_agent/agent.py`. | Always |
| Gemini authentication | A valid Gemini API key or supported Google Cloud/Vertex AI credentials | Allows the Planning and Outcome Analysis agents to invoke the configured Gemini model. | When using live LLM invocation |
| Git | A recent Git client available on `PATH` | Clones target repositories, checks out the baseline commit, creates remediation branches, commits changes, and pushes branches. | Always |
| Git credentials | Credentials with read access to the target repository and push access when publishing a PR | Allows checkout of private repositories and publication of remediation branches. | Private repositories and automatic PR publication |
| JDK | A JDK version compatible with the target Maven project, commonly JDK 17 or JDK 21 | Compiles and tests the Java Spring Boot Maven application. | Always |
| `JAVA_HOME` | Set to the selected JDK installation when required by the local environment | Ensures Maven and validation commands use the intended Java runtime. | Environments that do not resolve Java automatically |
| Apache Maven | A Maven version compatible with the target project, available as `mvn` on `PATH` | Runs baseline builds, `mvn clean install`, `mvn test`, effective-POM generation, and dependency-tree analysis. | Always |
| Maven repository access | Network and credentials for Maven Central and any configured private artifact repositories | Resolves project dependencies, plugins, parent POMs, and BOMs during analysis and validation. | Always; credentials are conditional for private repositories |
| OSV-Scanner | OSV-Scanner CLI available on `PATH` | Scans the resolved project dependencies before and after remediation for in-scope OSS vulnerabilities. | Always |
| GitHub CLI | GitHub CLI (`gh`) available on `PATH` | Creates the final draft pull request after the validated patch branch is pushed. | `AUTO` PR creation mode |
| GitHub CLI authentication | An authenticated `gh` session with permission to create branches and pull requests | Enables automated pull-request publication. Verify with `gh auth status`. | `AUTO` PR creation mode |
| Internet/network access | Access to GitHub, the configured Git remote, Maven repositories, OSV services/data, and the configured Gemini endpoint | Supports repository operations, dependency resolution, vulnerability scanning, and LLM invocation. | Always, unless every dependency and service is available locally |
| Filesystem permissions | Read/write permission for the repository checkout and `oss-remediation-workspaces` directory | Persists manifests, analyzer reports, patch plans, diffs, validation logs, and final PR artifacts. | Always |
| Disk space | Enough space for repository clones, Maven caches, build outputs, and remediation workspaces | Each attempt creates an isolated repository workspace and validation artifacts. | Always |

### Authentication notes

- Configure the Gemini authentication method expected by your ADK environment before starting the agent. Do not commit API keys or service-account secrets to the repository.
- Run `git ls-remote <repository-url>` to confirm repository read access.
- When automatic PR publication is enabled, run `gh auth status` and confirm the authenticated account can push branches and create pull requests in the target repository.
- Configure Maven `settings.xml` when the target project uses private artifact repositories, mirrors, proxies, or repository credentials.

### Command availability check

Run these commands from the same terminal or virtual environment that will start the ADK workflow:

```bash
python --version
pip --version
git --version
java -version
mvn --version
osv-scanner --version
gh --version
gh auth status
```

The exact JDK and Maven versions must follow the target application's build requirements. The workflow should not silently replace the target project's required Java or Maven toolchain.

## Architecture Documentation

The finalized architecture, artifact contracts, deterministic tool APIs, AI agent specifications, workflow orchestration, and implementation plan are documented here:

- [Phase 1 Architecture: ADK OSS Remediation Workflow](docs/phase-1-architecture.md)
- [Phase 2 Artifact Contracts](docs/phase-2-artifact-contracts.md)
- [Phase 3 Deterministic Tool API Definitions](docs/phase-3-deterministic-tool-apis.md)
- [Phase 4 AI Agent Specifications](docs/phase-4-ai-agent-specifications.md)
- [Phase 5 ADK Workflow Orchestration Specification](docs/phase-5-workflow-orchestration-specification.md)
- [Phase 6 Implementation Plan and Code Structure](docs/phase-6-implementation-plan-and-code-structure.md)

The Phase 1 document captures:

- AI agent responsibilities
- deterministic tool responsibilities
- remediation workspace and attempt manifest design
- baseline build gate
- exact patch planning model
- validation model
- retry lifecycle
- partial PR strategy
- PR summary requirements

The Phase 2 document captures:

- Attempt Manifest contract
- Vulnerability Assessment Report contract
- Project Analyzer Report contract
- Exact Remediation Patch Plan contract
- Patch Application Proof contract
- Validation Result contract
- Outcome Analysis Summary contract
- PR Summary contract
- Principal Engineer clarifications for validation success, controlled direct patching, and outcome analysis boundaries

The Phase 3 document captures:

- common deterministic tool result envelope
- tool responsibility matrix
- capabilities and limitations metadata
- orchestrator-only manifest update rule
- Baseline Build Result as a first-class artifact
- Repo Checkout Tool API
- Baseline Build Tool API
- OSV Scanner Tool API
- Project Analyzer Tool API
- Generic Patch Apply Tool API
- Validation Tool API
- PR Creation Tool API
- Principal Engineer clarification that tool payloads are summaries only and full outputs must be persisted as workspace artifacts

The Phase 4 document captures:

- AI agent responsibility matrix
- Remediation Planning Agent authority model
- vulnerability-centric planning model
- evidence-based planning requirements
- manual review decision contract and categories
- replanning model
- additional deterministic investigation request model
- Remediation Outcome Analysis Agent authority model
- outcome failure and responsibility classifications
- AI guardrails
- partial remediation strategy
- prompt definitions

The Phase 5 document captures:

- ADK workflow execution lifecycle
- runtime ownership model
- workflow state transitions
- remediation attempt lifecycle
- attempt counting rules
- additional investigation lifecycle and guard behavior
- stored-artifacts-first data regeneration policy
- patch dry-run and patch application lifecycle
- validation lifecycle and validation success semantics
- accepted patch set lifecycle
- outcome analysis routing
- failure artifact persistence
- manual review and max-attempt handling
- PR creation conditions
- orchestrator decision rules
- runtime pseudocode

The Phase 6 document captures:

- implementation order and principles
- final recommended project structure
- contract model implementation plan
- JSON schema folder and validation strategy
- external remediation policy configuration
- prompt file organization
- workspace, artifact, and manifest storage layers
- deterministic tool implementation plan
- AI agent implementation boundaries
- orchestrator method structure
- CLI and ADK entrypoint separation
- examples and Maven fixture repositories
- unit and integration testing strategy
- MVP implementation priority

## Current Architecture Principle

```text
AI Agents      = reasoning and engineering decisions
Tools          = deterministic facts and execution
Workspace      = persisted artifacts
Manifest       = artifact index and attempt status
ADK Workflow   = execution order and lifecycle control
```
