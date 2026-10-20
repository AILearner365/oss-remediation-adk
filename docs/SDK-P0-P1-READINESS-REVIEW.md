# OpenHands SDK P0 and P1 readiness review

## Current verification assessment — 2026-10-20

This update supersedes the P1 findings in the original review retained below.
Implementation entering verification: `0669c1b4cd6e32124f89f1cd3340289a35c20a6e`.
**Not live-ready: P0 remains BLOCKED/deferred and unchanged.** No Gemini, target
remediation, target-repository edits, pushes to a target or PR creation occurred.
Only the product branch is delivered. No SDK upgrade or authority workaround.

### Evidence-based status

| Area | Assessment | What is actually established |
| --- | --- | --- |
| P0 independent authority | NOT PROVEN / BLOCKED | The unconditional `files.require_independent_authority()` and its execution paths remain unchanged. No same-user isolation guarantee is implemented or waived. |
| P1-A strict baseline | PROVEN offline | `StrictBaselineTests` rejects failed/incomplete/stale/tampered evidence before SDK dispatch; graph/inventory/coverage/tests and configured checks remain mandatory. Checks are baseline AND candidate invariants by the approved contract, not final-only goals. No baseline relaxation was required. |
| P1-A Boot comparison | PROVEN offline | `BootPolicyTests` covers unchanged sets, module patch/minor/major moves, real/mixed/swapped downgrades, ambiguous ownership and independent root-controller/module-override movement. Root upgrade cannot hide a module downgrade; a major controller change cannot hide behind pinned modules. These are retained-graph fixtures, not live multi-module Maven remediation proof. |
| P1-B retained SBRI CLI/backend | PROVEN for controlled fixture | Actual historical CLI, Maven, Maven Central metadata and OSV executed successfully: 3.3.0 baseline and selected 3.3.1, both COMPLETE, profile enabled, 11 resolved/input packages per release. Not a model-selected strategy or independent acceptance. |
| P1-B product adapter | PARTIAL | Approved profiles, cache identity/reuse/retry, response handling and tool dispatch pass fixtures. Real CLI parsing was previously verified with a fixture Evaluator. Direct backend evidence now verifies the retained engine, but guarded product pre-edit/tool-to-backend execution remains NOT PROVEN. No `sbri` is installed on PATH; backend was extracted temporarily from Git, not silently installed. |
| P1-C Skills/native tools | PROVEN offline; behavior PARTIAL | Real SDK constructs/resumes a conversation without inference, loads/renders native Skills and dispatches registered tools. Native hooks/terminal execute harmless probes. Model use, reasoning quality and autonomous reassessment remain NOT PROVEN. |
| Timeout/recovery | PROVEN scoped offline | Native waits return control; interruption and a subsequent command work. PreToolUse rejects missing/excessive waits. Deterministic runner kills its timed-out process group/child. Expired tasks block initial dispatch and recovery; missing receipts and exhausted run budget block recovery. No hard task wall-clock kill or background-process containment is claimed. |
| Stop acceptance/delivery | PROVEN offline contracts; live NOT PROVEN | Separate self-check/Stop authority, deny/PASS, report-only, explicit draft authorization, exact-tree guards and uncertain delivery reconciliation pass test doubles. No actual Maven Stop acceptance or GitHub mutation was exercised. |

### Actual SBRI execution and retained evidence

Authoritative backend snapshot: `openhands-poc-evaluation` at
`e5d160cb6080e5c6ed8fef16ca4ba42ab6106c8f`. Only `sbri` and
`spring_boot_release_intelligence/` were extracted with `git archive` into
`/tmp/p1-verification.hjRNA4`; no historical source was modified. The authored
fixture is [tests_native/fixtures/sbri-profile/pom.xml](../tests_native/fixtures/sbri-profile/pom.xml).
No application code, tests, credentials or target checkout was used.

Exact argv, source/fixture hashes, versions and exit codes are in
[provenance.json](evidence/p1-verification-20261020/provenance.json). The run used:

```text
<pinned-python> <extracted>/sbri evaluate --project <fixture-copy> --output <output>
  --releases 3.3.1 --max-candidates 1 --profiles intelligence-fixture
  --scopes compile,runtime --maven /opt/maven/bin/mvn
  --scanner /home/kavya_parivarababu/bin/osv-scanner --timeout 120
```

Exit 0, schema 1.0, SUCCESS, no errors, approximately 41.35 seconds. Maven 3.9.16,
Java 21.0.12.1 and OSV 2.6.0 were real installed tools, not stand-ins. Explicit
selection was checked against authoritative Maven metadata (its URL/hash are in
the result). A separate rejected `--releases 0.0.0` invocation exited 2 with the
actual useful error retained in `invalid-release.stderr`. It made no evaluation.
Range selection remains fixture/source-verified, not exercised by this backend run.

Durable [evidence directory](evidence/p1-verification-20261020/) retains:

- Original `backend/result.json`, both Maven TGF trees, generated SBOMs, raw OSV
  responses and Maven/scanner logs; `SHA256SUMS` protects copy consistency.
- Original backend schema and schema validation using jsonschema 4.26.0.
- `profile-disabled.tgf`: an actual additional Maven tree collection with
  `-P!intelligence-fixture` removes Commons Text. With the approved profile,
  Commons Text 1.12.0 and its transitive dependency are present in BOTH releases.
- `tests-pinned.log`, `tests-stdlib.log`, `terminal-focused.log`, and the initial
  unsuccessful terminal-probe logs (trailing padding whitespace normalized);
  these are test evidence, not agent trajectories. Reused fixture conversation
  IDs in those logs are not new executions of the historical conversations.

`RetainedBackendEvidenceTests` verifies TGF external compile/runtime packages =
SBOM components = per-release result dependency records (11 each). Scanner logs
confirm 11 packages extracted per SBOM. Boot and Spring resolved versions move
between releases; retained ownership/defaults/findings references can be inspected.
The original fixture POM SHA is identical before/after. Both releases retain ten
unique findings (four HIGH, three MEDIUM, three LOW); **no complete remediation is
claimed**. The old backend's ranking is supporting security evidence only.

Coverage qualification: this is one module with an active profile, not evidence
of complete arbitrary-reactor/test/plugin/private-repository coverage. OSV output
omits nonvulnerable packages; its result length alone cannot prove full coverage.
This backend uses deprecated `--sbom` (still accepted by 2.6.0), not the independent
validator's stronger coverage contract. Raw advisory data is a time-specific
network snapshot, not a permanent guarantee. Maven/HTTP caches, generated HTML and
disposable working copies are omitted from Git; full temporary originals remain
at the diagnostic path but are not durable. Committed paths above are durable.

### Minimal corrections made during verification

`capabilities.sbri` previously returned only an exception class or generic missing
report, losing the actual ordinary failure reason. It now retains private
`execution-error.json`, exposes existing `command.json`/error evidence references,
and includes bounded stderr (stdout fallback) and exception details using the
installed SDK redactor. Without the optional SDK, feedback points to private
evidence rather than exposing raw diagnostics. Raw private command output remains
available; redaction is best-effort, not a new credential/isolation guarantee.
Malformed/unavailable/failed optional results remain INCONCLUSIVE/UNAVAILABLE;
integrity errors still block. No acceptance/cache/delivery authority was changed.
Real harmless failing-process tests verify actual stderr, private 0600 evidence,
redacted feedback and launch-error details, in addition to existing fixtures.

The first full discovery failed only the terminal timeout probe: its one-second
warm-up had not finished before the next command. An intermediate probe exposed
that SDK 1.55.1 leaves `TerminalObservation.timeout` at its default False; installed
`terminal_session.py` represents foreground timeout in `metadata.exit_code == -1`
and rendered suffix instead. The test now waits boundedly for warm-up, verifies
the timeout command really ran, uses the supported observation metadata/text,
interrupts it and verifies the next command. No SDK internals were patched.

### Tests and remaining proof boundaries

Pinned SDK/Tools **1.55.1** full discovery:

```sh
OPENHANDS_SUPPRESS_BANNER=1 /tmp/openhands-sdk-1.55.1/venv/bin/python -m unittest discover -s tests_native -v
python3 -S -m unittest discover -s tests_native -q
```

Final pinned result: **83 discovered, 78 passed, 5 skipped**, 36.303 seconds.
Stdlib-only fallback: **83 discovered, 67 passed, 16 skipped**, 34.869 seconds.
Counts and individual test names (verbose pinned run) are recorded in
`tests-pinned.log` and `tests-stdlib.log`. The pinned suite includes all existing native SDK tests and
new diagnostics, process cleanup, root/override comparison, deadline and retained
real-backend consistency/schema/hash tests. Five historical remote Agent Server
probes skip because that package is absent; they are not standalone regressions
and were not re-investigated. SDK fixture tests trap model completion; injected
evaluators/authority mocks are test-only, never real product/backend execution.
Compileall, shell syntax for `scripts/openhands/sdk-cloudshell-setup.sh`, task
configuration validation and `git diff --check` are additional checks. SDK
LocalWorkspace emits nonfatal unclosed-pipe ResourceWarnings; terminal probes can
emit PS1 metadata warnings. These vendor behaviors are retained, not suppressed
as evidence of security or reliability.

The task deadline is checked before dispatch/resume, new terminal work and
deterministic evaluation. It cannot terminate an ongoing model/tool/background
process exactly at expiry. Native timeout is a **soft foreground wait**, unlike
the deterministic helper's process-group kill. Native hook infrastructure can
fail open; trusted direct `execute_tool()` bypasses action hooks. None of these
is a security boundary or a resolution of P0.

Remaining blockers/gaps: independent host authority (deferred P0); installed and
versioned backend deployment; real product adapter invocation with its guard
intact; full multi-module/private-repository SBRI behavior; actual model strategy,
validation feedback/reassessment and end-to-end acceptance/delivery. Those cannot
be established by passing offline fixtures. **P1 verification is PARTIAL overall;
controlled live readiness is NOT PROVEN.** A separately authorized live run also
requires resolving P0 first; this verification authorizes neither.

## Original review snapshot (before P1 corrections)

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
