# Autonomous OSS Remediation Agent - Design Proposal

**Status:** Proposed for review. No implementation is authorized by this document.

## 1. Review Basis

This proposal is based only on:

- `docs/AUTONOMOUS_OSS_REMEDIATION_REQUIREMENTS.md` as the authoritative requirements;
- the current `oss_remediation_agent` source as reference material;
- the current tests and committed Maven fixtures;
- direct inspection of the locally installed Google ADK and Google Gen AI packages.

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
- ADK's separate `ExecuteBashTool` cannot be imported on this Windows host because Python's `resource` module is unavailable. It is also confirmation-driven and Unix-oriented.

Therefore the proposal uses stable ADK callable/function-tool integration with a small independent tool layer rather than exposing the stock local environment toolset directly.

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

## 7. Exact Agent Toolset

The `LlmAgent` receives exactly these six tools, each pre-bound to the prepared repository root so the model never supplies a host workspace root:

1. `list_workspace(path=".", glob=None, max_results=500)`
   - Lists relative files/directories without following links outside the repository.
2. `read_file(path, start_line=1, end_line=None)`
   - Reads a bounded UTF-8 text range and reports truncation/total lines.
3. `search_workspace(query, path=".", glob=None, max_results=200)`
   - Searches names/content and returns bounded relative-path, line-number matches.
4. `write_file(path, content)`
   - Creates or replaces a repository file after path and size checks.
5. `edit_file(path, old_text, new_text, expected_occurrences=1)`
   - Performs a checked exact replacement; this is the safe patch-equivalent for focused edits.
6. `run_command(argv, cwd=".", timeout_seconds=None)`
   - Executes one non-shell command and returns command, relative cwd, stdout, stderr, exit code, duration, timeout state, and full-output artifact references.

The model does not receive deterministic scanner, validator, Git delivery, manifest, credential, or PR tools.

## 8. Tool Boundaries and Permissions

File tools will:

- canonicalize every path and require it to remain below the repository root;
- reject absolute paths, traversal, NULs, and symlink/junction targets outside the root;
- reject direct `.git` mutation;
- cap individual read/write sizes and result counts;
- append an action record with path, result, and before/after hashes.

The command tool will:

- use an argument vector with `shell=False` rather than accepting shell syntax;
- require the executable and cwd to pass policy checks;
- force cwd below the repository root;
- reject absolute/outside path arguments where they can be identified;
- enforce per-command and remaining-overall time limits;
- terminate the process on timeout and make best-effort termination of descendants;
- cap returned output while preserving complete output in deterministic run artifacts;
- strip credentials and sensitive host environment variables;
- redirect temporary/home/cache locations into the run workspace;
- force Maven's local repository into a workspace-local cache;
- block `sudo`, service/system configuration tools, interactive shells, global package installation, `git push`, `gh`, credential/config mutation, and other delivery operations;
- allow local developer binaries such as Maven/Maven Wrapper, Java, local-only Git inspection/revert operations, Python, `rg`/`grep`/`find`, and `jq`; network tools such as `curl` require an explicit request policy.

Repository code, Maven plugins, and Python scripts can execute arbitrary code once permitted by a general developer command tool. The above controls create a strong application-level boundary but are not a hostile-code OS sandbox. Initial POC use must therefore be limited to trusted repositories/runners. A container or restricted OS identity is the future hard-isolation option; it is not silently claimed by this design.

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

The deterministic delivery service then:

1. creates a uniquely named remediation branch from the recorded baseline commit while retaining the validated working tree;
2. stages only the validated changed paths;
3. commits with deterministic metadata/message policy;
4. pushes the branch;
5. creates a Draft PR with `gh pr create --draft`;
6. records branch, commit, PR URL, commands, and failures.

No patch-plan replay is required because the validated repository itself is delivered. PR prose may use the agent's recorded rationale, but delivery eligibility and Git mechanics remain deterministic. If validation passes but push/PR creation fails, the run is not `SUCCESS`; it becomes manual review with delivery-failure evidence.

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
  workspace.py             # isolated run layout and path guards
  tools/
    __init__.py
    developer_tools.py     # the exact six LLM tools
    command_runner.py      # bounded non-shell execution
  deterministic/
    __init__.py
    repository.py          # clone and Git metadata
    maven.py               # baseline/validation command execution
    osv.py                 # scanner execution and normalization
    constraints.py         # baseline capture and typed checks
    validation.py          # independent validation report
    delivery.py            # branch/commit/push/Draft PR
    trace.py               # concise append-only evidence
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

- path containment, traversal, absolute path, symlink/junction escape, `.git` protection, size/output limits;
- exact edit/write/search/list/read behavior;
- command allow/deny policy, sanitized environment, stdout/stderr/exit code, timeout, and budget accounting;
- OSV parsing across representative report shapes, alias-aware identity, severity scope, target resolution, and new-finding detection;
- Java/Spring Boot/suppression constraint checks;
- validation outcome mapping and validated-digest delivery gate;
- package import scan proving no runtime dependency on `oss_remediation_agent`.

### Integration tests

- deterministic clone/baseline against temporary local Git repositories;
- one fake/model-backed ADK agent session receiving validation failure and continuing in the same session/workspace;
- build failure, remaining finding, constraint violation, and then-success feedback cases;
- maximum cycles, command timeout, tool-call limit, and overall deadline;
- delivery commands mocked to prove no branch/push/PR before validation success.

### End-to-end smoke tests

- a committed vulnerable Maven/Spring fixture with real Maven and OSV Scanner when binaries/network/cache make it practical;
- a two-cycle scenario in which the first change fails deterministic validation and the same agent session corrects it;
- Draft PR delivery exercised only in an explicitly configured test repository; otherwise verify through a fake GitHub boundary.

Existing tests are reference coverage only and will not be imported by the independent package.

## 17. Important Limitations and Open Decisions

1. ADK 2.4.0 and Google Gen AI 2.11.0 are installed but not repository-pinned. Implementation should add an explicit independent dependency declaration after approval.
2. The native ADK environment toolset is experimental and unsafe as the direct workspace boundary; the proposal intentionally uses ADK callable tools with independent guards.
3. The local general command tool is not an OS sandbox against malicious repository code or Maven plugins. Trusted-runner/repository scope is required unless a later design adds container/OS isolation.
4. Reliable descendant-process termination is platform-specific, especially on Windows, and needs focused tests.
5. OSV Scanner JSON and exit-code behavior can vary by installed version; recognizable output plus raw evidence must be required rather than trusting exit code alone.
6. Spring Boot startup applicability/readiness is project-specific. The request must be able to specify the module/command/readiness rule; otherwise startup is only enforced when reliably detectable.
7. GitHub delivery depends on installed `git`/`gh`, repository permissions, and credentials that remain outside the LLM tool environment.
8. Unstructured user constraints cannot all be proven automatically. Unknown constraints prevent automated delivery rather than being treated as satisfied.
9. `InMemoryRunner` is sufficient for one process/run and preserves the same-session feedback loop; resumability across process restarts would require a persistent ADK session service and is deferred for the initial POC.

## 18. Approval Gate

Implementation must not start until this proposal is reviewed and explicitly approved. Approval should resolve whether the trusted-repository application-level command boundary is acceptable for the initial POC or whether hard container/OS isolation is required first.
