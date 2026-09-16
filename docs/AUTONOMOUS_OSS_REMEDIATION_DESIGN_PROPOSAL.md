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
- ADK contains an `McpToolset`, but the optional `mcp` package and a reviewed server are not currently configured. Node/npm/npx are available, so a pinned project-scoped MCP provider could be started without global installation; that remains an option only if its capability, boundary, or integration value justifies the protocol and provider lifecycle.
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
- enforce text-tool path containment and process timeout, output, environment, and budget controls while recording the shell's trusted-runner scope;
- run fresh validation after every agent work cycle;
- determine validation pass/fail and final outcome;
- gate and perform approved Git branch/commit/push/Draft PR operations, or select the validated/manual-delivery outcome when automated delivery is ineligible;
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
| ADK MCP client plus local filesystem/command or GitHub servers | ADK adapter source and Node/npm/npx are available; `mcp` and a reviewed/pinned server are not currently configured | A project-scoped provider could be launched without global installation and may add portability, centralized credentials, or provider-enforced scoping. For the current local read/patch/shell needs it adds protocol, version pinning, provider trust, and process lifecycle without removing the shell trust boundary or adding unique capability | Deferred on material-value grounds, not merely installation state |
| Local Docker/WSL sandbox | Docker CLI is installed, but the daemon is unavailable and no usable WSL development distribution is present | Would strengthen isolation, but requires daemon availability, images matching repository JDK/tool needs, mount/cache/network design, and materially more operations | Alternative if hard isolation is required, not the initial backend |
| Hosted sandbox providers such as E2B/Daytona/Vertex sandbox | Relevant optional packages and credentials/configuration are absent; the inspected Vertex sandbox integration is browser/computer-use oriented | Adds vendor credentials, remote repository transfer, cost, and environment parity work without an established project requirement | Not selected |
| ADK `bash_tool` or Gemini built-in code execution | `bash_tool` fails to import on Windows; built-in execution is not attached to the host repository | Cannot provide the required local repository/build workflow | Rejected |

### Selected capability surface

The initial POC will use stable ADK `FunctionTool` integration for three coding-oriented capability categories bound to the prepared repository:

1. a bounded repository text-read capability with line/range metadata;
2. a repository-relative patch capability that can create, update, or delete text files and returns changed paths/hashes;
3. a host-native workspace shell capability with a repository-relative working directory, configurable timeout, structured process result, and full-log artifact reference.

Discovery, search, dependency analysis, local Git inspection, and diff review use the shell with installed/project-provided commands such as `rg`, `git`, Maven/Maven Wrapper, Java, and workspace-local scripts. This deliberately avoids separate Maven, Java, Python, Git-inspection, list, and search abstractions that would constrain how the agent investigates. The read and patch capabilities remain separate because they give the model reliable, auditable text interaction without shell quoting, while the shell retains pipes, command chaining, wrapper behavior, plugins, and ad hoc helpers that the original `shell=False` argument-vector proposal would lose.

The same internal execution service will run deterministic build/test/scanner commands outside the model-facing tool surface. The LLM does not receive validator, delivery, manifest, credential, or PR-publication tools.

The investigation imported and inspected the installed `FunctionTool` interface and callbacks, confirmed same-session runner support, and executed the installed Git, Maven, Java, and `rg` binaries. It also confirmed the native 30-second timeout and optional-provider dependency gaps described above. This is design and environment evidence only: no runtime capability implementation was created, the proposed bindings were not exercised end to end, and `osv-scanner` is not currently on `PATH`. Runtime demonstration remains part of the implementation checklist and test strategy.

### Capability coverage in design

| Required behavior | Designed support |
| --- | --- |
| Inspect/read/search | text-read tool plus `rg`, `git ls-files`, and host-native shell discovery |
| Create/edit/delete | repository patch tool; shell-created workspace-local helpers remain possible |
| Build/test/dependency analysis | shell invokes Maven Wrapper or Maven, plugins, Java, and repository scripts with request-sized timeouts |
| Scan and security evidence | deterministic scanner uses the shared execution service; normalized reports and failures are supplied to the same agent session |
| Diagnose and iterate | every command returns structured status/output/log references; failed deterministic validation becomes the next same-session user message |
| Git engineering context | local `git status`, diff, log, show, restore, and related inspection are available; delivery authority is separate |

This selection introduces independent code for patch application, process control, policy, and tracing, but avoids an MCP server and optional provider dependency that provide no material benefit for the current POC. The capability categories, not an immutable tool count or schema, are the architectural choice; implementation may consolidate or split callable bindings if testing shows a clearer model interface without changing authority or boundaries. This preserves more engineering freedom than the previous six-tool/argument-vector design while keeping a reviewable model-facing surface.

## 8. Permissions, Security, Network, and Operational Boundaries

### Initial POC boundary decision

The initial POC explicitly accepts a **trusted-repository/trusted-runner operational boundary** for host-native shell, build, plugin, and script execution. Hard container, restricted-filesystem identity, or remote-sandbox isolation is not a prerequisite for this POC. Consequently, it may run only on a dedicated, least-privilege runner identity with no delivery credentials or unrelated sensitive data and only against repositories whose build code is trusted. The currently inspected developer workstation establishes tool availability but is not automatically an approved runtime merely because the tools exist there.

If those operational assumptions cannot be met, the run fails preflight before the autonomous agent receives shell capability. It must then be deployed behind a separately reviewed hard-isolation backend; it must not silently fall back to unrestricted execution on a general-purpose workstation.

### Hard guarantees

- Deterministic code selects the prepared repository, creates the run layout, exposes only the approved capability bindings, sets budgets/timeouts, records results, and retains the validation/delivery gates.
- Deterministic validation alone establishes remediation success; the LLM cannot override checks or authorize delivery.
- Automated push/PR delivery is disabled unless a delivery adapter and credential boundary inaccessible to the remediation execution identity pass preflight and are rechecked after validation.
- Per-command timeout, overall elapsed time, cycle/tool-call budgets, returned-output bounds, full-log capture, and process cleanup are enforced outside the prompt.
- Text read/patch calls are canonically confined below the repository root and reject absolute paths, traversal, NULs, direct `.git` edits, and symlink/junction escape. This guarantee applies to those file capabilities only.
- Every model tool call and deterministic command is traceable with redacted arguments, result metadata, log reference, and affected paths where applicable.

### Operational assumptions, not containment guarantees

- A repository-relative shell working directory is convenience and context, not filesystem containment.
- Arbitrary shell commands, Maven plugins, repository scripts, Python, and Java can read or modify any resource available to the OS identity. Repository path checks on the separate text tools do not change that fact.
- Environment stripping, isolated Git configuration, disabled push URLs, and command filtering reduce accidental exposure but do not make the shell a hostile-code sandbox or prevent all equivalent actions.
- Prohibitions on administrative elevation, service/daemon changes, system security changes, global JDK replacement, global package installation, unrelated paths, and autonomous delivery are enforced by policy, deterministic checks where practical, and the trusted-runner operating model—not claimed as complete syscall/filesystem isolation.

The effective filesystem and process boundary for the initial POC is therefore the runner identity and machine assigned to the run. The dedicated runner must contain no secrets or unrelated assets that would be unacceptable for agent-run code to access. Untrusted repositories or a requirement for destination-level filesystem/process containment require a container, restricted OS identity, or approved remote sandbox instead.

For arbitrary shell execution, deterministic control of “where” means deterministic selection and preflight of that dedicated runner identity/machine and prepared working repository; it does not mean that application-level cwd or path parsing confines every filesystem access made by child code.

### Selected local controls

- The host-native shell starts in a repository-relative directory, uses a sanitized non-interactive environment, redirects temporary/cache locations into the run, and returns bounded output while preserving complete logs.
- Timeout handling terminates the process and makes a platform-specific best effort to terminate descendants; Windows process-tree behavior is covered by focused tests rather than assumed.
- Git commands in the remediation environment use isolated system/global Git configuration, disable interactive prompting, and disable the prepared clone's normal push path. Local history/diff/revert operations remain available.
- Obvious administrative, delivery, interactive, and machine-wide commands are rejected as defense in depth. Command-string filtering is not treated as a security boundary.

The shell accepts host-native command syntax rather than a `shell=False` executable/argument list. That choice permits pipes, conditional/chained commands, wrapper scripts, redirection, and temporary helpers needed for realistic coding-agent work. An exhaustive executable allowlist, path-token parser, blanket network ban, or forced empty Maven repository was rejected because each is both bypassable by allowed build code and likely to break legitimate repository-specific engineering.

### Network behavior

Maven, scanner provisioning, and some remediation investigations require outbound access. The run policy declares network mode explicitly. The initial local backend may use the trusted runner's approved outbound network for dependency/plugin/scanner access, but no delivery credential is present in or reachable from the remediation identity. Destination-level egress enforcement, when required, must be provided by the runner/container/network platform rather than inferred from shell command filtering.

## 9. Baseline and Assessment

Before repository baseline work, deterministic scanner preflight resolves OSV Scanner in one of two approved modes:

1. use a configured executable whose resolved path, version, and required integrity metadata satisfy policy; or
2. provision a configured, pinned scanner version into a runner-managed tools location from an approved source and verify its checksum/signature before use.

The resolved absolute scanner path and identity are recorded and reverified before the baseline scan and every validation scan; scanner execution never relies on an agent-modified `PATH`. Provisioning and replacement are deterministic lifecycle operations outside the model-facing tools. The remediation LLM is never asked to install, upgrade, replace, or select the scanner. A project-local scanner installation is available to the agent only if a future approved runtime policy explicitly permits it; that is not the initial design.

The deterministic preparer will:

1. create `<run>/repository`, `<run>/artifacts`, `<run>/cache`, and `<run>/temp`;
2. clone the requested reference, resolve and record `HEAD`, remote, branch/ref, and clean status;
3. run configured baseline build/test commands, preferring a checked-in Maven Wrapper;
4. perform Spring Boot startup validation only when requested or when a runnable target can be determined reliably; aggregator/non-runnable projects are recorded as not applicable rather than failed by an unconditional `spring-boot:run`;
5. run the proven OSV source-scan pattern against a temporary scan copy that excludes `.git` and build outputs;
6. require a recognizable JSON report and normalize Maven findings, aliases, coordinates, versions, fixed versions, severity, and raw evidence;
7. select findings matching the requested IDs/severities;
8. capture protected Java/Spring Boot values, suppression configuration, relevant file hashes, and the initial Git tree.

An unavailable/unverifiable scanner, failed deterministic provisioning, unusable baseline build, scanner failure, empty/unrecognized scanner evidence, or missing requested ref produces `BASELINE_FAILURE` and prevents autonomous work. A later scanner integrity or execution failure makes validation fail and can never be converted into success by an LLM assertion.

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

The architecture defines a deterministic `DeliveryAdapter` boundary rather than prescribing GitHub REST, `gh`, MCP, or another provider mechanism. An approved adapter must support non-interactive preflight, branch/commit/push, Draft PR creation, structured/redacted evidence, credential isolation, and an idempotent or safely diagnosable failure model.

Material adapter choices are:

| Adapter | Benefits | Costs/credential implications |
| --- | --- | --- |
| Git subprocess plus GitHub REST | Cross-platform, direct structured API response and Draft PR control, no `gh` binary requirement; `requests` is already available in the inspected environment | Requires an explicitly scoped token or broker, API/version/error handling, and secure Git push authentication separate from agent execution |
| Git plus `gh` | Mature GitHub workflow, concise Draft PR operation, and established authentication support | `gh` is not currently installed; its credential store is unacceptable if reachable by the remediation identity, so the same isolation/preflight requirement remains |
| Approved trusted-provider or MCP integration | May centralize credentials, audit, and provider-side authorization outside the runner | Requires provider approval, dependency/process lifecycle, availability, and proof that the agent cannot invoke delivery authority directly |

Git subprocess plus GitHub REST is a reasonable initial adapter candidate when an approved broker can supply short-lived, repository-scoped credentials only to the deterministic delivery boundary: it has the required GitHub capabilities, produces structured responses, and avoids an additional CLI installation. The absence of `gh` alone is not the selection reason, and REST is not an architectural requirement. If `gh` or a trusted provider offers a stronger available credential boundary in the deployment environment, that adapter should be selected instead without changing the lifecycle.

Credential handling is fail closed:

1. before autonomous work, delivery preflight records whether automated delivery is eligible without obtaining or exposing a delivery secret to the remediation identity;
2. if no adapter/credential source exists, or the same OS identity used for remediation could access the credential manager, token, or secret store, automated delivery is disabled and no push/PR credential is resolved;
3. remediation may continue in validation-only/manual-delivery mode so useful validated work is not discarded;
4. after validation, the adapter and isolation conditions are rechecked before any credential resolution or remote mutation;
5. loss or ambiguity of credential isolation aborts automated delivery without fallback to environment variables, inherited Git configuration, or an agent-accessible credential helper.

When automated delivery remains eligible, the deterministic delivery service then:

1. creates a uniquely named remediation branch from the recorded baseline commit while retaining the validated working tree;
2. stages only the validated changed paths;
3. commits with deterministic metadata/message policy;
4. pushes the branch;
5. creates a Draft PR through the configured approved adapter;
6. records branch, commit, PR URL, commands, and failures.

No patch-plan replay is required because the validated repository itself is delivered. PR prose may use the agent's recorded rationale, but delivery eligibility and Git/GitHub mechanics remain deterministic. The remediation agent may use local Git history and remote metadata already obtained during deterministic preparation; a credentialed delivery tool is not justified for the current remediation objective. If future requests require issue/PR context, deterministic prefetch or a separately authorized read-only trusted integration can be reviewed without changing the delivery authority boundary.

If validation passes while automated delivery is disabled, or if the approved adapter fails after validation, the run is not `SUCCESS`. It ends as `PARTIAL / MANUAL REVIEW REQUIRED` with reason `VALIDATED_MANUAL_DELIVERY_REQUIRED`, preserves the validated digest/diff and validation evidence, and performs no further credential fallback. This outcome distinguishes validated remediation from technically incomplete remediation.

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
- `PARTIAL / MANUAL REVIEW REQUIRED`: validation or delivery remains incomplete. Reason `VALIDATED_MANUAL_DELIVERY_REQUIRED` explicitly means deterministic validation passed but automated delivery was disabled or failed, so a human may deliver the preserved validated change.
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
    toolset.py             # ADK bindings for approved capability categories
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
    delivery.py            # approved deterministic delivery adapter boundary
    github.py              # optional GitHub adapter implementations
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
- OSV executable preflight/provisioning policy, version/integrity recheck, parsing across representative report shapes, alias-aware identity, severity scope, target resolution, and new-finding detection;
- Java/Spring Boot/suppression constraint checks;
- validation outcome mapping and validated-digest delivery gate;
- package import scan proving no runtime dependency on `oss_remediation_agent`.

### Integration tests

- deterministic clone/baseline against temporary local Git repositories;
- one fake/model-backed ADK agent session receiving validation failure and continuing in the same session/workspace;
- build failure, remaining finding, constraint violation, and then-success feedback cases;
- maximum cycles, command timeout, tool-call limit, and overall deadline;
- delivery adapters mocked to prove no branch/push/PR before validation success, fail-closed manual-delivery behavior when credentials are not isolated, and no credential exposure to the agent;
- configured-scanner, pinned-provisioning, missing-scanner, integrity-failure, and validation-rescan cases without agent-controlled installation.

### End-to-end smoke tests

- a committed vulnerable Maven/Spring fixture with real Maven and OSV Scanner when binaries/network/cache make it practical;
- a two-cycle scenario in which the first change fails deterministic validation and the same agent session corrects it;
- Draft PR delivery exercised only in an explicitly configured test repository; otherwise verify through a fake GitHub boundary.

Existing tests are reference coverage only and will not be imported by the independent package.

## 17. Important Limitations and Prerequisites

1. ADK 2.4.0 and Google Gen AI 2.11.0 are available but not repository-pinned. Implementation should declare and pin its direct dependencies after approval, including any dependency required by the selected delivery adapter.
2. Stable ADK `FunctionTool` binding is the proposed initial integration for the three developer-capability categories and requires independent patch, execution, policy, and trace code. The capability contract is architectural; the exact callable count and binding mechanism may evolve if implementation evidence favors an ADK-native, MCP, or trusted-provider adapter without weakening boundaries.
3. The boundary decision is resolved for the initial POC: host-native shell is permitted only for trusted repositories on a dedicated, least-privilege, delivery-credential-free trusted runner. It is not an OS sandbox. If that deployment cannot be provided, implementation is blocked until a hard-isolation backend is approved.
4. Reliable descendant-process termination is platform-specific, especially on Windows, and needs focused tests.
5. `osv-scanner` is not currently on `PATH`. Deployment must choose configured-executable or deterministic pinned-provisioning mode; scanner identity/integrity is rechecked for every scan, and the LLM has no scanner installation/replacement authority.
6. Spring Boot startup applicability/readiness is project-specific. The request must be able to specify the module/command/readiness rule; otherwise startup is only enforced when reliably detectable.
7. Git is installed and Git Credential Manager is configured, but `gh` and token environment variables are absent. Configuration neither proves a usable credential nor establishes isolation. Deployment must select an approved delivery adapter and inaccessible credential boundary; otherwise automated delivery remains disabled and validated runs require manual delivery.
8. Unstructured user constraints cannot all be proven automatically. Unknown constraints prevent automated delivery rather than being treated as satisfied.
9. `InMemoryRunner` is sufficient for one process/run and preserves the same-session feedback loop; resumability across process restarts would require a persistent ADK session service and is deferred for the initial POC.
10. Capability coverage is supported by source/environment investigation and design mapping, not runtime demonstration. The bindings, scanner lifecycle, iterative diagnosis, and end-to-end workflow remain implementation verification work.

## 18. Final Review Changes and Approval Gate

This final review preserves the accepted architecture and makes only the remaining boundary/evidence corrections:

- explicitly selects the trusted-repository/dedicated-trusted-runner operating model for the initial host-native shell and states that cwd/path/command controls are not hard shell containment;
- corrects the design checklist and proposal language from runtime “demonstrated” capability to design coverage supported by investigation;
- makes automated delivery fail closed and adds a validated/manual-delivery reason when credentials are not isolated;
- makes deterministic delivery adapter-neutral while retaining Git-plus-REST as a justified candidate when its credential model fits;
- defers MCP because it adds no material capability or boundary value for this POC, not because it lacks a global installation;
- assigns OSV Scanner resolution, pinned provisioning, and integrity checks to deterministic code rather than the remediation LLM.

The security-boundary design choice is no longer open: the initial POC accepts the documented trusted-runner boundary. The remaining approval decision is whether to authorize implementation of this revised design.

Deployment prerequisites are:

1. an approved dedicated, least-privilege, delivery-credential-free remediation runner identity, or a separately approved hard-isolation replacement;
2. configured OSV Scanner executable or pinned deterministic provisioning policy with integrity metadata;
3. an approved deterministic delivery adapter and credential boundary inaccessible to the remediation identity, or explicit validation-only/manual-delivery mode;
4. pinned independent runtime dependencies and the configured model/provider credentials needed by ADK without exposing delivery credentials to agent-run commands.

Implementation must not start until this proposal receives explicit approval. No implementation file is authorized by this design pass.
