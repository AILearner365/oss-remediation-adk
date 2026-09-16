# Autonomous OSS Remediation Agent - Design Proposal

**Status:** Revised after design review. No implementation is authorized by this document.

## 1. Review Basis

This proposal is based on:

- `docs/AUTONOMOUS_OSS_REMEDIATION_REQUIREMENTS.md` as the authoritative requirements;
- `docs/AUTONOMOUS_OSS_REMEDIATION_DESIGN_REVIEW.md` as the required revision scope;
- the current `oss_remediation_agent` source as reference material;
- the current tests and committed Maven fixtures;
- direct inspection of the locally installed Google ADK and Google Gen AI packages;
- direct inventory of available developer executables, optional integration packages, container support, Git/GitHub support, and credential/configuration presence without reading credential values.

The existing `oss-remediation-workspaces` directory and all other repository documentation were excluded from the investigation.

## 2. Existing Implementation Findings

The reference implementation is a staged, artifact-heavy workflow:

1. `oss_remediation_agent/agent.py` exposes multiple ADK `LlmAgent` stages in an ADK `Workflow`.
2. `WorkflowOrchestrator` and its Phase 5/6 subclasses own lifecycle, manifests, attempts, validation, and delivery.
3. Repository preparation clones into `baseline/repository`, records the baseline commit, runs `mvn clean install`, and unconditionally performs a time-window `mvn spring-boot:run` check.
4. OSV Scanner runs against a temporary copy so a parent `.gitignore` cannot hide the target repository. Its JSON is normalized to Maven findings and filtered by severity.
5. Maven analysis gathers POM locations, properties, parent/Spring Boot information, `dependency:tree`, and `help:effective-pom` evidence.
6. The planning LLM emits a rigid `PATCH_PLAN`, `REQUEST_ADDITIONAL_EVIDENCE`, or `MANUAL_REVIEW` JSON contract. Deterministic code interprets exact-text, POM-only patches.
7. Validation checks a narrow change scope, runs build/startup/test, rescans with OSV, compares findings, and records a Git diff.
8. A separate outcome-analysis LLM classifies failures before another planning attempt.
9. Delivery is deterministic and policy-gated: clone again, create a remediation branch, replay the accepted patch plan, commit, push, and invoke `gh pr create --draft`.
10. Tests cover contracts, OSV normalization, Maven fixture analysis, exact-text patching, validation gates, retry limits, accepted patch sets, and PR summaries. Most external commands and all LLM behavior are mocked; the fixtures primarily exercise Maven POM shapes rather than a live vulnerable Spring application.

Useful reference behavior exists, but the planner/patch-interpreter/outcome-agent pipeline and its Maven-specific strategy prompt are explicitly not the target architecture for the new package.

## 3. Installed ADK Capability Investigation

The active project virtual environment has `include-system-site-packages = true` and resolves:

- `google-adk==2.4.0` from the user site-packages directory;
- `google-genai==2.11.0`;
- no repository dependency manifest currently pins either package.

ADK 2.4.0 provides:

- `LlmAgent` with callable tools, tool callbacks, agent timeouts, and normal multi-tool model turns;
- `Runner.run_async(...)` and session services, allowing repeated invocations with the same `session_id` so validation evidence can be sent back to the same agent conversation;
- experimental `LocalEnvironment`, `BaseEnvironment`, and `EnvironmentToolset` APIs;
- experimental environment tools named `Execute`, `ReadFile`, `EditFile`, and `WriteFile`.

The native environment tools are not sufficient as the POC security boundary:

- `LocalEnvironment` accepts absolute paths and does not prevent `..` or symlink escape.
- `LocalEnvironment.execute` uses an unrestricted shell in the configured working directory; a working directory is not a filesystem sandbox.
- the native `Execute` tool hard-codes a 30-second timeout, which is unsuitable for Maven builds and is not configurable through `EnvironmentToolset`.
- `EnvironmentToolset` has no dedicated list/search tools; those operations are expected to use command execution.
- returned command/file output is truncated to 30,000 characters.
- all of these environment APIs are marked experimental.
- ADK's `bash_tool` cannot be imported on this Windows host because Python's `resource` module is unavailable. It is Unix-oriented and therefore not a viable local option here.

Other materially relevant local findings are:

- ADK's `FunctionTool`, tool callbacks, and normal multi-tool turns are installed and import successfully without optional dependencies.
- ADK contains an `McpToolset`, but the optional `mcp` package is not installed and no local MCP server is installed. Using MCP would therefore add both a protocol dependency and a server/process lifecycle.
- Gemini's `BuiltInCodeExecutor` is model-hosted code execution; it does not expose the prepared host repository or the required Maven/OSV toolchain.
- The environment has Git 2.46.0, Maven 3.9.11, Java 21, PowerShell 5.1, Python, Node/npm/npx, and `rg`. `gh`, `osv-scanner`, `jq`, and `pwsh` are not currently on `PATH`.
- Docker CLI 27.1.1 is installed, but its Linux daemon is not running. WSL has only the Docker Desktop distribution, and the Python Docker SDK, E2B, Daytona, Kubernetes, and MCP packages are absent.
- Git Credential Manager is configured at the system level, but no `GH_TOKEN` or `GITHUB_TOKEN` environment variable is present. Credential values were not inspected.
- No repository dependency manifest pins ADK, Google Gen AI, MCP, or a sandbox provider.

These facts weaken or eliminate some options in this environment, but do not by themselves select the developer-capability implementation. Section 7 compares the materially available choices before making that selection.

## 4. Proposed Architecture

```text
RemediationRequest
       |
       v
Deterministic preparation
  - create isolated run/workspace directories
  - clone requested ref and record immutable baseline
       |
       v
Deterministic baseline and assessment
  - build/test/startup expectations
  - fresh OSV scan and normalization
  - capture enforceable constraint baseline
       |
       v
+---------------------------------------------------+
| Bounded remediation loop                          |
|                                                   |
| same ADK LlmAgent + same Runner session           |
|   -> inspect/edit/execute in same repository      |
|   -> agent turn ends                              |
|                                                   |
| deterministic validator                           |
|   PASS -> leave loop                              |
|   FAIL -> structured evidence becomes next        |
|           user message in the same ADK session    |
+---------------------------------------------------+
       |
       v
Deterministic delivery gate
  - recheck validated tree/diff identity
  - branch, commit, push, Draft PR
```

There is one primary remediation `LlmAgent`. Preparation, baseline assessment, validation, outcome selection, and delivery are ordinary deterministic Python services called by the outer orchestrator, not additional LLM agents.

The orchestrator retains one working repository across cycles. It does not reset the repository or ask the model for a machine-interpreted patch plan. The model directly investigates and changes the repository with developer tools.

## 5. Remediation Contract

`RemediationRequest` will contain:

- repository URL and reference branch;
- workspace root or configured workspace parent;
- requested vulnerability IDs and/or severity scope;
- required build, test, and optional startup commands;
- typed enforceable constraints;
- free-text engineering constraints for agent context;
- command timeout, maximum cycles, maximum command/tool calls, and overall elapsed-time budget;
- delivery mode and Draft PR settings.

Initial typed constraints will cover at least:

- protected Java version;
- protected Spring Boot version;
- prohibited vulnerability suppression/ignore changes;
- prohibited new vulnerability severities;
- allowed or protected file paths when supplied;
- required validation commands.

Free-text constraints are always shown to the agent and retained as evidence. A free-text constraint that cannot be mapped to a deterministic validator makes automated PR delivery ineligible unless the request explicitly marks it informational. This prevents an LLM assertion from substituting for enforcement.

## 6. Deterministic and LLM Responsibilities

### Deterministic responsibilities

- validate the request and create the isolated run layout;
- clone and resolve the requested Git ref to a baseline commit;
- choose Maven wrapper versus installed Maven by repository evidence/configuration;
- execute and record baseline build/test/startup requirements;
- execute OSV Scanner, validate its report, normalize findings, and select requested scope;
- capture protected versions, relevant config, initial Git state, and constraint baselines;
- bind all LLM tools to the one prepared repository;
- enforce path, command, timeout, output, environment, and budget boundaries;
- run fresh validation after every agent work cycle;
- determine validation pass/fail and final outcome;
- gate and perform Git branch/commit/push/Draft PR operations;
- persist concise trace artifacts.

### Autonomous LLM responsibilities

- inspect repository structure and project files;
- investigate direct/transitive dependencies, effective versions, parents, BOMs, and framework management;
- decide which supported engineering approach to try;
- edit any in-scope repository file needed for a compatible remediation;
- run permitted developer commands and Maven plugins;
- create workspace-local temporary scripts or tools;
- observe command failures and revise or revert its approach;
- explain its work and blockers.

The LLM never decides that validation passed, never performs delivery, and never receives credentials required to push or create a PR.

## 7. Developer Capability Options and Selection

### Required capabilities

The remediation objective requires the agent to be able to:

- discover repository/module structure and search names and content;
- read text with bounded results and inspect generated build/dependency evidence;
- create, replace, patch, and delete repository-local text files;
- run repository wrappers, Maven goals/plugins, tests, Git inspection, and workspace-local scripts with shell composition when useful;
- receive stdout, stderr, exit status, duration, timeout state, and references to full logs;
- inspect diffs and local history, preserve one workspace across cycles, and continue from concrete validation failures;
- use normal build dependency resolution and other explicitly approved network access without receiving delivery credentials.

### Material options investigated

| Option | Current-environment evidence | Autonomy, dependency, and boundary trade-off | Decision |
| --- | --- | --- | --- |
| ADK `EnvironmentToolset(LocalEnvironment)` | Installed; provides shell execute and read/edit/write tools | Low added code and broad shell autonomy, but experimental, fixed 30-second command timeout, 30,000-character returned-output limit, inherited host environment, and no filesystem confinement | Not used directly |
| Stable ADK `FunctionTool` wrappers over local capabilities | Installed and importable; supports typed callables, callbacks, and the existing same-session runner design | Adds a small amount of independent bridge/policy code, but permits Maven-scale timeouts, full log artifacts, selected editing semantics, budget accounting, and honest boundary enforcement | Selected for the initial POC |
| ADK MCP client plus local filesystem/command or GitHub servers | ADK adapter source exists, but optional `mcp` and all required servers are absent | Could improve provider portability, but adds packages, subprocess/session lifecycle, server trust, and still requires the same workspace/command policy; no current server provides unique value for this POC | Deferred |
| Local Docker/WSL sandbox | Docker CLI is installed, but the daemon is unavailable and no usable WSL development distribution is present | Would strengthen isolation, but requires daemon availability, images matching repository JDK/tool needs, mount/cache/network design, and materially more operations | Alternative if hard isolation is required, not the initial backend |
| Hosted sandbox providers such as E2B/Daytona/Vertex sandbox | Relevant optional packages and credentials/configuration are absent; the inspected Vertex sandbox integration is browser/computer-use oriented | Adds vendor credentials, remote repository transfer, cost, and environment parity work without an established project requirement | Not selected |
| ADK `bash_tool` or Gemini built-in code execution | `bash_tool` fails to import on Windows; built-in execution is not attached to the host repository | Cannot provide the required local repository/build workflow | Rejected |

### Selected capability surface

The initial POC will use stable ADK `FunctionTool` integration with three coding-oriented capabilities bound to the prepared repository:

1. a bounded repository text-read capability with line/range metadata;
2. a repository-relative patch capability that can create, update, or delete text files and returns changed paths/hashes;
3. a host-native workspace shell capability with a repository-relative working directory, configurable timeout, structured process result, and full-log artifact reference.

Discovery, search, dependency analysis, local Git inspection, and diff review use the shell with installed/project-provided commands such as `rg`, `git`, Maven/Maven Wrapper, Java, and workspace-local scripts. This deliberately avoids separate Maven, Java, Python, Git-inspection, list, and search abstractions that would constrain how the agent investigates. The read and patch capabilities remain separate because they give the model reliable, auditable text interaction without shell quoting, while the shell retains pipes, command chaining, wrapper behavior, plugins, and ad hoc helpers that the original `shell=False` argument-vector proposal would lose.

The same internal execution service will run deterministic build/test/scanner commands outside the model-facing tool surface. The LLM does not receive validator, delivery, manifest, credential, or PR-publication tools.

The investigation successfully imported and inspected the installed `FunctionTool` interface and callbacks, confirmed same-session runner support, and executed the installed Git, Maven, Java, and `rg` binaries. It also confirmed the native 30-second timeout and MCP/sandbox dependency gaps described above. No package or runtime implementation was created during this capability spike.

### Capability coverage

| Required behavior | Selected support |
| --- | --- |
| Inspect/read/search | text-read tool plus `rg`, `git ls-files`, and host-native shell discovery |
| Create/edit/delete | repository patch tool; shell-created workspace-local helpers remain possible |
| Build/test/dependency analysis | shell invokes Maven Wrapper or Maven, plugins, Java, and repository scripts with request-sized timeouts |
| Scan and security evidence | deterministic scanner uses the shared execution service; normalized reports and failures are supplied to the same agent session |
| Diagnose and iterate | every command returns structured status/output/log references; failed deterministic validation becomes the next same-session user message |
| Git engineering context | local `git status`, diff, log, show, restore, and related inspection are available; delivery authority is separate |

This selection introduces independent code for patch application, process control, policy, and tracing, but avoids an MCP server and optional provider dependency. It preserves more engineering freedom than the previous six-tool/argument-vector design while keeping a reviewable model-facing surface.

## 8. Permissions, Security, Network, and Operational Boundaries

### Stable boundaries independent of tool mechanism

- Work occurs in a fresh run directory and prepared repository; unrelated repositories and machine-wide changes are out of scope.
- Deterministic validation alone establishes success, and deterministic delivery alone may commit, push, or create a Draft PR.
- The LLM execution environment receives no delivery credential, secret-bearing host environment variable, or validator override.
- Per-command timeout, overall elapsed time, cycle/tool-call budgets, returned-output bounds, full-log capture, and process cleanup are enforced outside the prompt.
- Administrative elevation, service/daemon changes, system security changes, global JDK replacement, and global package installation are prohibited.
- Every model tool call and deterministic command is traceable with arguments after redaction, result metadata, log reference, and affected paths where applicable.

### Controls required by the selected local FunctionTool approach

- Text read/patch paths are canonicalized below the repository root; absolute paths, traversal, NULs, direct `.git` edits, and symlink/junction escape are rejected.
- The host-native shell starts in a repository-relative directory, uses a sanitized non-interactive environment, redirects temporary/cache locations into the run, and returns bounded output while preserving complete logs.
- Timeout handling terminates the process and makes a platform-specific best effort to terminate descendants; Windows process-tree behavior is covered by focused tests rather than assumed.
- Git commands in the LLM environment run with isolated system/global Git configuration, without interactive prompting, and with the prepared clone's push authority disabled. Local history/diff/revert operations remain available.
- The agent runner identity must not own delivery credentials. Disabling Git configuration and stripping environment variables are defense in depth, not sufficient isolation if the same OS identity can directly invoke a credential manager or secret store.
- Delivery secrets are resolved only after the agent tool phase has ended and a validated-tree digest has been rechecked, through a deterministic delivery process/identity or approved secret broker that the agent execution identity cannot access. They are never written to command logs or agent-visible artifacts.
- Obvious administrative, delivery, interactive, and machine-wide commands are rejected as defense in depth. The design does not claim that command-string filtering turns a shell into a security sandbox.

The shell accepts host-native command syntax rather than a `shell=False` executable/argument list. That choice permits pipes, conditional/chained commands, wrapper scripts, redirection, and temporary helpers needed for realistic coding-agent work. An exhaustive executable allowlist, path-token parser, blanket network ban, or forced empty Maven repository was rejected because each is both bypassable by allowed build code and likely to break legitimate repository-specific engineering.

### Network and trust model

Maven/OSV and some remediation investigations require outbound access. The run policy therefore declares network mode explicitly. The initial local backend may use the trusted runner's normal outbound network for dependency/plugin/scanner access, but supplies no agent-visible delivery credentials. Where an organization requires destination-level egress enforcement or execution of untrusted repositories, the local backend is insufficient and the run must use an externally enforced container/OS/remote sandbox or fail preflight.

Repository builds, Maven plugins, and scripts can execute arbitrary code, and a raw local shell can access resources allowed to the runner identity. Application path checks and command policy are not a hostile-code boundary. The initial POC is therefore limited to trusted repositories on a dedicated/trusted runner unless the reviewer requires the hard-isolation alternative. This is an explicit operational limit, not a hidden security claim.

## 9. Baseline and Assessment

The deterministic preparer will:

1. create `<run>/repository`, `<run>/artifacts`, `<run>/cache`, and `<run>/temp`;
2. clone the requested reference, resolve and record `HEAD`, remote, branch/ref, and clean status;
3. run configured baseline build/test commands, preferring a checked-in Maven Wrapper;
4. perform Spring Boot startup validation only when requested or when a runnable target can be determined reliably; aggregator/non-runnable projects are recorded as not applicable rather than failed by an unconditional `spring-boot:run`;
5. run the proven OSV source-scan pattern against a temporary scan copy that excludes `.git` and build outputs;
6. require a recognizable JSON report and normalize Maven findings, aliases, coordinates, versions, fixed versions, severity, and raw evidence;
7. select findings matching the requested IDs/severities;
8. capture protected Java/Spring Boot values, suppression configuration, relevant file hashes, and the initial Git tree.

An unusable baseline build, scanner failure, empty/unrecognized scanner evidence, or missing requested ref produces `BASELINE_FAILURE` and prevents autonomous work.

## 10. Autonomous Feedback Loop and Budgets

The orchestrator creates one `LlmAgent`, one `Runner`, and one session ID for the run.

First invocation content contains the remediation contract, normalized baseline findings, repository-relative location, supported deterministic constraints, completion criteria, budgets, and tool policy. The agent uses tools until its turn ends. Its final text is advisory; the orchestrator validates regardless of whether the agent claims completion.

After a failed validation, the orchestrator sends the same session a new user message containing the structured validation report and a concise instruction to continue in the same repository. The report includes failed checks, command exit codes, relevant stderr/stdout tails and log references, remaining/new findings, constraint violations, changed files, and diff summary. Prior conversation and tool history remain available through the reused ADK session.

Termination occurs on the first of:

- deterministic validation success;
- maximum remediation/validation cycles;
- maximum tool/command calls;
- overall elapsed-time deadline;
- unrecoverable tool/agent/runtime failure;
- an agent-declared safe blocker followed by deterministic validation/report capture.

Budget exhaustion never becomes success. Command timeouts consume budget and are returned as concrete evidence.

## 11. Independent Deterministic Validation

Every cycle produces a structured `ValidationReport` containing individual checks, evidence references, and an overall pass/fail result. At minimum it will:

1. capture `git status`, changed paths, and a reviewable binary-safe diff;
2. ensure the repository remains based on the recorded baseline and contains no forbidden path changes;
3. run all required build/test commands from the request;
4. run applicable startup validation;
5. run a fresh OSV scan and require scanner success;
6. prove every requested baseline finding is absent according to a normalized identity based on vulnerability ID/aliases plus Maven coordinate;
7. compare the full prohibited severity scope against baseline and reject new identities;
8. validate typed constraints against captured baseline state, including protected Java/Spring Boot versions;
9. detect prohibited additions/changes to known OSV suppression or ignore mechanisms and report uncertain cases for manual review;
10. record final file hashes and a validated tree/diff digest.

Success is established only by this validator. A build passing by itself, a changed file, a model statement, or an OSV scan alone is insufficient.

## 12. Delivery

Delivery is impossible unless the latest `ValidationReport` passes and the current working tree still matches its validated digest.

The current host has Git and system Git Credential Manager configuration, but no `gh` executable, GitHub token environment variable, MCP runtime, or GitHub MCP server. The selected initial delivery mechanism is therefore Git subprocesses for branch/commit/push plus a small deterministic GitHub REST client using the already-installed `requests` dependency for Draft PR creation. A delivery preflight must verify a supported GitHub remote, API base URL, non-interactive credential source, repository permission, network access, and separation between the uncredentialed agent runner identity and credentialed delivery boundary without exposing credential values.

The deterministic delivery service then:

1. creates a uniquely named remediation branch from the recorded baseline commit while retaining the validated working tree;
2. stages only the validated changed paths;
3. commits with deterministic metadata/message policy;
4. pushes the branch;
5. creates a Draft PR through the GitHub REST API with `draft=true`;
6. records branch, commit, PR URL, commands, and failures.

No patch-plan replay is required because the validated repository itself is delivered. PR prose may use the agent's recorded rationale, but delivery eligibility and Git/GitHub mechanics remain deterministic. The remediation agent may use local Git history and remote metadata already obtained during deterministic preparation; a credentialed GitHub tool is not justified for the current remediation objective. If future requests require issue/PR context, deterministic prefetch or a read-only trusted integration can be reviewed without changing the delivery authority boundary. If validation passes but push/PR creation fails, the run is not `SUCCESS`; it becomes manual review with delivery-failure evidence.

## 13. Traceability and Outcomes

The POC will retain a small set of JSON/JSONL and log artifacts:

- request and resolved policy;
- repository/baseline metadata;
- baseline build/test/startup logs;
- raw and normalized baseline scan;
- append-only tool action records and full command outputs;
- per-cycle agent summary and deterministic validation report;
- per-cycle Git diff;
- final build/scan/constraint evidence;
- final outcome and delivery information.

Outcome mapping:

- `SUCCESS`: validation passed and a Draft PR was created.
- `PARTIAL / MANUAL REVIEW REQUIRED`: useful changes exist but validation or delivery remains incomplete.
- `NO SAFE REMEDIATION`: the agent reports no viable approach without a supplied constraint violation, validation remains unsatisfied, and evidence is retained; this never implies technical success.
- `EXECUTION LIMIT REACHED`: a configured cycle/tool/command/time limit ended the run.
- `BASELINE FAILURE`: clone, build, startup requirement, or scanner baseline prevented safe work.

## 14. Proposed Independent Package Structure

```text
autonomous_oss_remediation_agent/
  __init__.py
  agent.py                 # one LlmAgent factory / ADK export
  cli.py                   # independent runnable entry point
  config.py                # request, policy, and budget models
  models.py                # scan, validation, trace, outcome models
  orchestrator.py          # deterministic five-stage lifecycle
  prompt.py                # autonomy/guardrail prompt, no recipes
  workspace.py             # isolated run layout
  capabilities/
    __init__.py
    toolset.py             # three FunctionTool bindings
    workspace_io.py        # bounded text read and repository patching
    execution.py           # host-native shell and shared process results
    policy.py              # path, environment, network-mode, and budget policy
  deterministic/
    __init__.py
    repository.py          # clone and Git metadata
    maven.py               # baseline/validation command execution
    osv.py                 # scanner execution and normalization
    constraints.py         # baseline capture and typed checks
    validation.py          # independent validation report
    delivery.py            # validation-gated Git delivery orchestration
    trace.py               # concise append-only evidence
  integrations/
    __init__.py
    github.py              # deterministic GitHub REST Draft PR client
tests/
  autonomous_oss_remediation_agent/
    unit/
    integration/
    e2e/
    fixtures/
```

The package will have its own imports, configuration, models, tools, entry point, and tests. Runtime imports from `oss_remediation_agent` are explicitly forbidden and will be checked by a focused import/dependency test.

## 15. Conceptual Adaptation from the Reference

The following behavior will be independently reimplemented, not imported:

- isolated clone/workspace and baseline commit recording;
- structured command result and log capture;
- Maven baseline/build/startup evidence patterns;
- OSV temporary scan-copy technique, JSON parsing, severity filtering, and Maven normalization;
- Maven wrapper/effective dependency evidence ideas where useful to deterministic baseline capture;
- validation artifact and Git diff evidence patterns;
- delivery preconditions, remediation branch naming, deterministic commit/push, and Draft PR creation;
- fixture-driven and mocked-boundary testing patterns.

The exact patch-plan schemas/interpreter, POM-only change policy, planning recipes, separate outcome-analysis agent, accepted-patch replay model, and staged many-agent ADK workflow will not be copied into the new architecture.

## 16. Focused Testing Strategy

### Unit tests

- path containment, traversal, absolute path, symlink/junction escape, `.git` protection, patch behavior, and size/output limits;
- shell-based discovery/search plus bounded text-read behavior;
- shell policy, sanitized environment, credential isolation, stdout/stderr/exit code, timeout, process cleanup, full-log references, and budget accounting;
- OSV parsing across representative report shapes, alias-aware identity, severity scope, target resolution, and new-finding detection;
- Java/Spring Boot/suppression constraint checks;
- validation outcome mapping and validated-digest delivery gate;
- package import scan proving no runtime dependency on `oss_remediation_agent`.

### Integration tests

- deterministic clone/baseline against temporary local Git repositories;
- one fake/model-backed ADK agent session receiving validation failure and continuing in the same session/workspace;
- build failure, remaining finding, constraint violation, and then-success feedback cases;
- maximum cycles, command timeout, tool-call limit, and overall deadline;
- Git commands and GitHub REST calls mocked to prove no branch/push/PR before validation success and no credential exposure to the agent.

### End-to-end smoke tests

- a committed vulnerable Maven/Spring fixture with real Maven and OSV Scanner when binaries/network/cache make it practical;
- a two-cycle scenario in which the first change fails deterministic validation and the same agent session corrects it;
- Draft PR delivery exercised only in an explicitly configured test repository; otherwise verify through a fake GitHub boundary.

Existing tests are reference coverage only and will not be imported by the independent package.

## 17. Important Limitations and Open Decisions

1. ADK 2.4.0, Google Gen AI 2.11.0, and the selected direct `requests` usage are available but not repository-pinned. Implementation should add an explicit independent dependency declaration after approval.
2. The selected stable ADK `FunctionTool` bridge requires independent patch, execution, policy, and trace code. The native environment toolset and MCP remain possible future adapters, not architectural requirements.
3. The selected local shell is not an OS sandbox against malicious repository code, Maven plugins, or a hostile model action. Docker is installed but its daemon is unavailable, so trusted-runner/repository scope is required unless approval instead mandates hard isolation.
4. Reliable descendant-process termination is platform-specific, especially on Windows, and needs focused tests.
5. `osv-scanner` is not currently on `PATH`. Implementation requires a configured/pinned scanner provision step or executable preflight, and recognizable JSON plus raw evidence must be required rather than trusting exit code alone.
6. Spring Boot startup applicability/readiness is project-specific. The request must be able to specify the module/command/readiness rule; otherwise startup is only enforced when reliably detectable.
7. Git is installed and Git Credential Manager is configured, but `gh` and token environment variables are absent. Configuration does not prove a usable credential and, under the same OS identity, a stored credential could be reachable by agent-run code. The selected GitHub REST delivery client therefore needs an approved non-interactive credential source isolated from the agent runner plus a delivery preflight; this is a deployment prerequisite, not agent authority.
8. Unstructured user constraints cannot all be proven automatically. Unknown constraints prevent automated delivery rather than being treated as satisfied.
9. `InMemoryRunner` is sufficient for one process/run and preserves the same-session feedback loop; resumability across process restarts would require a persistent ADK session service and is deferred for the initial POC.
10. The only unresolved architecture approval decision is whether the explicit trusted-repository/local-runner boundary is acceptable for the initial POC. If hard isolation is required now, the execution backend and operational prerequisites must be redesigned around an available container, restricted OS identity, or approved remote sandbox before implementation.

## 18. Revision Summary and Approval Gate

This revision preserves the accepted one-agent lifecycle, deterministic baseline/validation/delivery boundaries, same-session feedback loop, independent package, budgets, and truthful outcomes. It replaces the prematurely fixed six-tool/`shell=False` design with a capability-first comparison and selects a smaller three-capability `FunctionTool` surface with a host-native shell. It separates invariant safety objectives from local-backend controls, explicitly records the trusted-runner limitation, compares native ADK, MCP, container, hosted-sandbox, and trusted GitHub choices, and replaces the unavailable `gh` assumption with deterministic Git plus GitHub REST delivery.

Implementation must not start until this revised proposal is reviewed and explicitly approved. Approval must resolve whether the trusted-repository/local-runner boundary is acceptable for the initial POC or whether hard container/OS isolation is required first. OSV Scanner provisioning and the non-interactive GitHub credential source must also be configured before an implementation can pass its environment and delivery preflights.
