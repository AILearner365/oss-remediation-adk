# Native-first remediation integration: first implementation slice

**Date:** 2026-10-18  
**Status:** non-executing handoff code committed; offline test pending Cloud Shell.

## Goal

Native Canvas/Agent Server/SDK provides UI, conversation lifecycle, execution, native Stop Hook and feedback. Existing deterministic Git preparation, baseline, optional Spring Boot release intelligence and Maven/OSV validation remain domain-specific. There is **no new custom task HTTP API, LLM loop, event mirror or database** in this new slice.

`scripts/openhands_native_remediation.py` is a **read-only handoff builder** from existing durable task records to the official OpenHands Agent Server conversation create payload. It deliberately does not yet call native POST/create or `/run`, because the current records were provisioned using the legacy 1.50.0 adapter and a validated migration from them to the 1.55.1-native runtime is outstanding.

It requires:

- existing task `AGENT_RUNNING`, not accepted;
- exact prepared Git worktree and baseline;
- a persisted task-to-conversation ID and recorded dispatch claim;
- a compatible credential-free, approved Stop Hook configuration referring to the same durable SQLite database;
- the official native request's `worktree=false` so it uses **exactly that worktree**, not another checkout;
- native Stop Hook command pointing to `openhands_shared.stop_hook`, using explicit module import root so task working directory does not affect execution.

`validate_native_response()` checks conversation ID, `idle`, prepared workspace and persisted Stop Hook before execution. The safe CLI prints an allowlisted summary rather than LLM credentials.

## Offline verification

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
```

No paid LLM, network calls, scanner or modification to frozen Gate-2.

## Next narrow implementation slice

1. Add a native conversation **idle-create** action, using the existing Agent Server 1.55.1 API, with strict response verification and no automatic `/run`. Test with the local mock credentials from POC 3.
2. Replace legacy 1.50.0 runtime provisioning/dispatch *for new tasks* with a small verified native binding; avoid duplicating event history or custom API. Keep the independent PASS-only acceptance store until parity is demonstrated.
3. Integrate an agent-produced local fixture change and actual validation outcome using native Stop Hook.
4. Real Maven/OSV vulnerability remediation with explicit user approval for billable model execution, then GitHub PR delivery of exact validated state.

POC4 evidence supports native Stop Hook failure handling and non-acceptance without PASS, **not** real scanner/PR readiness. Agent completion or native Hook ALLOW cannot authorize delivery.

## Native idle-create extension (2026-10-18)

`create_idle_native_conversation()` invokes only the native Agent Server
`POST /api/conversations?include_skills=true` and
`GET /api/conversations/{id}?include_skills=true`. It requires exact
conversation identity, `idle` execution status, matching existing prepared
workspace and persisted independent Stop Hook. It never sends a user message or
calls `/run`.

Two offline HTTP-mock tests cover endpoint ordering, success and rejection of
a missing persisted hook. Smoke runner
`scripts/openhands_native_idle_create_poc.py` creates a fresh disposable
existing-service fixture and a native **idle** conversation on 1.55.1, using a
local-only mock LLM URL and dummy key. The mock model server need not run:
there are **zero model requests**.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_idle_create_poc.py
```

Smoke report: `~/openhands-native-poc-reports/native-idle-create-v1.json`.
No previous fixtures are overwritten. Do **not** execute that conversation:
its data records remain synthetic and the real scanner configuration is not
installed.

This checks native conversation creation but does **not** yet remove the legacy
provisioning records used solely by the fixture setup. The next work is to
replace that prerequisite cleanly for new tasks before removing the older
runtime adapter.

## Idle create v1 failure and v2 correction

Offline handoff tests: 7 passed. Live idle-create v1 failed at native
`POST /api/conversations` with HTTP 422 and error
`loc=["body","tags"], type=value_error`. Native OpenHands conversation
tags require lowercase alphanumeric keys; the bridge sent `taskId`.
The v2 correction uses `taskid`, adds an offline key-format regression
assertion, and uses fresh disposable `native-idle-create-v2` state.
Retain v1 failure evidence; do not overwrite it. No model execution occurred.

Run the same commands with the updated branch:
```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_idle_create_poc.py
```
Expected report: `~/openhands-native-poc-reports/native-idle-create-v2.json`.

## Native idle-create v2 initialization discovery and v3 correction

A user read-only GET demonstrated that POC3 had a Stop Hook, while
new native-idle-create-v2 immediately after POST had `hook_config=null`.
Attaching one initial user message using native `POST /events` with
`run=false` made `hook_config` appear while conversation remained `idle`.
The create-only helper now follows the observed native initialization
sequence: **POST conversation → POST initial user event with run=false →
GET persisted conversation → verify exact hook, workspace, ID and idle state**.
There is still no `/run` and no LLM request.

V2 state is retained; v3 uses a fresh isolated task fixture.
The offline tests assert exact call ordering, `run=false`, and rejection
when the native server fails to persist the Stop Hook.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_idle_create_poc.py
```

Expected report: `~/openhands-native-poc-reports/native-idle-create-v3.json`.

## Native-first provisioning without legacy runtime dispatch (v4)

The v3 live smoke passed native idle creation, Stop Hook persistence and
identity checks. The new v4 fixture uses the existing deterministic task
preparation/baseline/intelligence and SQLite runtime identity contract, but
**does not** call the 1.50.0 legacy adapter's `provision()` or
`start_execution()`. It records a `CONVERSATION_READY / NOT_STARTED`
native identity, creates and initializes the OpenHands 1.55.1 conversation
using native API endpoints with `run=false`, verifies Stop Hook and workspace,
and links the unique native initial `MessageEvent` as
`CONTEXT_ATTACHED`. No execution claim is created.

A new offline test asserts that a not-started native identity can construct
the handoff without a dispatch claim and that inconsistent context states
are rejected. A successful smoke demonstrates removal of the **fixture**
legacy provisioning dependency; it does not yet prove production end-to-end
real Maven/OSV remediation or native execution safety. v1-v3 are preserved.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_idle_create_poc.py
```

Expected v4 report: `~/openhands-native-poc-reports/native-idle-create-v4.json`.
No model requests are sent.

## Native one-shot dispatch guard (offline tests first)

`dispatch_native_once()` now uses native Agent Server endpoints for one
`/run` dispatch, with no custom conversation API. Preconditions are durable
`CONTEXT_ATTACHED` identity and an independent Stop Hook verified via native
GET while `idle`. It records `claim_execution` **before** native POST
`/run` and then marks `DISPATCHED` only after a successful response or
observable native `running/finished` state.

A second call with the same dispatched claim returns `ALREADY_DISPATCHED`
without sending `/run`. Lost POST responses are reconciled by native GET.
When the POST outcome cannot be proven, the durable claim transitions to
`RECOVERY_REQUIRED`, and later calls cannot resend `/run` automatically.
The same fail-closed rule applies to an existing unconfirmed intent.
The native `finished` state alone never implies security acceptance.

Two new offline tests simulate normal dispatch and an ambiguous connection
loss, enforcing only one POST and no duplicate dispatch.

**Scope restriction:** do not invoke this against v4's existing idle conversation.
Its Stop Hook uses the real validation CLI with a synthetic task fixture;
executing it would not constitute a valid real Maven/OSV experiment. A
separate fixture with explicitly synthetic Stop Hook and local-only MockLLM
will be needed for the next live /run test. No paid model call is authorized.

## Native-first execution + synthetic Stop Hook live test (v1)

`scripts/openhands_native_execution_poc.py` runs a fresh disposable
`native-execution-v1` task and native 1.55.1 conversation. It uses the
previously proven direct-native fixture (`CONVERSATION_READY`, no legacy
adapter), calls native `POST /run` using `dispatch_native_once()` with an
existing SQLite execution intent, and requests a duplicate dispatch to prove
it does **not** call `/run` a second time.

A loopback-only HTTP mock advertises the SDK FinishTool. A **synthetic**
native Stop Hook invokes `SharedValidationService` with `ArtifactRunner`,
which checks a disposable marker, **never** Maven/OSV. On first independent
FAIL, native Stop Hook must DENY. The *test coordinator*, not the agent,
creates the repair marker only after verifying the native DENY event and first
durable REMEDIATION_FAILURE. The subsequent mock Finish must receive the
failed-validation feedback and produce a durable PASS before security
acceptance. Results distinguish synthetic coordinator repair from real
agent-generated edits.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_execution_poc.py run
```

The smoke runs the **native agent with a local mock model** and invokes an
explicitly synthetic validator; no paid LLM, Maven, OSV or GitHub delivery.
The report is in
`~/openhands-native-poc-reports/native-execution-v1.json`. Do not
re-run an already attempted v1 fixture, and preserve it on any failure.
A passing test is not evidence of agent-written Maven vulnerability repairs.

## Native execution v1 result and exact-marker correction

Cloud Shell v1: 10 offline tests PASS; live verdict **NOT_PROVEN**.
Native finished, exactly one /run, repeat dispatch ALREADY_DISPATCHED,
four native Stop Hook events and four model requests, with independent
outcomes REMEDIATION_FAILURE x4. The coordinator repaired the fixture after
verified DENY and the mock model saw feedback, but the validator never
observed the expected exact marker. Consequently there was no false
independent acceptance.

Root cause: the existing synthetic ArtifactRunner requires the literal
two bytes `\\` + `n` at the end of its marker, while the new execution
coordinator wrote an actual newline. Both now use one shared
`REPAIR_BYTES` constant. Offline regression asserts that matching bytes
yield PASS while a newline yields FAIL. Previous v1 state/report are
preserved; next live scenario is `native-execution-v2`.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_execution_poc.py run
```

A v2 PASS demonstrates native synthetic feedback and validator-authorized
acceptance; it does not demonstrate autonomous agent-made remediation.

## First real Maven/OSV remediation gate: preparation (not execution)

The Cloud Shell user reported `native-execution-v2` PASS and 11/11
offline tests. A limited, explicitly user-reported summary is committed at
`docs/experiments/openhands/evidence/native-execution-v2-user-verified-20261018.json`.
The raw report remains on Cloud Shell and has not been independently uploaded.
The synthetic test used a coordinator-applied repair; it is not evidence of
autonomous vulnerability remediation.

The first *real* test must start with an independently reproducible,
**disposable** Maven repository, a clean exact Git commit, a known vulnerable
dependency/finding, a trusted approved OSV scanner binary, and a validator
configuration that matches the task acceptance criteria. Do not use a
production repository as the first scenario. The existing
`ExistingDeterministicBaselineRunner` and
`ExistingDeterministicValidationRunner` must run the real Maven build and
OSV scanner; neither the synthetic ArtifactRunner nor a mock repair marker
is sufficient for this acceptance gate.

A read-only preflight script now checks basic prerequisites without editing
or scanning the repository:
```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_real_remediation_preflight.py' -v
python3 scripts/openhands_real_remediation_preflight.py \
  --repository /absolute/path/to/disposable-maven-repo \
  --scanner /absolute/path/to/approved/osv-scanner
```

`READY_FOR_BASELINE_SETUP` means only: clean Git root and pom.xml present,
Maven responds to `-version`, and the explicitly supplied scanner binary
responds to `--version`. It is **not** a vulnerability baseline, scanner
approval, complete validation setup, or authorization to run an agent.
No scanner scan, Maven goal, dependency download or model call occurs.
A missing scanner or repository blocks progress rather than being guessed.

After preflight: capture the exact commit and scanner identity; run Maven build
and a real OSV baseline using the existing deterministic services; record
target advisory identities and a verified fixed-version candidate; confirm
that a deterministic fixed version builds and reduces target findings.
Then assemble an agent task/instruction from that authoritative baseline
and invoke native OpenHands with durable dispatch + independent real Stop Hook.
Obtain **explicit authorization before any paid model execution**. Finish with
full independent validation, exact workspace state binding and only then
possible safe delivery. The agent's native `finished` event is never PASS.

Current status: real Maven/OSV preflight code committed; no real baseline,
model execution, scanner output or GitHub PR has been claimed.

## Vertex Gemini 2.5 Flash autonomous run — preparation/authorization boundary

User selected **Vertex AI Gemini 2.5 Flash** for the first real autonomous
SnakeYAML remediation, and explicitly required inspection of the
execution/cost boundary **before any billable model call**.

Verified Cloud Shell source evidence (reported by user):
- disposable baseline repo `/tmp/openhands-real-remediation-snakeyaml-v1`,
  original short Git commit `f44f94c`
- Java 21, Maven 3.9.16, OSV scanner available
- baseline `mvn clean verify` exit 0; OSV reported exactly one finding:
  `org.yaml:snakeyaml:1.33`, `GHSA-mjmj-j48q-9wg2`
- separate fixed comparison `/tmp/openhands-real-remediation-snakeyaml-fixed-v1`:
  Maven exit 0, OSV exit 0, zero OSV findings.
- Baseline Maven created untracked `target/`; no tracked POM edit was reported.
  The plan verifier checks tracked POM identity; the eventual native worktree
  must be created from the immutable baseline commit rather than copying
  generated files.

The nonexecuting preparation utility:
```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_autonomous_run_plan.py' -v
python3 scripts/openhands_autonomous_run_plan.py --scanner "$(command -v osv-scanner)"
```

It checks immutable Git/POM identity and both existing OSV reports, hashes
the observed scanner binary, and emits a credential-free manifest to STDOUT.
It does not modify the repository or perform any network request, Maven
command, scanner scan, native conversation creation, or Vertex call. The
fixed candidate's POM/version is **not** passed to the agent objective.

### Explicit authorization boundary

Current state: `PREPARED_NOT_AUTHORIZED`. **Neither selecting the model,
running the plan script, nor creating an idle conversation authorizes
billable model execution.** Before a native `/run`:
1. Configure Vertex ADC/service account and project/region outside the
   agent-visible prompt; prove the exact model ID is routable without
   exposing credentials in the native conversation or evidence.
2. Verify real `ExistingDeterministicBaselineRunner` and the **real**
   `ExistingDeterministicValidationRunner` with Maven and OSV against a
   disposable Git worktree; bind target findings and acceptable constraints.
   No synthetic `ArtifactRunner` or preselected version as an answer.
3. Ensure a native 1.55.1 conversation contains the actual task objective,
   exact worktree and real Stop Hook. Verify native persisted Hook first,
   and preserve unique durable dispatch intent, stop-hook feedback and
   PASS evidence. The current `create_idle_native_conversation` has
   generic guidance only and is **not** a complete real-task launcher.
4. Freeze a concrete invocation budget (`max_iterations`), stop-hook denial
   bound, a realistic dollar/token ceiling and abort/monitoring mechanisms
   verified against the selected Vertex billing setup. The $ ceiling is
   **not yet calculated or enforced**; `max_iterations` alone is not a
   dollar cap. Native model requests, retries, context growth, and scanner
   network traffic can all affect use/cost.
5. Obtain a **separate explicit user go/no-go authorization** naming the
   model, bounded budget and approved scenario, *then* enable `/run`.
   Do not interpret this selection as that authorization.

Model interaction is strictly blocked in this preparation stage.
Outputs from existing local scans are verified scenario evidence only;
the autonomous agent must discover/evaluate the fix itself. Delivery remains
out of scope until a real independent PASS and exact Git state binding.

## Native 1.55.1 reuse of existing Vertex/ADC configuration (no model calls)

A repository review confirmed the original Gate-2 setup already defines
`openhands_resolve_vertex_env`, `openhands_verify_vertex_adc` and
`vertex-adc-preflight.py`. The earlier request to rediscover project/region
by manually inspecting unset environment variables was unnecessary: the
Cloud Shell POC resolver applies its own fallback. That fallback is acceptable
for the existing disposable POC **only**; never treat it as evidence of an
approved production billing project. Do not add project-specific credentials
or tokens to Git, prompts, native events or reports.

Committed preparation changes:

- `scripts/openhands_native_vertex_check.py` invokes **only**
  `openhands_resolve_vertex_env` from the existing script and prints
  project/location and evidence flags. It does not call
  `openhands_sync_gcloud_project`, `verify_vertex` (three billable model
  completions), ADC refresh, the Agent Server, or a model.
- `scripts/openhands_native_remediation.py` now has
  `render_task_objective(store, task_id)`, using the persisted immutable
  task objective and acceptance criteria. The
  `create_idle_native_conversation(..., initial_message=...)` path delivers
  this exact text in an initial native message with `run:false`. For
  `vertex_ai/` models the call **fails closed** when that explicit task text
  is missing. Synthetic mock-LLM fixture callers retain their generic text
  for native lifecycle tests.
- These edits do not modify the frozen `scripts/openhands/*` POC or the
  native 1.55.1 launcher. No billable model execution is authorized.

Offline verification:

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_vertex_check.py' -v
python3 scripts/openhands_native_vertex_check.py
```

### Known remaining integration gates (do not claim readiness)

1. In the **actual 1.55.1 Agent Server runtime**, verify
   `openhands-sdk[vertex]` provider dependencies and compatibility with the
   existing preflight; the current `openhands_native_poc.py` warms
   `openhands-sdk==1.55.1` without the explicit `[vertex]` extra.
   Do not assume a 1.50.0 Canvas patch also applies to 1.55.1.
2. Perform existing ADC preflight in that same runtime. The earlier
   missing-email Cloud Shell refresh regression means that a historical
   successful Gemini run cannot prove current ADC refresh. This preflight
   performs auth-network requests, not model inference, and must not
   expose credentials.
3. Create a real task in the durable store, with actual
   `ExistingDeterministicBaselineRunner` results and a deployment-owned
   Stop Hook configuration using the verified OSV scanner 2.6.0 and binary
   SHA-256. Ensure `ExistingDeterministicValidationRunner` is the configured
   Stop Hook (not a synthetic marker runner). Bind a fresh disposable worktree
   to the original `f44f94c...` baseline.
4. Bind the real task message to the idle native 1.55.1 conversation, verify
   actual persisted Hook and idle state, and preserve no /run execution claim.
5. Freeze and test iteration, runtime, cancellation and **real cost** limits,
   present the explicit budget, and get a separate user authorization before
   any model inference or native `/run`.

Current truth: environment reuse and native task-context wiring are coded,
but real-task setup, Vertex extra availability, ADC freshness, real Stop Hook
execution and cost limits remain **NOT PROVEN**.

## Real shared Maven/OSV runner integration probe

The standalone Maven/OSV baseline/fixed comparison was completed, but
that **does not** prove the repository's real shared deterministic runner
can build and classify OSV 2.6.0. To close that gap without a model call,
`scripts/openhands_real_shared_baseline_probe.py` uses the **actual**
`ExistingDeterministicBaselineRunner` with the existing
`MavenConfig`, `ScannerConfig`, `BaselineProfile`, and `TaskRequest`
types. It hashes and pins the configured scanner, checks the immutable
baseline POM against exact Git commit, clones the source into a fresh
disposable `/tmp` checkout and builds/scans **only the copy**. It uses
the full four-level OSV severity scope, expecting the original SnakeYAML
advisory. It does not call OpenHands or Vertex.

Run offline tests first, then authorize this **deterministic-only** Maven
build/OSV scan (network/downloads may occur; no model inference):

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_real_shared_baseline_probe.py' -v
python3 scripts/openhands_real_shared_baseline_probe.py \
  --scanner "$(command -v osv-scanner)"
```

`PASS` is only evidence that this shared baseline runner correctly
classifies the real single-dependency vulnerability on the current Cloud
Shell. It is **not** durable task registration/baseline, not the actual
`ExistingDeterministicValidationRunner` Stop Hook, and not a native agent
run. Do not silently promote this probe result to task acceptance. Next
integrate durable task registration/preparation/intelligence-disabled
baseline with the native Stop Hook, and verify the 1.55.1 server's Vertex
extra before asking for explicit, cost-bounded `/run` authorization.

## Durable controlled Maven task and real Stop Hook preparation

User supplied the historical larger Gate-2 comparison repository
`https://github.com/AILearner365/maven-multimodule-app`, branch
`main-runrunning`; GitHub inspection on 2026-10-18 showed commit
`9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`. This is a
**reference** for subsequent broader evaluation, not the first isolated
one-vulnerability run. Do not silently swap it into the SnakeYAML acceptance
case or modify the reference repository.

The first real run stays the independently proven, disposable single-module
SnakeYAML scenario. `scripts/openhands_real_task_prepare.py` is the
pre-execution vertical-slice assembly, not another synthetic validation
runner. It mirrors the known local fixture into a **new local-only bare
repository** and isolated trusted checkout, then invokes the existing
`DeterministicPreparer`, `DeterministicBaselineAssessor` with its **real**
Maven/OSV runner, and `SharedIntelligenceAssessor` in disabled mode.
It persists the task, exact-commit preparation, baseline reports and
intelligence outcome. It generates a credential-free, restricted-permission
Stop Hook config for the existing `openhands_shared.stop_hook` /
`ExistingDeterministicValidationRunner` path, and verifies configuration
parsing/profile selection. **It does not execute that validator, create
a native conversation, start /run, or execute the model.** The task ends
in `AGENT_RUNNING` with execution `NOT_STARTED`, which is not acceptance.

Run from Cloud Shell (deterministic Maven and OSV may access Maven/OSV
services; model calls are prohibited):

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_real_task_prepare.py' -v
python3 scripts/openhands_real_task_prepare.py \
  --scanner "$(command -v osv-scanner)" \
  --run-root "/tmp/openhands-real-durable-task-20261018-v1"
```

The run-root is intentionally one-shot: if it exists, preparation fails
closed and does **not** overwrite existing task evidence. Retain the exact
output (task ID, database, workspace, validation config). A clean
`DURABLE_TASK_PREPARED_NOT_AUTHORIZED` is the expected preparation result.
Do not report `READY_FOR_EXECUTION_AUTHORIZATION` before verifying
native persisted hooks, actual Server 1.55.1 Vertex dependencies, and
run budget/cost controls.

After this checkpoint: create/reconcile the native 1.55.1 idle conversation,
bind the real task objective, verify the persisted hook, exercise the
actual validator against the real baseline without a model call where
safe, then request explicit cost authorization before any `/run`.
