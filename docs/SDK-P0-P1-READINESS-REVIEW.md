# OpenHands SDK P0 and P1 readiness review

Review date: 2026-10-20. Repository: AILearner365/oss-remediation-adk.
Branch: autonomous-oss-remediation.
Reviewed implementation: `ce62775dd956b19965cc5b8c50334f1dd72b1d03`.
Historical reference: openhands-poc-evaluation at
`e5d160cb6080e5c6ed8fef16ca4ba42ab6106c8f`.

The standalone SDK architecture does not need replacing. Controlled execution
requires a narrow execution-permission correction and targeted functional fixes,
not another orchestration layer. This review does not authorize implementation,
model inference, credential changes or live remediation.

## A Executive assessment

| Area | Status | Assessment |
| --- | --- | --- |
| P0 Independent authority | BLOCKED | The trust problem is real and reproducible. The unconditional guard correctly refuses execution but does not implement the missing boundary. |
| P1-A Task configuration | PARTIAL | Defaults are configurable and generally conservative. Acceptance has a reproduced multi-version Boot defect and a baseline/final-check scope gap. |
| P1-B SBRI | PARTIAL | Basic CLI mapping matches the historical implementation. The backend is unavailable here; profiles, failure handling and cache validity need corrections. |
| P1-C Skills and execution | PARTIAL | Default Skills are preserved and actually delivered. Native tools work without inference, but execution authority and time-budget enforcement remain incomplete. |

## B Verified findings

### P0 The guard addresses a genuine contract requirement

References: [files.require_independent_authority](../native_remediation/files.py),
[mandatory contract guarantees](../PRODUCT-CONTRACT.md#mandatory-pre-inference-guarantees).

Git history shows that `a8ba73c6` attempted separation using restricted Docker
commands. Commit `02502848` removed that Docker boundary and introduced the
unconditional guard. Commit `ce62775d` retained it and applied it to self-validation
and SBRI too.

The implementation decision was to preserve the required trust boundary by
refusing execution when isolation disappeared. It was not primarily a substitute
for model-run authorization: CLI authorization already existed and remains
separate.

| Execution path | Effect of the guard |
| --- | --- |
| runtime.prepare_task | Default preparation stops before repository preparation/build. |
| runtime.dispatch | Model execution cannot start. |
| runtime.hook | Default independent acceptance cannot run. |
| validation.evaluate | Real Maven/OSV validation cannot run. |
| delivery.deliver | Delivery and reconciliation cannot proceed. |
| capabilities.self_validate | Real self-validation cannot run. |
| capabilities.sbri | Applicable SBRI command execution cannot run once an executable is found. |

Classification: intentional fail-closed limitation, not an accidental testing embargo.

### P0 Host authority exposure is demonstrated

References: [native.open_conversation](../native_remediation/native.py),
[files.environment](../native_remediation/files.py).

A harmless native terminal probe in temporary directories demonstrated that
execution remained UID 1000 and could read and write a sibling 0600 canary inside
a 0700 directory. Configuring username="nobody" did not change execution identity
in the installed subprocess backend. Installed SubprocessTerminal.initialize
launches Popen without switching UID/GID; the username parameter alone is not a
solution.

The Cloud Shell account also has passwordless sudo and Docker-group access.
Workspace placement and file modes therefore do not protect task/baseline/
acceptance/delivery records, validator code, SDK dependencies, existing ADC/GitHub
credentials or the trusted SDK process from same-user process access.

The SDK terminal sanitizer removes specific OpenHands secrets, not every possible
provider/GitHub credential variable. Environment filtering alone also leaves
filesystem and network credential sources.

Classification: proven trust-boundary failure. Actual credentials were not accessed.

### P0 Restricting terminal commands alone leaves initialization exposure

References: [native.verify_ready](../native_remediation/native.py),
[runtime.dispatch](../native_remediation/runtime.py). Installed SDK 1.55.1:
openhands/sdk/conversation/impl/local_conversation.py,
LocalConversation._ensure_plugins_loaded and send_message.

The installed SDK discovers ambient project plugins with include_project=True,
separately from AgentContext.load_project_skills=False. Project plugins can
contribute hooks and MCP configuration during lazy initialization. The product
calls verify_ready after send_message, which initiates loading. Detecting
unexpected hooks afterward is not a preventive privilege boundary.

Classification: source-verified design limitation; no malicious-plugin exploit was executed.

### P1-A Unchanged multi-version Boot dependencies can fail acceptance

Reference: [validation.compare](../native_remediation/validation.py).

Boot comparison forms every old/new version pair for a coordinate. Unlike the
generic dependency comparison, it does not first skip identical version sets.
A pure-function fixture with identical baseline/candidate Boot versions
{4.0.6, 4.1.1} returned FAIL with "Spring Boot downgrade movement not authorized".
Baseline and candidate digests were identical.

Legitimate multi-module projects with different resolved Boot versions can be
rejected despite making no Boot change. Classification: reproduced defect.

### P1-A Baseline health and final acceptance checks are conflated

References: [runtime.prepare_task](../native_remediation/runtime.py),
[validation.evaluate](../native_remediation/validation.py).

The same evaluator runs tools.checks and every task constraint during baseline
collection and final validation. Preparation requires COMPLETE. An acceptance
check intended to become true through remediation can therefore prevent the
agent from starting because it fails on the original baseline.

Classification: implemented behavior creating a configuration/design gap.
Invariant checks legitimately belong in both phases; final-goal checks need
distinct applicability.

### P1-B SBRI mapping mostly matches but the backend is unavailable

Reference: [capabilities.sbri](../native_remediation/capabilities.py). Historical
CLI authority: spring_boot_release_intelligence/sbri_cli.py at the pinned POC commit.

The evaluate command and --project, --output, --releases, --range, --scopes and
--max-candidates arguments match. SUCCESS/PARTIAL/FAILURE,
releases[].assessment_status and execution.release_selection match the response
schema. The canonical result reference allows inspection of dependency ownership,
findings and detailed evidence omitted from the summary. Security ranking is
correctly separated from compatibility and strategy selection.

However, no sbri executable is discoverable here, and the current package does
not include/install the historical backend. Approved tools.profiles are not
forwarded through the supported --profiles argument, so profile-dependent
projects could receive intelligence for the wrong graph.

Classification: deployment gap plus source-verified functional omission. Fixture
success is not actual backend integration proof.

### P1-B Optional SBRI failures can block preparation

References: [capabilities.sbri response parsing](../native_remediation/capabilities.py),
[runtime.prepare_task pre-edit invocation](../native_remediation/runtime.py).

Missing executables and ordinary reported failures are handled honestly. But
malformed result JSON and some execution/I/O failures propagate out of optional
pre-edit intelligence, preventing the preparation receipt from being written.

Cache reuse accepts retained INCONCLUSIVE results too. Its fingerprint does not
establish freshness of remote release/advisory data or changes behind a CLI
launcher.

Classification: error-handling gap and bounded cache design limitation. Neither
creates independent PASS, but both can obstruct useful investigation.

### P1-C Time settings are not hard agent execution limits

References: [native tool configuration](../native_remediation/native.py),
[runtime.dispatch](../native_remediation/runtime.py). Installed SDK authority:
TerminalAction and terminal/timeout_policy.py.

command_seconds bounds deterministic validation commands, not native agent
terminal actions. task_seconds is checked at gates and validation, not
continuously during conversation.run. The installed action schema accepted
timeout=999999 and runtime-idle timeout configuration was unset. No long-running
command was executed.

Classification: verified enforcement gap. Iterations are bounded, but the
configured task duration is not a hard wall-clock limit.

## C P0 resolution

### Historical POC guarantees

The historical runner used a host terminal, harness-owned validator scripts,
fixed baseline/policy arguments and a separate Stop invocation. Its records and
launchers remained accessible to the same OS user.

Retained evidence under docs/experiments/openhands/evidence on the reference commit:

| Run directory | Verified result |
| --- | --- |
| gate2-task-24-orchestrated-run-20261016T041326Z | execute.log: finished, one Stop, deterministic PASS. |
| gate2-task-26-orchestrated-run-20261016T043639Z | execute.log: finished, two Stops, one denial, deterministic PASS. |
| gate2-task-25-orchestrated-run-20261016T043317Z | startup.log: Python ADC-refresh startup failure. |

Those results establish logical validation independence and useful reassessment
behavior, not filesystem/process isolation or credential protection. The current
contract explicitly requires the stronger properties. Returning to POC
permissions would weaken that contract.

### Practical alternatives

| Approach | Assessment |
| --- | --- |
| Same user with instructions/private directories | Unenforceable; reproduced failure. |
| Native username parameter alone | Ineffective in the installed subprocess backend. |
| Separate unprivileged UID alone | Useful but incomplete: credential endpoints, inherited environment and privileged SDK initialization remain relevant. |
| Restricted local execution identity plus OS protections | Recommended smallest approach; preserves standalone SDK and host tools. |
| Docker/container deployment | Possible alternative, not inherently necessary; still needs credential-safe networking and protected mounts. |
| Remote service/framework | Unnecessary for this controlled proof. |

### Recommended local boundary

Keep the SDK process, native hooks, acceptance decisions and delivery in the
trusted account. Run all repository-controlled commands, including agent shell,
baseline/candidate Maven, task checks and SBRI builds, as a dedicated unprivileged
identity.

Required properties:

- No sudo/Docker groups, privilege escalation or inherited credentials.
- Protected control state, implementation code, Git metadata and SDK dependencies.
- Read-only evidence views for the agent.
- Restricted metadata/local credential endpoint access, retaining authorized
  Maven/OSV/research networking.
- Task-descendant cleanup and safe generated-file handling before privileged parsing.

UID separation alone does not prevent metadata credential access. Google
documents that metadata access is not inherently limited by process/user identity:
[Google IAM guidance](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts).

Initialize the SDK from a trusted control directory, not the agent-controlled
repository, to avoid ambient repository-plugin execution in the trusted process.
The native terminal can enter the repository through a small protected OS-boundary
launcher using the documented shell_path extension, not a new agent loop/service:
[native terminal configuration](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-tools/openhands/tools/terminal/README.md).

Affected components include native conversation/workspace/terminal configuration,
deterministic command execution, self-validation and SBRI subprocesses, evidence
publication and guard checks. Acceptance decisions and delivery remain trusted.

Cloud Shell has relevant local primitives and administrative capability;
temporary namespace probes succeeded. The complete boundary is not configured
or verified. Retain the guard until its required checks pass.

## D Necessary P1 corrections

1. Fix unchanged multi-version Boot comparison, retaining conservative handling
   of ambiguous module movements.
2. Distinguish invariant/baseline checks from final acceptance checks.
3. Forward Maven profiles to SBRI and verify the actual backend executable/version.
4. Retain malformed/failed optional SBRI execution as INCONCLUSIVE without
   swallowing authority or identity failures.
5. Provide bounded, explicit cache refresh/invalidation semantics.
6. Enforce or accurately narrow promised agent execution deadlines.

No blanket relaxation of task defaults is justified. POM-only edits, Java
preservation and major-version restrictions are configurable policies, not fixed
remediation recipes. Acceptance checks original/remaining/new findings and exact
scanner coverage. Severity-only targeting is not implemented; compatibility
beyond build/tests requires explicit deterministic checks.

All three intended Skills are present. General guidance matches the POC;
decision/Maven changes appropriately rename capabilities. Actual native message
delivery activated both default Skills. No mandatory questionnaire or fixed Boot
strategy was found. FileEditorTool could improve POC tool parity, but shell
editing works and adding it is not a prerequisite.

## E Recommended implementation sequence

1. Implement the local authority boundary first. Offline checks must demonstrate
   that restricted commands cannot alter canary state/code, read credential
   canaries, elevate privileges or reach credential endpoints. Verify trusted
   plugin initialization and descendant containment.
2. Correct acceptance semantics. Unchanged multi-version Boot must pass;
   forbidden real movements must fail. Final-goal checks may fail on baseline
   but remain mandatory for acceptance.
3. Complete SBRI integration. No-network backend/CLI fixtures must verify
   profiles, ranges, scopes, raw references, malformed results, stale cache
   handling and optionality.
4. Verify bounds and full native wiring without a model: initialization,
   preparation gate, persistence/resume, actual Skill attachment, tools, Stop
   denial/PASS and report-only versus authorized delivery doubles.
5. Only then request controlled live authorization.

## F Verification and remaining live proof

Seventeen focused offline tests passed using installed SDK/Tools 1.55.1:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENHANDS_SUPPRESS_BANNER=1 \
  /tmp/openhands-sdk-1.55.1/venv/bin/python -B -m unittest \
  tests_native.test_product.ContractTests \
  tests_native.test_product.RepositoryTests \
  tests_native.test_product.ScannerTests \
  tests_native.test_product.MavenPipelineTests \
  tests_native.test_parity.ConfigurationParityTests \
  tests_native.test_local_execution tests_native.test_sdk_parity -q
```

Additional temporary no-model probes established terminal sibling-file access,
ineffective username switching, actual native message Skill attachment and
acceptance of a large terminal timeout. A pure-function fixture reproduced the
Boot comparison defect. require_independent_authority remained unchanged and
continued to raise Blocked. No credentials were refreshed/read, privileges or
firewall rules changed, target modified, model run or PR created.

Offline checks can prove wiring, identity protection, fail-closed behavior and
deterministic contracts. They cannot prove Gemini strategy quality, effective
reassessment, real network/toolchain behavior or full remediation. A separately
authorized run must demonstrate baseline, Gemini investigation/edit/self-check
and independent Stop validation. Draft delivery requires explicit authorization.

The review proposes corrections only. Saving this document does not implement
them or change existing evidence capture, delivery authorization or product guards.
